# DRP Phase 0 Execution Kickoff — Session 3

**Prior session ended:** 2026-04-10
**Design doc state:** LOCKED (Sections 0-19)
**Phase 0 plan state:** Ready for execution
**PR state:** studio-b-ai/acumatica-ci-cd#305 (design + plan)

## Context

This is the third DRP session. Sessions 1-2 were design. Session 3 is implementation kickoff. The design doc and Phase 0 plan are both locked and committed. Your job is to start executing Phase 0 tasks, not to redesign.

**Read in order:**
1. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-09-drp-implementation-design.md` — locked design, sections 0-19. Reference when a task requires understanding *why* a piece of the architecture exists, not *what* to build next.
2. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-10-drp-phase-0-implementation-plan.md` — the task list. 25 tasks across 9 streams. This is your worklist.
3. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md` — project memory index with the decisions you should not re-debate.
4. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — full memory index.

## Pre-flight questions for Kevin (answer before starting execution)

These block specific tasks. Stream A (Acumatica GIs) can start the moment #2 is answered. Stream G (email watcher) needs #1. None block the entire Phase 0.

1. **Procurement shared inbox identity.** One address (`purchasing@heritagefabrics.com`) or multiple personal inboxes rolled up? Affects Task P0-G.2 Microsoft Graph subscription scope. If it's personal inboxes, we need a list.
2. **SO types to exclude from cross-dock matching.** Default is CO/SO only (excludes RM/IN/TR). Confirm or override. Affects `DRP_OpenSOCommitments` GI filter in Task P0-A.2.
3. **`StockItem.UsrCbmPerUnit` coverage today.** Audit blocks freight-consolidation NPV math in Phase 2, not Phase 0. Fine to defer until Phase 1 paper-trading is running, but confirm that's acceptable.
4. **Shadow-scheme promotion authority.** Procurement alone, or Kevin-approval, for promoting a shadow ABC scheme to active? Affects Task P0-E.1 seed data and the weekly review format.
5. **Stream priority.** The plan lists 9 streams; which does Kevin want started first? Natural first pick is Stream A (Acumatica GIs) because it unblocks everything downstream, but Kevin may prefer Stream C (MOQ intake) because it delivers immediate procurement value even without the agent running.

Ask all 5 at the start of the session, in one consolidated AskUserQuestion call.

## Execution discipline for this session

- **Worktree first.** Use `superpowers:using-git-worktrees` to create a new worktree for whatever stream you start. Do not execute Phase 0 in this same worktree; its purpose is design artifact storage.
- **TDD per task.** The plan has TDD steps for every task that has test infrastructure (heritage-wms, webhook-router, cs-order-entry, studiob-api). Honor them. Do not skip steps 1-3 ("write failing test, run it, confirm it fails") to save time.
- **Verification before completion.** Use `superpowers:verification-before-completion` before claiming any task is done. Acumatica tasks (Stream A, Stream B) require Playwright verification against the live sandbox, not just "pipeline reports SUCCESS" — the user's rule #4 is explicit about this.
- **Business hours.** Stream A and Stream B deploy to Acumatica and restart the app pool. They only run outside 06:00-18:00 ET. Check the clock before queuing the deploy. If it's mid-day, queue the other zero-downtime streams first and batch the Acumatica work for off-hours.
- **Reuse audit.** Before writing new code for any task, follow the "Reuses:" pointer in the plan. If the referenced file doesn't exist at the stated path, STOP and verify with `ls` or `git log --all`. Do not rewrite something that already exists.
- **One task = one PR.** Do not batch tasks into a single PR. Each task gets its own commit and its own PR against `main` of its repo.

## Memory + continuation discipline

- Update `project_drp_implementation.md` status after each merged PR. Note which Phase 0 tasks are complete.
- If any design assumption gets contradicted by reality during implementation (e.g., an Acumatica field doesn't exist where the design said it does), don't silently work around it — surface the contradiction, fix the design doc, commit the correction.
- Write a fourth continuation prompt at the end of this session at `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-12-drp-phase0-<stream>-continuation.md` (actual date + stream name). Confirm it's saved.

## Critical reminders from Kevin's standing rules

- **Don't require monitoring.** If a deploy needs watching, push results back to Kevin with a clear summary. Don't leave him to poll Slack.
- **Operational knowledge lives in Qdrant** `studiob-knowledge` collection — search it before debugging any Acumatica error. `topic=acumatica-help-wiki` filter for the 51-guide KB, `client=aesthetik` for HF-specific prior art.
- **Every Acumatica deploy restarts the app pool.** Get it right before deploying. There is no "one more quick fix."
- **Plain ops language in staff-facing UIs.** DRP math can use trader vocabulary in commit messages and design doc updates. Anything rendered in heritage-wms, SB501000/501100/501200, or Slack briefs uses plain ops words (Days of Cover, Cross-Dock Rate, Working Capital $, Dead Inventory).
- **Verify package ground truth before editing.** Run `ls /Users/kevin/dev/acumatica-ci-cd/Customization/` before designing around or editing any customization package. Memory can drift. Disk is truth.

## Open items that can be deferred

Items #1-#10 in Section 16 of the design doc remain open. Most are Phase 0 diligence items that resolve during execution (e.g., HubSpot per-SKU granularity is answered by inspecting the existing sync). Don't re-design around them up front; answer them as the relevant task reaches them.

## Starting state summary

- **Repo:** `/Users/kevin/dev/acumatica-ci-cd`
- **Branch at handoff:** `claude/recursing-lamport` (design + plan commit) — merged state of main will include these artifacts once PR #305 lands
- **PR:** studio-b-ai/acumatica-ci-cd#305 (design doc + Phase 0 plan + session 2 continuation prompt + superseded current-state draft)
- **No code written for Phase 0 yet.** All 25 tasks are unstarted.

Good luck. The design is solid. Execute it.
