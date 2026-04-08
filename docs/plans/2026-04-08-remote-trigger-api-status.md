# Remote Trigger API Status — Track 4.3.0 Kill Criterion Result

> **Track 4.3.0 deliverable** from `2026-04-08-remote-trigger-convergence-design.md`.
> This doc records the outcome of the 1-hour API verification gate.

## TL;DR

**❌ API STILL BROKEN.** Same `Unable to resolve organization UUID` auth error as 2026-04-06.
**Kill criterion fires → automatic fallback to option (c) Hybrid Formalized.**
Tracks 4.3.1–4.3.5 are **deferred indefinitely** pending upstream fix. Tracks 2.1–2.4 proceed unchanged per the (c) execution order.

## Test details

- **Test date/time:** 2026-04-08 (early AM ET, post-PR-#273 merge)
- **Test operator:** Claude Code session in worktree `elastic-blackburn` @ `claude/elastic-blackburn`
- **Tooling:** `RemoteTrigger` tool (Claude Code CLI built-in)

### Step 1 — `RemoteTrigger action=list`

**Result:** ❌ `Unable to resolve organization UUID.`

This is the exact same error observed on 2026-04-06 when `agents/deploy-agent.md` was originally designed. No behavior change between 2026-04-06 and 2026-04-08.

### Step 2 — `RemoteTrigger action=create`

**Skipped.** Per Track 4.3.0 spec: create/run tests are conditional on `list` succeeding. Because `list` returned the auth error, the kill criterion fires immediately with no further experimentation (the spec explicitly budgets ≤15 min on create schema fiddling and only if list works).

### Step 3 — `RemoteTrigger action=run`

**Skipped** — same reason as step 2.

## Decision

Per the `2026-04-08-remote-trigger-convergence-design.md` kill-criterion clause:

> **❌ API still broken** → Fall back to (c) Hybrid Formalized automatically.

This is now the active plan direction. The convergence design doc's decision header has been updated to reflect the fallback (same PR as this doc).

### What changes

- **(a) execution order is suspended.** Tracks 4.3.1 / 4.3.2 / 4.3.3 / 4.3.4 / 4.3.5 are deferred.
- **(c) execution order is active.** Tracks 2.1 → 2.2 → 2.3 → 2.4 proceed, but with the `invoke-agent` prompt scoped to **diagnosis-only** (not full lifecycle), and `anthropics/claude-code-action@v1` stays as the runtime inside GH Actions (no cloud VM cutover).
- `agents/deploy-agent.md` is preserved on main as the intended (a) target for when the upstream API is fixed. No deletion, no rewrite.
- Stop after Track 2.4. Track 3 (Studio B platform vision) is unblocked post-2.4 green.

### What does NOT change

- **No regressions in tonight's work.** PR #273 (docs) + PR #272 (SB501000 fix) + PR #274 (host assertion in deploy job) stand. All tonight's operational fixes are unaffected.
- **Calcification rules still apply** for Track 2.3 (keep the agent's input contract pure JSON; don't add conventional-job logic that duplicates agent capabilities) so that if/when the API is fixed, cutover to (a) is straightforward.
- **P1 backlog ships in either direction:**
  - P1.1 — fixture-gen OData 404 (wrap step in `continue-on-error: true`)
  - P1.2 — workflow `push.paths` add `'src/**'`
  - P1.3 — studiob-api session pool audit (the verify.py 401 storm root cause)

## Quarterly re-test cadence

A scheduled task has been created to re-test the RemoteTrigger API automatically on the first day of every third month at 9 AM local time. When a re-test returns success, it will update this doc and notify Kevin via Slack so the (a) convergence path can be re-evaluated.

**Schedule cron:** `0 9 1 */3 *` (local time)
**Script:** re-runs `RemoteTrigger action=list`, appends an entry to this doc's history table, DMs Kevin on status change.

## History

| Date | List result | Create result | Run result | Action |
|---|---|---|---|---|
| 2026-04-06 | ❌ "Unable to resolve organization UUID" | not tested | not tested | Design moved to claude-code-action@v1 failure-recovery only |
| 2026-04-08 | ❌ "Unable to resolve organization UUID" | skipped | skipped | **Kill criterion fires → (c) fallback active** |

## References

- `docs/plans/2026-04-08-remote-trigger-convergence-design.md` — decision framework + kill criterion clause
- `docs/plans/2026-04-07-agentic-pipeline-next-stage-v2.md` — v2 plan with (c) execution order
- `docs/plans/2026-04-08-phase3-vs-reality-audit.md` — Track 4.1 audit, design vs reality diff
- `docs/prompts/2026-04-08-execute-phase3-convergence.md` — session handoff prompt authorizing this work
- `agents/deploy-agent.md` — 599-line full-lifecycle prompt (preserved for eventual (a) cutover)
