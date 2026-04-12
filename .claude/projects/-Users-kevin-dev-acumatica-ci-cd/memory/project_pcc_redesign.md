---
name: PCC SB501000 Layout Redesign
description: PCC layout redesign shipped 2026-04-11 — stacked grid, SmartPanel slide-out, LATE/AT RISK/PIPELINE tiles, yard-based cross-dock
type: project
---

**Status:** DEPLOYED + VERIFIED (2026-04-11)

PRs #375 (main redesign) + #378 (AfterRowDblClick fix) merged and published to production.

**What shipped:**
- Stacked full-width grid (PXSplitContainer removed)
- PXSmartPanel slide-out detail panel (LinkCommand on ContainerCD)
- KPI tiles: LATE / AT RISK $ / PIPELINE (replaced ACTION/WATCH/EXPOSURE)
- Yard-based cross-dock rate: MIN(PO qty, SUM(open SO qty)) per InventoryID
- Timeline: promised vs actual factory dates, yellow/red color thresholds
- New DAC fields: MillAckDate, FactoryPromisedDate, FactoryActualDate

**Incident during deploy:** `AfterRowDblClick` is not a valid PXGrid ClientEvents property. Fix: use `LinkCommand` on grid column instead. KB entry ingested.
