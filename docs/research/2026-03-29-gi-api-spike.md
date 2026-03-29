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

**Status:** PENDING — to be tested after Spike 1 cleanup.

---

## Spike 3: Direct SQL via CustomizationPlugin

**Status:** PENDING — requires plugin deploy to sandbox.

**Known from existing code (StudioBAcuOps/project.xml):**
- `ConfigurationManager.ConnectionStrings["ProjectX"]` works inside `UpdateDatabase()`
- SQL queries (SELECT, DELETE) against GI tables work
- Connection string requires `TrustServerCertificate=True` append
- `WriteLog()` outputs to customization publish log

---

## Spike 4: Callable Plugin Endpoint

**Status:** PENDING — background research agent investigating.

---

## Summary of Execution Paths

| Path | Viable? | Notes |
|------|---------|-------|
| A: XML Deploy (CustomizationApi) | YES (proven) | Requires publish + app pool restart |
| B: Direct SQL via plugin | LIKELY YES | Needs transaction wrapping, schema discovery |
| C: GI CRUD API | **NO** | Does not exist — SM208000 is WebForms-only |
| D: Browser automation (Playwright) | YES (fallback) | Fragile but avoids publish |
| E: Screen-Based SOAP API | UNKNOWN | SM208000 may not be exposed via SOAP |
