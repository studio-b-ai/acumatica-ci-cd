# PCC Post-Deploy — Make It Work For Imports

**Prior session:** 2026-04-11 PCC Implementation (charming-chatelet worktree)
**Outcome:** PCC structural changes deployed to production. Screen loads but is NOT usable — detail panel doesn't sync, metrics row hidden, KPI counts wrong.

## Priority 0: Make SB501000 100% Functional for Imports Team

The imports team manages containers by manually entering data from forwarder emails into Acumatica. IIG was the same manual workflow — carrier API was never automated. PCC must be **better than IIG** as a daily manual-entry tool.

### Bug 1: Detail Panel Doesn't Sync to Selected Row (CRITICAL)

When clicking a different container in the left grid, the right panel (timeline, form, tabs) stays on the first loaded container. This makes the screen completely unusable.

**Root cause:** Grid uses `DataMember="Containers"` (list view with data delegate). Detail form uses `DataMember="Container"` (separate view). Acumatica's `SyncPosition` syncs `Current` on the grid's data member, but the separate `Container` view doesn't receive the update.

**Fix options (investigate in order):**
1. Change `frmTimeline` and `frmDetail` to `DataMember="Containers"` — simplest if it works with the split container
2. Add `Container.Current` sync in graph — set it when `Containers.Current` changes
3. Merge the two views into one

**Partial fix already in worktree (not deployed):** Added `frmTimeline` to `RepaintControlsIDs`. Won't help if `Container.Current` isn't syncing.

**Verify:** Click 3 different containers in the grid. Container Nbr, Status, Timeline, and Events tab must update each time.

### Bug 2: Metrics Row Not Visible

OPEN PO VALUE / CROSS-DOCK RATE / UNCOVERED VALUE renders inside `htmlKPITiles` but the PXHtmlView has `Height="160px"` — the metrics row is below the visible area.

**Fix:** Increase Height to `280px` or move metrics to a separate PXHtmlView.

### Bug 3: KPI Tile Counts Are Wrong

Production has active containers (CNT000026 In Transit, CXDU1525524 + HLBU1391671 + TEMU7301439 Customs Hold). But ACTION shows 0 and WATCH shows 0. The risk calculator should flag Customs Hold containers.

**Investigate:** Step through `ContainerRiskCalculator.ComputeRiskLevel()` with actual container data. May be a field-mapping issue (Status values don't match constants).

### Usability: Validate the Manual Workflow End-to-End

After bugs are fixed, test the full imports manager workflow:

1. **Create new container** — click Add New, enter container number (e.g., TEST000001), set Status=Booked, enter carrier, ETD, ETA, port of loading/discharge
2. **Link POs** — click PO Links tab, Add PO Line, select a real open PO
3. **Update lifecycle** — change status to Departed, then In Transit. Verify timeline updates.
4. **Update ETA** — change ETA date. Verify ETA History tab records the change.
5. **Mark Customs Cleared** — click toolbar button. Verify status changes, event logged.
6. **Mark Delivered** — click toolbar button. Verify container moves to terminal state.
7. **Import CSV** — try Import Forwarder CSV with a sample file. Verify containers update.
8. **Delete test container** — clean up.

If any step fails or is confusing, fix it. The test is: could Melanie do this without asking Kevin?

## Read These First

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/feedback_pcc_is_ops_tool.md`

## What Was Deployed (PRs #357-363)

- 8-stage hybrid PO-lifecycle timeline
- Portfolio metrics row (hidden — Bug 2)
- Lead Time tab (6th tab)
- PLAN NEXT ORDER action button
- SB501200 Supplier Intake shell
- verify.py nested $adHocSchema fix
- Sandbox test timeout 20m→35m

## Reverted: DRP_ItemWarehouseSnapshot GI (#361→#363)

SiteMap circular ref broke publish. Don't re-attempt until Bugs 1-3 are fixed and the manual workflow is validated. Lower priority than screen usability.

## Key Source Files

| File | Purpose |
|------|---------|
| `Customization/AesthetikContainers/Pages/SB/SB501000.aspx` | Screen layout — detail sync is here |
| `src/StudioB.Containers/Graphs/ContainerMaint.cs` | Main graph — Container vs Containers views |
| `src/StudioB.Containers/Graphs/ContainerKPITileBuilder.cs` | KPI HTML + metrics row |
| `src/StudioB.Containers/Graphs/ContainerTimelineBuilder.cs` | Timeline HTML |
| `src/StudioB.Containers/Graphs/ContainerRiskCalculator.cs` | Risk level computation |
| `tests/ui/test_container_tracking.py` | UI tests |

## DLL Build

```bash
cd src/StudioB.Containers && dotnet build -c Release
cp bin/Release/net48/StudioB.Containers.dll ../../Customization/AesthetikContainers/Bin/
```

## Deploy Constraints

- After-hours only (America/New_York) — but weekend is fine
- Run `python3 scripts/sync-aspx-cdata.py` after ANY ASPX edit
- `DataMember` goes on `PXGridLevel`, NOT on `PXGrid` (ASPPARSE error)
- 24h dispatch cap is 20 — may need `force_dispatch_cap=OVERRIDE`

## ASCII Architecture (Save This)

```
┌─────────────────────────────────────────────────────────────────────┐
│ SB501000 — Procurement Command Center (DAILY OPS TOOL)             │
│                                                                     │
│ ┌─KPI Tiles──────────────────────────────────────────────────────┐  │
│ │ ACTION (n)  │  WATCH (n)  │  $ EXPOSURE                       │  │
│ ├─Metrics Row────────────────────────────────────────────────────┤  │
│ │ OPEN PO VALUE  │  CROSS-DOCK RATE  │  UNCOVERED VALUE          │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌─Grid (left)──────────┐ ┌─Detail (right)──────────────────────┐  │
│ │ Container Nbr │Status│ │ ○─○─○─○─○─○─○─● Timeline           │  │
│ │ CNT000026  InTransit │ │ PLACED→ACKED→FACTORY→SHIPPED→...    │  │
│ │ CXDU152... CustHold  │ │                                      │  │
│ │ HLBU139... CustHold  │ │ Identity │ Booking │ Timeline&Ports  │  │
│ │ TEMU730... CustHold  │ │                                      │  │
│ │ ...                  │ │ ┌─Tabs──────────────────────────────┐│  │
│ │ Click → syncs right ▶│ │ │Events│PO Links│Costs│Docs│ETA│Lead││  │
│ └──────────────────────┘ │ └──────────────────────────────────┘│  │
│                           └────────────────────────────────────┘  │
│                                                                     │
│ Toolbar: CREATE LC │ CUSTOMS CLEARED │ DELIVERED │ PLAN NEXT ORDER  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐  ┌──────────────────────┐
│ SB501100 (DEFERRED) │  │ SB501200 — Supplier  │
│ Vendor Planning Hub │  │ Intake (shell)       │
│ → links to WMS when │  │ → links to heritage- │
│   DRP data flows    │  │   wms MOQ intake     │
└─────────────────────┘  └──────────────────────┘

Data flows:
  Acumatica ──OData GIs──▶ heritage-wms DRP pipeline (future)
  Forwarder emails ──manual──▶ PCC (today)
  Carrier API ──webhook-router──▶ PCC (future, needs vendor API)
```
