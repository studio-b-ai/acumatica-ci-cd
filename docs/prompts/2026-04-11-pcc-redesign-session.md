# PCC Redesign — Procurement Command Center + Heritage WMS

**Prior session:** 2026-04-11 Session 5 (sandbox reliability)
**Session 5 outcome:** PR #353 — PO3010PL fix, --no-merge suppression, sandbox entity sync. Ready for merge.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md`

## Context

Kevin confirmed PCC is critical and in scope — not deferred. The sandbox reliability work (PR #353) directly enables PCC:
- PO3010PL→PO301000 fix means SiteMap navigation works for PO deep-links
- --no-merge suppression needs expanding when PCC adds SB501100/SB501200 ASPX
- Sandbox entity sync gives PCC screens real data during testing

## PCC Scope (from memory/project_pcc_redesign.md)

**SB501000 — Procurement Command Center (refactor of Container Maintenance):**
1. Rename SiteMap title → "Procurement Command Center"
2. 7-stage lifecycle timeline: PLACED → ACKED → FACTORY READY → SHIPPED → IN TRANSIT → ARRIVED PORT → CUSTOMS → DELIVERED
3. New LEAD TIME tab (6th) — per-container PO lines with 4-stage breakdown
4. Upgrade EXPOSURE KPI card — cross-reference drp_recommendations + drp_lead_time_distributions
5. PLAN NEXT ORDER action on PO LINKS → deep-link to SB501100
6. KPI retheme (plain ops language): POSITION/CROSS-DOCK/SPECULATION
7. Keep untouched: COSTS tab, DOCUMENTS tab, ETA HISTORY tab, action ribbon

**SB501100 — Vendor Planning Hub (new screen):**
- Vendor ranked list + 7-section detail

**SB501200 — Supplier Intake (new screen):**
- External link to heritage-wms MOQ intake

**Heritage WMS web companion:**
- heritage-wms Vendors section (aesthetik-platform PR #117) — web-first, ships first
- Acumatica screens follow when after-hours deploy window allows

## Prerequisites before starting

1. Merge PR #353 (sandbox reliability) — unblocks pipeline
2. Confirm sandbox-gate passes after merge
3. Read the locked design doc for PCC sections (§7.1-7.3) — locate in aesthetik-platform or acumatica-ci-cd docs

## Repos in play

- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` (Acumatica screens)
- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` (heritage-wms web app)

## Deploy constraints

- All three Acumatica screens require after-hours deploy (app pool restart)
- heritage-wms (Railway) can deploy anytime
- Web-first: heritage-wms Vendors ships before Acumatica PCC

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).

## What's NOT in scope

- Phase 2 DRP implementation
- Exogenous signals (HubSpot, Shopify)
- Accuracy tracking
