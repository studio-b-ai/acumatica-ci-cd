# SB501000 Procurement Command Center — Refinements

## Current State

SB501000 is live on production (deployed 2026-04-06). The screen loads with:
- KPI cards (Open, In Transit, Arriving This Week, Customs Hold)
- PXSplitContainer with container grid on left, detail panel on right
- Events and PO Links tabs in the detail panel
- FormDetail.master (fixed from TabView.master in PR #221)
- StudioB.Containers.dll (compiled DLL pattern, not CDATA)

The SiteMap title still says "Container Maintenance" — the ASPX title says "Procurement Command Center" but the navigation menu shows the SiteMap value.

## What Needs User Feedback

The screen was deployed without iteration. These areas need feedback from Kevin and Heritage Fabrics staff:

1. **KPI cards** — Are the four categories (Open, In Transit, Arriving This Week, Customs Hold) the right ones? Are the counts correct against real data?

2. **Grid columns** — Are the right fields shown in the list view? Is the sort order (ETA ascending) useful?

3. **Detail panel** — Are the editable fields in the right layout? Is anything missing that warehouse staff need?

4. **Events tab** — Is the tracking event data showing correctly? Are the columns useful?

5. **PO Links tab** — Can staff link POs to containers? Does the selector work?

6. **SiteMap title** — Should it say "Container Maintenance" or "Procurement Command Center" in the nav menu? (One-line change in project.xml ScreenWithRights section)

7. **Status color-coding** — The design called for color-coding container status in the grid (red for CUSTOMS_HOLD, green for DELIVERED, etc.). Was this implemented or still needed?

## Design Docs

- Design: `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-05-procurement-command-center-design.md`
- Implementation plan: `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-05-procurement-command-center-impl.md`

## Key Files

- ASPX: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Pages/SB/SB501000.aspx`
- Graph: `/Users/kevin/dev/acumatica-ci-cd/src/StudioB.Containers/Graphs/ContainerMaint.cs`
- Filter DAC: `/Users/kevin/dev/acumatica-ci-cd/src/StudioB.Containers/DACs/ContainerFilter.cs`
- project.xml CDATA: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (line ~169)
- SiteMap title: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` (search for `Title="Container Maintenance"` in ScreenWithRights section)

## How to Iterate

1. Collect feedback (Kevin + staff using the screen)
2. Make changes to .cs files and/or ASPX
3. Rebuild DLL: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
4. Copy DLL: `cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/`
5. PR → merge → pipeline deploys automatically

## Known Issue

The ASPX import may not overwrite existing files on the Acumatica instance (see `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/aspx-import-overwrite-investigation.md`). If ASPX changes don't take effect after deploy, delete the file from SM204505 and redeploy.
