# DRP Phase 1 — Session 5 (Pipeline Hardening + Next Work Package)

**Prior session ended:** 2026-04-11 ~1:00 AM ET (Session 4)
**Session 4 outcome:** Production deploy succeeded. All 4 OData GIs confirmed 200 after unpublish+republish. Nightly DRP sync cron at 1 AM ET.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_pcc_redesign.md`
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_prod_snapshots.md`
4. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md`
5. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — §7 (SB501000 Revisit)

## Session 4 completed items

| Item | Status |
|---|---|
| Production deploy (run 24272578342) | **Deployed** via force_deploy=OVERRIDE |
| PR #342 — GI field fix + access rights (Accessrights 0→4) | **Merged + deployed** |
| PR #344 — Strip XML comments | **Merged + deployed** |
| PR #346 — Toolbar button wait + timeout fix (AI Recovery) | **Merged** |
| PR #348 — PO301000 navigation test direct ASPX | **Merged** |
| OData DRP_VelocityHistory | **200** — real shipment data |
| OData DRP_OpenSOCommitments | **200** — required unpublish+republish (stale OData cache) |
| OData DRP_OpenPOLines | **200** |
| OData DRP_InventoryBySite | **200** |

---

## Session 5 Track 1: Fix sandbox gate flaky tests

**Decision: keep sandbox gate.** Do NOT remove or make non-blocking. Fix the root causes.

### 1a. Fix `test_container_tracking_navigates_to_sb501000`

This test fails on every sandbox run. Root cause chain:
- `acumatica_screen("PO301000")` navigates via SiteMap
- AesthetikWMS overrides SiteMap entry with ScreenID="PO3010PL"
- SiteMap navigation redirects instead of loading PO form
- PR #348 switched fixture to `acumatica_page` + direct ASPX but the CONTAINER TRACKING button click navigates to error on sandbox

The button click itself is the issue — on sandbox, clicking CONTAINER TRACKING navigates to an error page. Investigate whether SB501000 loads on sandbox (it may be the MUIWorkspace orphan pattern). Options:
1. Mark as `xfail` with clear reason if sandbox SB501000 is genuinely broken
2. Fix the CONTAINER TRACKING action URL if it's pointing wrong
3. Skip when `ACUMATICA_URL` contains `sandbox` (last resort)

### 1b. Fix `--no-merge` permanent verify failures

3 fields fail verify on every run: `PurchaseOrder.UsrExpArrivalDate`, `PurchaseOrder.UsrActArrivalDate`, `PurchaseOrder.UsrContainerRef`. Root cause: `--no-merge` skips ASPX file extraction, so `$adHocSchema` doesn't include custom fields added via ASPX. Options:
1. Downgrade these 3 from `fail` to `warn` in verify.py manifest
2. Fix `--no-merge` root cause (IIG orphan CustProject rows — VAR support ticket pending)
3. Add the fields to verify.py's known-exclusion list

---

## Session 5 Track 2: GCS production snapshot system

**Decision: daily snapshots with GFS (grandfather-father-son) retention.**

### Snapshot schedule

- **Daily:** Take Acumatica customization snapshot via SM204505 API, upload to GCS. Keep last **7 dailies**.
- **Weekly:** The most recent daily that has survived 7 days gets promoted to weekly. Keep last **4 weeklies**.
- **Monthly:** The most recent weekly that has survived 4 weeks gets promoted to monthly. Keep last **12 monthlies**.

### Implementation

1. **GCS bucket:** Create `gs://studiob-acumatica-snapshots/` (or use existing bucket from `reference_gcs_sdk_bucket.md`)
2. **Daily cron:** GitHub Actions scheduled workflow (`0 10 * * *` UTC = 6 AM ET) or Railway cron job
   - Login to Acumatica via REST
   - Call SM204505 export/snapshot API
   - Upload to GCS: `production/{date}/snapshot.zip` + metadata JSON (commit SHA, timestamp, published packages)
   - Prune: delete dailies older than 7 days (but not if promoted to weekly)
3. **Weekly promotion:** Same cron checks if today is Sunday. If so, copy the oldest surviving daily to `production/weekly/{date}/`
4. **Monthly promotion:** Same cron checks if today is 1st of month. Copy oldest surviving weekly to `production/monthly/{date}/`
5. **Pre-deploy snapshot:** Activate the existing `Pre-deploy snapshot` step in `acuops-deploy.yml` (currently `completed skipped`). Upload to `production/pre-deploy/{run_id}/`
6. **Rollback:** Script that downloads from GCS and imports via SM204505 API

### Tag metadata per snapshot

```json
{
  "timestamp": "2026-04-11T10:00:00Z",
  "environment": "production",
  "source": "daily-cron",
  "commit_sha": "f8d48bd",
  "published_packages": ["AesthetikWMS", "AesthetikContainers", "StudioBAcuOps"],
  "retention_tier": "daily",
  "promoted_to": null
}
```

### Must land BEFORE PCC Acumatica refactor

The SB501000/SB501100/SB501200 deploy is high-risk (3 new/modified screens). Having rollback capability in place before that deploy is a prerequisite.

---

## Session 5 Track 3: Design next work package — PCC + heritage-wms harmonization

**CRITICAL CONTEXT — DO NOT DROP.** Kevin's core design intent is a **two-surface procurement system** where Acumatica and heritage-wms show the same data, same KPIs, same language. This is NOT "build one then the other" — it's ensuring complementary views that never contradict each other.

### The Two-Surface Architecture (design doc §7)

| Surface | Role | Users |
|---|---|---|
| **Acumatica** (SB501000/SB501100/SB501200) | PO-centric, existing workflow, container ops, PO approvals | Melanie, Steve, Lauren (daily PO work) |
| **heritage-wms** (heritage-wms-production.up.railway.app) | Vendor-centric, action-oriented, daily DRP review, analytics | Kevin, procurement team (strategic review) |

### Screen-to-Page Mapping

| Acumatica Screen | heritage-wms Page | Shared Data | Acumatica Status | WMS Status |
|---|---|---|---|---|
| **SB501000** Procurement Command Center | `Dashboard.tsx` | Container lifecycle, KPIs | EXISTS (needs refactor) | EXISTS (needs DRP KPI integration) |
| **SB501100** Vendor Planning Hub | `VendorDetail.tsx` + `VendorOverview.tsx` | `drp_*` tables via studiob-api | **NOT BUILT** | **EXISTS** |
| **SB501200** Supplier Intake | `MOQIntake.tsx` + `MOQBulkIntake.tsx` | `drp_vendor_moq_*` tables | **NOT BUILT** | **EXISTS** (service layer remaining) |
| — | `VendorScorecard.tsx` | `drp_vendor_lead_time_stats` | No Acumatica complement | **EXISTS** |
| — | `Recommendations.tsx` | `drp_recommendations` | Feeds SB501100 | **EXISTS** (needs agent output) |

### Harmonization Requirements (the part that keeps getting dropped)

1. **KPI definitions must match** — `Dashboard.tsx` KPIs and SB501000 KPI cards compute from the same source, display the same numbers
2. **Vendor rankings must match** — `VendorOverview.tsx` sort order = SB501100 ranked list sort order (working-capital impact)
3. **Lead time displays must match** — `VendorScorecard.tsx` 4-stage breakdown = SB501000 LEAD TIME tab breakdown
4. **Recommendations flow both ways** — `Recommendations.tsx` review queue feeds SB501100 "what to order next" and vice versa
5. **Plain ops language everywhere** — No trader vocabulary in either surface. "Days of Cover" not "position days", "Cross-Dock Rate" not "turn velocity", "Dead Inventory" not "long tail exposure"

### ASCII Wireframes — Acumatica Screens

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║  PROCUREMENT COMMAND CENTER (SB501000)                          ◄ ► K |K >|   ║
║  ┌─────────────────────┐  ┌─ TOOLBAR ──────────────────────────────────────┐  ║
║  │ Container: CTR-0045 │  │ CREATE LANDED COST │ MARK CUSTOMS │ MARK      │  ║
║  │ Status: IN TRANSIT   │  │ CLEARED           │ DELIVERED   │ IMPORT CSV │  ║
║  │ Forwarder: MSC       │  │ PRINT RECV DOC    │ PLAN NEXT ORDER ← NEW   │  ║
║  └─────────────────────┘  └────────────────────────────────────────────────┘  ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  ┌─ LIFECYCLE TIMELINE (7 stages) ─────────────────────────────────────────┐  ║
║  │                                                                         │  ║
║  │  ●━━━━━●━━━━━●━━━━━●━━━━━◉━━━━━○━━━━━○━━━━━○                          │  ║
║  │  PLACED ACKED FACTORY SHIPPED IN     ARRIVED CUSTOMS DELIVERED          │  ║
║  │  03/01  03/05 READY   04/02  TRANSIT PORT                              │  ║
║  │                03/28          ← NOW                                     │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                                ║
║  ┌─ KPI CARDS (plain ops language) ────────────────────────────────────────┐  ║
║  │                                                                         │  ║
║  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐    │  ║
║  │  │ POSITION         │ │ CROSS-DOCK       │ │ SPECULATION          │    │  ║
║  │  │                  │ │                  │ │                      │    │  ║
║  │  │  $142,380        │ │  34%             │ │  $18,200             │    │  ║
║  │  │  Turns: 4.2      │ │  ▲ 6% vs prev   │ │  Overhang: 3 items   │    │  ║
║  │  │  Dead: 12 items  │ │  month           │ │                      │    │  ║
║  │  └──────────────────┘ └──────────────────┘ └──────────────────────┘    │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
║                                                                                ║
║  ┌─ TABS ──────────────────────────────────────────────────────────────────┐  ║
║  │ [EVENTS] [PO LINKS] [LEAD TIME ←NEW] [COSTS] [DOCUMENTS] [ETA HISTORY]│  ║
║  ├─────────────────────────────────────────────────────────────────────────┤  ║
║  │                                                                         │  ║
║  │  ══ LEAD TIME TAB (new — 4-stage observed breakdown) ══                │  ║
║  │                                                                         │  ║
║  │  PO Lines for Container CTR-0045                                        │  ║
║  │  ┌──────────┬────────┬──────┬──────┬───────┬───────┬───────┬────────┐  │  ║
║  │  │ PO Nbr   │ Item   │ Ack  │Prod  │Transit│Port→  │ Total │ vs p50 │  │  ║
║  │  │          │        │ Lag  │ Days │ Days  │Dock   │ Lead  │        │  │  ║
║  │  ├──────────┼────────┼──────┼──────┼───────┼───────┼───────┼────────┤  │  ║
║  │  │ PO000801 │ 38042  │  4d  │ 27d  │  23d  │  3d   │  57d  │  -9d   │  │  ║
║  │  │ PO000801 │ 39138  │  4d  │ 27d  │  23d  │  3d   │  57d  │  -9d   │  │  ║
║  │  │ PO000803 │ 41205  │  2d  │ 35d  │  —    │  —    │  —    │  —     │  │  ║
║  │  └──────────┴────────┴──────┴──────┴───────┴───────┴───────┴────────┘  │  ║
║  │                                                                         │  ║
║  │  ══ PO LINKS TAB (existing + PLAN NEXT ORDER button) ══                │  ║
║  │                                                                         │  ║
║  │  ┌──────────┬────────┬──────┬──────────┬──────┬──────────────────────┐  │  ║
║  │  │ PO Nbr   │ Vendor │ Qty  │ Promised │ Open │        Actions      │  │  ║
║  │  ├──────────┼────────┼──────┼──────────┼──────┼──────────────────────┤  │  ║
║  │  │ PO000801 │ V00149 │ 500  │ 06/08    │ 500  │ [PLAN NEXT ORDER]   │  │  ║
║  │  │ PO000803 │ V00092 │ 200  │ 05/15    │ 200  │ [PLAN NEXT ORDER]   │  │  ║
║  │  └──────────┴────────┴──────┴──────────┴──────┴──────────────────────┘  │  ║
║  │                          ↓ deep-links to SB501100 filtered by vendor    │  ║
║  └─────────────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════════════════╝


╔══════════════════════════════════════════════════════════════════════════════════╗
║  VENDOR PLANNING HUB (SB501100)                                 ◄ ► K |K >|   ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  Ranked by: Working Capital Impact ▼                    [Filter] [Refresh]     ║
║                                                                                ║
║  ┌────┬──────────────────┬──────────┬────────┬─────────┬──────────┬────────┐  ║
║  │ #  │ Vendor           │ Open PO$ │ Avg LT │ On-Time │ Action   │ Impact │  ║
║  ├────┼──────────────────┼──────────┼────────┼─────────┼──────────┼────────┤  ║
║  │  1 │ D'Decor Exports  │ $24,550  │  66d   │  72%    │ 3 recs   │ $8,200 │  ║
║  │  2 │ Warwick Fabrics  │ $18,300  │  45d   │  88%    │ 1 rec    │ $4,100 │  ║
║  │  3 │ Kravet Inc       │ $12,800  │  12d   │  95%    │ —        │ $1,900 │  ║
║  └────┴──────────────────┴──────────┴────────┴─────────┴──────────┴────────┘  ║
║                                                                                ║
║  ═══ VENDOR DETAIL: D'Decor Exports (V000149) ═══                             ║
║                                                                                ║
║  ┌─ 1. Open POs ──────────────────────────────────────────────────────────┐   ║
║  │  PO000807  500 YDS  $2,455  Promised: 06/08  Status: Open             │   ║
║  │  PO000791  200 YDS  $1,100  Promised: 05/22  Status: Open             │   ║
║  └────────────────────────────────────────────────────────────────────────┘   ║
║  ┌─ 2. Lead Time Analytics ──────────────────────────────────────────────┐   ║
║  │  Ack Lag: p50=4d  │ Production: p50=27d │ Transit: p50=23d │ Total:57d│   ║
║  │  Regime: STABLE since 2026-01-15  │  Bias: -2d (arriving early)       │   ║
║  └────────────────────────────────────────────────────────────────────────┘   ║
║  ┌─ 3. MOQ Summary ─────────────────────────────────────────────────────┐   ║
║  │  12 items with active MOQs  │  Strictness: STRICT                     │   ║
║  │  [Open in Supplier Intake →]  (links to SB501200 / heritage-wms)      │   ║
║  └────────────────────────────────────────────────────────────────────────┘   ║
║  ┌─ 4. Preferred Items ─┐ ┌─ 5. Scorecard ──┐ ┌─ 6. Closures ──────┐      ║
║  │  38042, 39138, 41205  │ │  Quality: A      │ │  CNY: Feb 10-24    │      ║
║  │  44018, 51209         │ │  Fill Rate: 94%  │ │  Diwali: Oct 20-25 │      ║
║  └───────────────────────┘ └──────────────────┘ └────────────────────┘      ║
║  ┌─ 7. Activity Log ────────────────────────────────────────────────────┐   ║
║  │  04/10 — DRP recommended 300 YDS item 38042 (cross-dock candidate)    │   ║
║  │  04/09 — PO000807 placed by Melanie                                    │   ║
║  │  04/05 — Lead time regime stable (n=42 samples)                        │   ║
║  └────────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════════╝


╔══════════════════════════════════════════════════════════════════════════════════╗
║  SUPPLIER INTAKE (SB501200)                                     ◄ ► K |K >|   ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║                                                                                ║
║  ┌────────────────────────────────────────────────────────────────────────┐   ║
║  │                                                                        │   ║
║  │  This screen opens the Heritage WMS MOQ Intake tool.                   │   ║
║  │                                                                        │   ║
║  │  ┌──────────────────────────────────────────────────────────────┐      │   ║
║  │  │  → Open MOQ Intake (single vendor)                          │      │   ║
║  │  │    https://wms.asthetik.com/moq-intake?vendor={VendorID}    │      │   ║
║  │  └──────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                        │   ║
║  │  ┌──────────────────────────────────────────────────────────────┐      │   ║
║  │  │  → Open Bulk MOQ Intake (multiple vendors)                  │      │   ║
║  │  │    https://wms.asthetik.com/moq-bulk                        │      │   ║
║  │  └──────────────────────────────────────────────────────────────┘      │   ║
║  │                                                                        │   ║
║  └────────────────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════════════════╝
```

### ASCII Wireframe — heritage-wms Complement

```
heritage-wms-production.up.railway.app
┌─────────────────────────────────────────────────────────────────┐
│  SIDEBAR              │  CONTENT                                │
│                       │                                         │
│  Dashboard            │  ═══ Vendor Overview ═══                │
│  ──────────           │                                         │
│  Recommendations ←──────── DRP agent daily output               │
│  ──────────           │  Same ranking as SB501100 vendor list   │
│  Vendors              │  Same working-capital-impact sort       │
│    Overview ←────────────→ mirrors SB501100 ranked list         │
│    Scorecard ←───────────→ mirrors SB501000 LEAD TIME tab       │
│    Detail ←──────────────→ mirrors SB501100 vendor detail       │
│  ──────────           │                                         │
│  MOQ Intake ←────────────→ linked from SB501200                 │
│  MOQ Bulk ←──────────────→ linked from SB501200                 │
│  ──────────           │  ═══ KPIs (MUST MATCH SB501000) ═══    │
│  Inventory            │                                         │
│  Receiving            │  Position $  │  Cross-Dock %  │  Dead  │
│  Waves                │  $142,380    │  34%           │  12    │
│  ...                  │  Same numbers as Acumatica KPI cards    │
└───────────────────────┴─────────────────────────────────────────┘
```

### Phase 0 Remaining (7 tasks — feeds into PCC + WMS)

**Group 1 — Data pipeline (enables Phase 1 full signal coverage):**
- P0-D.3: Nightly lead-time mining job
- P0-D.4: Weekly Vendor.LeadTimedays write-back
- P0-A.5: studiob-api gateway routes

**Group 2 — MOQ intake (user-facing, SB501200 + MOQIntake.tsx service layer):**
- P0-C.2: MOQIntake.tsx service + route
- P0-C.3: MOQBulkIntake.tsx orchestrator
- P0-C.4: MOQ write-back to Acumatica

**Group 3 — Email automation (blocked on imports@heritagefabrics.com setup):**
- P0-G.2: po-email-watcher.ts worker
- P0-G.3: studiob-api Ack/FactoryReady writeback

**Group 4 — UI polish:**
- P0-D.5: VendorScorecard.tsx — 4 new lead-time columns

### Phase 0 Completed (17/25 shipped)

| Task | Description | PR |
|---|---|---|
| P0-A.1 | DRP_VelocityHistory GI | acumatica-ci-cd#312 |
| P0-A.2 | DRP_OpenSOCommitments GI | acumatica-ci-cd#312 + #342 |
| P0-A.3 | DRP_OpenPOLines GI | acumatica-ci-cd#312 |
| P0-A.4 | DRP_InventoryBySite GI | acumatica-ci-cd#312 |
| P0-B.1 | POOrder.UsrAcknowledgedDate + UsrFactoryReadyDate | acumatica-ci-cd#311 |
| P0-C.1 | drp_vendor_moq_* migrations | aesthetik-platform#104 |
| P0-D.1 | drp_lead_time_* migrations | aesthetik-platform#105 |
| P0-D.2 | Lead-time learner service (49 tests) | aesthetik-platform#109 |
| P0-E.1 | drp_abc_* migrations + seed | aesthetik-platform#106 |
| P0-E.2 | ABC classifier service + initial run | aesthetik-platform |
| P0-E.3 | Write-back StockItem.ABCCode | aesthetik-platform |
| P0-F.1.a | drp_lost_demand_events table | aesthetik-platform#107 |
| P0-F.1.b | heritage-wms receiver endpoint | aesthetik-platform#108 |
| P0-F.1.c | cs-order-entry emitter | cs-order-entry#8 |
| P0-G.1 | Email tables (drp_signal_email_*) | webhook-router#68 |
| P0-I.1 | drp_agent_runs table | aesthetik-platform#102 |
| P0-I.2 | drp_phase_config singleton | aesthetik-platform#103 |

| Deferred | Reason |
|---|---|
| P0-H.1 DLM policies | Cross-DB capture not in DLM architecture |

---

## Deferred to future session

- Confirm nightly DRP sync succeeded (check `drp_agent_runs` table after 1 AM ET)
- Verify staff access: Melanie/Steve/Lauren on SB501000, Sarah on PO302000

## Repos in play

- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` — heritage-wms React + Express + Postgres
- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` — Acumatica customization packages
- `studiob-api` — Python FastAPI gateway (DRP routes)
- `webhook-router` — Email watcher, Slack integration
- `cs-order-entry` — Lost demand emitter

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).

## What's NOT in scope for Session 5

- Phase 2/3 implementation
- Exogenous signals (HubSpot, Shopify)
- Accuracy tracking
