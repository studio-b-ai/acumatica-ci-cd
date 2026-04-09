# DRP design continuation — Sections 4-8

**Previous session ended:** 2026-04-09
**Design doc state:** Sections 0-3 locked, Sections 4-8 pending
**Design doc path:** `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md`

## Context

This is the second of at least two sessions designing Heritage Fabrics' DRP (Distribution Resource Planning) implementation. The first session locked the strategic philosophy, current-state diagnosis, design decisions, architecture, Phase 0 plan, data model, and signal ingestion. This session finishes Sections 4-8 of the design doc, writes the full implementation plan via the `writing-plans` skill, and transitions to execution.

**Read this first, in order:**
1. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — the in-progress design doc (Sections 0-3 locked)
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — project memory index
3. `/Users/kevin/Library/CloudStorage/OneDrive-HeritageFabrics,LLC/memory/project_container-tracking.md` — container tracking status
4. Qdrant collection `studiob-knowledge` — Acumatica help wiki (51 guides / 30K chunks) ingested during previous session. Filter: `{"must":[{"key":"topic","match":{"value":"acumatica-help-wiki"}}]}`

## Locked decisions carried over from previous session

- **Approach B** — external forecasting agent writes to Acumatica; agent is the brain, Acumatica is system of record
- **Objective function** — minimize inventory dollar-days subject to committed fill-rate floor (NOT service-level maximization)
- **Primary metric** — cross-dock hit rate (% of receipts shipped within 7d)
- **Tiered service levels** — A=98% / B=95% / C=90%, treated as floors, not targets
- **Commitment horizon** — 30-60 days default (measure empirically in Phase 0)
- **Speculation floor** — 14 days A / 7 days B / 0 days C
- **MOQ intake surface** — heritage-wms (React) reusing existing parser stack, NOT SharePoint
- **Custom fields package** — `AesthetikContainers` (POOrder.UsrAcknowledgedDate + POOrder.UsrFactoryReadyDate)
- **Phase-gated autonomy** — paper trading months 1-2 → draft POs months 3-4 → C-item autopilot month 5+
- **Pluggable ABC scheme registry** — v1 = `revenue_weighted_90`, shadow-mode backtest machinery built in from day 1
- **Data archive** — reuse `webhook-router/src/lib/data-lifecycle/` DataLifecycleManager policies for all `drp_*` tables, no new archival code
- **Human override TTL** — 180 days ROP/SS/Max, 365 days full opt-out, silent takeback if agent agrees within 10% on expiry
- **Factory closures** — `drp_vendor_calendar` + `drp_country_calendar` with seeded priors (CNY, Diwali, Turkish bayrams, etc.) + agent-learned patterns
- **SB501000 reconciliation** — 3 screens in Container Tracking workspace: PCC (SB501000, container ops refined) + Vendor Planning Hub (SB501100, new) + Supplier Intake (SB501200, external link to heritage-wms)
- **UI language** — plain operations vocabulary only. Internal math uses trader thinking; staff never sees commodities jargon

## Sections to design in this session

### Section 4 — Forecast Engine
- Per-item forecast with uncertainty bands (not point estimates)
- Weak-seasonality detection stack (STL, Fourier, pooled class-level, industry priors, exogenous signals)
- Integration with HubSpot pipeline velocity + Shopify sessions + cs-order-entry stockout events as forward-looking demand signals
- How forecasts flow into the ROP/speculation-floor calculations
- Model state persistence in `drp_forecast_state`
- Accuracy tracking (MAPE 7/28/90 day windows)
- Fallback logic when signals are missing

### Section 5 — Lead Time Learning (detailed math)
- 4-stage distribution math: ack_lag / production / transit / total_lead
- Outlier detection (3σ from running mean, auto-flag)
- Regime-change detection (pre/post COVID, pre/post Red Sea, pre/post CNY)
- Factory closure overlay (how closures add days to effective lead time at runtime)
- Bias correction feedback loop (observed vs promised lead time)
- Vendor beta (how much a vendor's delivery covaries with market conditions)
- Writing back to `Vendor.LeadTimedays` (weekly, min 10 samples)

### Section 6 — DRP Math (detailed)
- Full cross-dock-first recommendation logic (committed → hedged → speculative fallback)
- Order quantity calculation respecting MOQ, EOQ, container-fill economics
- Concentration guardrails (per-vendor, per-country, per-collection limits)
- NPV-aware freight consolidation (partial container vs full container trade-off)
- Allocated-vs-speculative tagging on every PO line
- Soft cash cap handling (warning not refusal)

### Section 7 — Agent Orchestration
- Nightly run structure (start → signal check → model refresh → recommendation generation → governance check → writes → brief generation)
- Signal freshness gate (healthy / degraded / blocked run states)
- Phase-gated write paths
- Daily brief generation (Slack DM + canvas)
- Approval workflows for draft POs
- Exception routing (who gets what alerts when)
- Run logging + replay capability

### Section 8 — Governance & Monitoring
- Full safety rail specification
- Kill-switch state machine (advisor → draft → autopilot, reversible)
- Drift detection (forecast accuracy degrading, lead times regime-changing)
- Weekly human review cadence and content
- Success metrics: working capital $, days of cover, cross-dock hit rate, dead inventory, stockout count, override agreement rate
- Red-flag conditions that auto-revert phase (e.g., drawdown > threshold, override storm, signal outage)

## After Sections 4-8 are locked

1. **Write the final design doc** to `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` (append or rewrite Sections 4-8)
2. **Invoke `superpowers:writing-plans` skill** to create the implementation plan breaking Phase 0 into executable tasks with review checkpoints
3. **Commit the design doc + plan**
4. **Save memory entries** to `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/`:
   - `project_drp_implementation.md` — project memory with status, decisions, blockers
5. **Update MEMORY.md index** to include the new project file
6. **Write a third continuation prompt** if implementation starts in yet another session

## Critical reminders

- **This is a read-only investigation + design session.** No code changes, no Acumatica writes, no PR merges.
- **Heritage Fabrics procurement cycle is long (India 12-16 weeks, Turkey 8-12 weeks).** Every section should keep "minimum inventory, maximum cross-docking" as the primary lens.
- **Do not propose commodities jargon in staff-facing UI.** Internal math language is fine in the design doc, but anything rendered in heritage-wms or Acumatica UI uses plain ops words.
- **Reuse over rebuild.** heritage-wms parser stack, DataLifecycleManager, vendor-scorecard-service, existing Acumatica customizations, existing webhook-router sync workers — all get reused. Net-new code should be flagged and justified.
- **Absolute paths only.** No `./` or `../` references.
- **Acumatica business hours 6am–6pm ET.** Any customization deploy restarts the app pool. Phase 0 work that touches Acumatica (custom fields, GI registration) happens off-hours.
- **Continuation prompt discipline:** end this next session with a third continuation prompt written to an absolute path, confirmed saved, handed off cleanly.

## Open questions to answer or defer in this session

From Section 11 of the current design doc:

1. HubSpot deal pipeline signal granularity (per-SKU or aggregate?)
2. Shopify sync granularity (per-SKU events or order-level?)
3. Procurement shared inbox identity (single address or multi?)
4. SO types to exclude from cross-dock matching (default: CO/SO only)
5. Actual commitment horizon per customer class (measure in Phase 0)
6. 7-stage lifecycle timeline stages (validate with ops)

These can either be answered by Kevin in the continuation session or flagged as "Phase 0 diligence tasks" and left for empirical measurement.

## Branch + workspace state at handoff

- **Repo:** `/Users/kevin/dev/acumatica-ci-cd`
- **Worktree:** `.claude/worktrees/sweet-poincare` (DRP design work + kb-crawler shipped here)
- **Branch:** depends on what the previous session committed (check `git log` first)
- **PR:** #298 was opened for the kb-crawler work (51 Acumatica help guides, 30K chunks ingested)
- **New uncommitted files at handoff:**
  - `docs/plans/2026-04-09-drp-current-state-and-approaches.md` (superseded draft)
  - `docs/plans/2026-04-09-drp-implementation-design.md` (the in-progress design doc)
  - `docs/prompts/2026-04-10-drp-design-continuation-sections-4-8.md` (this file)
