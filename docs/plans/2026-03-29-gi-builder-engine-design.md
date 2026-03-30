# Design: AcuDev GI Builder Engine + CI/CD Pipeline Hardening

**Date:** 2026-03-29
**Status:** Approved
**Context:** [AAR: 2026-03-29 GI SQL INSERT Outage](../AAR-2026-03-29-gi-sql-insert-outage.md) | [Session Brief](2026-03-29-gi-builder-and-pipeline-hardening.md)

---

## Goal 1: AcuDev GI Builder Engine

### Research Spike

Four unknowns that determine the engine's execution architecture. Must be answered before implementation.

#### Spike 1: SM208000 Network Traffic

**Method:** Browser DevTools on sandbox instance.

- Navigate to SM208000 (Generic Inquiry designer)
- Open network tab, create a simple test GI (1 table, 1 result column, save)
- Capture every API call — especially the save/create action
- Look for REST endpoints, SOAP envelopes, screen API patterns (`/Screen/...`)

**Success criteria:** Discover a callable endpoint for GI CRUD, or confirm none exists.

#### Spike 2: CustomizationApi Import Without Publish

**Method:** API call to sandbox.

- Generate a minimal valid GI XML package (single table, single result column)
- Call `POST /CustomizationApi/Import` with the package
- Do NOT call `publishBegin`/`publishEnd`
- Check: does the GI appear in SM208000? Is it queryable via REST API?

**Success criteria:** Determine if import alone creates the GI, or if publish is required.

#### Spike 3: Direct SQL via CustomizationPlugin

**Method:** Code analysis + test plugin on sandbox.

The expected primary execution path. `CustomizationPlugin.UpdateDatabase()` has access to
`ConfigurationManager.ConnectionStrings["ProjectX"]`, giving direct SQL access during publish.

- Confirm: does `UpdateDatabase()` have a working SQL connection on the sandbox instance?
- Test: query `INFORMATION_SCHEMA.COLUMNS` for all GI tables from within a plugin
- Test: execute a `BEGIN TRAN` / `SELECT` / `ROLLBACK` to confirm transaction support
- Map: what connection string names are available? Does this work on Acumatica Cloud?

**Key insight from AAR:** SQL itself isn't dangerous. SQL without schema discovery + transactions is
dangerous. With proper `BEGIN TRAN`/`COMMIT` + `INFORMATION_SCHEMA` discovery, direct SQL is the
fastest path — no publish cycle, no app pool restart for the GI data itself.

**Success criteria:** Confirm SQL access works inside plugins, map connection constraints per hosting type.

#### Spike 4: CustomizationPlugin Callable Endpoint

**Method:** Research + test.

- Can a `PXGraph` extension or custom endpoint registered in a plugin be called via REST?
- Check if Acumatica's contract-based API allows calling custom graphs
- Look at how existing custom screens/endpoints work in the codebase

**Success criteria:** Determine if AcuDev can trigger GI creation inside Acumatica's runtime on-demand
(without a full publish cycle).

#### Spike Output

A research findings document with go/no-go for each path. The findings determine which execution
path(s) the engine supports.

---

### Engine Architecture

Four phases, each building on the previous.

#### Phase 1: Schema Discovery (read-only, zero risk)

Execution: SQL query inside CustomizationPlugin (or REST if spike discovers an API).

1. Query `INFORMATION_SCHEMA.COLUMNS` for ALL GI tables:
   - GIDesign, GITable, GIResult, GIWhere, GISort, GIFilter
   - GIRelation, GIOn, GIGroupBy
   - GINavigationCondition, GINavigationParameter, GINavigationScreen
2. For each table, capture: column name, data type, nullable, default value, max length
3. Extract "template row" from existing known-good GI (SELECT from InventoryQuantityDetail)
   to learn exact audit column values (CreatedByID, CreatedByScreenID, etc.)
4. Cache as versioned schema map: `gi-schema-{acuVersion}.json`

Output: Complete validated schema map used by the builder for every subsequent GI creation.

Re-discovery trigger: Acumatica version change (compare against cached version).

#### Phase 2: GI Definition Builder (in-memory, zero risk)

Input: GI specification object.

```
{
  name: "UserAuditTrail",
  screenId: "GI000001",
  tables: [
    { dac: "PX.SM.AuditHistory", alias: "AuditHistory" }
  ],
  results: [
    { field: "ScreenID", caption: "Screen", width: 120, visible: true },
    { field: "TableName", caption: "Table", width: 150, visible: true },
    ...
  ],
  filters: [
    { name: "@ScreenFilter", displayName: "Screen ID", dataType: "string" }
  ],
  where: [
    { field: "AuditHistory.ScreenID", condition: "E", value: "@ScreenFilter" }
  ],
  sort: [
    { field: "AuditHistory.CreatedDateTime", order: "D" }
  ]
}
```

Process:

1. Generate fresh UUIDs (DesignID, NoteIDs, RowIDs following the `{designPrefix}0001-...` pattern)
2. Build all rows using the cached schema map
3. Fill audit columns from template row (CreatedByID, CreatedByScreenID, CreatedDateTime, etc.)
4. Validate every row against schema:
   - All NOT NULL columns have values
   - Data types match constraints
   - LineNbrs are sequential starting at 1
   - String lengths within max length
5. Fail fast with structured error if ANY validation fails

Output depends on execution path:
- **Path A (XML Deploy):** Valid GI XML customization package (.zip)
- **Path B (Direct SQL):** Transactional SQL script embedded in CustomizationPlugin
- **Path C (GI CRUD API):** API request payload (if spike discovers an endpoint)

#### Phase 3: Safe Execution (atomic)

Possible execution paths (spike determines which are available):

| Path | Method | Publish needed? | App pool restart? | Cloud-compatible? |
|------|--------|-----------------|-------------------|-------------------|
| A: XML Deploy | CustomizationApi Import + Publish | Yes | Yes (2-5 min) | Yes |
| B: Direct SQL | `BEGIN TRAN` inside `UpdateDatabase()` | Yes (plugin deploy) | Yes (once) | Maybe |
| C: GI CRUD API | Undocumented endpoint (if discovered) | No | No | Yes (if exists) |
| D: Browser | Playwright drives SM208000 UI | No | No | Yes |

**Expected primary path: B (Direct SQL via plugin).** The SQL runs inside `UpdateDatabase()` during
a customization publish. The publish itself causes one app pool restart, but the GI data is inserted
transactionally within that publish cycle.

All paths share these safety checks:

- **Pre-flight:** Verify no GI with same Name already exists (`SELECT COUNT(*) FROM GIDesign WHERE Name = @name`)
- **Execution:** Atomic — SQL wrapped in `BEGIN TRAN`/`COMMIT`, any failure → `ROLLBACK`
- **Post-flight:** Query back all inserted rows, confirm row counts match expectations per table
- **REST probe:** `GET /entity/Default/24.200.001/{GIName}?$top=1` to confirm GI is queryable
- **On failure:** Full ROLLBACK, structured error returned, no orphaned rows

#### Phase 4: Verification

1. **REST API query:** `GET /entity/Default/24.200.001/{GIName}?$top=1`
   Confirms GI is registered and queryable by the entity API.

2. **Data validation:** Does the GI return expected columns with correct types?
   Confirms result column definitions match the specification.

3. **Audit log:** Record full creation metadata.
   Schema version, template source, execution path used, rows inserted per table,
   verification result, total duration.

### Safety Constraints (non-negotiable)

1. NEVER write to any GI table without first completing schema discovery on that specific instance
2. NEVER execute partial INSERTs — all-or-nothing transactions only
3. NEVER deploy GI creation code to production without first testing on sandbox AND Heritage Test
4. Schema discovery results must be cached and versioned — re-discover on Acumatica version change
5. Every GI creation must be idempotent — if the GI already exists, skip or update (never duplicate)
6. The builder must work on Acumatica Cloud instances — cannot assume direct DB access from external services

### Deliverables

1. Research spike findings document (answers to 4 unknowns)
2. This design document (approved)
3. Schema discovery implementation (Phase 1)
4. GI Definition Builder (Phase 2)
5. Safe execution implementation for primary path (Phase 3)
6. Verification suite (Phase 4)
7. Proof-of-concept: create UserAuditTrail GI on Heritage Test tenant

---

## Goal 2: CI/CD Pipeline Hardening

### Deployment Topology

```
Sandbox instance (separate URL)
  └─ First publish target — catches compilation + runtime errors

Production instance (two tenants)
  ├─ Heritage Test tenant  ← hard gate: must pass before prod deploy
  └─ Production tenant     ← final target
```

Pipeline gate progression:

```
build → qualify → sandbox publish → Heritage Test validation → countdown → prod deploy → post-deploy verify
```

### Hardening 1: Unskippable Sandbox Gate + Heritage Test Gate

**Files:** `.github/workflows/deploy-customization.yml`

**Sandbox gate (existing, strengthened):**

- New step before sandbox job: diff changed files against `main`
- If diff contains `CustomizationPlugin`, `UpdateDatabase()`, `<Sql>`, or `<Graph>` elements with
  SQL patterns (INSERT, DELETE, UPDATE, ALTER, DROP, TRUNCATE) → set `plugin_changes=true`
- When `plugin_changes=true` AND `skip_sandbox=true` → **reject with error:**
  "Sandbox gate cannot be skipped for CustomizationPlugin changes. See AAR-2026-03-29.
  Use skip_sandbox_force=true to override (will be logged)."
- `skip_sandbox_force=true` allows override but logs prominently to Slack with operator and reason

**Heritage Test gate (new, hard gate):**

- After sandbox publish succeeds, deploy the same package to the production instance targeting
  the Heritage Test tenant
- Run the same post-publish verification suite (login, entity checks, custom field validation)
- Additionally run GI health checks (Hardening 2) on Heritage Test
- **Hard gate:** Heritage Test failure blocks prod deploy. No override flag.
- Heritage Test gate runs for ALL deploys, not just plugin changes

### Hardening 2: GI Health Check in Post-Publish Verification

**File:** `scripts/validate-publish.py`

New checks added to post-publish verification, running on both Heritage Test and prod:

1. **GI subsystem probe:** Query a known GI via REST API (e.g., InventoryQuantityDetail).
   HTTP 500 or timeout → GI subsystem is broken → trigger auto-rollback.

2. **GI baseline comparison:** Compare current GI list against pre-deploy baseline (see Hardening 5).
   Unexpected new/missing/duplicated GIs → warning (not hard fail, since some deploys intentionally
   add GIs).

3. **Orphan detection (if SQL access available):** Query for GIDesign records with no matching
   child rows (GITable, GIResult), or child rows with no matching GIDesign parent.
   Orphans detected → trigger auto-rollback.

### Hardening 3: Destructive SQL Detection in Project Validation

**File:** `scripts/validate-project.py`

New pattern matching in `<Graph>` and `<Sql>` elements:

- Match: `INSERT INTO GI`, `DELETE FROM GI`, `UPDATE GI`, `DROP TABLE GI`, `TRUNCATE TABLE GI`,
  `ALTER TABLE GI` (case-insensitive, allowing whitespace variations)
- Without a `-- REVIEWED: gi-sql-safe` marker comment in the same `<Graph>`/`<Sql>` block → **hard fail**
- Error message:

  ```
  BLOCKED: Direct SQL against GI tables detected in {file}:{element}.
  This pattern caused a 45-minute production outage on 2026-03-29.
  See docs/AAR-2026-03-29-gi-sql-insert-outage.md.
  If this SQL has been reviewed and is safe, add: -- REVIEWED: gi-sql-safe
  ```

### Hardening 4: Emergency Deploy Fix (HTTP 401)

**File:** `scripts/emergency-deploy-basic-auth.py`

- Investigate why basic auth returned HTTP 401 during the 2026-03-29 incident
- Likely causes: expired credentials, wrong endpoint, basic auth disabled on instance
- Fix the auth mechanism (update credentials, fix endpoint URL, or switch to alternative auth)
- Add minimal post-publish smoke test: login attempt + GI probe (reuse Hardening 2 logic)
- Log emergency deploy usage to Slack: operator, reason, timestamp, outcome

### Hardening 5: Pre/Post-Deploy GI Baseline Diffing

**New file:** `scripts/gi-baseline.py`

**Pre-deploy (baseline capture):**

- Query the Acumatica REST API for all available GI endpoints
- Or query SM208000 screen API for GIDesign list (names + DesignIDs)
- Save as JSON: `{ timestamp, instance, tenant, gis: [{ name, designId }] }`

**Post-deploy (diff):**

- Capture the same GI list after publish
- Compare against baseline:
  - New GIs not in baseline → log (expected for GI-creating deploys)
  - Missing GIs (in baseline but not post-deploy) → **warning**
  - Duplicated GI names → **error** (trigger rollback investigation)

**Integration:** Called from the deploy workflow:
- Pre-deploy: run after pre-deploy snapshot, before publish
- Post-deploy: run as part of post-publish verification (Hardening 2)
- Runs on both Heritage Test and prod tenants

---

## Implementation Order

1. **Research spike** (Goal 1) — answers determine engine architecture
2. **Destructive SQL detection** (Hardening 3) — immediate risk reduction, validate-project.py change
3. **Sandbox gate strengthening** (Hardening 1, sandbox portion) — prevent skip for plugin changes
4. **GI health check** (Hardening 2) — add GI probe to post-publish validation
5. **Emergency deploy fix** (Hardening 4) — investigate and fix HTTP 401
6. **GI baseline diffing** (Hardening 5) — new script + workflow integration
7. **Heritage Test gate** (Hardening 1, Heritage Test portion) — new pipeline stage
8. **Schema discovery** (Phase 1) — GI Builder foundation
9. **GI Definition Builder** (Phase 2) — in-memory builder
10. **Safe execution** (Phase 3) — transactional SQL via plugin
11. **Verification suite** (Phase 4) — REST probe + data validation
12. **Proof-of-concept** — create UserAuditTrail GI on Heritage Test
