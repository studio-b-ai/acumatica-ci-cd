# DRP Architectural Pivot — Continuation Prompt

**Prior session ended:** 2026-04-11
**Session outcome:** Architectural pivot from Approach B (agent as brain) to Approach C (agent supplements native DRP). Design doc revised with Section 20 amendment. No shipped work invalidated.
**Branch:** `claude/elastic-dirac` in worktree `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/elastic-dirac`

## Read in order before doing anything

1. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — **READ SECTION 20 FIRST.** Architectural pivot documented there. Then skim revised Sections 2, 3, 8, 10, 13, 14, 15.
2. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-11-drp-phase-0.5-go-live-plan.md` — FERNCREST-MEDLINE native DRP canary plan (pending Kevin review)
3. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-10-drp-phase-0-implementation-plan.md` — Phase 0 task list (needs matching pass to drop dead tasks per pivot)
4. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md` — project memory (updated for pivot)
5. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/feedback_native_drp_first.md` — **CRITICAL standing feedback:** agent supplements native DRP, never replaces it

## What the pivot changed

**Core principle:** Native Acumatica DRP (IN508500 → AM510000 → AM400000 → PO503000 → PO301000) is the planning engine. The agent writes better inputs and selectively overrides parameters where backtest earns it. The agent NEVER creates POs, tracks allocations, or enters the approval workflow.

**Killed:**
- `drp_po_allocations` table (not yet built)
- `drp_cross_dock_matches` table (not yet built)
- Phase 2 draft-PO creation
- Phase 3 C-item autopilot
- All PO-generation logic from Section 13 (old)

**Revised phases:**
- Phase 0.5: Native DRP canary on FERNCREST-MEDLINE (78 items, zero code)
- Phase 1 (`input_only`): Agent writes Vendor.LeadTimedays, VendorDetails.MinOrderQty, StockItem.ABCCode. Native DRP runs with better inputs. Agent posts daily brief comparing shadow ROP vs native-computed ROP.
- Phase 2 (`selective_override`): Agent writes ItemWarehouse.ROP/SS/Max on items where 60+ days of backtest proves it beats native.

**All 15 merged PRs survive unchanged.** The pivot killed only planned work.

## What still needs doing

### Immediate (this session or next)

1. **Merge the design doc revision.** Changes are on `claude/elastic-dirac` branch. Review diff, merge to main.

2. **Update Phase 0 implementation plan** (`/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-10-drp-phase-0-implementation-plan.md`):
   - Add a revision log entry noting the pivot
   - Mark any PO-allocation or draft-PO tasks as KILLED (check — most weren't started)
   - Simplify `drp_recommendations` schema tasks (remove allocation_type, cross_dock_status, so_nbr columns if they exist)
   - Verify remaining tasks still make sense under Approach C

3. **Merge open PRs** (check current state first — these were open as of 2026-04-11):
   - `acumatica-ci-cd#313` — P0-A.3 DRP_OpenPOLines GI (blocked until #311 deploys)
   - `aesthetik-platform#111` — P0-D.5 VendorScorecard lead-time tab
   - `aesthetik-platform#112` — P0-C.2 MOQ intake backend
   - `cs-order-entry#9` — P0-F.1.d frontend emit hook

4. **Execute Phase 0.5 canary** (manual, no code):
   - Set lead times on 25 missing PRODUCT vendors (~90 min)
   - Set PlanningMethod=DRP on FERNCREST-MEDLINE item class
   - Run IN508500 on FERNCREST items
   - Review action messages on AM400000
   - Plan at: `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-11-drp-phase-0.5-go-live-plan.md`

### Soon (remaining Phase 0 tasks)

5. **Fix nightly DRP sync** — failed first run, worker config issue in aesthetik-platform (`/Users/kevin/dev/aesthetik-platform/`). Likely pointing at wrong Acumatica instance.

6. **Remaining Phase 0 code tasks** (~9 remaining, all survive the pivot):
   - P0-C.3 — MOQ intake frontend (React page)
   - P0-C.4 — MOQ write-back to Acumatica (POVendorInventory.MinOrderQty)
   - P0-E.2 — ABC classification nightly runner
   - P0-G.2 — Email watcher (imports@heritagefabrics.com)
   - P0-G.3 — Email signal bridge
   - studiob-api gateway routes for 4 GIs
   - Others per implementation plan

7. **Expand api-bot permissions** — currently 403 on PurchaseOrder/PurchaseReceipt/Bill. Needed for agent signal reads.

### Later

8. **Phase 1 agent service** — nightly cron, reads signals, computes shadow parameters, writes improved inputs, posts daily brief. Architecture is simpler now — no PO generation, no allocation tracking.

## Repos in play

- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/` (design doc changes on `claude/elastic-dirac` branch)
- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` (nightly sync failure)
- `webhook-router` at `/Users/kevin/dev/webhook-router/`
- `cs-order-entry` — verify path: `find /Users/kevin/dev /Users/kevin/code -maxdepth 4 -type d -name cs-order-entry`
- `studiob-api` — verify path same way

## Key files changed in this session

All on `claude/elastic-dirac` branch in `/Users/kevin/dev/acumatica-ci-cd/`:
- `docs/plans/2026-04-09-drp-implementation-design.md` — Sections 2, 3, 5, 8, 10, 13, 14, 15 revised + Section 20 added
- Memory files updated (project_drp_implementation.md, feedback_native_drp_first.md, MEMORY.md)
