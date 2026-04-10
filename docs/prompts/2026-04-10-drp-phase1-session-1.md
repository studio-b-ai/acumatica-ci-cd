# DRP Phase 1 — Paper Trading Advisor (Session 1)

**Prior session ended:** 2026-04-09 (Session 6 — Phase 0 completed)
**Session 6 outcome:** C.2b/C.3/C.4 shipped (PRs #114 + #115 merged). Phase 0: 24/25 code-complete. H.1 (DLM) deferred.
**Phase 0 scoreboard at handoff:** 24/25 merged + deployed. All data foundation in place.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md` — project memory (updated by session 6)
2. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — locked design doc (sections 0-19), especially:
   - §8 Phase-Gated Rollout (line ~360) — Phase 1 = paper trading
   - §6 Signal Ingestion — 17 signals, freshness matrix
   - §9 Backtesting Framework — paper trading as first backtest
   - §10 Cross-Dock-First Logic — agent ordering algorithm
   - §5.2 Postgres tables — `drp_agent_runs`, `drp_recommendations`, `drp_forecast_state`, `drp_phase_config`
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — full memory index

## What Phase 1 IS

Phase 1 = "Paper Trading Advisor" (months 1-2). The agent:
- Runs nightly
- Reads all signals (GIs, velocity, inventory, POs, SOs, containers, lead times)
- Computes recommendations (ROP, safety stock, max qty, reorder suggestions)
- Writes to `drp_recommendations` table (NOT to Acumatica)
- Posts a daily brief to Slack
- `drp_phase_config.phase = 'advisor'`, `write_enabled = false`

Humans review the brief, manually apply recommendations they agree with, and the backtester tracks agreement rate.

## Phase 1 deliverables (by component)

### 1. Database migrations (aesthetik-platform)

New tables needed (from §5.2):
- `drp_agent_runs` — one row per nightly execution, config snapshot, signal freshness
- `drp_recommendations` — per-item recs: before/after values, rationale, status (pending/accepted/rejected/expired)
- `drp_forecast_state` — persistent per-item forecast model state (ES/Holt-Winters coefficients)
- `drp_phase_config` — singleton config row with kill-switches, phase, service levels, thresholds
- `drp_signal_inventory_snapshot` — nightly on-hand/allocated/on-order snapshot
- `drp_signal_open_so_cache` — open SO commitments cache
- `drp_signal_open_po_cache` — open PO lines cache
- `drp_signal_velocity_cache` — sales velocity history cache

### 2. Signal ingestion workers (aesthetik-platform)

Workers that pull data from Acumatica GIs (via studiob-api gateway) into local Postgres caches:
- **velocity-sync** — pulls DRP_VelocityHistory GI → `drp_signal_velocity_cache` (nightly)
- **inventory-sync** — pulls InventoryAllocDetEnq → `drp_signal_inventory_snapshot` (nightly)
- **so-sync** — pulls DRP_OpenSOCommitments → `drp_signal_open_so_cache` (nightly)
- **po-sync** — pulls DRP_OpenPOLines → `drp_signal_open_po_cache` (nightly)
- **item-warehouse-sync** — pulls ItemWarehouse params → local cache (nightly)

Each worker:
- Uses `createAcumaticaClient()` in gateway mode
- Calls `client.query('GenericInquiry/{giName}', { ... })` or inquiry endpoint
- Upserts to local Postgres table
- Records freshness timestamp

### 3. Forecast engine (aesthetik-platform)

Core math service `src/services/drp-forecast-engine.ts`:
- Exponential smoothing (ES) as v1 model
- Reads velocity cache + lost demand events
- Produces per-item demand forecast (daily/weekly buckets)
- Persists model state to `drp_forecast_state`
- Seasonality: pooled class-level from `drp_class_seasonality` (pre-seeded or computed)

### 4. Recommendation engine (aesthetik-platform)

Core service `src/services/drp-recommendation-engine.ts`:
- Reads: forecast, on-hand, on-order, lead time distributions, MOQs, ABC class
- Computes: target ROP, safety stock, max qty per (item, warehouse)
- Applies: MOQ shaping, cross-dock-first preference, speculation guardrails
- Writes: `drp_recommendations` rows with before/after/rationale
- Safety: single-run change >20% → flag for review

### 5. Nightly orchestrator (aesthetik-platform)

Service `src/services/drp-nightly-orchestrator.ts`:
- Creates `drp_agent_runs` row
- Checks signal freshness (healthy/degraded/blocked)
- Runs signal sync workers
- Runs forecast engine
- Runs recommendation engine
- Generates daily brief (markdown)
- Posts brief to Slack channel
- Records run completion + metrics

### 6. Daily brief + Slack integration

- Markdown-formatted daily brief: top-N ROP changes, new stockout risks, container ETAs, override conflicts
- Posted to a designated Slack channel via existing webhook-router Slack integration
- Brief includes: run ID, signal freshness status, recommendation count, top changes, warnings

### 7. Phase config + kill switch

`drp_phase_config` table + admin route:
- `phase`: 'advisor' | 'draft_po' | 'autopilot'
- `write_enabled`: boolean (false for Phase 1)
- `max_daily_po_value_usd`: spending cap
- `max_single_change_pct`: 20 (flag threshold)
- `service_level_a/b/c`: target service levels per ABC class
- `speculation_floor_days_a/b/c`: minimum days of cover
- Admin route: `GET/PUT /api/drp/config`

### 8. H.1 DLM policies (deferred from Phase 0)

Register retention policies in webhook-router's DataLifecycleManager:
- `drp-recommendations`: hot 90d, warm 365d, cold GCS
- `drp-lead-time-samples`: hot 365d, warm 1095d, cold GCS
- `drp-forecast-state`: hot 30d, warm 365d (weekly snapshots)
- `drp-agent-runs`: hot 90d, warm 365d

## Repos in play

- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` — no new Acumatica work expected in Phase 1
- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` — primary repo (migrations, workers, engines, orchestrator)
- `webhook-router` at `/Users/kevin/dev/webhook-router/` — H.1 DLM policies, Slack brief posting
- `studiob-api` — verify route availability: `GET /api/v1/acumatica/inquiry/{name}` for GI queries

## Existing Phase 0 infrastructure to build on

| Component | Location | What it provides |
|---|---|---|
| 4 GIs (Velocity, OpenSO, OpenPO, AllocDetEnq) | Acumatica sandbox (deployed) | Signal data via OData |
| POOrder custom fields (UsrAcknowledgedDate/UsrFactoryReadyDate) | Acumatica sandbox (deployed) | Lead time stage tracking |
| Lead-time learner (D.2) | `aesthetik-platform/src/services/drp-lead-time-learner.ts` | 4-stage lead time distributions |
| Lead-time mining (D.3) | `aesthetik-platform/src/services/lead-time-stats-service.ts` | Completed PO mining |
| ABC classifier (E.2) | `aesthetik-platform` (merged) | Revenue-weighted ABC classification |
| MOQ intake (C.2/C.2b/C.3/C.4) | `aesthetik-platform` (merged) | Vendor MOQ data + Acumatica sync |
| Lost demand events (F.1) | `aesthetik-platform` + `cs-order-entry` (merged) | Stockout event capture |
| studiob-api gateway | `studiob-api` (live) | Generic GI proxy + entity update routes |
| Vendor scorecard (D.5) | `aesthetik-platform` (merged) | Lead-time distribution display |

## Recommended session strategy

1. **Start with migrations** — get the tables created so everything else can build on them
2. **Signal workers next** — they're independent and testable in isolation
3. **Forecast engine** — depends on velocity cache
4. **Recommendation engine** — depends on forecast + all signal caches
5. **Nightly orchestrator** — wires everything together
6. **Slack brief** — final integration point
7. **H.1 DLM** — can be done anytime as a side task in webhook-router

Each component should be a separate PR with tests. Target: TDD with vitest, same patterns as Phase 0.

## Key design constraints (from locked design doc)

- Phase 1 is READ-ONLY to Acumatica. `write_enabled = false` is enforced.
- Three-store principle: Acumatica = system of record, Postgres = agent working memory, Qdrant = unstructured corpus.
- Cross-dock-first: allocation taxonomy is Committed/Hedged/Speculative. Agent prefers committed over speculative.
- MOQ shaping: agent respects vendor MOQs as hard floor, rounds up to MOQ when ordering.
- Safety rails: >20% single-run change = review flag, aggregate $ cap, override blocking.
- Walk-forward backtesting is mandatory for any parameter change.
