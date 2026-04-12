# PCC Layout Redesign — Implementation

## Context
Design doc: /Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-11-pcc-layout-redesign.md
Worktree: /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/
Branch: claude/wonderful-kalam (rebase onto origin/main before starting)

## What's deployed to production (as of 2026-04-11 7:15 PM ET)
- PRs #366, #367, #370, #371, #372, #373 all merged
- SB501000 loads, detail panel syncs on row click, KPI tiles + metrics row visible
- All containers currently "Delivered" — no active risk items

## What this session should do
Implement the approved PCC layout redesign. Use the `writing-plans` skill to create an implementation plan from the design doc, then execute it. The design covers 5 areas:

### 1. Layout — Remove SplitContainer, go stacked
- Remove `PXSplitContainer` from SB501000.aspx
- Move command bar (timeline + summary) into phF below frmFilter
- Grid goes full-width in phG
- frmDetail + tabDetail move into a PXSmartPanel (right-anchored via CSS)
- Double-click grid row → `OpenContainerDetail` action → `Container.AskExt()`

### 2. KPI Tiles — Replace ACTION/WATCH/EXPOSURE
- Tile 1: LATE (containers with any overdue date — factory, ETA, LFD, customs)
- Tile 2: AT RISK $ (dollars actively accruing — demurrage, customs hold cost)
- Tile 3: PIPELINE (stage counts: Booked N, In Transit N, At Port N, Customs N)
- Rebuild `ContainerKPITileBuilder.Build()` and `KPIData` struct

### 3. Timeline — Promised vs actual dates, color thresholds
- Show Factory Promised and Factory Actual dates side by side
- Green = complete, Gray = future, Yellow = within 5 days of due, Red = past due
- Update `ContainerTimelineBuilder.Build()` and `TimelineData` struct

### 4. Cross-Dock Rate — Yard-based
- Replace container count with `MIN(PO OrderQty, SUM(open SO OrderQty))` per InventoryID
- MetricsData: replace `int ContainersWithSO` with `decimal CrossDockedYards` + `decimal TotalYards`
- Display: `74% (18,400 OF 24,800 YDS)`

### 5. New DAC fields
- `MillAckDate` (DateTime) — when mill acknowledged the PO
- `FactoryPromisedDate` (Date) — mill's promised ready date
- `FactoryActualDate` (Date) — when goods were actually ready
- Add to `UsrContainer.cs` DAC + EnsureColumn in install graph

## Key files
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/Customization/AesthetikContainers/Pages/SB/SB501000.aspx
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/Graphs/ContainerMaint.cs (1139 lines)
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/Graphs/ContainerKPITileBuilder.cs
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/Graphs/ContainerTimelineBuilder.cs
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/Graphs/ContainerRiskCalculator.cs
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/DACs/UsrContainer.cs
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/wonderful-kalam/src/StudioB.Containers/DACs/ContainerFilter.cs

## Deploy constraints
- Each deploy restarts the production app pool. Real users get disrupted.
- Weekend window is open — deploy Sunday evening ET.
- Use force_dispatch_cap=OVERRIDE + skip_sandbox_gate=OVERRIDE + force_qualify=true
- Run `python3 scripts/sync-aspx-cdata.py` after ANY ASPX edit
- Local build fails (missing SDK libs) — CI runner builds it. Just edit and push.
- Git tag step fails with 403 — non-critical, doesn't affect deploy.
- Sandbox has pre-existing compilation failure — don't waste time on sandbox.

## Verification
- Use Chrome MCP (Claude in Chrome) against production after deploy
- Production URL: heritagefabrics.acumatica.com, screen SB501000
- Test: single-click updates command bar, double-click opens slide-out panel
- Test: metrics row shows yard-based cross-dock rate
- Test: KPI tiles show LATE/AT RISK/PIPELINE instead of ACTION/WATCH/EXPOSURE
