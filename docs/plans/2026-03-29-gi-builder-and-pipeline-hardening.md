# Session Prompt: AcuDev GI Builder Engine + CI/CD Pipeline Hardening

## Context

On 2026-03-29, a CustomizationPlugin that attempted to create a Generic Inquiry via SQL INSERT bricked the Acumatica production instance for 45 minutes. The root cause was blind SQL — inserting into GI tables (GIDesign, GITable, GIResult, GIWhere, GISort, GIFilter, etc.) without understanding their NOT NULL constraints, without transaction wrapping, and without pre-production testing. Each failed deploy left orphaned rows that crashed `PXGenericInqGrph+Definition` prefetch on app pool restart, blocking ALL customization publishing.

Read the full AAR: `docs/AAR-2026-03-29-gi-sql-insert-outage.md`

This session has two goals that are deeply connected: building a safe, programmatic GI creation engine for AcuDev, and hardening the CI/CD pipeline so nothing like this reaches production again.

---

## Goal 1: AcuDev GI Builder Engine

### Why this matters

The ability to programmatically create Generic Inquiries at runtime — without the Acumatica UI, without a customization publish, without an app pool restart — is **the foundational capability for AcuDev**. Every data extraction, reporting, and audit feature depends on it. If AcuDev can't safely create GIs, it can't do its job.

### What we know

**GI storage lives in SQL tables:**
- `GIDesign` — parent record (Name, ScreenID, DesignID GUID, behavior flags)
- `GITable` — query tables/DACs (has `Type` NOT NULL, does NOT have `RowID`)
- `GIResult` — display columns (has `RowID` NOT NULL)
- `GIWhere` — WHERE conditions (has `IsExpression` NOT NULL, no `RowID`)
- `GISort` — ORDER BY columns
- `GIFilter` — user-facing filter parameters (has `Name`, `IsExpression` NOT NULL)
- `GIRelation` — JOIN definitions
- `GIOn` — JOIN conditions
- `GIGroupBy` — aggregation groups
- All tables have audit columns (CreatedByID, NoteID, etc.) that are NOT NULL
- Each table has DIFFERENT NOT NULL columns — there is no documentation for this

**What failed:** Direct SQL INSERTs without schema discovery, without transactions, deployed to production via CustomizationPlugin. Partial failures left orphaned rows that bricked the system.

**What works:**
- GI XML exports from the Acumatica UI deploy correctly via customization packages (4 examples in `Customization/_project/GenericInquiryScreen_*.xml`)
- DELETE statements in CustomizationPlugin run before GI prefetch (this is how we recovered)
- The Acumatica REST API can query GIs once they exist (`/entity/Default/24.200.001/{GIName}`)

**Unknown — MUST investigate:**
1. Can we execute SQL against Acumatica's database from OUTSIDE a CustomizationPlugin? (Direct SQL connection from external service — requires connection string. May not be available on Acumatica Cloud.)
2. Can the Customization API's `/CustomizationApi/Import` endpoint accept a dynamically-generated GI XML package WITHOUT triggering a publish? (Import without publish = no app pool restart)
3. Does Acumatica have any undocumented REST/SOAP endpoints for GI CRUD? (Check the UI's network traffic when creating a GI in SM208000)
4. Can a CustomizationPlugin expose a callable endpoint (e.g., a custom API endpoint or screen) that AcuDev can invoke to trigger GI creation inside Acumatica's runtime?

### Design requirements

The GI Builder must follow this architecture:

**Phase 1: Schema Discovery (read-only, zero risk)**
- Query `INFORMATION_SCHEMA.COLUMNS` for ALL GI tables on the target instance
- Map every NOT NULL column, data type, default value, and constraint
- Extract a "template row" from an existing known-good GI (SELECT, not INSERT) to learn the exact row shape including audit column values
- Cache the discovered schema — it only changes on Acumatica version upgrades
- Output: a complete, validated schema map that the builder uses for every subsequent GI creation

**Phase 2: GI Definition Builder (in-memory, zero risk)**
- Accept a GI specification (target DAC, fields, filters, joins, sort order)
- Construct all SQL rows in memory using the discovered schema
- Validate every row against the schema map BEFORE any database write
- Fail fast with a clear error if any required column is unknown or missing
- Output: a complete SQL transaction script (or GI XML document) ready for execution

**Phase 3: Safe Execution (single transaction, atomic)**
- ALL INSERTs wrapped in `BEGIN TRANSACTION` / `COMMIT` — partial failures roll back completely
- Pre-flight check: verify no GI with the same Name already exists
- Post-flight check: query back all inserted rows, confirm row counts match expectations
- REST API probe: hit `/entity/Default/24.200.001/{GIName}?$top=1` to confirm the GI is queryable
- If any check fails: ROLLBACK and return a structured error

**Phase 4: Verification**
- Confirm the GI appears in the Acumatica UI (SM208000) or at minimum responds to REST queries
- Run a test query through the GI to confirm it returns data
- Log the full creation audit trail (schema version, template source, rows inserted, verification result)

### Safety constraints (non-negotiable)

1. **NEVER write to any GI table without first completing schema discovery on that specific instance**
2. **NEVER execute partial INSERTs — all-or-nothing transactions only**
3. **NEVER deploy GI creation code to production without first testing on sandbox**
4. **Schema discovery results must be cached and versioned** — if the Acumatica version changes, re-discover
5. **Every GI creation must be idempotent** — if the GI already exists, skip or update (never duplicate)
6. **The builder must work on Acumatica Cloud instances** — cannot assume direct DB access

### Deliverables

1. A research spike that answers the 4 "unknown" questions above
2. A design document for the GI Builder engine architecture
3. A proof-of-concept that creates ONE simple GI (e.g., UserAuditTrail) on the Heritage Fabrics test company safely
4. Integration into AcuDev as a core capability

---

## Goal 2: CI/CD Pipeline Hardening

### Why this matters

Today's outage happened because `skip_sandbox=true` was used, bypassing the sandbox gate. The sandbox gate exists specifically to catch issues like this before production. But there are deeper problems:

1. **The sandbox gate doesn't test CustomizationPlugin SQL** — it tests compilation and field existence, but `UpdateDatabase()` SQL only runs during publish. If the SQL is destructive, the sandbox publish catches it... on sandbox. But today we skipped sandbox entirely.
2. **There's no "GI health check"** post-publish — the field validation checks DAC extensions but doesn't verify GI integrity
3. **The emergency path (`force_qualify=true`) bypasses ALL safety gates** — qualification, sandbox, countdown. It's meant for incidents but was used during the incident that caused the problem.
4. **No circuit breaker for GI corruption** — the pipeline detects NullReferenceException and Invalid Column errors, but not `PXGenericInqGrph` duplicate key crashes

### What the pipeline already does well

Read the full pipeline architecture: the CI/CD explorer found 7 safety gates, a sandbox publish gate, automatic rollback from snapshots, qualification checks, concurrency control, and circuit breakers. This is a mature pipeline — it just has gaps for this specific failure mode.

### Hardening requirements

1. **Make sandbox gate unskippable for CustomizationPlugin changes**
   - If the commit diff includes any `CustomizationPlugin`, `UpdateDatabase()`, `<Sql>`, or `<Graph>` elements with SQL, the sandbox gate CANNOT be skipped
   - `skip_sandbox=true` should be rejected with a clear error explaining why
   - Only a separate `skip_sandbox_force=true` (different flag) should allow override, and it must be logged prominently

2. **Add GI health check to post-publish verification**
   - After publish, query `INFORMATION_SCHEMA` for orphaned GI rows (GIDesign records with no matching child rows, or child rows with no matching GIDesign parent)
   - Probe the GI subsystem by hitting any known GI via REST API
   - If GI corruption is detected, trigger automatic rollback

3. **Add "destructive SQL" detection to project validation**
   - `validate-project.py` should flag any `INSERT INTO GI*` or `DELETE FROM GI*` or `UPDATE GI*` statements in CustomizationPlugin code or `<Sql>` elements
   - These should require explicit acknowledgment (a marker comment or flag) to proceed
   - Without the marker, the build should fail with a warning about the 2026-03-29 incident

4. **Improve the emergency deploy path**
   - The basic auth path returned HTTP 401 today. Investigate and fix.
   - Emergency deploys should still run a minimal post-publish smoke test (login + GI probe)
   - Log emergency deploy usage prominently in Slack with the reason

5. **Pre-deploy GI baseline**
   - Before publishing, snapshot the current GI state (list of GIDesign names + DesignIDs)
   - After publishing, compare against baseline — any unexpected new/missing/duplicated GIs trigger a warning

### Deliverables

1. Updated `validate-project.py` with destructive SQL detection
2. Updated post-publish verification with GI health checks
3. Sandbox gate enforcement for CustomizationPlugin changes
4. Emergency deploy path fix (basic auth 401)
5. Pre-deploy GI baseline capture + post-deploy diff

---

## Key files to read first

| File | Why |
|------|-----|
| `docs/AAR-2026-03-29-gi-sql-insert-outage.md` | Full incident post-mortem |
| `.github/workflows/deploy-customization.yml` | The CI/CD workflow |
| `scripts/deploy.py` | Main deploy script |
| `scripts/qualify.py` | Pre-deploy qualification checks |
| `scripts/validate-project.py` | Build-time project validation |
| `scripts/validate-publish.py` | Post-publish field validation |
| `scripts/emergency-deploy-basic-auth.py` | Emergency deploy path |
| `Customization/_project/GenericInquiryScreen_*.xml` | Working GI XML examples |
| `Customization/StudioBAcuOps/project.xml` | Current cleanup plugin |
| `Customization/AesthetikContainers/project.xml` | Working CustomizationPlugin SQL pattern |

## Session approach

**Start with Goal 1 research spike** — answer the 4 unknown questions about GI creation outside CustomizationPlugin. This determines the entire architecture. Use the Acumatica MCP tools and direct API calls to probe what's possible. Check SM208000's network traffic if browser access is available.

**Then design the GI Builder** — schema discovery, in-memory builder, transactional execution, verification. Write the design doc.

**Then harden the pipeline (Goal 2)** — this is implementation work on existing Python scripts and the GitHub Actions workflow. Use the AcuDev skill for any Acumatica-specific patterns.

**Test everything on sandbox/test company first.** No production changes without passing the full pipeline.
