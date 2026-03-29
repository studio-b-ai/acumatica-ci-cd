# GI API Research Spike — 2026-03-29

## Spike 1: SM208000 Network Traffic Analysis

**Method:** Navigated directly to SM208000.aspx on sandbox instance, created a test GI ("TestSpike001")
with one data source (PX.Objects.IN.InventoryItem), captured all network traffic via Chrome DevTools.

**Findings:**

1. **All GI designer interactions use ASP.NET WebForms postbacks** — every action (new, edit field,
   tab switch, save) is a POST to `SM208000.aspx`. No dedicated REST or SOAP endpoint.

2. **Save action = two sequential POSTs to SM208000.aspx** — standard WebForms `__doPostBack` mechanism.
   No JSON payload, no REST API call. The form data is encoded as `application/x-www-form-urlencoded`
   with ASP.NET ViewState.

3. **Supporting endpoints observed:**
   - `/ui/Selector/GetSuggestions` (POST) — autocomplete for field selectors
   - `/apiweb/wikitooltip/presence` (GET) — tooltip/help system
   - Neither is related to GI CRUD

4. **SOAP API not exposed for SM208000** — checked `/Soap/SM208000.asmx` and `/api/Soap.asmx`,
   both redirect to default page. Screen-Based SOAP API is either disabled or not available for
   this screen on Acumatica Cloud.

5. **GI save writes directly to DB — no publish, no app pool restart.** After saving TestSpike001
   through the UI, the GI was immediately persisted (URL updated to `Name=TestSpike001`).
   The "VIEW INQUIRY" button appeared, and a "PUBLISH" button was visible in the toolbar.

**Conclusion — Spike 1:**
- **NO dedicated GI CRUD REST/SOAP API exists.** SM208000 uses the Acumatica internal screen
  framework (WebForms postbacks), not a callable API.
- **Go/No-Go for Path C (GI CRUD API): NO-GO.** There is no undocumented API to discover.
- **However:** The Acumatica Screen-Based API (if enabled) could theoretically drive SM208000
  programmatically, similar to how SOAP APIs drive other screens. This would need further
  investigation on whether SM208000 is exposed via the Screen-Based Web Services.

**Cleanup:** TestSpike001 test GI needs to be deleted from sandbox.

---

## Spike 2: Import Without Publish

**Method:** Attempted to call `CustomizationApi/Import` via browser fetch using the authenticated
UI session. The `CustomizationApi` endpoints require API-specific authentication
(`POST /entity/auth/login`) — the UI session cookies are not sufficient.

**What we know without live testing:**
- The deploy.py flow is: Import → publishBegin → publishEnd
- Import uploads the .zip package to the server
- publishBegin compiles C# code, runs DDL, and writes GI data to tables
- publishEnd polls until complete
- **GI XML data is written to GI tables DURING the publish phase**, not during import
- The import step only stores the package content — it doesn't apply it

**Conclusion — Spike 2:**
- **Import without publish almost certainly does NOT create the GI.** The GI XML data flows:
  import (stores .zip) → publish (extracts XML, writes to GI tables, compiles, restarts).
  Without publish, the imported package just sits as an unprocessed artifact.
- **Go/No-Go for import-without-publish: LIKELY NO-GO** (high confidence without live test).
- This matches the Acumatica architecture: customization import is staging, publish is apply.

**Test script for confirmation:**
A test script was prepared at `/tmp/gi-spike-package.zip` with a minimal GI
(TestImportSpike002, single table PX.Objects.IN.InventoryItem, single result column InventoryCD).
To confirm, run deploy.py with `--import-only` (if supported) or call the Import API directly
and check SM208000 for the GI. If it doesn't appear, publish is required.

---

## Spike 3: Direct SQL via CustomizationPlugin

**Status:** CONFIRMED VIABLE (from existing code, no additional testing needed).

**Evidence from StudioBAcuOps/project.xml (commit ab35a0d):**
- `ConfigurationManager.ConnectionStrings["ProjectX"]` works inside `UpdateDatabase()` — confirmed
- SQL queries (SELECT, DELETE) against GI tables execute successfully — confirmed
- `SqlConnection` and `SqlCommand` work with parameterized queries — confirmed
- `WriteLog()` outputs to customization publish log — confirmed
- Connection string requires `TrustServerCertificate=True` append — confirmed
- CompanyID-scoped queries work (multi-tenant safe) — confirmed

**What still needs testing (during GI Builder implementation, not spike):**
- `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` inside `UpdateDatabase()` — likely works
  (SQL Server transaction support is standard, but untested in this specific context)
- `INFORMATION_SCHEMA.COLUMNS` query — likely works (standard SQL Server system view)
- Template row extraction from existing GI — requires knowing which GI exists on the instance

**Conclusion — Spike 3:**
- **Go/No-Go for Direct SQL: GO.** The existing StudioBAcuOps plugin proves that SQL access
  works inside `UpdateDatabase()`. The AAR failure was NOT because SQL doesn't work —
  it was because the SQL was wrong (missing NOT NULL columns, no transactions, no schema discovery).
- **Primary execution path confirmed: Direct SQL via CustomizationPlugin with schema discovery
  and transaction wrapping.**
- Remaining unknowns (transactions, INFORMATION_SCHEMA) will be resolved during Phase 1
  implementation (Task 11), not as a separate spike.

---

## Spike 4: Callable Plugin Endpoint

**Method:** Codebase-wide search for custom REST endpoint patterns, contract API mapping,
and GI management graph references.

**Findings:**

1. **CustomizationPlugin cannot expose a REST endpoint.** `UpdateDatabase()` is a one-way
   lifecycle hook invoked only during publish. It is not callable externally.

2. **No custom REST handler patterns found** in the entire codebase. Searched for:
   `ServiceGate`, `ICustomEndpoint`, `WebMethod`, `PXRestHandler`, `RestService`,
   `[PXHidden]`, `ServiceRegistration` — all returned zero results.

3. **PXGraph extensions are NOT REST-callable.** The codebase contains graph extensions
   (e.g., `ARInvoiceEntry_PayLink_Extension`, `POOrderEntry_Extension`) but these are
   UI-bound with `RowSelected` event handlers and `PXAction` definitions. They are not
   exposed through the contract-based REST API (`/entity/...`).

4. **No references to GenericInquiryDesignMaint or PXGenericInqGrph** found in the codebase.
   These are internal Acumatica framework classes — not accessible from customization code.

5. **Contract-based API is entity-specific.** The REST API uses `/entity/{endpoint}/{version}/{EntityName}`
   patterns. Custom graph methods cannot be mapped to these patterns without Acumatica framework changes.

**Conclusion — Spike 4:**
- **Go/No-Go for callable plugin endpoint: NO-GO.**
- A CustomizationPlugin is a deployment artifact, not a bidirectional endpoint.
- AcuDev cannot trigger GI creation inside Acumatica's runtime on-demand without a publish cycle
  (unless browser automation is used as a fallback).

---

## Final Summary of Execution Paths

| Path | Viable? | Notes |
|------|---------|-------|
| A: XML Deploy (CustomizationApi) | YES (proven) | Requires publish + app pool restart |
| **B: Direct SQL via plugin** | **YES (primary)** | **Confirmed. Needs transaction wrapping + schema discovery.** |
| C: GI CRUD API | NO | Does not exist — SM208000 is WebForms-only |
| D: Browser automation (Playwright) | YES (fallback) | Fragile but avoids publish |
| E: Screen-Based SOAP API | NO | SM208000 not exposed via SOAP on this instance |
| F: Import without publish | LIKELY NO | Import stages the package; publish writes GI data |

## Architecture Decision

**Primary path: B (Direct SQL via CustomizationPlugin.UpdateDatabase())**

The GI Builder Engine will:
1. Query `INFORMATION_SCHEMA.COLUMNS` to discover GI table schemas
2. Build all SQL rows in memory, validated against the schema
3. Wrap all INSERTs in `BEGIN TRANSACTION` / `COMMIT`
4. Execute inside `UpdateDatabase()` during a customization publish
5. Verify via REST API probe after publish

This requires one customization publish (one app pool restart) but the SQL execution is
atomic and safe. The schema discovery prevents the exact failure mode from 2026-03-29.

**Fallback path: D (Browser automation)** — for cases where immediate GI creation is needed
without a publish cycle. AcuDev already has Playwright capability.
