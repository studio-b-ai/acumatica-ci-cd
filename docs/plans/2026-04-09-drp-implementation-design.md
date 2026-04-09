# Heritage Fabrics DRP Implementation — Design Doc

**Date:** 2026-04-09
**Status:** LOCKED — design complete, ready for Phase 0 implementation
**Author:** Claude (procurement-manager lens) + Kevin
**Supersedes:** `docs/plans/2026-04-09-drp-current-state-and-approaches.md`

---

## 0. Strategic Philosophy

**The name of the game is to hold the least amount of inventory and do as much cross-docking as possible.** Heritage Fabrics doesn't win by maintaining shelves full of goods; we win by turning capital into fabric into customer deliveries with minimum dwell time in between.

This reframes the DRP objective function entirely:

**Old frame (standard retail DRP):** Maximize service level subject to cost constraints.
**HF frame:** Minimize inventory dollar-days subject to committed-demand fill rate ≥ 98%, speculative fill rate ≥ 90%.

Every design decision downstream flows from this inversion. Safety stock becomes a floor to stay above, not a target to optimize toward. Reorder points become minimum viable positions, not buy triggers. The primary trigger for a PO is committed demand (an open SO) arriving without matching supply, not an inventory level hitting a threshold. ROP and MaxQty exist to keep the minimum floor healthy; they don't drive the ordering rhythm.

The agent thinks like a trader (backtest everything, attribute P&L, respect position limits, minimize capital locked) but the staff-facing UI uses plain ops vocabulary. No one in procurement sees "long position" or "book limit" — they see "Days of Cover," "Cross-Dock Rate," "Dead Inventory."

---

## 1. Current-State Diagnosis

### 1.1 Reorder-point coverage gap (item-warehouse level)

| Scope | Items | RP Set | SS Set | Method = Min/Max |
|---|---:|---:|---:|---:|
| Main warehouse (WH 99) | 2,164 | 1,226 (57%) | 1,224 (57%) | 1,293 (60%) |
| All real warehouses | 2,298 | 1,327 (58%) | 1,325 (58%) | 1,401 (61%) |
| Including SAMPLES | 4,341 | 1,327 (31%) | 1,325 (31%) | 1,401 (32%) |

- **888 items in WH 99 are purchased but have NO reorder point.**
- **0 of 4,341 rows have `OverrideReplenishmentSettings=true`** — nobody has ever tuned per warehouse.
- Reorder-point distribution on the 1,226 items that DO have them shows round-number clustering (100, 200, 250, 500) — the signature of manual entry, not calculation.

### 1.2 The replenishment-source mismatch (biggest finding)

| ReplenishmentSource | Count | % |
|---|---:|---:|
| **Purchase** (stock replenishment) | 2,223 | **99.9%** |
| **Purchase to Order** (direct to SO) | **1** | **0.05%** |
| Transfer / None | 39 | 2% |

HF's stated strategy is cross-docking. HF's Acumatica configuration is 99.9% stock-purchase. **These are incompatible.** Moving items from Purchase → Purchase-to-Order where appropriate could free a meaningful fraction of working capital without any forecast improvement. This is the single largest Phase 0 configuration change.

### 1.3 Vendor lead time — the root cause for why reorder points were manual

| Metric | Value |
|---|---:|
| Total vendors | 594 |
| Active vendors | 296 |
| **Vendors with `LeadTimedays > 0`** | **15 / 594 (2.5%)** |
| Vendors with `VendorClass = "TBD"` | 435 (73%) |
| Lead-time median (of the 15 populated) | 60 days |

Acumatica's built-in replenishment calculator (`IN508500`) uses lead time in its safety-stock formula. Without lead times on 98% of vendors, the calculator is mathematically disabled — which is exactly why the 1,327 existing reorder points had to be entered manually.

### 1.4 Item taxonomy (2,242 real DRP-eligible items)

| Class | Count | Procurement cycle |
|---|---:|---|
| SAMPLES | 1,961 | Exclude (not replenishable) |
| **COO INDIA** | **1,430** | ~12-16 weeks |
| **COO TURKEY** | **734** | ~8-12 weeks |
| FERNCREST-MEDLINE | 78 | Domestic, 1-2 weeks |

Class names already encode the long-cycle reality. This intelligence isn't yet wired into `Vendor.LeadTimedays` or factory-closure calendars.

### 1.5 Existing infrastructure (reuse, don't rebuild)

- **`AesthetikContainers`** customization with `UsrContainer`, `UsrContainerPOLink`, ETA propagation (SB501000 live on test tenant).
- **`SB501000 — Procurement Command Center`** already exists (ASPX page, 283 lines, titled "Container Maintenance" in SiteMap). Container-centric, has 5 detail tabs: EVENTS / PO LINKS / COSTS / DOCUMENTS / ETA HISTORY. 3 KPI cards: ACTION / WATCH / EXPOSURE.
- **Fabric Tracker** (`webhook-router/src/portal/tracker-api.ts`) — pure-function SO→PO→Container walker, 10 passing tests. Inverse walk (InventoryID → PO → Container) is the primitive DRP needs.
- **studiob-api gateway** — wraps Acumatica REST. Gaps: api-bot blocked on `PurchaseOrder` (403); `InventoryAllocDetEnq` inquiry not registered.
- **`heritage-wms` parser stack** (`smart-parser.ts`, `packing-slip-ocr.ts`, `sku-matcher.ts`, `column-mapper.ts`, `learning-store.ts`, `vendor-scorecard-service.ts`) — 2,000+ lines of production code handling xlsx/csv/pdf/image parsing, LLM extraction, per-vendor column-mapping memory, 5-tier fuzzy SKU matching. Reusable for MOQ intake with near-zero new code.
- **`DataLifecycleManager`** (`webhook-router/src/lib/data-lifecycle/`) — three-tier Postgres→GCS archival with policy registry. Handles 11+ entity types. Reusable for DRP table retention.
- **Qdrant `studiob-knowledge`** — 30K+ chunks of Acumatica help wiki already ingested.
- **Customization packages on disk:** `AesthetikContainers` (1,965 lines, 33 POOrder refs), `AesthetikContainerGIs`, `AesthetikWMS` (429 lines, mostly empty), `StudioBAcuOps`. `HeritageFabricsPOv5` and `StudioBPORelations` are gone from the repo. `AesthetikContainers` is the de facto home for POOrder extensions.

### 1.6 Blind spots the agent cannot see today

| Blind spot | Why | Phase 0 fix |
|---|---|---|
| Historical sales velocity per SKU | `SalesOrder` gateway returns only 7 rows (implicit filter) | Expose `DRP_VelocityHistory` Generic Inquiry via SM208030 |
| Current qty on hand per item/warehouse | No `InventorySummary` endpoint, `$expand=WarehouseDetails` drops silently | Register `InventoryAllocDetEnq` inquiry via SM208030 |
| Open PO pipeline depth | api-bot blocked (403) on `PurchaseOrder` | Expand api-bot role OR expose `DRP_OpenPOLines` GI |
| Stockout events | cs-order-entry renders badges but doesn't persist | Add event logger in `cs-order-entry/src/api/inventory.ts` |
| Lead-time variance | Only 15 vendor `LeadTimedays` populated | Mine `UsrContainer.ATA` vs `UsrContainer.ETA` deltas, email-watcher populates `UsrAcknowledgedDate` / `UsrFactoryReadyDate` |

---

## 2. Design Decisions Locked

| Decision | Value | Notes |
|---|---|---|
| **Approach** | B — External forecasting agent writes to Acumatica | Agent is the brain; Acumatica is the system of record |
| **Objective function** | Minimize inventory dollar-days, subject to committed fill-rate floor | Not service-level maximization |
| **Primary metric** | Cross-dock hit rate (% of receipts shipped within 7d) | Plus turns/year, dead inventory $, days of cover |
| **Service level floor** | 98% committed / 90% speculative | Floor, not target |
| **ABC service tiers** | A=98%, B=95%, C=90% | Tiered by revenue rank |
| **ABC scheme** | Pluggable scheme registry; v1 = `revenue_weighted_90` (last 90 days weighted 2x) | Evolvable via `drp_abc_schemes` + shadow mode + backtest machinery |
| **MOQ model** | Per-item MOQ from `StockItem.VendorDetails.MinOrderQty` | Agent respects as hard floor |
| **Commitment horizon** | 30-60 days default (B2B textile); measure empirically in Phase 0 | Per-customer-class override if data warrants |
| **Speculation floor** | 14 days A / 7 days B / 0 days C | Floor below which agent shouldn't recommend zero inventory |
| **Legacy ROP fate** | Reinterpret as speculation floors (no migration) | Agent challenges them over time; daily brief flags disagreements >30% |
| **Agent autonomy** | Phase-gated: paper trading (mo 1-2) → draft-PO (mo 3-4) → C-item autopilot (mo 5+) | Every phase has kill-switch via `drp_phase_config.write_enabled` |
| **Cash constraint** | Soft cap — working capital alert if projected $ exceeds threshold | No hard optimization |
| **UI language** | Plain operations vocabulary | Internal math uses trader thinking, staff never sees commodities jargon |
| **Custom field package** | `AesthetikContainers` | `HeritageFabricsPOv5` and `StudioBPORelations` are gone; `AesthetikContainers` holds POOrder extensions |
| **SB501000 reconciliation** | 3 screens in Container Tracking workspace: PCC (SB501000, container ops) + Vendor Planning Hub (SB501100) + Supplier Intake (SB501200) | PCC stays container-centric; DRP work lives in siblings |
| **MOQ intake surface** | heritage-wms (React), reached from SB501200 as external link | Reuses existing parser stack unchanged |
| **Data archive** | Reuse `DataLifecycleManager` policies for all `drp_*` tables | No new archival code |
| **Human override TTL** | 180 days ROP/SS/Max, 365 days full opt-out | Agent re-evaluates on expiry; silent takeback if delta <10%, else enqueue for review |
| **Factory closures** | `drp_vendor_calendar` + `drp_country_calendar` with seeded priors (CNY, Diwali, Bayram, etc.) + agent-learned patterns | Impact added to lead time at runtime when order window crosses closure |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DRP AGENT (Railway service)                   │
│                  nightly @ 02:00 ET, cron driven                 │
│                                                                   │
│  Pulls signals → forecasts → writes parameters → posts report   │
└────────────┬────────────────────────────────────────────────────┘
             │
   ┌─────────┴──────────┬──────────────────────┬──────────────┐
   ↓                    ↓                      ↓              ↓
┌─────────────┐  ┌──────────────┐    ┌─────────────────┐  ┌──────────┐
│ studiob-api │  │ heritage-wms │    │ Acumatica       │  │ Slack    │
│ (gateway)   │  │ Postgres     │    │ (system of      │  │ (briefs  │
│             │  │ (drp_* +     │    │  record)        │  │  + alerts│
│ READ:       │  │  parser DB)  │    │ WRITE:          │  │          │
│ • sales     │  │              │    │ • ItemWhse.ROP  │  │ Phase 1: │
│ • PO lines  │  │ • forecasts  │    │ • ItemWhse.SS   │  │  advisor │
│ • containers│  │ • recs       │    │ • ItemWhse.Max  │  │  (paper) │
│ • vendors   │  │ • allocations│    │ • StockItem.ABC │  │ Phase 2: │
│ • items     │  │ • LT samples │    │ • PO drafts     │  │  drafts  │
│             │  │ • overrides  │    │   (phase 2+)    │  │ Phase 3: │
│             │  │ • MOQ intake │    │                 │  │  autop.  │
└─────────────┘  └──────────────┘    └─────────────────┘  └──────────┘
```

**Three-store principle:**
- Acumatica = system of record. Anything a human reads in an Acumatica screen and expects to be authoritative lives here.
- heritage-wms Postgres = agent working memory. Recommendations, forecast state, override tracking, MOQ intake audit.
- Qdrant `studiob-knowledge` = unstructured corpus. Help docs for the agent to consult; no agent output.

---

## 4. Phase 0 — Data Foundation (5-6 weeks, parallel streams)

### 4.1 Gateway read unblocks (1 week)
- Register `DRP_VelocityHistory` GI via SM208030 — exposes INTran-derived shipment history
- Register `DRP_OpenSOCommitments` GI — exposes open SO lines with ship dates
- Register `DRP_OpenPOLines` GI — exposes PO + POLine + container link, bypasses api-bot 403
- Register `InventoryAllocDetEnq` via SM208030 — on-hand / on-order / allocated qty
- Deploy `ContainerTracking` REST endpoint (verify api-bot access)
- Add studiob-api gateway routes for each of the 4 GIs

### 4.2 Acumatica custom fields (1 week)
- Add `POOrder.UsrAcknowledgedDate` (DateTime, nullable) to `AesthetikContainers`
- Add `POOrder.UsrFactoryReadyDate` (DateTime, nullable) to `AesthetikContainers`
- Both rendered in the existing PO301000 container-tracking panel
- Deploy via `acumatica-ci-cd` pipeline
- Backfill strategy: both start null, populated by humans via Vendor Planning Hub OR by email watcher (Phase 0.4)

### 4.3 MOQ intake — steady-state (1.5 weeks)
- Page: `heritage-wms/client/src/pages/MOQIntake.tsx` (copy of `ImportPackingSlip.tsx` pattern)
- Route: `heritage-wms/src/routes/moq.ts` (mirrors `receive.ts/bulk-import` shape)
- Service: `heritage-wms/src/services/moq-intake-service.ts` (~200 LoC wrapping existing parsers)
- DB migrations: `drp_vendor_moq_profiles`, `drp_vendor_moqs`, `drp_vendor_moq_extractions`
- Column-mapper extension: add MOQ-specific header patterns in multiple languages
- Write-back path: approved MOQs sync to Acumatica `StockItem.VendorDetails.MinOrderQty` via studiob-api

### 4.4 MOQ intake — bulk backlog (1.5 weeks)
- Page: `heritage-wms/client/src/pages/MOQBulkIntake.tsx` — drag-drop N files
- Service: `heritage-wms/src/services/moq-bulk-orchestrator.ts` (~400 LoC)
  - Concurrency pool (8-12 parallel parses based on Claude rate limits)
  - File dedup (MD5)
  - Vendor guessing from filename + content (LLM-assisted)
  - Cost tracker ($ spent during bulk run)
  - Confidence-ranked review queue
  - Bulk-approve action

### 4.5 Vendor lead-time learning foundation (1 week)
- Extend `heritage-wms/src/services/vendor-scorecard-service.ts` with 4-stage distributions:
  - `ack_lag_mean/stddev/n`
  - `production_mean/stddev/n`
  - `transit_mean/stddev/n`
  - `total_lead_mean/stddev/n`
  - `lead_time_bias_days`
- New table `drp_lead_time_samples` — one row per received PO line with the 4 timestamps
- Materialized view `drp_vendor_lead_time_stats` refreshed in agent's nightly run
- Nightly mining job pulls completed PO receipts from Acumatica, computes intervals, inserts samples
- Extend `VendorScorecard.tsx` page with 4 new columns

### 4.6 ABC classification baseline (3 days)
- Build `drp_abc_schemes` registry with v1 scheme `revenue_weighted_90`
- Initial classification run against whatever history is available
- Write results to `drp_abc_classifications` + `StockItem.ABCCode`
- Schedule monthly recompute
- Shadow-mode backtest framework scaffolding (even if only one scheme in v1)

### 4.7 cs-order-entry stockout event logger (2 days)
- Add event emit in `cs-order-entry/src/api/inventory.ts` where stockout badge decision is made
- New table `drp_lost_demand_events` in heritage-wms Postgres
- Event shape: `(event_at, inventory_id, requested_qty, available_qty, customer_id, customer_class)`
- Feeds the ABC classifier and the velocity calculator

### 4.8 Vendor acknowledgment email watcher (3-4 days)
- New worker: `webhook-router/src/workers/po-email-watcher.ts`
- Reuses existing Microsoft Graph subscription (verify it covers procurement inbox)
- Reuses Claude API integration from existing smart-parser
- New tables: `drp_signal_email_raw`, `drp_signal_email_parsed`
- Confidence thresholds: ≥0.85 auto-apply, 0.60–0.85 propose for review, <0.60 ignore
- Writes `POOrder.UsrAcknowledgedDate` / `POOrder.UsrFactoryReadyDate` via studiob-api

---

## 5. Data Model

### 5.1 Acumatica side

**New custom fields in `AesthetikContainers`:**
```csharp
public class POOrderExt : PXCacheExtension<POOrder> {
    [PXDBDate]
    [PXUIField(DisplayName = "Vendor Acknowledged Date")]
    public DateTime? UsrAcknowledgedDate { get; set; }

    [PXDBDate]
    [PXUIField(DisplayName = "Factory Ready Date")]
    public DateTime? UsrFactoryReadyDate { get; set; }
}
```

**Fields the agent reads:** `ItemWarehouse.*`, `StockItem.*` + `VendorDetails`, `Vendor.*`, `PurchaseOrder` + `Details`, `InventoryReceipt`, `UsrContainer`, `UsrContainerPOLink`, `INTran` (via GI).

**Fields the agent writes (phase-gated):** `ItemWarehouse.ReorderPoint/SafetyStock/MaxQty`, `StockItem.ABCCode`, `Vendor.LeadTimedays`, `StockItem.VendorDetails.MinOrderQty`, `PurchaseOrder` (Draft status, Phase 2+).

### 5.2 heritage-wms Postgres tables (all prefixed `drp_`)

| Table | Purpose |
|---|---|
| `drp_agent_runs` | One row per nightly execution, full metadata + config snapshot |
| `drp_recommendations` | The delta-report artifact: per-item recommendations with before/after/rationale/status |
| `drp_forecast_state` | Persistent per-item forecast model state (ES/Holt-Winters coefficients) |
| `drp_class_seasonality` / `drp_sku_seasonality` | Seasonal indices, pooled class-level and per-SKU when history allows |
| `drp_lead_time_samples` | Raw 4-stage PO lifecycle observations |
| `drp_vendor_lead_time_stats` | Materialized view, rolling aggregates |
| `drp_po_allocations` | PO-line ↔ SO-line allocation tracking (committed/hedged/speculative + cross_dock_status) |
| `drp_cross_dock_matches` | Specific PO-to-SO cross-dock match proposals and execution tracking |
| `drp_vendor_moq_profiles` / `drp_vendor_moqs` / `drp_vendor_moq_extractions` | MOQ intake + parser learning |
| `drp_manual_overrides` | Human override tracking with TTL + silent-takeback resolution |
| `drp_vendor_calendar` / `drp_country_calendar` | Factory closures (declared + seeded priors + learned patterns) |
| `drp_abc_schemes` / `drp_abc_classification_runs` / `drp_abc_classifications` / `drp_abc_backtest_results` | Pluggable ABC classification + backtest framework |
| `drp_phase_config` | Singleton config with kill-switches, service levels, thresholds, TTLs |
| `drp_lost_demand_events` | cs-order-entry stockout events (real demand signal) |
| `drp_signal_*` (velocity, open_po_cache, open_so_cache, inventory_snapshot, containers, email_raw, email_parsed, fx_rates, etc.) | Landing tables for raw pulled signals |

### 5.3 Retention via DataLifecycleManager

New policies registered in `webhook-router/src/lib/data-lifecycle/policies.ts`:

```typescript
drp-recommendations:  hot 90d, warm 365d, cold GCS (drp/recommendations/)
drp-lead-time-samples: hot 365d, warm 1095d, cold GCS (drp/lead-time/)
drp-forecast-state:   hot 30d, warm 365d (weekly snapshots)
drp-agent-runs:       hot 90d, warm 365d
drp-moq-extractions:  hot 180d, warm 730d, never prune
```

No new archive code — reuses existing `DataLifecycleManager`.

---

## 6. Signal Ingestion — 17 Signals

### 6.1 Acumatica-native (9 signals)

| # | Signal | Cadence | Blocker |
|---|---|---|---|
| 1 | Sales velocity (INTran via DRP_VelocityHistory GI) | Nightly | GI not registered |
| 2 | Open SO commitments (DRP_OpenSOCommitments GI) | 15 min | Gateway filter mystery, fix via GI |
| 3 | Open PO lines (DRP_OpenPOLines GI) | 15 min | api-bot 403, fix via GI |
| 4 | Current on-hand (InventoryAllocDetEnq) | 15 min | Inquiry not registered |
| 5 | Receipt transactions (closes 4-stage lead time loop) | Nightly | Depends on #3 |
| 6 | ItemWarehouse parameters + override flag | Nightly | None |
| 7 | StockItem master + VendorDetails + MOQ | Nightly | `$expand=VendorDetails` drops; use per-item `/record/` |
| 8 | Vendor master (lead time, class, country) | Weekly | None |
| 9 | Container lifecycle (ETA/ATA/events via ContainerTracking endpoint) | 15 min | Verify api-bot access |

### 6.2 External (via webhook-router workers)

| # | Signal | Source | Reuse? |
|---|---|---|---|
| 10 | Shopify sessions + add-to-cart | Shopify Storefront API | Existing sync, add aggregation |
| 11 | HubSpot deal pipeline velocity | HubSpot CRM | Existing 15-min sync, add DRP aggregation view |
| 12 | cs-order-entry stockout events | cs-order-entry app | New event logger (~40 lines) |
| 13 | Vendor acknowledgment emails | Microsoft Graph procurement inbox | New worker (~400 lines), reuses Graph + Claude |
| 14 | FX rates (INR/USD, TRY/USD) | FRED or free FX API | v2+ |
| 15 | Freight rate indices (Drewry, Baltic) | Public/paid feeds | v2+ |

### 6.3 Pre-seeded + learned

| # | Signal | Notes |
|---|---|---|
| 16 | Country holiday priors + vendor closures | Seeded at install, agent-learned from lead time drift |
| 17 | Lead time distributions (4-stage) | Derived from `drp_lead_time_samples` |

### 6.4 Freshness matrix + failure handling

Three run states: **healthy** (all primary signals <4h stale), **degraded** (secondary signals stale, confidence-penalized recs), **blocked** (primary signal missing/>12h, run aborts with alert).

---

## 7. SB501000 Revisit — Container Tracking Workspace

**Current state (live on Heritage Test):** SB501000 = "Container Maintenance" (SiteMap label), container-centric, 5 detail tabs (EVENTS / PO LINKS / COSTS / DOCUMENTS / ETA HISTORY), 3 KPI cards, action ribbon with CREATE LANDED COST / MARK CUSTOMS CLEARED / MARK DELIVERED / PRINT RECEIVING DOC / IMPORT FORWARDER CSV.

**Revised 3-screen workspace:**

```
Container Tracking workspace

Transactions                                Configuration
• Procurement Command Center  (SB501000)    • Freight Forwarders
  Container ops (refined)                   • Container Types
                                             • Destinations/Ports
• Vendor Planning Hub         (SB501100)    • Container Preferences
  Agent brief + vendor mgmt

• Supplier Intake             (SB501200)
  MOQ drop zone (opens heritage-wms)
```

### 7.1 SB501000 light refactor

- **Rename SiteMap** title to "Procurement Command Center" (removes Container Maintenance mismatch)
- **Extend lifecycle timeline** to 7 stages: PLACED → ACKED → FACTORY READY → SHIPPED → IN TRANSIT → ARRIVED PORT → CUSTOMS → DELIVERED
- **New tab: LEAD TIME** (6th tab) — per-container PO lines with 4-stage observed breakdown
- **Upgrade EXPOSURE KPI card** to cross-reference `drp_recommendations` and `drp_lead_time_distributions` (lead-time drift, stockouts on preferred vendors, etc.)
- **New action button: PLAN NEXT ORDER** on the PO LINKS tab — deep-link to Vendor Planning Hub pre-filtered to vendor
- **KPI cards retheme (plain ops language):** POSITION $ + turns + dead / CROSS-DOCK % / SPECULATION $ + overhang count
- **Keep untouched:** COSTS tab, DOCUMENTS tab, ETA HISTORY tab, action ribbon

### 7.2 SB501100 — Vendor Planning Hub (new)

Ranked to-do list of vendors + single-pane detail view. Mirrors heritage-wms `VendorDetail.tsx` layout in native Acumatica ASPX. 7 stacked sections: Open POs / Lead Time Analytics / MOQ Summary (links to Supplier Intake) / Preferred Items / Scorecard / Closures / Activity Log. Reads from `drp_*` tables via studiob-api.

Default sort: working-capital impact of acting on this vendor today.

### 7.3 SB501200 — Supplier Intake (new, external link v1)

Thin Acumatica shell that externally links to `https://wms.asthetik.com/moq-intake?vendor={id}` (or `/moq-bulk`). v1 uses an external link for simplicity; v2 can revisit iframe embedding if UX justifies it.

---

## 8. Phase-Gated Rollout

| Phase | Months | Agent does | Human does | Kill-switch state |
|---|---|---|---|---|
| **1 — Paper Trading** | 1-2 | Computes recommendations, writes to `drp_recommendations`, posts daily brief to Slack. Does NOT write to Acumatica. | Reviews brief, manually updates ItemWarehouse for picks they agree with. Tracks agreement rate. | `phase=advisor`, `write_enabled=false` |
| **2 — Draft POs + Parameter Autopilot** | 3-4 | Writes ROP/SS/Max to ItemWarehouse nightly (debounced). Creates draft POs in Acumatica. | Reviews draft POs in Acumatica, clicks Approve. | `phase=draft_po`, `write_enabled=true` |
| **3 — C-Item Autopilot** | 5+ | Auto-releases C-item POs. Still drafts A/B POs for review. Exception alerts. | Reviews A/B drafts; monitors exception log. | `phase=autopilot`, `autopilot_abc_classes=['C']` |

**Safety rails:**
- `drp_phase_config.write_enabled = false` → agent read-only in seconds
- Single-run ROP change >20% → review flag, no write
- Aggregate run-level $ change > `max_daily_po_value_usd` → pause + approval required
- Acumatica write failure → rollback + alert
- `ItemWarehouse.OverrideReplenishmentSettings = true` → hard opt-out, agent never touches
- Active `drp_manual_overrides` row → recommendation computed but not written, status = `blocked_by_override`

---

## 9. Backtesting Framework

Built in from day 1 as first-class infrastructure, not an afterthought.

### 9.1 Pluggable ABC scheme registry (the initial instance)

```sql
drp_abc_schemes — scheme definitions with signals, weights, recency scheme, thresholds, active/shadow flag
drp_abc_classification_runs — per-run metadata, scheme_id, is_shadow
drp_abc_backtest_results — per-run outcomes: service level achieved, stockouts on A, overstock on C, churn rate, override agreement, composite score
```

**v1 scheme:** `revenue_weighted_90` — revenue-only, last 90 days weighted 2x, standard 70/25/5 thresholds.

**Shadow mode:** create new schemes with `is_shadow=true`. Every nightly run computes under all shadow schemes. Composite scores accumulate over 30+ days. Procurement promotes a shadow to active when it beats the incumbent.

### 9.2 Generalized backtest framework

Every parameter that drives agent behavior is backtestable:
- Forecast model choice (ES vs Holt-Winters vs Naive) per item class
- Service level tiers (98/95/90 vs 95/92/88 vs item-specific)
- Safety stock formula (Z-score vs empirical quantile vs CVaR)
- Lead time lookback window (90d vs 180d vs 365d)
- Speculation floor days (A/B/C values)
- MOQ strictness rules
- Cross-dock matching tolerance windows

**Walk-forward validation** is mandatory. No parameter change ships to production without running backtests on ≥180 days of history with walk-forward train/test splits.

### 9.3 Paper trading as the first use of backtesting

Phase 1 IS a paper-trading exercise. Every night the agent publishes recommendations. Every morning the backtester reconstructs "what would the position look like if we'd followed all recommendations" vs "what actually happened." After 60 days we have a real comparison to justify promoting to Phase 2.

---

## 10. Cross-Dock-First Logic

### 10.1 Allocation taxonomy

Every open PO line is tagged one of three ways:

| Tag | Meaning | Treatment |
|---|---|---|
| **Committed** | Tied to a specific open SO line | Cross-dock target; zero warehouse dwell |
| **Hedged** | Tied to aggregate forecasted demand within commitment horizon (30-60d) | Must turn within horizon; limited dwell |
| **Speculative** | No demand backing | Tightest scrutiny; appears in speculation exposure KPI |

### 10.2 Agent ordering logic (rewritten from ROP-based to commitment-based)

```python
def recommend_order(item, warehouse):
    open_sos = get_open_so_lines(item, horizon_days=commitment_horizon)
    committed_qty = sum(line.open_qty for line in open_sos)
    allocated_on_order = sum_allocated_pos(item)
    uncommitted_demand = committed_qty - allocated_on_order

    # Primary: committed ordering
    if uncommitted_demand > 0:
        target_so = earliest_unallocated_so(open_sos)
        lead_time = effective_lead_time(item.preferred_vendor, today)
        slack = (target_so.ship_date - (today + lead_time)).days
        if slack >= 0:
            return Recommendation(
                qty=max(uncommitted_demand, item.moq),
                allocation_type='committed',
                so_nbr=target_so.nbr,
                cross_dock_status='feasible' if 0 <= slack <= 14 else 'will_sit',
                rationale=f"SO {target_so.nbr} ships {target_so.ship_date}, "
                         f"PO arrives {today + lead_time}, slack {slack}d"
            )
        else:
            return Recommendation(qty=0, rationale=f"Cannot cross-dock — lead time exceeds ship window by {-slack}d")

    # Fallback: speculation floor
    min_spec = max(speculation_days[abc_tier] * avg_daily_burn[item], item.moq)
    if current_position < min_spec:
        return Recommendation(
            qty=min_spec - current_position,
            allocation_type='speculative',
            rationale=f"Below speculation floor ({speculation_days[abc_tier]}d cover)"
        )

    return Recommendation(qty=0, rationale="Position balanced")
```

### 10.3 Primary KPIs

- **Working Capital $** (total $ at risk, with daily delta)
- **Days of Cover** (position / daily burn, per item and aggregate)
- **Cross-Dock Hit Rate** (% of receipts that shipped within 7 days of arrival)
- **Dead Inventory $** (SKUs with 0 shipments in last 90 days)
- **Speculation Exposure** (% of inventory that's uncommitted)
- **Inventory Turns** (annual COGS / avg inventory)

Service level is a constraint (must stay above floor), not a KPI.

---

## 11. Forecast Engine

### 11.1 Design constraints specific to HF

Heritage Fabrics' demand profile breaks most textbook forecasting assumptions:

- **Thin per-SKU history.** Median A-class SKU sees single-digit shipments per week; long-tail C-class SKUs go weeks without a single sale. Classical ARIMA/ETS trained per-SKU overfits noise.
- **Weak but real seasonality.** Designer fabric demand has pockets of annual seasonality (upholstery cycles, hospitality procurement bursts, January-February showroom restocks) but never strong enough to detect reliably from one SKU's history alone.
- **Forward-looking signals exist before orders land.** A deal moving to "Proposal Sent" in HubSpot, a Shopify session spike on a collection page, or a stockout badge in cs-order-entry are all earlier than the SO that eventually materializes.
- **Long procurement cycles make forecast error asymmetric.** Under-forecasting by 20% on an India fabric means a 12-16 week stockout. Over-forecasting by 20% means dead inventory that may never clear. The agent must emit distributions, not means, so the downstream ROP math can reason about cost under uncertainty.

The forecast engine is therefore a **cascaded ensemble with explicit uncertainty** — not a single best model — and it pools aggressively across SKUs to make the signal detectable at all.

### 11.2 Model cascade (per-item, per-horizon)

Every nightly run produces a forecast for each active item at three horizons: **7-day**, **28-day**, **90-day**. The cascade picks the first usable model for each horizon:

| Tier | Model | When it's used | Output |
|---|---|---|---|
| **T1** | Holt-Winters with pooled class seasonality | ≥52 weeks of history AND ≥26 non-zero weeks | mean + 10/50/90 quantiles from residual bootstrap |
| **T2** | Exponential smoothing with class-level multiplicative seasonal overlay | ≥26 weeks of history AND ≥13 non-zero weeks | mean + quantiles from class-pooled residual distribution |
| **T3** | Class-level Croston (intermittent demand) + per-SKU scaling factor | Newer SKU OR sparse (<13 non-zero weeks) | mean + quantiles from Croston inter-arrival variance |
| **T4** | Class average daily burn × speculation-floor multiplier | <4 weeks history (brand-new item) | mean only; quantiles set to wide priors from class distribution |

The chosen tier is persisted in `drp_forecast_state.tier` per item so the next run starts where it left off and only re-evaluates when enough new history accrues to promote it up a tier.

### 11.3 Seasonality detection stack

Per-SKU seasonality is almost never detectable from HF's data. The stack layers four mechanisms:

1. **STL decomposition on pooled class series.** For each item class (`COO INDIA`, `COO TURKEY`, `FERNCREST-MEDLINE`), sum daily shipments across all SKUs and run STL with a 365-day period. The resulting seasonal component becomes `drp_class_seasonality`. A class "has seasonality" if the seasonal-to-residual variance ratio exceeds 0.15 — otherwise the class series is flat and the multiplicative index is locked to 1.0.
2. **Fourier regression overlay.** For classes where STL finds signal, fit sin/cos terms at annual, semi-annual, and quarterly frequencies against the deseasonalized trend to smooth the seasonal index. Fourier coefficients are persisted in `drp_class_seasonality.fourier_coeffs` so the agent can evaluate the index at any future date without re-running STL.
3. **Industry priors** (static JSON seeded at install). Upholstery/drapery textiles have an observed industry bias toward Q1 restock and an August lull. When a class has insufficient history for STL, the agent blends 80% industry prior + 20% observed, decaying to 100% observed as history accumulates.
4. **Exogenous regressors** — three forward-looking signals merged in as linear adjustments on top of the baseline forecast:
   - **HubSpot pipeline velocity** (signal #11): aggregate `amount` of open deals tagged to SKUs in the commitment horizon window. A +20% week-over-week change applies a multiplicative bump proportional to historical deal-to-SO conversion rate (learned separately per class, stored in `drp_forecast_state.hubspot_conv_rate`).
   - **Shopify sessions + add-to-cart** (signal #10): collection-page sessions and product add-to-cart events, attributed to SKUs by `collection → sku_family` mapping. Used as a coincident indicator, not leading; contributes to short-horizon (7d) forecasts only.
   - **cs-order-entry stockout events** (signal #12): each `drp_lost_demand_events` row is censored demand. The forecaster adds a fraction of the stockout qty back into the observed demand series before fitting, based on `available_qty / requested_qty` (the fraction of the order that couldn't be filled). This prevents stockouts from silently teaching the model "there is no demand for item X" when reality is "we couldn't serve the demand."

### 11.4 Uncertainty bands

Every forecast row in `drp_forecast_state` carries:

```
item_id, warehouse_id, horizon_days, as_of_date,
mean_qty, p10_qty, p50_qty, p90_qty,
tier, model_version, seasonality_applied, exogenous_adjustments_json,
last_refit_at, rmse_7d, rmse_28d, mape_7d, mape_28d, mape_90d
```

The ROP/speculation-floor calculator consumes `p90_qty` over lead time (not `mean_qty`) for A-class items and `p50_qty` for C-class items — directly implementing the asymmetric-cost principle. B-class uses a mix (p75). This tier-specific quantile choice is stored in `drp_phase_config.forecast_quantile_by_class` so it can be tuned without code changes.

### 11.5 Fitting cadence and state persistence

- **Nightly:** refresh exogenous adjustments (HubSpot, Shopify, stockout events) and emit a new forecast row per (item, horizon) using the existing model parameters. Cheap — pure vector math.
- **Weekly:** refit Tier 1/2 model coefficients on the rolling 104-week window. Expensive — only runs on Sundays between 02:00-04:00 ET.
- **Monthly:** re-run STL on pooled class series and refresh `drp_class_seasonality`. Also re-check tier eligibility (did any SKUs accumulate enough history to promote from T3 → T2?).

All state lives in `drp_forecast_state` (per-item) and `drp_class_seasonality` / `drp_sku_seasonality` (shared). Weekly DataLifecycleManager snapshots keep 52 weeks hot, the rest cold.

### 11.6 Accuracy tracking

Each nightly run stores the prior forecast's predicted qty alongside the new run's *actual* observed qty at the same horizon (look back 7, 28, 90 days). `drp_forecast_accuracy` rolls these into:

- **MAPE** (mean absolute percentage error) at each horizon, per-item AND pooled at class level.
- **Bias** (mean error signed) at each horizon — catches consistent under- or over-forecasting.
- **Calibration** (what fraction of actuals fall inside the p10-p90 band; healthy range 70-85%, outside that means bands are mis-sized).

The daily brief flags classes where MAPE_28d > 40% or calibration drifts below 60% for 7 days running. Drift detection in Section 15 promotes these to red-flag conditions.

### 11.7 Fallback logic when signals are missing

Exogenous signals (HubSpot, Shopify, cs-order-entry) are *adjustments*, never primary. If any of the three is stale (>24h), the agent drops that term, records `exogenous_adjustments_json = { "hubspot": "stale", ... }`, and widens the p10-p90 bands by a degradation factor (default ×1.2) to reflect lower confidence. The run state goes **degraded** (see 14.2) but does not abort. If *all three* exogenous signals are missing, the agent falls back to pure historical forecasts with a ×1.5 band widening and flags the condition in the brief. Primary signals (Acumatica velocity history, lead times) being missing is a **blocked** run — the forecast step does not execute at all.

---

## 12. Lead Time Learning (Detailed)

### 12.1 The four stages

Every received PO line generates one `drp_lead_time_samples` row with four timestamps and the three derived intervals:

```
po_placed_at       → POOrder.OrderDate
vendor_acked_at    → POOrder.UsrAcknowledgedDate (email watcher or manual)
factory_ready_at   → POOrder.UsrFactoryReadyDate (email watcher or manual)
shipped_at         → first UsrContainer linked to this PO line, ContainerEvent type='SHIPPED'
arrived_at         → same container, ContainerEvent type='ARRIVED'
received_at        → InventoryReceipt.TranDate on the line

ack_lag_days       = vendor_acked_at - po_placed_at
production_days    = factory_ready_at - vendor_acked_at
transit_days       = arrived_at - shipped_at
port_to_dock_days  = received_at - arrived_at
total_lead_days    = received_at - po_placed_at
```

Samples with a missing timestamp fall back cleanly: if `vendor_acked_at` is null, both `ack_lag_days` and `production_days` are null for that sample but `total_lead_days` is still usable in the total-only distribution. The four stages are therefore tracked as independent distributions, each with its own sample count.

### 12.2 Running distribution math

For each (`vendor_id`, `stage`) pair, `drp_vendor_lead_time_stats` (materialized view refreshed nightly) holds:

```
mean, stddev, n_samples,
p10, p50, p90, p95,
last_sample_at, distribution_kind  -- 'lognormal'|'gamma'|'empirical'
```

Distribution kind is chosen once per vendor per stage via a one-shot Shapiro-Wilk + K-S test (lognormal vs gamma) during the weekly refit. For vendors with <10 samples, `distribution_kind='empirical'` and the agent uses the observed quantiles directly rather than fitting.

### 12.3 Outlier detection (3σ with regime guard)

Each new sample is checked against the running mean and stddev before it's folded in:

```python
z = (sample.total_lead_days - stats.mean) / max(stats.stddev, 1.0)
if abs(z) > 3.0:
    sample.flagged_as_outlier = True
    sample.outlier_reason = "3sigma_from_running_mean"
    # held for review, NOT folded into stats yet
elif stats.n_samples < 10:
    sample.flagged_as_outlier = False  # need data before rejecting
    fold_into_stats(sample)
else:
    sample.flagged_as_outlier = False
    fold_into_stats(sample)
```

Flagged outliers sit in `drp_lead_time_samples` with `flagged_as_outlier=true` and appear in the weekly human review. If an outlier is confirmed as real (e.g. a genuine factory delay), a human clears the flag and the sample is folded in. If it's rejected (data entry error), it stays flagged and never contributes.

### 12.4 Regime-change detection

Individual outliers are one thing; a *regime change* is when every recent sample is shifting the mean in one direction. The agent detects this with a rolling CUSUM test:

```
S_t = max(0, S_{t-1} + (sample.total_lead_days - stats.mean) - 0.5*stats.stddev)
```

When `S_t` exceeds `5*stats.stddev` for any (vendor, stage), the agent declares a regime break, archives the prior distribution to `drp_vendor_lead_time_regimes`, and starts a new distribution from the last 10 samples. The archival row stores `start_at`, `end_at`, and a free-text `regime_label` that the weekly human review populates (`"pre-Red-Sea"`, `"post-CNY-2026"`, etc.) so the agent can later condition on expected regime states.

### 12.5 Factory closure overlay

`drp_vendor_calendar` (per-vendor) and `drp_country_calendar` (per-COO bucket) contain `{start_date, end_date, label, impact_multiplier}` rows. The impact multiplier defaults to 1.0 but can be learned per vendor — e.g., CNY for a specific supplier who restarts slowly might be 1.2 on the two weeks following the calendar entry.

When computing `effective_lead_time(vendor, today)` the agent walks forward from today:

```python
def effective_lead_time(vendor, today):
    base = vendor_stats[vendor].p90  # p90 per A-class, p50 per C-class
    end = today + timedelta(days=base)
    extra = 0
    for closure in calendars_for(vendor, today, end):
        overlap_days = days_overlap(closure, today, end)
        extra += overlap_days * (closure.impact_multiplier - 1.0)
    return base + extra
```

The impact multiplier being at least 1.0 means a closure adds its full length to the effective lead time unless manually tuned. Seeded closures at install: Chinese New Year, Diwali, Turkish Bayram(s), Indian monsoon regional slowdowns, Christmas/New Year week.

### 12.6 Bias correction feedback loop

For each vendor the agent tracks `lead_time_bias_days = mean(observed_total_lead - promised_total_lead)` over the last 20 receipts, where `promised_total_lead` is whatever the `Vendor.LeadTimedays` was on the PO's placement date. The bias is added to the effective lead time used in ROP and order-date calculations, capped at ±30 days to prevent a single bad vendor from running away.

### 12.7 Vendor beta (market covariance)

A single lead-time distribution assumes the vendor is independent of broader conditions. In reality, a Red Sea disruption or a port strike hits all India-COO vendors at once. The agent computes a **vendor beta** — how much each vendor's lead-time shock correlates with the pooled country shock:

```
country_shock_t = (country_mean_lead_t - country_mean_lead_baseline) / country_stddev_baseline
vendor_shock_t  = (vendor_mean_lead_t  - vendor_mean_lead_baseline)  / vendor_stddev_baseline
beta = cov(vendor_shock, country_shock) / var(country_shock)
```

Persisted as `drp_vendor_lead_time_stats.country_beta`. A vendor with β=1.4 during India shocks gets an extra margin when country-level signals (Baltic/Drewry indices, FX moves) point to broad disruption. This is wired up in v2 — v1 just computes and stores the beta without using it.

### 12.8 Write-back to `Vendor.LeadTimedays`

Weekly (Sunday 03:30 ET), for every vendor with `n_samples >= 10` on the `total_lead_days` distribution and where the stats are stable (not in a declared regime-change state), the agent writes `round(p50)` back to `Vendor.LeadTimedays` via studiob-api. Acumatica's built-in replenishment calculator uses this field as an input; having it populated for the first time in HF's history is itself a major Phase 0 win independent of any other DRP work.

---

## 13. DRP Math (Detailed)

### 13.1 Cross-dock-first recommendation logic (expanded)

Section 10.2 sketched the shape. The full logic handles MOQ, EOQ, container fill, concentration, NPV, and cash cap:

```python
def recommend_order(item, warehouse, today, run_config):
    # 1. Pull all demand signals inside the commitment horizon
    horizon = run_config.commitment_horizon_days
    open_sos = get_open_so_lines(item, warehouse,
                                 ship_by=today + horizon,
                                 so_types=run_config.cross_dock_so_types)
    committed_qty = sum(so.open_qty for so in open_sos)
    allocated_on_order = sum_allocated_pos(item, warehouse)

    # 2. Pull forecast quantile for this ABC tier
    f = get_forecast(item, horizon)
    q = f.p90 if item.abc == 'A' else f.p75 if item.abc == 'B' else f.p50

    # 3. Compute effective lead time with closures and bias
    vendor = preferred_vendor(item)
    L = effective_lead_time(vendor, today) + vendor.bias_days

    # 4. Branch: committed first, then hedged, then speculative
    uncommitted_demand = max(0, committed_qty - allocated_on_order)

    if uncommitted_demand > 0:
        target_so = earliest_unallocated_so(open_sos)
        slack = (target_so.ship_date - (today + L)).days
        if slack >= 0:
            rec = build_committed_rec(item, uncommitted_demand, target_so,
                                       slack, L, vendor)
        else:
            return mark_cannot_serve(item, target_so, slack)
    else:
        # No open SO — speculation-floor branch
        daily_burn = q / horizon
        floor_days = run_config.speculation_floor_days[item.abc]
        current_position = on_hand_qty(item, warehouse) + allocated_on_order
        target_position = floor_days * daily_burn
        if current_position >= target_position:
            return no_action(item, "Position balanced")
        rec = build_speculative_rec(item, target_position - current_position,
                                     L, vendor)

    # 5. Quantity shaping — MOQ, EOQ, container-fill
    rec.qty = shape_quantity(rec.qty, item, vendor, rec.allocation_type,
                              run_config)

    # 6. Guardrails — concentration, NPV, cash cap
    rec = apply_concentration_limits(rec, run_config)
    rec = apply_npv_check(rec, run_config)
    rec = apply_cash_cap_warning(rec, run_config)

    return rec
```

Each helper is specified below.

### 13.2 Order quantity shaping

Three pressures on the raw demand-driven quantity:

**MOQ floor.** `qty_after_moq = max(raw_qty, item.vendor_moq)`. MOQ is a hard floor — if raw demand is 40 yds and MOQ is 100 yds, the rec goes to 100 and the extra 60 is tagged `allocation_type='speculative'` even inside an otherwise-committed rec (a "committed + MOQ spillover" pattern, stored as a second row in `drp_po_allocations` linked to the same rec).

**EOQ awareness.** Classical Wilson EOQ is computed but used as a *ceiling on freight-consolidation savings*, not a target. The agent prefers smaller, more frequent orders to minimize inventory dollar-days — EOQ just caps how hard to push in the freight-consolidation direction.

**Container-fill economics.** For India/Turkey sourcing where freight is container-based, hitting 85%+ of container capacity (cbm or kgs, whichever binds first) is materially cheaper per yard than 50% fill. The agent computes:

```
rec_cbm = rec.qty * item.cbm_per_unit
vendor_pending_cbm = sum(other_recs_for_same_vendor_this_run)
total_cbm = rec_cbm + vendor_pending_cbm
fill_pct = total_cbm / container_capacity_cbm

if fill_pct < 0.60:
    # Flag for freight consolidation — see NPV check in 13.5
    rec.freight_consolidation_flag = True
elif fill_pct >= 0.85:
    rec.freight_consolidation_flag = False  # already efficient
```

This relies on `StockItem.UsrCbmPerUnit` being populated. Phase 0 diligence: audit coverage — Phase 1 paper trading flags all items missing cbm data so procurement can fill them in against the top 200 by revenue first.

### 13.3 Concentration guardrails

Three limits enforced after order shaping:

| Guardrail | Default | Stored in |
|---|---|---|
| **Per-vendor nightly cap** | 25% of any single nightly-run total $ may go to one vendor | `drp_phase_config.max_vendor_share_per_run` |
| **Per-country nightly cap** | 50% of nightly-run total $ may go to one COO | `drp_phase_config.max_country_share_per_run` |
| **Per-collection committed-qty cap** | Total open POs for any `StockItem.ItemClass` ≤ 4× trailing 90-day velocity | `drp_phase_config.max_collection_overhang_x` |

If a run would breach any cap, the agent sorts candidate recs by `committed_$ desc, speculative_$ asc` and trims the tail speculative recs until the cap holds. Trimmed recs are logged to `drp_recommendations` with `status='trimmed_by_concentration'` so the weekly review can see what was held back.

### 13.4 NPV-aware freight consolidation

Partial-container vs. full-container trade-off:

```
partial_cost = rec_cbm * partial_container_rate_per_cbm
full_cost    = container_flat_rate
savings_if_filled = partial_cost - (full_cost * fill_pct)
holding_cost_of_pulling_forward = sum(
    future_rec.qty * item.unit_cost * daily_cost_of_capital *
    (target_receive_date - (today + L_vendor))
    for future_rec in future_recs_for_same_vendor_within_45d
)

consolidate = savings_if_filled > holding_cost_of_pulling_forward
```

If `consolidate=True`, the agent pulls forward the near-future speculative recs for the same vendor into this run, tags them `allocation_type='speculative'` + `consolidation_reason='freight_npv'`, and logs the savings + holding cost numbers on the recommendation so the weekly review can verify the agent's math is working.

`daily_cost_of_capital` is a config knob (default 0.00033/day ≈ 12%/year pretax). It lives in `drp_phase_config.daily_cost_of_capital` and is the lever procurement tunes as HF's actual financing cost shifts.

### 13.5 Allocated-vs-speculative tagging on every PO line

When a draft PO is written (Phase 2+), each line gets tagged via `drp_po_allocations`:

```
po_nbr, po_line_nbr, inventory_id, qty,
allocation_type,          -- 'committed' | 'hedged' | 'speculative'
so_nbr, so_line_nbr,      -- null for hedged/speculative
cross_dock_status,        -- 'feasible' | 'will_sit' | 'n/a' for spec
consolidation_reason,     -- 'freight_npv' | 'moq_spillover' | null
rationale_text,           -- human-readable line used in approval UI
```

This is the source of truth for the cross-dock hit rate metric. When the container arrives and the line receives, a post-receipt worker checks `(receipt_date - ship_date_for_linked_so) ≤ 7 days` and writes `cross_dock_hit=true|false` back to the same row. The composite cross-dock hit rate reported in the daily brief rolls up from this table.

### 13.6 Soft cash cap (warning, not refusal)

```
projected_working_capital_$ = (
    current_open_po_$ +
    sum(rec.qty * item.unit_cost for rec in tonights_recs)
)

if projected_working_capital_$ > drp_phase_config.soft_cash_cap_usd:
    brief.warnings.append({
        "kind": "cash_cap_breach",
        "projected_$": projected_working_capital_$,
        "cap_$": drp_phase_config.soft_cash_cap_usd,
        "suggestion": "Review and trim speculative recs in tonight's brief",
    })
```

The run still completes and still writes (phase-gated). The warning lives in the Slack brief and in the Vendor Planning Hub until procurement dismisses it. A *hard* cash cap is explicitly not in the design — finance is not Acumatica's job and the agent should never refuse a committed-demand purchase for cash reasons without a human in the loop.

---

## 14. Agent Orchestration

### 14.1 Nightly run structure

Cron: `0 2 * * *` America/New_York (02:00 ET). Lives as a Railway service in `studiob-platform`, service name `drp-agent`. One invocation = one row in `drp_agent_runs` with structured phase tracking:

```
00:00  start                     — insert drp_agent_runs row, status='starting'
00:05  signal_freshness_check    — pull heartbeats from all 17 signals
00:10  signal_pull               — refresh drp_signal_* landing tables
00:30  lead_time_refresh         — mine completed receipts, update stats
01:00  forecast_refresh          — nightly quantile update (weekly: full refit)
01:30  abc_classification_check  — re-run if monthly cadence hit
02:00  recommendation_generation — loop items, build recs, shape, guardrail
02:45  governance_check          — phase gate, write caps, override checks
03:00  writes                    — conditional on phase + governance
03:15  brief_generation          — render Slack DM + canvas
03:30  status='complete', end    — stamp finished_at, write summary
```

Each phase is a distinct Python function with its own try/except; a phase that errors writes `phase_error` into `drp_agent_runs` and the run continues in degraded mode where the downstream phase can tolerate it (forecast failure → recs still run against the previous forecast), or aborts cleanly where it cannot (signal_pull failure on a primary signal → abort).

### 14.2 Signal freshness gate

Three possible run states, computed at phase 2 and stored in `drp_agent_runs.run_state`:

| State | Condition | Effect |
|---|---|---|
| **healthy** | All primary signals <4h stale, all exogenous signals <24h stale | Full nightly proceeds, recommendations written per phase |
| **degraded** | Any exogenous signal 24-72h stale OR any primary 4-12h stale | Run proceeds, forecast bands widened (×1.2-1.5), brief includes "Signal Degraded" banner, approval UI requires human ack before any writes |
| **blocked** | Any primary signal >12h stale OR signal_pull phase failed | Run aborts at phase 2, writes `drp_agent_runs.status='blocked'`, posts Slack alert to `#procurement-alerts`, no further phases execute |

Primary signals: 1 (velocity), 2 (open SOs), 3 (open POs), 4 (on-hand), 6 (ItemWarehouse), 7 (StockItem), 9 (containers). Exogenous: 10 (Shopify), 11 (HubSpot), 12 (stockouts), 13 (ack emails).

### 14.3 Phase-gated write paths

Section 8 defined the three phases. The write path in phase 14.1 step `03:00 writes` dispatches on `drp_phase_config.phase`:

```python
def execute_writes(run_id, recs, phase_config):
    if not phase_config.write_enabled:
        mark_recs_paper_only(recs); return

    if phase_config.phase == 'advisor':
        mark_recs_paper_only(recs); return

    if phase_config.phase == 'draft_po':
        write_itemwhse_parameters(recs, phase_config)  # ROP/SS/Max + ABC
        write_vendor_lead_times(phase_config)          # weekly only, 12.8
        create_draft_pos(recs, phase_config)           # status='draft' in Acu
        return

    if phase_config.phase == 'autopilot':
        write_itemwhse_parameters(recs, phase_config)
        write_vendor_lead_times(phase_config)
        draft = [r for r in recs if r.item.abc not in phase_config.autopilot_abc_classes]
        release = [r for r in recs if r.item.abc in phase_config.autopilot_abc_classes]
        create_draft_pos(draft, phase_config)
        create_and_release_pos(release, phase_config)
        return
```

Every write is wrapped in a try/except that rolls the run into `partial_write_failure` status if any Acumatica write returns non-2xx. The rolled-back run is re-runnable via a replay command (14.7).

### 14.4 Daily brief generation

Two artifacts per run:

**Slack DM to procurement-shared** (and optionally to Kevin during phases 1-2):
- One-liner: "DRP run {id} — {phase} — {healthy/degraded/blocked}"
- Top 5 committed recs (vendor, qty, $, SO linkage)
- Top 5 speculative recs (item, reason)
- Cash cap status
- Concentration flags
- Signal health traffic light
- Link to the canvas

**Slack canvas in the procurement channel**, rewritten each run:
- Full recommendation table (top 50 by $, collapsible)
- Exceptions (trimmed by guardrails, blocked by override, cannot-serve)
- Metrics panel: days of cover trend, cross-dock hit rate trend, dead inventory count, speculation $ trend
- "What the agent disagreed with staff on" — top 10 items where the agent's ROP differs from the current ItemWhse value by ≥30%
- A weekly rollup of forecast MAPE, lead-time bias, override agreement rate

Brief rendering reuses the Slack canvas primitives already in webhook-router.

### 14.5 Approval workflows (phase 2)

Draft POs created by the agent land in Acumatica as `POOrder.Status='H'` (On Hold / Draft). Human approval happens inside Acumatica — procurement opens the PO, reviews, and clicks Release. The agent is not in the approval loop, by design: approval is an Acumatica-native operation and the agent only supplies the draft.

Two enhancements:

1. **`drp_recommendations.reviewed_at` backfill.** A nightly tail job queries Acumatica for all draft POs that transitioned from Hold to Open since yesterday and fills in `reviewed_at` + `reviewed_by` on the linked recommendation. This gives the agent the override-agreement rate data it needs to promote / demote phases.

2. **Vendor Planning Hub (SB501100) review queue.** Instead of opening 30 individual POs, procurement opens the hub, sees the ranked to-do list, and bulk-approves by vendor. The hub screen is Acumatica-native, so the approval action is still a real PO release — the hub is just a grouping UI layered over `drp_recommendations` joined to `POOrder`.

### 14.6 Exception routing

| Exception | Where it lands | Who gets paged |
|---|---|---|
| Blocked run (signal failure) | Slack `#procurement-alerts` + email to Kevin | Kevin |
| Partial write failure | Slack `#procurement-alerts`, `drp_agent_runs.status='partial'` | Kevin |
| Concentration cap breach | Brief warning section, canvas | Procurement shared (daytime) |
| Cash cap breach | Brief warning section, canvas | Procurement shared (daytime) + Kevin DM (phase 2+) |
| Forecast drift > red-flag threshold (Section 15) | Brief + canvas + `drp_phase_config` auto-revert | Kevin DM |
| Override storm (>20 overrides in 7 days) | Brief + canvas + auto-revert phase | Kevin DM |
| Cannot-serve rec (slack < 0) | Brief top section, canvas | Procurement shared |

Exception routing uses the Slack identity stored in `drp_phase_config.exception_routes` (JSON map) so contact lists can be edited without code changes.

### 14.7 Run logging and replay

Every phase writes a structured event to `drp_agent_run_events`:

```
run_id, phase_name, step_name, started_at, finished_at,
status ('ok'|'warn'|'error'|'skipped'),
input_hash, output_hash, rows_read, rows_written, error_text
```

A **replay command** (`drp-agent replay <run_id>`) re-runs the same phase sequence with the *input_hash*-referenced snapshot of signals, so post-mortems can reproduce exactly what the agent saw. This is critical for phase-promotion decisions (re-running last week's "advisor mode" with "draft PO" logic to see what would have happened). Snapshots are held by DataLifecycleManager — hot 90d, warm 365d.

---

## 15. Governance & Monitoring

### 15.1 Safety rails (complete specification)

Rails are enforced in the governance phase (14.1 step `02:45`). Every rec passes through each rail in order; failing any rail either *trims* the rec, *blocks* the rec, or *aborts* the run. All outcomes logged to `drp_recommendations.status`.

| # | Rail | Trigger | Action |
|---|---|---|---|
| R1 | `OverrideReplenishmentSettings=true` on ItemWarehouse | Item is hard-opted-out | Skip item entirely |
| R2 | Active `drp_manual_overrides` row | Human override present | Compute rec but set `status='blocked_by_override'`, no write |
| R3 | Single-rec ROP change >20% | Delta too large | `status='review_required'`, no write |
| R4 | Run-level write $ change > `max_daily_po_value_usd` (default $500k) | Aggregate too large | Pause + page Kevin, no writes this run |
| R5 | Forecast p90 < p10 or NaN anywhere | Forecast invalid | Abort run, blocked state |
| R6 | Effective lead time = 0 or negative | Lead-time invalid | Skip item, log warning |
| R7 | Vendor with no `LeadTimedays` populated after Phase 0 | Data gap | Skip item, flag in brief |
| R8 | Concentration cap breach (13.3) | Trim tail spec recs | Log trimmed recs |
| R9 | Cash cap breach (13.6) | Warning only | Continue, flag in brief |
| R10 | `drp_phase_config.write_enabled=false` | Kill-switch | No writes, recs saved as paper |
| R11 | Acumatica write returns non-2xx | Network/validation error | Rollback run, mark partial |
| R12 | Item newly created (<4 weeks) AND rec is speculative | Cold-start risk | Skip, log as `too_new_to_speculate` |

R1-R12 are code-enforced. Tuning knobs (R3 threshold, R4 cap, R8 limits, R9 cap) live in `drp_phase_config` so procurement can tighten/loosen without deploys.

### 15.2 Kill-switch state machine

```
                  ┌─────────────────────────────┐
                  ↓                             │
             ┌─────────┐    promote    ┌────────────┐    promote    ┌───────────┐
  initial → │ advisor │ ────────────→ │  draft_po  │ ────────────→ │ autopilot │
             └─────────┘                └────────────┘                └───────────┘
                  ↑                             ↑                             │
                  │  ←─────── auto-revert (red flag) or manual revert ────────┘
```

Transitions are explicit rows in `drp_phase_config_transitions`:

```
transition_at, from_phase, to_phase, reason, actor
                                              ('human:kevin'|'auto:red_flag:mape_breach'|...)
```

**Promote conditions** (manual only):
- advisor → draft_po: 60 days of paper trading completed, forecast MAPE_28d pooled <30%, override agreement rate >70%, Kevin approval in Slack
- draft_po → autopilot: 60 days of drafted POs completed, human-accept rate >80%, no R4 breaches, Kevin approval in Slack

**Auto-revert conditions** (programmatic):
- Forecast MAPE_28d pooled >50% for 3 runs in a row → revert one phase
- Override storm: >20 new human overrides in 7 days → revert one phase
- Signal blocked state persisting across 3 nightly runs → revert one phase
- R4 (run-level $ cap) breach → revert one phase
- Drawdown (metric defined 15.4) > threshold → revert one phase

Reverts are silent to autopilot → draft_po, loud (Slack DM + canvas banner) going to advisor.

### 15.3 Drift detection

Two drifts the agent watches for every run, stored in `drp_drift_state`:

**Forecast drift.** Rolling 28-day pooled MAPE per class. If MAPE trend is monotonically increasing for 14 days AND absolute MAPE crosses the phase-gated threshold (40% advisor, 35% draft_po, 30% autopilot), the agent emits a `forecast_drift` event and widens bands for that class by ×1.2 until MAPE recovers.

**Lead-time drift.** Rolling CUSUM (see 12.4) per vendor. A declared regime change on any vendor whose total open PO value exceeds `drp_phase_config.significant_vendor_po_usd` (default $50k) triggers a `lead_time_regime` event and auto-flags all recs for that vendor as `status='lead_time_regime_review'` until the regime is manually labeled by a human.

Both drift events feed the brief and the Kevin-DM routing in 14.6.

### 15.4 Weekly human review

Every Monday 09:00 ET, Kevin + procurement shared review (45 min):

**Agenda, in order:**
1. **Phase health** — current phase, days in phase, any auto-reverts since last review
2. **Metrics scoreboard** — primary KPIs (15.5) vs trailing 4 weeks, flagged deltas
3. **Recent exceptions** — anything that hit `#procurement-alerts` in the past week
4. **Flagged outliers awaiting verdict** — 3σ lead-time samples, regime labels
5. **Override aging** — which of the 180-day ROP/SS/Max overrides are approaching expiry and whether the agent now agrees (silent takeback) or disagrees (enqueue for decision)
6. **Shadow ABC scheme standings** — composite scores of shadow schemes, promote/retire decisions
7. **Forecast MAPE by class** — trend lines, calibration
8. **Freight consolidation audit** — recs tagged `consolidation_reason='freight_npv'`, did the NPV math hold after receipt?
9. **Cross-dock hit rate** — primary metric, trend, miss attribution
10. **Promotion / demotion decisions** — any manual phase changes? document reasons

The review itself runs off a rendered Slack canvas (same primitives as daily brief) auto-generated at 08:00 each Monday from `drp_weekly_review` — just a specialized query over the same tables. No new infra.

### 15.5 Success metrics

The primary KPIs — what determines whether DRP is actually working:

| Metric | Target | How computed |
|---|---|---|
| **Working capital $** | -15% vs baseline (month 6) | sum(OnHand * StdCost) + sum(OnOrder * StdCost) |
| **Days of cover (aggregate)** | 45-60 days steady, down from ~90 baseline | total_position_$ / avg_daily_cogs_90d |
| **Cross-dock hit rate** | ≥40% by month 6, ≥60% by month 12 | sum(cross_dock_hit=true) / sum(all_receipts) in window |
| **Dead inventory $** | -25% vs baseline (month 6) | sum(unit_cost * qty) where last_shipment > 90d ago |
| **Stockout count** | ≤baseline, ideally -50% | count(drp_lost_demand_events) by week |
| **Override agreement rate** | ≥70% baseline → rising | count(overrides where agent within 10% on expiry) / count(expired overrides) |
| **Forecast MAPE_28d (pooled by class)** | <30% by month 6 | avg(abs(forecast - actual) / actual) |
| **Forecast calibration (p10-p90)** | 70-85% actuals inside band | count(p10 ≤ actual ≤ p90) / count(forecasts with 28d actuals) |

Service level (98% A, 95% B, 90% C) is a constraint — tracked as a floor, not a headline KPI. It shows in the brief only when it's at risk of breaching.

### 15.6 Red-flag auto-revert conditions

Consolidated list of what flips the agent backwards a phase without human action:

| Condition | Threshold | Revert |
|---|---|---|
| Forecast MAPE_28d pooled | > 50% for 3 runs | 1 phase |
| Override storm | >20 new overrides in 7d | 1 phase |
| Signal blocked | ≥3 consecutive blocked runs | 1 phase |
| R4 run-level $ cap | Any single breach | 1 phase |
| Drawdown (dead_inv_$ + speculation_$ increase) | >10% WoW for 2w | 1 phase |
| Cross-dock hit rate | <20% for 14 consecutive days, post month 3 | 1 phase |
| Manual kill (`write_enabled=false`) | Any | Immediate to advisor |

Autopilot → draft_po and draft_po → advisor are the reversion paths. Never skips two phases at once — a second red flag during a recovery state forces the revert from draft_po to advisor on top of whatever is live.

---

## 16. Open Questions

Items deferred to Phase 0 empirical measurement or to a future session:

1. **po_receipts schema extension** — CONFIRMED RETRACTED. Table is dock-side, not PO lifecycle. 4 timestamps live in Acumatica `POOrder` only.
2. **HubSpot deal pipeline signal granularity** — does the existing sync capture per-SKU deal line items or only aggregate deal values? Phase 0.1 diligence.
3. **Shopify sync granularity** — does existing integration capture per-SKU events or order-level only?
4. **Procurement shared inbox identity** — single `purchasing@heritagefabrics.com` address or multiple individual inboxes? Affects email watcher scope.
5. **SO types to exclude from cross-dock matching** — default to CO/SO only, excluding RM/IN/TR. Confirm with ops.
6. **Actual commitment horizon per customer class** — measure empirically in Phase 0. B2B retailer, designer, hospitality, wholesale contract all likely have different horizons.
7. **iframe vs external link for SB501200** — starting with external link, revisit if UX complaints warrant iframe.
8. **7-stage lifecycle timeline stages** — are PLACED / ACKED / FACTORY READY / SHIPPED / IN TRANSIT / ARRIVED PORT / CUSTOMS / DELIVERED the right set? Need ops input.
9. **`StockItem.UsrCbmPerUnit` coverage** — 13.2 requires per-item cbm for freight consolidation. How many of the 2,242 DRP-eligible items have it populated today? If <50%, Phase 0 includes a "top 200 by revenue" backfill task.
10. **Shadow-scheme promotion authority** — does procurement alone promote a shadow ABC scheme to active, or does Kevin approve? Phase 0 decision, affects weekly review format.

---

## 17. What's Next

Design is locked. Implementation proceeds against the Phase 0 plan in `docs/plans/2026-04-10-drp-phase-0-implementation-plan.md` (written via `superpowers:writing-plans` alongside this doc).

**Sequence:**
1. Phase 0 streams (5-6 weeks, parallel) — data foundation, custom fields, MOQ intake, lead-time learning, ABC baseline, stockout logger, email watcher
2. Phase 1 (months 1-2) — advisor / paper-trading, runs nightly, writes to `drp_recommendations` only
3. Phase 0 completes while Phase 1 runs
4. Phase 2 (months 3-4) — draft POs + ItemWhse parameter writes, after promote decision
5. Phase 3 (month 5+) — C-item autopilot, after second promote decision

Design changes after this point go through RFCs appended as Section 18+ amendments. The doc is a living artifact but the decisions in Sections 0-15 are baseline.

---

## 18. Implementation Notes

**Branches:** Phase 0 work lives across 5 repos. Each stream gets its own branch prefixed `drp/phase0-<stream>`:
- `acumatica-ci-cd` — `drp/phase0-custom-fields`, `drp/phase0-gi-registrations`
- `heritage-wms` — `drp/phase0-moq-intake`, `drp/phase0-lead-time-learning`, `drp/phase0-forecast-state`
- `webhook-router` — `drp/phase0-email-watcher`, `drp/phase0-signal-ingestion`, `drp/phase0-dlm-policies`
- `cs-order-entry` — `drp/phase0-stockout-logger`
- `studiob-api` — `drp/phase0-drp-routes`

**Cross-repo dependencies:**
- `acumatica-ci-cd` — `AesthetikContainers` custom fields deploy, 4 GI registrations via SM208030
- `heritage-wms` — new pages/routes/services/tables, forecast engine service, lead-time learner extension
- `webhook-router` — email watcher, DLM policy registrations, signal ingestion workers
- `cs-order-entry` — stockout event logger (~40 lines)
- `studiob-api` — new gateway routes for the 4 DRP GIs and the DRP-specific endpoints

**Phase 0 streams can run in parallel** with Phase 1 (advisor mode) because Phase 1 doesn't need any of the Phase 0 outputs. By the time Phase 1 ends at month 2, Phase 0 should have landed everything needed for Phase 2.

**Acumatica customization deploys** (custom fields in 18.1) restart the app pool and must happen off-hours (before 06:00 ET or after 18:00 ET). All other Phase 0 work is in heritage-wms / webhook-router / cs-order-entry and is zero-downtime.

**Reuse-over-rebuild audit:** every Phase 0 task that proposes new code must state what it's reusing. Net-new code is justified in the implementation plan task-by-task.

---

## 19. References

- Prior analysis doc (superseded by this one): `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-current-state-and-approaches.md`
- Prior session prompt: `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-09-drp-and-date-population-investigation.md`
- This session prompt: `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-10-drp-design-continuation-sections-4-8.md`
- Phase 0 implementation plan: `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-10-drp-phase-0-implementation-plan.md`
- KB crawler: `/Users/kevin/dev/acumatica-ci-cd/scripts/kb-crawler/` — 51 Acumatica help guides, 30K chunks in `studiob-knowledge` Qdrant (topic=acumatica-help-wiki)
- Container tracking project memory: `/Users/kevin/Library/CloudStorage/OneDrive-HeritageFabrics,LLC/memory/project_container-tracking.md`
- Vendor scorecard service: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/vendor-scorecard-service.ts`
- Smart parser stack: `/Users/kevin/code/studio-b/heritage-fabrics/heritage-wms/src/services/{smart-parser,packing-slip-ocr,column-mapper,sku-matcher,learning-store,import-learning}.ts`
- Data lifecycle manager: `/Users/kevin/dev/webhook-router/src/lib/data-lifecycle/`
- SB501000 ASPX: `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Pages/SB/SB501000.aspx`
- Fabric Tracker (SO→PO→Container walker, reusable primitive): `/Users/kevin/dev/webhook-router/src/portal/tracker-api.ts`

---

**End of design doc. Sections 0-15 LOCKED. Implementation begins in Phase 0.**
