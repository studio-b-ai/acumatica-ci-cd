# Heritage Fabrics DRP — Current-State Analysis + Approach Options

**Date:** 2026-04-09
**Status:** REVIEW — not yet approved
**Author:** Claude (procurement-manager lens) + Kevin
**Next step:** Kevin reviews, picks approach (A/B/C), then full design doc

---

## 1. Context

- Heritage Fabrics went live on Acumatica August 2025 (~8 months ago).
- Prior to go-live: all reordering was manual and by gut feel ("sticking your finger in the air").
- Post go-live: reorder points were introduced but only partially populated.
- Business goal: tune DRP (Distribution Requirements Planning) so the inbound flow of goods matches the long procurement cycle (India 12-16 weeks, Turkey 8-12 weeks), with an agent that is always forecasting and feeding DRP.

## 2. Current-state diagnosis (from Acumatica production tenant, 2026-04-09)

### 2.1 Reorder-point coverage — item-warehouse level

| Scope | Items | RP Set | SS Set | Min/Max Method |
|---|---:|---:|---:|---:|
| Main warehouse (WH 99) | 2,164 | 1,226 (57%) | 1,224 (57%) | 1,293 (60%) |
| All real warehouses | 2,298 | 1,327 (58%) | 1,325 (58%) | 1,401 (61%) |
| Everything including SAMPLES | 4,341 | 1,327 (31%) | 1,325 (31%) | 1,401 (32%) |

- **888 items in WH 99 have `ReplenishmentSource=Purchase` but NO reorder point.** These items are being bought but not tracked by the replenishment engine.
- **0 of 4,341 rows have `OverrideReplenishmentSettings=true`.** Nobody has tuned a single item at the warehouse level. All numbers are whatever got typed at the StockItem template level at go-live.

### 2.2 Reorder-point distribution (where set)

```
min=1  p25=75  median=100  p75=225  max=14,000
  1-10:     7 items
  11-50:   19 items
  51-100: 610 items   ← biggest bucket, tight median cluster
  101-500: 470 items
  501-1000: 91 items
  1000+:   29 items
```

**Interpretation:** The tight clustering at 100 and the round-number buckets (100, 200, 250, 500) are the signature of **gut-feel entry, not calculation**. A calculated ROP (`avg_demand × lead_time + safety_stock`) would rarely land on round numbers.

### 2.3 Vendor lead time — the root cause

| Metric | Value |
|---|---:|
| Total vendors | 594 |
| Active vendors | 296 |
| **Vendors with `LeadTimedays > 0`** | **15 / 594 (2.5%)** |
| Active vendors with lead time set | **~15 / 296 (5%)** |
| Vendors with `VendorClass = "TBD"` | 435 (73%) |
| Lead-time median (of the 15 populated) | 60 days |
| Lead-time range (populated) | 56 – 98 days |

Acumatica's built-in replenishment calculator (`IN508500`) uses:

```
Safety Stock = Z(service_level) × √(LT × demand_variance + demand² × LT_variance)
Reorder Point = avg_daily_demand × LT + Safety Stock
```

**Without lead times on 98% of vendors, the calculator is mathematically disabled.** This is precisely why the 1,327 existing reorder points were entered manually — Acumatica literally could not compute them.

### 2.4 Item-class distribution (2,242 real DRP-eligible items)

| Class | Count | Implied procurement cycle |
|---|---:|---|
| SAMPLES | 1,961 | Exclude (not replenishable) |
| **COO INDIA** | **1,430** | **~12-16 weeks** (mfg + container + customs) |
| **COO TURKEY** | **734** | **~8-12 weeks** |
| FERNCREST-MEDLINE | 78 | Domestic (1-2 weeks) |

The class taxonomy is **accurate** but **not connected to the planning engine.** You already know each item's rough lead-time profile by its class — that intelligence just isn't wired into `Vendor.LeadTimedays` or `ItemWarehouse` parameters.

### 2.5 Existing infrastructure that helps (don't rebuild)

- **AesthetikContainers customization** with `UsrContainer`, `UsrContainerPOLink`, ETA propagation to PO lines (SB501000 on test).
- **Fabric Tracker** (`webhook-router/src/portal/tracker-api.ts`) — pure-function SO→PO→Container walker with 10 passing tests. Inverse walk (InventoryID → PO → Container) is the missing primitive.
- **studiob-api gateway** — wraps Acumatica REST for cs-order-entry, webhook-router, heritage-wms. Current gap: api-bot blocked on `PurchaseOrder` (403), so PO data must be read via `InventoryAllocDetEnq` inquiry or `ContainerTracking` endpoint.
- **Shopify + EDI + cs-order-entry** feeding order intake.
- **HubSpot ↔ Acumatica** 15-minute sync.
- **Qdrant `studiob-knowledge`** — includes the full Acumatica help wiki (51 guides, 30K chunks) covering all replenishment/DRP docs.

### 2.6 Blind spots — what the gateway cannot currently see

| Blind spot | Why | Fix |
|---|---|---|
| Historical sales velocity per SKU | `SalesOrder` gateway query returns only 7 rows (implicit filter) | Expose `SOShipLineSplit` or `INTran` via a Generic Inquiry |
| Current qty on hand per item/warehouse | No `InventorySummary` endpoint, `$expand=WarehouseDetails` drops silently | Register `InventoryAllocDetEnq` inquiry via SM208030 |
| Open PO pipeline depth | api-bot blocked on `PurchaseOrder` (403) | Expand api-bot role, OR route through `ContainerTracking` |
| Stockout incidents | Needs historical `INTran` | Same GI path as velocity |
| Lead-time variance | Only 15 data points in `Vendor.LeadTimedays` | Mine `UsrContainer.ATA` vs `UsrContainer.ETA` deltas |

**Phase 0 of any DRP rollout has to unblock these reads.** An agent that can't see yesterday's shipments is an agent doing astrology.

---

## 3. Design decisions locked in (2026-04-09)

| Decision | Choice |
|---|---|
| **Service level policy** | 98% A-items / 95% B-items / 90% C-items (tiered by ABC classification) |
| **MOQ model** | Per-item MOQ (vendor sets per-SKU minimums; containers mixed freely) |
| **Agent autonomy** | Phase-gated — advisor month 1-2 → draft POs month 3-4 → C-item autopilot month 5+ |
| **Cash constraint** | Soft cap — agent warns if projected on-order + on-hand $ exceeds threshold; human decides |

---

## 4. Three implementation approaches

### Approach A — Pure native Acumatica (minimal code)

Fix data quality, then let Acumatica's built-in replenishment engine do the work.

**Steps:**
1. Populate `Vendor.LeadTimedays` for all 296 active vendors.
2. Create three `ReplenishmentClass` records: `COO_INDIA` (98%), `COO_TURKEY` (95%), `DOMESTIC` (90%).
3. Configure `Moving Average` or `Exponential Smoothing` as forecast model on each class.
4. Configure `Replenishment Seasonality` records (IN206600) for known collection cycles.
5. Schedule `IN508500 — Calculate Replenishment Parameters` nightly.
6. Schedule `PO503000 — Prepare Replenishment` nightly for PO suggestions.
7. Humans approve suggestions in the PO Preparation screen.

**Pros:** Minimal new code. Upgrade-safe. All calculations in one system.
**Cons:** Basic forecast models (MA + ES). No cross-signals (Shopify, HubSpot, returns). No learning loop. Container ETA drift not consumed. Doesn't answer the `cs-order-entry` "backordered — Apr 23" problem (still needs custom walker).

**Verdict:** Fills the 43% gap. Solid floor but leaves accuracy on the table.

---

### Approach B — External forecasting agent → Acumatica ⭐ RECOMMENDED

**Idea:** Agent is the brain. Acumatica is the book of record. Agent pulls every signal, runs modern forecast, writes `ReorderPoint/SafetyStock/MaxQty` directly into `ItemWarehouse`. Acumatica behaves normally with better numbers.

**Architecture:**

```
      ┌─────────────────────────────────────────────┐
      │        DRP Agent (nightly @ 2am ET)          │
      │                                              │
      │  Signal Ingestion                            │
      │   • SO history (INTran / SOShipLineSplit)   │
      │   • Shopify sessions + add-to-cart           │
      │   • UsrContainer ETA↔ATA drift                │
      │   • cs-order-entry stockout events           │
      │   • HubSpot deal stage velocity              │
      │   • Sampling rate per SKU                    │
      │                                              │
      │  Forecast Engine                             │
      │   • Exponential smoothing + Holt-Winters     │
      │   • Seasonality (collection cycles)          │
      │   • ABC classification refresh               │
      │   • Lead-time distribution estimate          │
      │                                              │
      │  DRP Math                                    │
      │   ROP = μ_d·LT + Z(SL)·√(LT·σ_d² + μ_d²·σ_LT²)│
      │   Max = ROP + EOQ (or MOQ if larger)         │
      │                                              │
      │  Output Gates (phase-gated)                  │
      │   Month 1-2: Slack brief + Canvas            │
      │   Month 3-4: Draft POs in Acumatica          │
      │   Month 5+:  Auto-release C-items            │
      └─────────────────│───────────────────────────┘
                        ↓
         ┌───────────────────────────────────────┐
         │ Writes to Acumatica via studiob-api   │
         │  • ItemWarehouse.ReorderPoint          │
         │  • ItemWarehouse.SafetyStock           │
         │  • ItemWarehouse.MaxQty                │
         │  • PurchaseOrder (Draft) phase 2+      │
         └───────────────────────────────────────┘
```

**Why this is the recommendation:**
1. Directly delivers "always forecasting, feeding DRP." Native approach has no learning loop.
2. Phase-gated autonomy maps perfectly (advisor → draft → autopilot).
3. Better signal than Acumatica can see alone (Shopify, HubSpot, container drift).
4. Lead-time bias correction from `UsrContainer.ATA` vs `UsrContainer.ETA` is a free signal no native tool captures.
5. Acumatica stays the system of record — we just populate fields better.
6. Same pipeline solves the `cs-order-entry` "Backordered — Apr 23" badge (uses the same lead-time + allocation walker).

**Cons:**
- Writes to Acumatica need governance (kill-switch, diff log, >20% change debounce).
- ~1,500-2,500 lines agent code + ~300 lines gateway write plumbing.
- Still needs Phase 0 (vendor lead times must exist or be derived from 3-6 months of ATA history).

---

### Approach C — Hybrid (native for C-items, agent for A/B)

Split the work by ABC classification. C-items go through `IN508500`, A/B items go through the agent.

**Pros:** ~60% of Approach B's code volume. Natural fit with the tiered service levels.
**Cons:** Two systems of truth for replenishment parameters. Training burden ("which items are agent-managed?"). Fractured learning loop. Agent only trains on the high-value items where cross-signals help most — which is actually the right carve-out, but operational complexity is high.

**Verdict:** Legitimate middle ground but not recommended. Split-brain ops > code savings.

---

## 5. Phase 0 prerequisites (applies to ALL approaches)

Before any approach can work:

1. **Unblock gateway reads:**
   - Register `InventoryAllocDetEnq` inquiry via SM208030
   - Either grant api-bot `PurchaseOrder` read OR expose a wrapped endpoint via the ContainerTracking customization
   - Expose a Generic Inquiry for `SOShipLineSplit` (velocity) and `INTran` (stockout events)

2. **Baseline vendor lead times:**
   - 3-month mining job reads `UsrContainer.ETA` vs `UsrContainer.ATA` and computes per-vendor actual lead times
   - Populate `Vendor.LeadTimedays` from mined data
   - For vendors with no container history, use item-class defaults (INDIA=105, TURKEY=75, DOMESTIC=7 days)

3. **Data quality pass on 888 "purchased but no ROP" items in WH 99:**
   - Classify each: active SKU? discontinued? new? sample escapee?
   - Active ones get brought into the replenishment scope; inactive ones get `ReplenishmentSource=None` explicitly

4. **ABC classification:**
   - Compute ABC buckets from 12 months of sales history
   - Store in `StockItem.ABCCode` (field already exists)
   - Feed service-level tiers off this

---

## 6. Open questions (not blocking approach choice)

1. **Forecast horizon:** 26 weeks? 52 weeks? Tied to collection cycle length.
2. **Container-load threshold:** at what fill rate do we release a multi-item PO from Turkey vs wait for more items to batch? (MOQ answer was per-item — but container economics still influence timing.)
3. **Who owns DRP kill-switch?** (Procurement lead? Kevin? Ops?)
4. **Where does the agent run?** (Railway service? Scheduled task? AcuDev agent extension?)
5. **Review cadence for auto-generated POs:** daily morning stand-up? Or async Slack channel?

---

## 7. Next step

**Kevin reviews this doc → picks Approach A/B/C → Claude writes the full design doc → implementation plan → ship.**

If Approach B is approved, the full design doc will cover:
- Data model (new tables, schema changes, Qdrant collections)
- Signal ingestion pipeline (source-by-source spec)
- Forecast engine (algorithm choice + hyperparameters + seasonality model)
- DRP math module (ROP/SS/Max formulas, ABC tiering, class-specific Z-scores)
- Agent orchestration (schedule, triggers, kill-switches, audit log)
- Phase rollout (month 1-2 advisor, 3-4 draft, 5+ autopilot)
- Integration with existing infra (studiob-api gateway writes, container ETA hooks, cs-order-entry backorder badge)
- Monitoring & success metrics (forecast accuracy, service level achieved, inventory turns, stockout reduction)
- Governance (kill-switch, diff log, change debounce, audit trail)
