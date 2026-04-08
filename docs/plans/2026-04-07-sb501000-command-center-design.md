# SB501000 Procurement Command Center — Full Redesign

**Date:** 2026-04-07
**Status:** Approved (design + tile layout greenlit 2026-04-07)
**Repo:** acumatica-ci-cd
**Scope:** HF's own imports only. 3PL containers are explicitly out of scope (see 2026-04-07-aesthetikwms-multitenancy-design.md).
**Related prior work:** PR #232 (Bucket B Phase 1 — Container Costs tab), PR #234 (Phase 3 — AP invoice linking + receipt line backfill)

## Context

SB501000 today is functional but presents container state neutrally rather than leading with what requires action. Compared to IIG's `IGCM3098`, our screen is structurally simpler but less useful — imports manager cannot answer "what needs my attention today" without scanning the full list. Gap analysis against an experienced imports manager workflow identified 10+ missing features that are on the critical path for operational value.

This design scopes the UX and data additions needed to make SB501000 the single operational surface for HF's imports workflow — exception-first, financial-exposure-visible, action-reachable — without contaminating it with 3PL concerns.

## Goals

1. Imports manager sees what needs attention and what it will cost within 5 seconds of page load.
2. Every common daily action is reachable from SB501000 without navigating away.
3. Financial exposure (demurrage, unbilled LC, ETA slippage) is the primary success metric for the tool.
4. Field grouping and visual hierarchy match operational priorities, not database structure.

## Non-goals

- 3PL customer containers (handled in AesthetikWMS multi-tenancy work).
- Carrier API integration (Project44, Searates, VesselFinder) — XLSX import from forwarder covers v1.
- Mobile responsiveness — imports manager works from a desk.
- Replacing or theming Acumatica master page chrome.

## Design north star

**Aesthetic direction:** Airport ramp control tower. High-contrast, information-dense, status-colored, no decoration. The screen's memorable moment is the KPI tile row showing "what needs action" and "$ at risk" at the top — every other Acumatica screen opens to a grid, this one opens to a to-do list with money attached.

## Schema additions

All additive, non-breaking. Default values preserve existing behavior.

### New fields on `UsrContainer`

| Field | Type | Purpose |
|---|---|---|
| `BookedDate` | DateTime, null | Booking confirmation timestamp |
| `DepartedDate` | DateTime, null | Origin port departure |
| `ArrivedPortDate` | DateTime, null | Destination port arrival |
| `CustomsReleasedDate` | DateTime, null | CBP release timestamp |
| `DeliveredDate` | DateTime, null | Final warehouse delivery |
| `LastFreeDay` | DateTime, null | Port free-time cutoff |
| `DemurrageDailyRate` | Decimal(10,2), null | $/day after LFD passes |
| `FreightForwarderID` | int, null | FK to `UsrFreightForwarder` |
| `BrokerID` | int, null | FK to new `UsrCustomsBroker` |
| `EntryNumber` | string(20), null | CBP entry number |
| `EntryType` | string(2), null | Entry type code (01/03/11/etc.) |
| `EntryReleaseDate` | DateTime, null | Entry released by CBP |
| `DutyPaid` | Decimal(12,2), null | Entry summary duty |
| `MPFAmount` | Decimal(10,2), null | Merchandise processing fee |
| `HMFAmount` | Decimal(10,2), null | Harbor maintenance fee |
| `ISFFiledDate` | DateTime, null | ISF 10+2 filing timestamp |
| `ISFFilingNbr` | string(20), null | ISF reference |
| `RiskLevel` | string(1), unbound | CRITICAL / WARNING / OK — computed at RowSelected |
| `DaysToLFD` | int, unbound | Computed for sort/filter |
| `DemurrageExposure` | Decimal(12,2), unbound | Projected $ exposure |

### New child table `UsrContainerETAHistory`

Tracks every ETA update for audit and "forwarder is lying" detection.

| Field | Type |
|---|---|
| `ETAHistoryID` | int identity PK |
| `ContainerID` | int FK |
| `RecordedDate` | DateTime |
| `PreviousETA` | DateTime, null |
| `NewETA` | DateTime |
| `Source` | string(10) — MANUAL / XLSX / API |
| `Note` | string(255) |

### New child table `UsrContainerDocument`

Per-container document checklist with file attachments.

| Field | Type |
|---|---|
| `DocumentID` | int identity PK |
| `ContainerID` | int FK |
| `DocumentType` | string(10) — CI / PL / BOL / ISF / 7501 / CO / FDA / USDA / FCC / OTHER |
| `Required` | bool |
| `Status` | string(10) — MISSING / RECEIVED / VERIFIED |
| `ReceivedDate` | DateTime, null |
| `NoteID` | Guid, null — Acumatica file attachment key |

### New root table `UsrCustomsBroker`

| Field | Type |
|---|---|
| `BrokerID` | int identity PK |
| `BrokerCD` | string(15), unique |
| `Description` | string(60) |
| `ContactName` | string(60) |
| `ContactEmail` | string(100) |
| `ContactPhone` | string(20) |
| `Active` | bool |
| `Notes` | string(255) |

## Graph additions (`ContainerMaint`)

### New views
- `ETAHistory` — child of current container, ordered by RecordedDate DESC
- `Documents` — child of current container
- `Exceptions` — virtual view returning CRITICAL containers
- `WatchList` — virtual view returning WARNING containers
- `ArrivingSevenDays` — ETA in next 7 days, not delivered

### New KPI fields on `ContainerFilter`
- `KPIActionCount` (int) — CRITICAL container count
- `KPIWatchCount` (int) — WARNING container count
- `KPIExposureTotal` (decimal) — sum of DemurrageExposure for CRITICAL+WARNING
- `KPIActionBreakdown` (string) — "• 2 PAST LFD · $450/DAY\n• 4 CUSTOMS HOLD > 2D\n• 2 ISF CUTOFF < 6H"
- `KPIWatchBreakdown` (string)
- `KPIExposureBreakdown` (string)
- `KPITilesHtml` (string) — rendered HTML for `PXHtmlView`
- `ViewMode` (string) — EXCEPTIONS / WATCH / ARRIVING / ALL — current filter

### New actions
- `ImportForwarderXLSX` — file picker, parse, update ETAs + history + events
- `MarkCustomsCleared` — sets CustomsReleasedDate, adds event
- `MarkDelivered` — sets DeliveredDate, adds event
- `AttachDocument` — file picker, creates UsrContainerDocument
- `AddPOLink` — opens PO selector panel
- `RemovePOLink`
- `PrintReceivingDoc`
- `RecordETAUpdate` — manual ETA change with history row

### Risk level computation (RowSelected<UsrContainer>)

**CRITICAL if any of:**
- `LastFreeDay < today` (past free time)
- `Status = CUSTOMS_HOLD` AND CustomsHoldDays > 2
- `ISFFiledDate IS NULL` AND `DepartedDate IS NULL` AND estimated departure < today + 1 day
- Required documents incomplete AND ETA < today + 3 days

**WARNING if any of (and not CRITICAL):**
- `LastFreeDay < today + 3 days`
- `ETA < today + 7 days`
- ETA changed more than once in last 7 days
- Required documents incomplete

**OK otherwise.**

### Exposure computation

```
DemurrageExposure = max(0, today - LastFreeDay) * DemurrageDailyRate
                  + max(0, today - (LastFreeDay + 7)) * (DemurrageDailyRate * 1.5)  // escalation
                  + (CustomsHoldDays > 2 ? EstimatedHoldCostPerDay * CustomsHoldDays : 0)
```

Configurable escalation multiplier lives on `UsrContainerPrefs`.

## ASPX rewrite

Full rewrite of `SB501000.aspx` with stacked layout:

1. **KPI tile row** — `PXFormView` with `PXHtmlView` bound to `KPITilesHtml`
2. **View selector tab bar** — `PXTab` with 4 tabs, labels bound to count fields
3. **Container grid** — full width, risk column, row CssClass binding
4. **Detail form** — `PXFormView` with three `PXLayoutRule StartGroup` blocks + action button bar
5. **Timeline strip** — `PXHtmlView` bound to server-computed milestone HTML
6. **Detail tabs** — `PXTab` with 5 tabs, labels with counts, each filling the full width below

See 2026-04-07-sb501000-kpi-tile-approved.md for the approved tile spec.

## Custom CSS

`Customization/AesthetikContainers/Stylesheets/sb501000.css` — ~60 lines total. Declares the 5-color token palette, tile classes, grid row risk classes, timeline cell classes. Injected via customization-embedded stylesheet link (needs to be verified working in Acumatica SaaS — may require alternate injection via master page hook if customization stylesheet loading is not supported).

## XLSX forwarder import

Button in toolbar → file upload → EPPlus parser → updates for each row:
- `ContainerNumber` (required) — match by ContainerCD
- `NewETA` — updates `ETA`, writes ETAHistory row
- `NewStatus` — updates `Status`
- `EventDate`, `EventDescription` — writes event row

Returns summary: "Updated N containers, added M events, K not found."

Column mapping hardcoded v1. Per-forwarder profiles in v2.

## Phases

| Phase | Scope | Est. | Deployable independently |
|---|---|---|---|
| A | Schema + DACs + new graph views/fields (no UI) | 1 day | Yes |
| B | KPI tile HTML generation + ContainerFilter KPI computation | 0.5 day | Yes |
| C | ASPX rewrite — layout restructure, grid risk column, row coloring | 1 day | Yes |
| D | Timeline PXHtmlView + grouped detail form + tab count bindings | 1 day | Yes |
| E | New actions (MarkCleared, AddPOLink, etc.) + Documents tab + ETA History tab | 1 day | Yes |
| F | XLSX forwarder import | 1 day | Yes |
| G | Stylesheet polish, empty states, Heritage Test soak, production promote | 0.5 day | Gated on soak |

**Total: ~6 days** focused work.

Each phase deploys independently to Heritage Test first, then Heritage Fabrics production. Every deploy restarts the app pool — bundle where practical.

## Testing

### Automated
- Unit tests for `RiskLevel` and `DemurrageExposure` calculation (pure C#, no Acumatica dep)
- Integration test: create container → backfill from events → verify timeline renders
- Integration test: XLSX import 10 containers → verify ETA history + events
- CI pipeline build + publish to stage validates the customization project

### Manual verification in Heritage Test
- Load SB501000 as prod user, confirm no existing data broken
- Spot-check 5 real containers for risk level accuracy
- Verify tile click filters grid correctly
- Verify empty states
- Run full `python3 verify.py` before promoting to prod

### Soak
- Minimum 2 business days in Heritage Test before promotion
- Sign-off required from Kevin before prod deploy

## Risks

| Risk | Mitigation |
|---|---|
| Risk level thresholds opinionated | Configurable on `UsrContainerPrefs` |
| `PXHtmlView` approach for tiles/timeline fragile | Fallback: `.ascx` user control if HTML grows beyond ~50 lines |
| App pool restart impact | Bundle phases into fewer PRs where possible |
| File storage growth from Documents tab | Purge policy for containers delivered > 1 year |
| Customization stylesheet loading in SaaS | Verify in Heritage Test first; fallback to inline style in `PXHtmlView` strings |

## Open questions

1. Should `DemurrageDailyRate` default from `UsrFreightForwarder` or be per-container? **Decision: forwarder default, per-container override.**
2. Should document requirements be template-driven (per vendor, per HTS) or manual per container? **Decision: manual v1, template-driven in v2.**
3. Who populates `LastFreeDay`? **Decision: manual entry v1, XLSX import populates going forward.**

## Implementation file list

- `docs/plans/2026-04-07-sb501000-command-center-design.md` (this file)
- `docs/plans/2026-04-07-sb501000-kpi-tile-approved.md` (approved tile spec)
- `docs/plans/2026-04-07-sb501000-command-center-impl.md` (impl log, created during implementation)
- `Customization/AesthetikContainers/DBSchema/20260407_sb501000_command_center.sql` (schema migration)
- `src/StudioB.Containers/DACs/UsrContainer.cs` (new fields)
- `src/StudioB.Containers/DACs/UsrContainerETAHistory.cs` (new)
- `src/StudioB.Containers/DACs/UsrContainerDocument.cs` (new)
- `src/StudioB.Containers/DACs/UsrCustomsBroker.cs` (new)
- `src/StudioB.Containers/DACs/ContainerFilter.cs` (new KPI fields)
- `src/StudioB.Containers/Graphs/ContainerMaint.cs` (new views, actions, RowSelected logic)
- `src/StudioB.Containers/Graphs/CustomsBrokerMaint.cs` (new)
- `Customization/AesthetikContainers/Pages/SB/SB501000.aspx` (full rewrite)
- `Customization/AesthetikContainers/Pages/SB/SB501000.aspx.cs` (unchanged — stays minimal)
- `Customization/AesthetikContainers/Pages/SB/SB302040.aspx` (new — CustomsBroker maintenance)
- `Customization/AesthetikContainers/Stylesheets/sb501000.css` (new, ~60 lines)
