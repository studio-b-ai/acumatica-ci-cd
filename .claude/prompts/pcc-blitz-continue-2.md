# PCC Weekend Blitz — Continuation 2

## Context
Plan: /Users/kevin/.claude/plans/indexed-stirring-origami.md
Worktree: /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/loving-bell/
Branch: claude/loving-bell (rebase onto origin/main before starting)

## What's deployed to production
- PR #366: PCC bug fixes + 12 IIG date fields (DAC + ASPX)
- PR #367: Swap primary project to AesthetikContainers (for ASPX extraction under --no-merge)
- PR #370: EnsureColumn for 12 new date fields (was crashing SB501000 with "Invalid column name")
- SB501000 now LOADS on production (no more error page)

## Remaining bugs (verified on production via Chrome at 6:23 PM ET 2026-04-11)

### Bug 1: Detail panel does NOT sync when clicking grid rows
**Symptom:** Clicking different containers in the grid does not update the Identity section (Container Nbr, Status, Carrier) or Timeline in the detail panel. Stays stuck on the first container (884786718618).
**What was tried:** PR #366 changed frmTimeline and frmDetail DataMember from "Container" to "Containers" (same as gridContainers). Also added Container.Current = e.Row in RowSelected<UsrContainer> and put frmTimeline in RepaintControlsIDs.
**Root cause hypothesis:** DataMember="Containers" alone may not be enough — Acumatica's SplitContainer / FormDetail master page may need a SyncPosition="true" attribute, or the grid needs to be wired as the "master" control. Check if there's an AutoCallBack or SyncPosition config missing. Compare with a working FormDetail screen (e.g., PO301000) for the correct pattern.
**Files:**
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/loving-bell/Customization/AesthetikContainers/Pages/SB/SB501000.aspx (frmTimeline ~line 88, frmDetail ~line 105, gridContainers)
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/loving-bell/src/StudioB.Containers/Graphs/ContainerMaint.cs (RowSelected<UsrContainer> ~line 889)

### Bug 2: KPI tiles HTML is empty (metrics row invisible)
**Symptom:** htmlKPITiles has innerHTML="" and height=0. The blank space between the tile area and the grid shows the Height=280px took effect, but no content renders.
**What was tried:** PR #366 increased Height from 160px to 280px. The KPITilesHtml field is set in RowSelected<ContainerFilter> via e.Cache.SetValue.
**Root cause hypothesis:** The KPITilesHtml virtual field may not be getting set because RowSelected<ContainerFilter> has an exception or early return. Or the PXHtmlView doesn't render because the field value is null/empty. Check ContainerMaint.cs RowSelected<ContainerFilter> (lines 748-887) for: null checks on Filter.Current, exception swallowing, or the HTML generation code.
**Files:**
- /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/loving-bell/src/StudioB.Containers/Graphs/ContainerMaint.cs (RowSelected<ContainerFilter> ~line 748-887)

### Bug 3: KPI counts all zero (may be correct)
All containers in production are "Delivered" status, so ACTION=0 / WATCH=0 is plausibly correct. Verify by checking if there are any non-Delivered containers (In Transit, Customs Hold) in the data. If all are Delivered, this is not a bug.

## Infrastructure issues (don't block on these)
- Sandbox has pre-existing compilation failure ("customization failed to apply automatically after the upgrade"). Needs manual SM204505 unpublish/republish. Don't waste time trying to deploy to sandbox.
- Playwright web login fails for api-bot/api-test/api-verify on both environments (REST works). Use Chrome (Claude in Chrome) for verification instead.
- The git tag step fails with 403 on deploys — non-critical, doesn't affect the actual deploy.

## Deploy constraints
- Each deploy restarts the production app pool. Real users get disrupted.
- Use force_dispatch_cap=OVERRIDE + skip_sandbox_gate=OVERRIDE + force_qualify=true for production deploys.
- Run `python3 scripts/sync-aspx-cdata.py` after ANY ASPX edit.
- Build DLL: `cd src/StudioB.Containers && dotnet build -c Release && cp bin/Release/net48/StudioB.Containers.dll ../../Customization/AesthetikContainers/Bin/`
  (Note: local build fails due to missing SDK libs — CI runner builds it. Just edit the code and push.)
