# AAR: Generic Inquiry SQL INSERT Outage — 2026-03-29

## Incident Summary

**Duration:** ~45 minutes (16:20 UTC – 17:05 UTC)
**Impact:** Acumatica production instance bricked — all screen navigations redirected to error page, customization publishing blocked
**Root Cause:** Orphaned GI (Generic Inquiry) rows inserted via CustomizationPlugin SQL caused duplicate key exception in GI cache prefetch during app pool restart
**Resolution:** CI/CD deploy of cleanup plugin that DELETEs orphaned rows during `UpdateDatabase()` phase

## Timeline

| Time (UTC) | Event |
|------------|-------|
| ~16:00 | Multiple StudioBAcuOps deploys attempted — each version tried to INSERT rows into GI tables (GIDesign, GITable, GIResult, GIWhere, GISort, GIFilter) to create a UserAuditTrail Generic Inquiry |
| ~16:15 | Repeated publish failures due to NOT NULL column mismatches (Type, CreatedByID, RowID, NoteID, Name, IsExpression). Each failed attempt left partial rows in the database. |
| ~16:20 | Final publish caused `PXGenericInqGrph+Definition: An item with the same key has already been added` — GI prefetch crashed on app pool restart, bricking the instance |
| ~16:25 | Replaced StudioBAcuOps plugin with safe cleanup-only no-op (DELETE orphaned rows, no INSERTs). Committed as `ab35a0d`. |
| ~16:28 | CI/CD auto-deploy on push failed — Acumatica API unreachable (app pool crashed) |
| ~16:35 | Kevin manually deleted StudioBAcuOps from SM204505 and attempted republish of good packages |
| ~16:40 | Manual republish ALSO failed — orphaned GI rows survive project deletion. Same duplicate key crash. |
| ~16:45 | CI/CD triggered with `force_qualify=true` — failed with HTTP 401 (basic auth path broken) |
| ~16:48 | CI/CD triggered with session auth (no force_qualify) — **succeeded**. Cleanup plugin ran during `UpdateDatabase()`, deleted orphaned rows before GI prefetch. |
| ~16:55 | System fully restored. SO301000, API, all screens operational. |

## Root Cause Analysis

### What happened

The goal was to create a UserAuditTrail Generic Inquiry programmatically via SQL INSERTs in a `CustomizationPlugin.UpdateDatabase()` method. This approach was chosen because:

1. SOAP API for SM205530 (Audit History screen) is confirmed dead for batch data extraction
2. GI XML files in customization packages are dead code for NEW GIs — fabricated GUIDs don't match existing records
3. Direct SQL was the only remaining programmatic path

### Why it failed

**Problem 1: GI table schema is undocumented and varies per table**

Each GI child table (GITable, GIResult, GIWhere, GISort, GIFilter, GIRelation, GIOn, GIGroupBy) has different NOT NULL columns. There is no documentation for these schemas. Discovery required multiple deploy-fail-diagnose cycles, each leaving partial rows.

- GITable: has `Type` (NOT NULL), does NOT have `RowID`
- GIResult: has `RowID` (NOT NULL)
- GIFilter: has `Name` and `IsExpression` (NOT NULL)
- GIWhere: does NOT have `RowID`
- All tables: have audit columns (CreatedByID, NoteID, etc.) that are NOT NULL

**Problem 2: Failed INSERTs left orphaned rows**

When a publish fails mid-SQL (e.g., INSERT into GITable succeeds but INSERT into GIResult fails on RowID), the successful inserts are NOT rolled back. Each retry created more orphaned rows.

**Problem 3: Orphaned GI rows survive project deletion**

Deleting a customization project from SM204505 does NOT undo the SQL that the project's `UpdateDatabase()` method already executed. The GI rows persist in the database permanently.

**Problem 4: Duplicate GI rows crash the entire GI subsystem**

Acumatica's `PXGenericInqGrph+Definition` prefetch loads all GI records from GIDesign into a dictionary keyed by Name. Duplicate rows (from partial inserts across multiple attempts) throw `ArgumentException: An item with the same key has already been added`, which crashes the app pool on restart. This blocks ALL customization publishing, not just the offending package.

**Problem 5: No pre-deploy validation caught the issue**

The CI/CD pipeline validates project.xml syntax and C# compilation, but cannot validate that runtime SQL will succeed. The `UpdateDatabase()` code compiles fine — it only fails when executed against the live database.

## What went right

1. The cleanup plugin pattern worked — `UpdateDatabase()` runs BEFORE `PXGenericInqGrph` prefetch during publish, so the DELETE statement executes before the duplicate key crash would occur
2. CI/CD session auth path worked when basic auth failed
3. System was fully recoverable without Acumatica support intervention

## What went wrong

1. **No transaction wrapping on SQL INSERTs** — each INSERT was independent. Should have used a SQL transaction so partial inserts roll back on failure.
2. **No pre-deploy testing** — SQL was deployed directly to production. Should have been tested against the sandbox/test company first.
3. **Multiple rapid deploy attempts** — each failed attempt added more orphaned rows, compounding the problem.
4. **No GI table schema discovery before coding** — should have queried `INFORMATION_SCHEMA.COLUMNS` on the test instance FIRST to understand all NOT NULL constraints before writing any INSERT statements.
5. **Underestimated blast radius** — a broken GI doesn't just affect that GI; it crashes the entire GI subsystem and blocks all customization publishing.

## Action Items

### Immediate

- [x] System restored via CI/CD cleanup deploy
- [ ] Remove StudioBAcuOps from `ALSO_PUBLISH_PROJECTS` and `KNOWN_PROJECTS` — it should not be co-published until it has real, tested functionality
- [ ] Update `ALSO_PUBLISH_PROJECTS` GitHub variable to remove StudioBAcuOps

### Process Changes

- [ ] **MANDATORY: All CustomizationPlugin SQL must be tested on sandbox/test company before production deploy** — add sandbox gate that actually runs the plugin, not just compiles it
- [ ] **MANDATORY: Wrap all SQL INSERTs in explicit transactions** — partial inserts are the #1 cause of orphaned data
- [ ] **Add GI table schema documentation** to lessons-learned.md — the NOT NULL column map for each GI child table
- [ ] **Add CI/CD rollback capability** — when a publish fails and bricks the system, the pipeline should be able to import+publish a known-good snapshot automatically
- [ ] **Rate-limit deploy retries** — prevent rapid-fire re-deploys that compound data corruption

### Architecture Decision

**GI creation via SQL is too dangerous for production use.** The correct approach for creating new Generic Inquiries is:

1. Create the GI manually in the Acumatica UI (SM208000)
2. Export it as part of a customization project
3. Deploy via CI/CD (the XML export from an existing GI includes correct GUIDs and all required fields)

Fabricating GI rows via SQL should be permanently abandoned as an approach.

## Lessons Learned

1. **Acumatica's GI subsystem is a single point of failure** — one corrupted GI row can brick the entire instance
2. **CustomizationPlugin.UpdateDatabase() is irreversible** — there is no undo. Failed SQL persists forever unless explicitly cleaned up.
3. **Deleting a customization project does NOT rollback its database changes** — the project deletion only removes the project metadata, not the data it created
4. **The CI/CD pipeline needs a "nuclear rollback" option** — import a known-good snapshot and publish, bypassing all validation
5. **GI table schemas are NOT documented** — any future SQL work against GI tables requires INFORMATION_SCHEMA discovery first
