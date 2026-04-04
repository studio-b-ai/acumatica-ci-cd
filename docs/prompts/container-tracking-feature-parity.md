# Container Tracking Feature Parity — IIG Replacement

## Context

Read the full gap analysis at:
`/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-04-container-tracking-gap-analysis.md`

On 2026-04-03, we unpublished the IIG Container Management ISV and cleaned up all IGCM artifacts (GIs, SiteMap entries, preferences) via CleanupIGCMArtifacts() in the AesthetikContainers CustomizationPlugin. PRs #154-159 in acumatica-ci-cd, PRs #2-3 in acuops-pipeline.

AesthetikContainers has the data layer (DACs, extensions, DDL) but is missing 10 of 15 user-facing screens that IIG provided. The Container Tracking workspace currently only has SB501000 (Container Maintenance).

## Goal

Build GIs and screens to reach feature parity with IIG. Our container tracking must be equal or better.

## Phase 1 — Critical UI Screens (priority order)

1. **PO Containers GI** — Browse active containers, ETAs, delays. GI on UsrContainer + linked PO counts.
2. **SO Containers GI** — Outbound shipment container visibility. GI on SOShipment + ShipmentExt.
3. **Container Events GI** — Tracking event timeline. GI on UsrContainerEvent.
4. **Freight Forwarders** — Carrier master + API config. New DAC + ASPX form.
5. **Custom Classification** — HTS codes, tariff rules. StockItemExt exists, needs UI.

## Phase 2 — Webhook Integration

- Create container-event-worker in webhook-router (BullMQ)
- Normalize carrier event codes (Seatrates/FedEx/UPS -> standard schema)
- Wire RefreshTracking action on SB501000 to trigger worker
- Auto-propagate ETA/ATA to linked POs via ContainerDatePropagation

## Phase 3 — Master Data & Analytics

- Container Types (20ft, 40ft, HC)
- Destinations/Ports (UN/LOCODE)
- Container Management Preferences
- PO Container Lines detail GI

## Key Files

| File | Repo | Purpose |
|------|------|---------|
| `Customization/AesthetikContainers/project.xml` | acumatica-ci-cd | All DACs, graphs, ASPX, CustomizationPlugin |
| `instance-manifest.json` | acumatica-ci-cd | ISV registry (IIG entries still listed as published) |
| `scripts/heritage/gi_builder.py` | acumatica-ci-cd | GI Builder tool for creating GIs via SQL |
| `tests/ui/test_container_tracking.py` | acumatica-ci-cd | 27 Playwright tests verifying IIG removal |

## Constraints

- GIs can be built via gi_builder.py (generates SQL with REVIEWED marker)
- ASPX screens go in project.xml as `<File>` elements
- New DACs go in project.xml as `<Graph>` elements with inline C#
- All changes deploy through the AcuOps pipeline (branch -> PR -> merge -> auto-deploy)
- After-hours deploys only (publishes restart app pool)
- Read `memory/context/lessons-learned.md` before touching project.xml
