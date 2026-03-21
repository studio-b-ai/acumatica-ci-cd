# After-Action Review: StudioBPORelations (PO301000 Relations + Activities)

**Date:** 2026-03-09
**Duration:** ~7 hours (34 commits, ~30 CI/CD pipeline runs)
**Outcome:** Success — UsrPORelation + UsrPOActivity tables created, Relations + Activities tabs live on PO301000

---

## Summary

15 distinct approaches tried before finding the working solution. Three cascading problems were solved:

1. **CRM DAC incompatibility** (2.5 hrs) — CRM DACs crash non-CRM graphs at the field attribute level
2. **`<Sql>` silent failures** (2 hrs) — CREATE TABLE via `<Sql>` elements silently ignored on cloud
3. **`PXDatabase.Execute()` misconception** (30 min) — Framework method is a stored proc caller, not raw SQL

---

## What Failed (15 Approaches)

| # | Approach | Why it failed |
|---|----------|--------------|
| 1 | `CRRelationDetailsExt<POOrderEntry>` | CRM base class requires CRM views (PXViewDoesNotExistException) |
| 2 | Raw `PXSelect<CRRelation>` | DAC field `[PXSelector]` attributes reference missing CRM views |
| 3 | Raw `PXSelect<CRPMTimeActivity>` | Same DAC-level problem as #2 |
| 4 | Custom DACs + `<Table>` elements | NullReferenceException on cloud (always) |
| 5 | Custom DACs + `<Sql>` CREATE TABLE (secondary project) | Silently ignored — never appeared in publish log |
| 6 | Renamed `<Sql>` elements to bypass cache | Still silently ignored |
| 7 | Moved `<Sql>` to primary project (HeritageFabricsPOv5) | Still silently ignored for CREATE TABLE |
| 8 | Wrapped in `EXEC sp_executesql` | Same silent failure |
| 9 | Bare CREATE TABLE without guards | Same silent failure |
| 10 | `CustomizationPlugin` (namespace `PX.Data.Update`) | CS0246 — wrong namespace |
| 11 | `CustomizationPlugin` (namespace `Customization`) | `PXDatabase.Execute()` was a stored proc caller |
| 12 | Graph `Initialize()` + `PXDatabase.Execute()` | Same stored proc issue, caught silently |
| 13 | Added diagnostic `WriteLog()` to CustomizationPlugin | **Revealed the root cause** |
| 14 | Switched to raw ADO.NET (`Microsoft.Data.SqlClient`) | SSL certificate trust error |
| **15** | **ADO.NET + TrustServerCertificate=True** | **SUCCESS** |

---

## Root Cause Analysis

### Problem 1: CRM DAC Incompatibility (cost: 2.5 hours, 7 commits)

**Assumption:** CRM DACs (`CRRelation`, `CRPMTimeActivity`) could be used on any graph via `PXSelect<>`.

**Reality:** CRM DACs have field-level `[PXSelector]` attributes that reference CRM views (contact caches, address caches). These attributes are evaluated during graph initialization by the REST API automation framework — even if the view is never queried. On non-CRM graphs like `POOrderEntry`, these views don't exist, causing `PXViewDoesNotExistException` at runtime.

**Deceptive signal:** CI/CD smoke tests (`PurchaseOrder?$top=1` → HTTP 200) passed because view resolution can be deferred. The screen only crashed when a user opened it in a browser.

**Correct approach:** Build completely custom DACs (`UsrPORelation`, `UsrPOActivity`) with zero CRM dependencies. All fields are primitive types — no selectors referencing external views.

### Problem 2: `<Sql>` Element Silent Failures (cost: 2 hours, 8 commits)

**Assumption:** `<Sql>` elements with CREATE TABLE statements would execute during publish, just like ALTER TABLE statements do.

**Reality:** On Acumatica cloud, `<Sql>` elements containing CREATE TABLE are silently skipped during publish. They don't appear in the publish log at all — not as success, not as failure, not as "skipped." ALTER TABLE statements in `<Sql>` elements DO work, but CREATE TABLE does not.

Additionally, `<Sql>` elements in secondary co-published projects may be silently ignored entirely.

**Why it was hard to diagnose:** Zero feedback. The publish reported success. The smoke test reported success (the graph extension loaded, but queries against the non-existent tables returned HTTP 500 with "Invalid object name").

**Correct approach:** Use `CustomizationPlugin.UpdateDatabase()` with raw ADO.NET for CREATE TABLE operations.

### Problem 3: `PXDatabase.Execute()` Misconception (cost: 30 min before diagnostics)

**Assumption:** `PXDatabase.Execute(sqlString)` executes raw SQL against the database.

**Reality:** `PXDatabase.Execute()` is a **stored procedure caller**. It wraps the input in `EXEC @input`, treating the entire string as a stored procedure name. Passing `SELECT 1` produces: `"Could not find stored procedure 'SELECT 1'"`. Passing `CREATE TABLE ...` produces: `"Could not find stored procedure 'CREATE TABLE ...'"`.

**Why it was hard to diagnose:** The `Initialize()` method on the graph extension had a bare `catch {}` that swallowed all exceptions. The `CustomizationPlugin` initially caught exceptions without logging details. The actual error message (`"Could not find stored procedure..."`) was never visible until explicit `WriteLog(ex.Message)` was added.

**Correct approach:** Use raw ADO.NET via `Microsoft.Data.SqlClient.SqlConnection` with connection string from `ConfigurationManager.ConnectionStrings["ProjectX"]` + `;TrustServerCertificate=True`.

---

## The Efficiency Gap

**The root cause was identifiable at approach #11** but wasn't identified until **approach #13** because exception details were swallowed.

The actual error message (`"Could not find stored procedure 'SELECT 1'"`) immediately pointed to the solution. But without `WriteLog()` capturing `ex.GetType().FullName + ": " + ex.Message`, I was iterating blind.

**Cost of late diagnostics:** ~10 wasted pipeline runs (50 minutes of pure wait time) + ~6 wasted commits.

### Timeline of Diagnostic Evolution

| Commit | Diagnostic Level | What was visible |
|--------|-----------------|------------------|
| 1-8 | None | `<Sql>` elements produced zero feedback |
| 9 (df478c7) | Minimal | "diagnostic test" — still caught exceptions silently |
| 10 (dcb145b) | Minimal | Bare CREATE TABLE test — still no error detail |
| **11 (e8530c7)** | **Full** | `WriteLog()` with `ex.GetType().FullName + ": " + ex.Message` — **root cause visible in 5 minutes** |
| 12-14 | Full | ADO.NET switch, SSL fix, cleanup — all resolved quickly |

---

## What Went Right

1. **Incremental commits** — Each attempt was a separate commit, making rollback trivial
2. **deploy.sh improvements** — Python-based publish log parsing caught C# compilation errors that raw output missed
3. **Lessons captured immediately** — `lessons-learned.md` updated with all findings before the session ended
4. **Clean architecture decision** — Custom DACs (zero CRM deps) was the right call once CRM incompatibility was proven
5. **CI/CD pipeline reliability** — 30 runs, 25 successes, 5 legitimate failures. The pipeline itself never broke.
6. **Working solution is production-grade** — `IF NOT EXISTS` guards make it idempotent, `CustomizationPlugin.UpdateDatabase()` runs on every publish (safe for re-deployment)

---

## Actions Required

### Immediate (Process Changes)

#### 1. Diagnostic-First Rule
When working with any opaque deployment system, the **FIRST commit** adds `WriteLog()`/logging with full exception details. No exceptions to this rule.

Template:
```csharp
try
{
    WriteLog("DIAG: About to attempt X");
    // actual code
    WriteLog("DIAG: X succeeded");
}
catch (Exception ex)
{
    WriteLog("DIAG: X FAILED: " + ex.GetType().FullName + ": " + ex.Message);
    if (ex.InnerException != null)
        WriteLog("DIAG: Inner: " + ex.InnerException.Message);
}
```

#### 2. Batch Hypothesis Testing
Combine 2-3 diagnostic probes per commit to minimize 5-minute pipeline round-trips. Example: test `PXDatabase.Execute("SELECT 1")`, test `ConfigurationManager.ConnectionStrings["ProjectX"]`, test raw ADO.NET — all in one commit, each with its own `WriteLog()`.

#### 3. Enhanced CI/CD Smoke Tests
The current smoke test (`PurchaseOrder?$top=1` → HTTP 200) is insufficient. It passed even when CRM DACs would crash the screen. Add:
- `$expand` on all custom views (catches view resolution failures)
- Verify `custom.{ViewName}.{FieldName}` exists in query responses
- Test `$adHocSchema` for expected custom fields

### Build (Tooling)

#### 4. Customization Validation Script
Post-publish validator that:
- Queries each entity with `$expand` on all custom views
- Verifies `custom.{ViewName}.{FieldName}` exists in responses
- Tests `$adHocSchema` for expected custom fields
- Reports pass/fail per view, not just per entity
- Catches CRM-style view failures at CI/CD time instead of requiring manual browser testing

#### 5. Acumatica Customization Template
A `project.xml` skeleton generator that includes:
- Pre-wired `CustomizationPlugin` with ADO.NET DDL pattern + `TrustServerCertificate`
- DAC template with CompanyID, IDENTITY PK, audit fields, timestamp
- ASPX tab template with correct `Children Key="Template"` structure
- `WriteLog()` diagnostic infrastructure baked in

Eliminates the namespace lookup, connection string discovery, SSL flag — all the things that burned time.

#### 6. Pipeline Feedback Enrichment
Enhance `deploy.sh` to:
- Extract and display `CustomizationPlugin.WriteLog()` output (filter `[information]` entries matching a prefix pattern like `"StudioB"`)
- Surface plugin diagnostic messages in GitHub Actions step summary
- Fail the pipeline if any `[error]` or `[exception]` log entries exist

---

## Working Solution Reference

The final working pattern for creating new tables on Acumatica cloud:

```csharp
using Customization;

namespace StudioB.PO
{
    public class PORelationsInstaller : CustomizationPlugin
    {
        public override void UpdateDatabase()
        {
            // 1. Get connection string
            string connStr = null;
            var cs = System.Configuration.ConfigurationManager.ConnectionStrings["ProjectX"];
            if (cs != null) connStr = cs.ConnectionString;

            if (connStr == null) { WriteLog("No connection string found"); return; }

            // 2. Add TrustServerCertificate (Microsoft.Data.SqlClient requires it on cloud)
            if (!connStr.Contains("TrustServerCertificate"))
                connStr += ";TrustServerCertificate=True";

            // 3. Execute DDL via raw ADO.NET
            ExecuteDDL(connStr, "MyTable", @"
                IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'MyTable')
                CREATE TABLE MyTable (
                    CompanyID INT NOT NULL DEFAULT 0,
                    MyTableID INT IDENTITY(1,1) NOT NULL,
                    -- ... columns ...
                    tstamp TIMESTAMP NOT NULL,
                    CONSTRAINT PK_MyTable PRIMARY KEY CLUSTERED (CompanyID, MyTableID)
                )");

            WriteLog("UpdateDatabase complete");
        }

        private void ExecuteDDL(string connStr, string label, string sql)
        {
            try
            {
                using (var conn = new Microsoft.Data.SqlClient.SqlConnection(connStr))
                {
                    conn.Open();
                    using (var cmd = conn.CreateCommand())
                    {
                        cmd.CommandText = sql;
                        cmd.CommandTimeout = 60;
                        cmd.ExecuteNonQuery();
                    }
                }
                WriteLog(label + " — OK");
            }
            catch (System.Exception ex)
            {
                WriteLog(label + " — FAILED: " + ex.GetType().FullName + ": " + ex.Message);
            }
        }
    }
}
```

**Key requirements:**
- Namespace: `using Customization;` (NOT `PX.Data.Update`)
- Class: inherits `CustomizationPlugin`, overrides `UpdateDatabase()`
- Connection: `ConfigurationManager.ConnectionStrings["ProjectX"]` + `;TrustServerCertificate=True`
- Driver: `Microsoft.Data.SqlClient.SqlConnection` (NOT `System.Data.SqlClient`, NOT `PXDatabase.Execute()`)
- SQL: `IF NOT EXISTS` guards for idempotency, `CompanyID` for multi-tenant, `IDENTITY` for auto-increment
- Include as `<Graph>` element in project.xml (same as DACs and graph extensions)

---

## Key Lessons

| Lesson | Impact |
|--------|--------|
| `PXDatabase.Execute()` is a stored proc caller, not raw SQL | Root cause of the entire table creation failure |
| `<Sql>` CREATE TABLE silently fails on Acumatica cloud | ALTER TABLE works, CREATE TABLE does not |
| `<Table>` elements always NullReferenceException on cloud | Never use for column/table creation |
| CRM DACs crash non-CRM graphs at the DAC attribute level | Not a graph-level or base-class issue — it's field-level `[PXSelector]` attributes |
| CI/CD smoke tests can pass when screens are broken | View resolution can be deferred; always verify with browser for CRM changes |
| Diagnostic logging should be the FIRST commit | Would have saved ~50 minutes of pipeline wait time and ~6 commits |
| Acumatica project names must be alphanumeric | No underscores or hyphens allowed |
| `CustomizationPlugin` namespace is `Customization` | NOT `PX.Data.Update` (community sources are wrong) |
| `Microsoft.Data.SqlClient` requires `TrustServerCertificate=True` on cloud | Stricter SSL validation than `System.Data.SqlClient` |
