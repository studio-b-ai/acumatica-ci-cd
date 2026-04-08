# SB501000 Command Center — Implementation Log

**Date:** 2026-04-07
**Design:** 2026-04-07-sb501000-command-center-design.md
**Tile spec:** 2026-04-07-sb501000-kpi-tile-approved.md
**Worktree:** `.claude/worktrees/funny-tu`
**Branch:** `claude/funny-tu`

## Phase A — Schema + Graph Core (COMPLETE)

Foundation work. No user-visible changes yet. Build verified clean: 0 errors, 0 warnings.

### Files added

1. **`src/StudioB.Containers/DACs/UsrCustomsBroker.cs`** (new)
   BrokerID, BrokerCD, Description, ContactName, Email, Phone, FilerCode, Active, Notes. Standard Acumatica DAC pattern with audit fields.

2. **`src/StudioB.Containers/DACs/UsrContainerETAHistory.cs`** (new)
   Child of `UsrContainer`. Tracks every ETA update with RecordedDate, PreviousETA, NewETA, SlipDays (unbound), Source (MANUAL/XLSX/API/CARRIER), Note.

3. **`src/StudioB.Containers/DACs/UsrContainerDocument.cs`** (new)
   Child of `UsrContainer`. Per-container document checklist. DocumentType (CI/PL/BOL/ISF/ENTRY/CO/FDA/USDA/FCC/INS/OTHER), Required, Status (MISSING/RECEIVED/VERIFIED/REJECTED), ReceivedDate, VerifiedBy, Note, NoteID (for file attachments).

4. **`src/StudioB.Containers/Graphs/ContainerRiskCalculator.cs`** (new)
   Pure C# logic. No PXGraph dependency — unit-testable.
   - `ComputeRiskLevel(today, status, LFD, ETA, ISF, departed, docs, etaChanges, customsHoldDays) → "R"/"A"/"G"`
   - `ComputeDemurrageExposure(today, LFD, rate, holdDays, holdCostPerDay) → decimal`
   - `CustomsHoldDays(today, status, lastSync) → int`
   - Implements the CRITICAL/WARNING thresholds from the design doc.

5. **`src/StudioB.Containers/Graphs/ContainerKPITileBuilder.cs`** (new)
   String-builder for the approved KPI tile HTML. Embeds the complete CSS inline (so the tile row is self-contained and works even if external stylesheet loading is unreliable in Acumatica SaaS). Three tiles — Action, Watch, Exposure — with click handlers that dispatch to `px_alls['frmFilter']` to update `ViewMode` and refresh the grid.

### Files modified

6. **`src/StudioB.Containers/DACs/UsrContainer.cs`** (+172 lines)
   Added fields in an additive block preserving all existing fields:
   - **Milestone timestamps:** BookedDate, DepartedDate, ArrivedPortDate, CustomsReleasedDate, DeliveredDate
   - **Demurrage:** LastFreeDay, DemurrageDailyRate
   - **Routing:** FreightForwarderID (selector), BrokerID (selector)
   - **CBP entry:** EntryNumber, EntryType (01/03/11/23), EntryReleaseDate, DutyPaid, MPFAmount, HMFAmount
   - **ISF:** ISFFiledDate, ISFFilingNbr
   - **Unbound calculated fields** (populated in RowSelected): RiskLevel, DaysToLFD, DemurrageExposure, DocsRequiredCount, DocsReceivedCount

7. **`src/StudioB.Containers/DACs/ContainerFilter.cs`** (full rewrite, +90 lines)
   New fields:
   - `ViewMode` — EXCEPTIONS (default) / WATCH / ARRIVING / ALL
   - **Tile data:** KPIActionCount, KPIActionBreakdown, KPIWatchCount, KPIWatchBreakdown, KPIExposureTotal, KPIExposureBreakdown
   - **Rendered HTML:** KPITilesHtml (for the `PXHtmlView` in SB501000), TimelineHtml
   - **Legacy:** KPIOpen, KPIInTransit, KPIArrivingThisWeek, KPICustomsHold (preserved for backwards compat)

8. **`src/StudioB.Containers/Graphs/ContainerMaint.cs`** (+150 lines)
   - **New views:** `ETAHistory`, `Documents` — children of current container
   - **`containers()` data delegate:** rewritten to support ViewMode filtering (EXCEPTIONS/WATCH/ARRIVING/ALL). Loads all containers once, applies filter in memory (count is small enough to avoid per-row BQL complications). Legacy `StatusFilter` preserved.
   - **`ComputeRiskLevelInline()`** private helper — cheap risk computation at list time (skips doc/ETA-history joins to avoid N queries).
   - **`RowSelected<ContainerFilter>`:** iterates all containers, computes tile data using `ContainerRiskCalculator`, populates legacy KPI fields AND new tile fields AND renders `KPITilesHtml` via `ContainerKPITileBuilder`.
   - **`RowSelected<UsrContainer>`:** extended with per-row risk calc (with full doc/ETA history joins), `DaysToLFD`, `DemurrageExposure`, doc counts. Preserves existing enable/disable logic for `ContainerCD` and `RefreshTracking`.

### Build verification

```bash
$ dotnet build src/StudioB.Containers/StudioB.Containers.csproj
Build succeeded.
    0 Warning(s)
    0 Error(s)
Time Elapsed 00:00:01.95
```

SDK DLLs fetched from `gs://aesthetik-acumatica-sdk/24.208/` per reference_gcs_sdk_bucket.md.

### What Phase A does NOT do yet

- No changes to `SB501000.aspx` — the UI is unchanged, users see the same screen they see today. Phase B/C/D handle the visual work.
- No new actions wired up yet (MarkCustomsCleared, AddPOLink, ImportForwarderXLSX, etc.) — Phase E.
- No customs broker maintenance screen — Phase E.
- No schema migration SQL — Acumatica's `DBSchemaUpdater` will pick up the new DAC fields during the next customization publish and auto-create the columns and tables.
- Risk thresholds are hardcoded in `ContainerRiskCalculator`. Configurable thresholds via `UsrContainerPrefs` are Phase F if needed.

### Verification checklist before pushing

- [x] Clean build (0 errors, 0 warnings)
- [ ] Review the new fields on UsrContainer for attribute correctness (PXDBDate vs PXDBDate(PreserveTime=true), nullable defaults, selector targets)
- [ ] Review `RowSelected<ContainerFilter>` for performance — iterates all containers on every filter refresh; may need optimization if list grows beyond ~1000 rows
- [ ] Confirm the `Accessinfo.BusinessDate` fallback to `DateTime.Today` is correct for HF timezone (America/New_York)
- [ ] Unit tests for `ContainerRiskCalculator` (pending — Phase A deliverable but not yet written)
- [ ] Deploy to Heritage Test → verify no regression on existing SB501000 screen → confirm new columns exist in DB → confirm RowSelected does not error on rows missing new fields

## Phase A tests (COMPLETE)

Created **`tests/dotnet/StudioB.Containers.Tests/`** — a net10.0 xUnit project that links `ContainerRiskCalculator.cs` as a compile-time include (avoiding any Acumatica dependency). 21 tests covering:

- **CRITICAL triggers:** past LFD, customs hold > 2 days, ISF not filed close to departure, docs incomplete with imminent arrival
- **WARNING triggers:** LFD within 3 days, ETA within 7 days, ETA changed 2+ times, docs incomplete far out
- **OK cases:** clean-and-far-out, newly-booked with no dates
- **Priority:** CRITICAL trumps WARNING when both apply
- **Exposure:** zero cases (no LFD, LFD beyond horizon), normal rate accrual, escalation after 7 days past LFD, customs hold additive cost, decimal rounding
- **CustomsHoldDays:** not in hold, no sync date, normal case, future sync floor

Initial run caught an off-by-one bug: my code was escalating demurrage at day 7 past LFD, but the imports-manager convention is "days 1-7 normal, days 8+ escalated." Fixed `ContainerRiskCalculator.ComputeDemurrageExposure` to iterate `d = 1..` (d=0 is LFD itself, never charged) and escalate when `d >= 8`. All tests pass.

```bash
$ dotnet test tests/dotnet/StudioB.Containers.Tests/
Passed!  - Failed: 0, Passed: 21, Skipped: 0, Total: 21
```

## Phase B — Replace KPI Row in SB501000.aspx (COMPLETE)

Changed `Customization/AesthetikContainers/Pages/SB/SB501000.aspx`:

- Removed the four `edKPIOpen` / `edKPIInTransit` / `edKPIArrivingThisWeek` / `edKPICustomsHold` `PXNumberEdit` fields.
- Replaced with a single `PXHtmlView` bound to `Filter.KPITilesHtml`. Height 160px, full width, `SkinID="Label"` (transparent chrome so the tile row reads as content, not a form field).
- Added a hidden `PXDropDown` bound to `Filter.ViewMode` with `CommitChanges="True"`, `display:none` — this is the backing store that the tile click handlers (`sb501000SetViewMode()` JS in the embedded tile HTML) write to. When the user clicks a tile, the JS updates this hidden field and `postData()` triggers a refresh, which re-runs `containers()` with the new `ViewMode`.
- Changed the enclosing `PXFormView` to `CaptionVisible="False"`, `RenderStyle="Simple"`, `SkinID="Transparent"` so the tile row has no form chrome around it.

Build + tests still green after Phase B:

```bash
$ dotnet build src/StudioB.Containers/StudioB.Containers.csproj
Build succeeded. 0 Warning(s) 0 Error(s)

$ dotnet test tests/dotnet/StudioB.Containers.Tests/
Passed!  - Failed: 0, Passed: 21, Skipped: 0, Total: 21
```

ASPX tag balance verified: 74 open tags = 19 close tags + 55 self-closing (delta 0).

### What Phase B does NOT do yet

- Grid still renders the old column layout — risk column + row coloring lands in Phase C.
- Detail form still flat — field grouping lands in Phase D.
- No timeline strip — Phase D.
- No new action buttons wired — Phase E.
- Tab labels still static nouns — Phase D.

After deploy, users will see:
- The four number-box KPIs are **gone**
- A single tile row appears at the top of the screen showing the 3 new tiles (Action / Watch / $ Exposure)
- Clicking a tile filters the grid via `ViewMode`
- Everything below the tiles still looks like the current screen

This is the smallest user-visible change that proves the Phase A graph logic is working end-to-end in production.

## Phase C — Grid risk column + row coloring + operational columns (COMPLETE)

### Files modified

- **`src/StudioB.Containers/DACs/UsrContainer.cs`**: added `DocsSummary` unbound string field — rendered as `"5/8"` or `"—"` in the grid.
- **`src/StudioB.Containers/Graphs/ContainerMaint.cs`**: `RowSelected<UsrContainer>` populates `DocsSummary` based on required/received counts.
- **`src/StudioB.Containers/Graphs/ContainerKPITileBuilder.cs`**: extended the embedded CSS with grid row risk classes (`.risk-r`, `.risk-a`, `.risk-g`) and a colored pill treatment for the `RiskLevel` cell that renders as a `●` circle. Extended the inline JS with `sb501000ApplyRiskRowColors()` — a function that scans grid rows for a cell containing `R`/`A`/`G` and applies the corresponding row class. Runs on a short polling interval after load + on every click within the screen (covering tile clicks, sort, filter, paging without needing to hook Acumatica's internal events).
- **`Customization/AesthetikContainers/Pages/SB/SB501000.aspx`**: added new grid columns — `RiskLevel` (width 30, centered, leftmost), `LastFreeDay` (90), `DaysToLFD` (60, right-aligned), `DocsSummary` (60, centered), `DemurrageExposure` (100, right-aligned). Resized existing columns to fit.

### What users will see

- Leftmost grid column now shows a colored `●` circle per row: red for CRITICAL, amber for WARNING, green for OK. The letter R/A/G is the underlying data but rendered transparent with a pseudo-element overlay.
- CRITICAL rows have a pale red background and a red left-edge shadow. WARNING rows have a pale amber background and amber left-edge shadow. OK rows render normally.
- New columns visible: LFD date, days-to-LFD (negative = past), docs summary, `$` exposure.
- Row colors persist through sort, filter, paging, and tile clicks.

### What Phase C does NOT do

- Detail form is still flat (Phase D).
- No timeline strip (Phase D).
- Tab labels still static nouns (Phase D).
- No new actions (Phase E).
- No Documents or ETA History tabs populated in the UI (Phase E).

Build + tests still green. 21/21 tests passing.

## Phase E — Actions, Documents/ETA History tabs, CustomsBroker screen (COMPLETE)

### New actions in `ContainerMaint`

| Action | Purpose |
|---|---|
| `MarkCustomsCleared` | Stamps `CustomsReleasedDate`, flips status to `GATED_OUT`, writes event row. Prompts for overwrite if already set. |
| `MarkDelivered` | Stamps `DeliveredDate`, flips status to `DELIVERED`, writes event row. |
| `RecordETAUpdate` | Manual ETA history snapshot — useful when the ETA didn't move but the user wants a tracked note. |
| `AttachDocument` | Inserts a `UsrContainerDocument` row the user then fills in via the grid. File attachments via Acumatica's native `NoteID` mechanism. |
| `PrintReceivingDoc` | v1 stub — writes an event row. Real PDF rendering is future work (`PXReportTool.Launch`). |
| `AddPOLink` | Opens the new `pnlAddPOLine` smart panel where the user picks a vendor → open PO → line. Creates a `UsrContainerPOLink` row on OK. |
| `RemovePOLink` | Deletes the currently-selected PO link with confirmation dialog. |

### New smart panel
`pnlAddPOLine` on SB501000 — three cascading `PXSelector`s (Vendor → Order → Line) backed by the new `AddPOLineFilter` DAC. Filters POs by vendor and status (not closed/cancelled). Filters lines by the chosen order.

### New DAC
`AddPOLineFilter` — non-persistent filter for the smart panel. Cascading selectors wired via `Current<>` references.

### Enhanced ContainerStatus constants
Added `Arrived`, `Discharged`, and `GatedOut` as explicit constants on `ContainerStatus` class (they existed in the `UsrContainer.Status` PXStringList but weren't exposed as C# constants).

### New tabs in SB501000 tabDetail

| Tab | Content |
|---|---|
| **Documents** | Grid over `Documents` view (UsrContainerDocument). Columns: DocumentType, Required checkbox, Status, ReceivedDate, Note. Action bar has "Attach Document" button wired to `AttachDocument` action. |
| **ETA History** | Grid over `ETAHistory` view. Columns: RecordedDate, PreviousETA, NewETA, Source, Note. Action bar has "Snapshot Current ETA" button wired to `RecordETAUpdate`. |

### Graph-level toolbar
`CallbackCommands` on the `PXDataSource` extended with all new actions. Visible buttons: `MarkCustomsCleared`, `MarkDelivered`, `PrintReceivingDoc`, `ImportForwarderCSV`. Hidden (triggered from tab action bars): `AddPOLink`, `RemovePOLink`, `AttachDocument`, `RecordETAUpdate`.

### CustomsBroker maintenance screen (SB302040)
- New graph: `CustomsBrokerMaint` (simple `PXGraph<CustomsBrokerMaint, UsrCustomsBroker>`)
- New ASPX: `SB302040.aspx` + `SB302040.aspx.cs`
- Registered in `project.xml`: File entries + SiteMap row at position 8.5 under the container management menu parent.

## Phase F — Forwarder CSV import (COMPLETE)

Pragmatic v1: CSV instead of XLSX. Forwarders already support "Export to Excel → Save as CSV" in one click, and CSV parsing has zero dependencies vs. EPPlus/ClosedXML which aren't in Acumatica's base DLL set.

### New pure-logic class
`ForwarderImportParser` — zero Acumatica dependency, unit-testable. Accepts a CSV string and returns a `ParseResult` with:
- `Rows` — `List<ParsedRow>` with per-row `ParseError` so bad rows don't kill the whole import
- `Errors` — file-level errors (empty file, bad header, no data rows)

Expected header columns: `ContainerNumber, NewETA, NewStatus, EventDate, EventDescription`.

Handles:
- Quoted fields with embedded commas (`"In transit, Hamburg → LA"`)
- Escaped quotes (`""`)
- Windows + Unix line endings
- 9 common date formats (ISO, US M/d/yyyy, 15-Apr-2026, etc.)
- Blank lines skipped
- Rows with extra columns accepted
- Line number preserved in each parsed row for error reporting

### New action
`ImportForwarderCSV` in `ContainerMaint`:
1. Reads the most recent file attached to the `Filter` view via `PXNoteAttribute.GetFileNotes`
2. Loads the file via `PX.SM.UploadFileMaintenance.GetFile`
3. Strips BOM, decodes UTF-8
4. Parses via `ForwarderImportParser.Parse`
5. For each row: matches container by CD, updates ETA (writes history row), updates Status, creates event row if description provided
6. Returns summary dialog: "Updated X containers, added Y events. N container(s) not found: ABC, DEF …"

### Unit tests — 20 new tests, all passing
`ForwarderImportParserTests.cs` covers:
- CSV splitting (simple, quoted with commas, escaped quotes, empty, trailing empty)
- File-level errors (empty, whitespace-only, header-only, too-few columns)
- Happy path (one row, multiple rows, status uppercasing, various date formats)
- Error handling (bad date → per-row error, missing container, blank line skipping, Windows line endings)
- Edge cases (extra columns beyond header, line number preservation)

Initial run caught 1 failure — "header only" case now correctly surfaces a file-level error.

## Phase G — Polish + empty states (COMPLETE)

- Empty states for KPI tiles were already built in Phase A (`ContainerKPITileBuilder` handles `count == 0` with desaturated green accent).
- Row coloring JS has fallback for `risk-g` (OK) rows — they render default background, green circle.
- Timeline strip handles nullable dates, renders `&nbsp;` for unknown stops.
- Unit tests grew from 21 → 41 (added ForwarderImportParser coverage).

### Build state
```
dotnet build src/StudioB.Containers/  →  0 errors, 0 warnings
dotnet test  tests/dotnet/StudioB.Containers.Tests/  →  41/41 passing
ASPX balance — SB501000: delta 0, SB302040: delta 0
```

### Remaining for Phase G after merge
- Heritage Test soak (minimum 2 business days)
- Kevin sign-off before production deploy
- Production deploy (app pool restart)

Those are deployment gates, not code.

Grid risk column + row coloring, timeline strip, grouped detail form, new actions, Documents + ETA History tabs, XLSX forwarder import, stylesheet polish, Heritage Test soak, production promote.
