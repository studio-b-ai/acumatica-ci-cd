# Execute Phase 3 Convergence — with API verification kill criterion

## Mission

Execute the Phase 3 Convergence decision made at the end of the 2026-04-07 night session. This is the **Track 4 implementation** of the agentic pipeline next-stage plan. Decision: **Option (a) — agent owns the full deploy lifecycle via Claude Code remote trigger** — with a 1-hour API verification kill criterion gating the commitment.

**REQUIRED SUB-SKILLS:**
- `superpowers:executing-plans` to execute the plan task-by-task
- `superpowers:verification-before-completion` before claiming any task complete
- `superpowers:systematic-debugging` if any task hits an unexpected failure

## First action — READ THESE FIRST

In order:

1. **`/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage-v2.md`** — the v2 plan with closeout log. The "Closeout log — 2026-04-07 ~21:15 ET" section at the top captures exactly what happened tonight (the AesthetikWMS false-alarm storm, the SB501000 missing-table fix, the studiob-api API Login Limit root cause, the Track 4 decision).

2. **`/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-08-phase3-vs-reality-audit.md`** — the Track 4.1 audit. Honest diff between the Phase 3 design and what's actually on main.

3. **`/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-08-remote-trigger-convergence-design.md`** — the Track 4.2 design doc with the (a) decision, calcification rules, and 15-step execution order. **The "Decision + execution plan" section at the bottom is the authoritative execution spec for this session.**

4. **`/Users/kevin/dev/acumatica-ci-cd/agents/deploy-agent.md`** — the 599-line full-lifecycle prompt that already ships on main. This becomes the agent's runtime prompt in Track 4.3.1.

All three planning docs are on PR #273 (draft) — merge that first so they're on main and your execution can reference canonical paths.

## Track 4.3.0 — API verification (DO FIRST, ~1 hour) — KILL CRITERION

**Goal:** prove the Claude Code remote trigger API auth bug from 2026-04-06 is fixed before committing resources to the full (a) path.

### Steps

1. **Test `RemoteTrigger list`.** Use the `RemoteTrigger` tool with `action: "list"`. Expected: returns an array of triggers (empty is fine). If it returns "Unable to resolve organization UUID" or any auth error, the API is still broken.

2. **If list works, test `RemoteTrigger create`.** Create a trivial echo trigger:
   ```
   RemoteTrigger action=create body={
     "name": "phase3-convergence-api-test",
     "job_config": {
       "prompt": "Echo 'hello from deploy agent test' and exit cleanly."
     }
   }
   ```
   The exact schema may differ from the one in `2026-04-06-phase3-deploy-agent-impl.md` — experiment with fields if the create fails, but don't invest more than 15 minutes. If the API rejects all reasonable shapes, treat it as broken.

3. **Run the test trigger.** `RemoteTrigger action=run trigger_id=<id from step 2>`. Verify it completes and produces output.

4. **Document the result.** Write `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-08-remote-trigger-api-status.md` with:
   - Test date + time
   - List/create/run results
   - Any errors encountered
   - Schema learned from experimentation
   - Decision: API works → proceed with (a), OR API broken → fall back to (c)

### Two outcomes

**✅ API works** → Continue with the (a) execution order below.

**❌ API still broken** → Fall back to (c) Hybrid Formalized automatically:
- Update `docs/plans/2026-04-08-remote-trigger-convergence-design.md` decision header to reflect the fallback
- Schedule a quarterly re-test of the API via `mcp__scheduled-tasks__create_scheduled_task` (cron `0 9 1 */3 *` = first day of every third month at 9am local)
- Continue with the (c) execution order: same Tracks 2.1 → 2.2 → 2.3 → 2.4, but with the `invoke-agent` prompt scoped to diagnosis-only instead of full lifecycle, and `claude-code-action@v1` stays as the runtime
- Stop after Track 2.4; Tracks 4.3.1 / 4.3.2 / 4.3.3 / 4.3.4 / 4.3.5 are deferred

**Either path is shippable. The kill criterion just decides which.**

## No-regret backlog — can run in parallel with Track 4.3.0

These three P1 items ship in either (a) or (c) and can be worked in parallel with API verification by a sister session or sequentially if you're solo:

### P1.1 — Fixture-gen OData 404 (small, ~1 hour)

The `scripts/heritage/generate_ui_fixtures.py` → `workflow_extractor/fetcher.py:117` step fails every sandbox-gate run with `OData request failed: HTTP 404`. This blocks sandbox-gate green runs.

**Quick fix:** wrap the `Generate UI fixtures from audit data` step in `.github/workflows/acuops-deploy.yml` (line ~840) with `continue-on-error: true`. It becomes a warning instead of a gate-blocking failure. Real fix (which OData endpoint it's calling, why it's 404) deferred.

### P1.2 — Workflow `push:` path filter (small, ~30 min)

`.github/workflows/acuops-deploy.yml` line 44 has `push: { paths: ['Customization/**', '.github/workflows/acuops-deploy.yml'] }`. Pure `src/**/*.cs` changes (like tonight's PR #272) don't auto-trigger deploys. **Fix:** add `'src/**'` to the `paths:` array. Tonight proved this is a trap — PR #272's C# edit merged without firing a run, requiring manual `workflow_dispatch` with `force_deploy=OVERRIDE`.

### P1.3 — studiob-api session pool audit (larger, ~2 sessions)

This is the root cause of tonight's verify.py 401 storm. `studiob-api` Railway service holds N concurrent `api-bot` sessions against prod's Heritage Test tenant, saturating Heritage Fabrics' Acumatica API user license limit. When verify.py tries to log in, initial 204 succeeds, then every subsequent call returns 401 because the session is immediately invalidated by Acumatica's license policy.

**Investigation steps:**
1. Read `/Users/kevin/dev/studiob/apps/api/` (or wherever the studiob-api service lives — find it via Railway: `cd ~/dev/studiob && railway variables --service studiob-api --kv`). Look for the Acumatica client / session pool configuration.
2. Check if the pool has a max-session cap, session reuse logic, or connection pooling. Classic symptoms: creating a new session per request, no logout on request completion, no idle-session cleanup.
3. Run `railway logs --service studiob-api` and look for session lifecycle events.
4. Count concurrent sessions by watching the logs for a full minute.

**Fix options:**
- **(a) Reduce pool size** to leave room for verify.py seats (quick fix)
- **(b) Add session reuse** (proper fix — each worker keeps a long-lived session and reuses it)
- **(c) Dedicated `api-verify` Acumatica user** so verify.py has its own license seat pool isolated from studiob-api's usage (infrastructure change — requires Acumatica admin to create the user)
- **Best:** (b) + (c) together.

Also: **mirror the `assertStagingConfigSafe()` host-assertion guard** from webhook-router PR #64 into studiob-api's Acumatica client (Track 0 regression — same pattern closed on webhook-router should be mirrored here). The env vars `ACUMATICA_URL=https://heritagefabrics.acumatica.com` + `ACUMATICA_TENANT=Heritage Test` are the same trap.

## Track 4.3.0 passed — execute the full (a) order

If API verification passes, proceed with the 15-step execution order from `docs/plans/2026-04-08-remote-trigger-convergence-design.md`:

1. ✅ Track 4.3.0 — API verification (done)
2. 🔄 P1.1, P1.2, P1.3 deferred backlog (in parallel)
3. **Track 2.0.b** — merge webhook-router PR #64. `cd ~/dev/webhook-router && /opt/homebrew/bin/gh pr merge 64 --squash --delete-branch --repo studio-b-ai/webhook-router`
4. **Track 2.1** — retire `GH_PAT_DISPATCH` via deploy keys. Full detail in `docs/plans/2026-04-07-agentic-pipeline-next-stage.md` Task 2.1.
5. **Track 2.2** — build `daily-dispatch-cap` composite action. Full detail in same plan Task 2.2.
6. **Track 2.3** — Safety Package A–F wired into `invoke-agent`, but with `agents/deploy-agent.md` as the runtime prompt (NOT the PR #248 failure-recovery prompt currently on main). Kill switch `INVOKE_AGENT_ENABLED=false` until 4.3.1+ pass.
7. **Track 4.3.1** — create the Claude Code remote trigger with `agents/deploy-agent.md` as the prompt body. Set `CLAUDE_TRIGGER_TOKEN` + `CLAUDE_TRIGGER_ID` GH secrets on `studio-b-ai/acumatica-ci-cd`. Rewrite the `invoke-agent` job step: replace `uses: anthropics/claude-code-action@v1 ...` with a `curl POST https://api.claude.ai/v1/code/triggers/$CLAUDE_TRIGGER_ID/run` step that uploads `deploy-context.json` artifact.
8. **Track 4.3.2** — sandbox-only dry run. Dispatch `invoke-agent` against a deliberately broken sandbox-gate run. Agent must: download artifacts, read `verify-result.json`, post Slack diagnosis to #ops, open a fix PR if applicable, NOT touch prod. Validate all 8 observations from the v1 plan Track 2.4 dry-run spec.
9. **Track 2.4** — full failure dry run against the prod path. With Safety Package + kill switch + daily cap enforced. Kevin flips `INVOKE_AGENT_ENABLED=true` ONLY after this passes end-to-end with zero false alarms.
10. **Track 4.3.3** — migrate `sandbox-gate` job logic into the agent prompt as tool calls. Delete the `sandbox-gate` job from `acuops-deploy.yml`. Verify one sandbox publish through the agent succeeds end-to-end.
11. **Track 4.3.4** — migrate `deploy` job logic (prod publish + snapshot + countdown + verify + tag + ingest + DM) into the agent prompt. Delete the `deploy` job. Verify one prod publish through the agent succeeds end-to-end.
12. **Track 4.3.5** — delete `post-deploy-validation` job. Final cleanup: unused secrets, dead GH variables, stale workflow comments. Pipeline ends at `build` + `build-validate` + `qualify` + `invoke-agent` (4 jobs).
13. **Track 2.5** — Mode-3 sentinel (orphan CustProject scan). Full detail in `docs/plans/2026-04-07-agentic-pipeline-next-stage.md` Task 2.5.
14. **Track 2.6** — VM autostop (Cloud Scheduler Fri 8pm stop / Mon 5am start).
15. **Track 3** — Studio B platform vision design docs (unblocked after 2.4 green). `docs/plans/2026-04-07-agentic-pipeline-next-stage.md` Track 3.

## Non-negotiables

- **Track 4.3.0 runs BEFORE 4.3.1.** No remote trigger creation until API verified working.
- **Track 2.4 dry run MUST pass before `INVOKE_AGENT_ENABLED=true`.** Zero exceptions.
- **studiob-api session pool root cause MUST be fixed (P1.3) before re-enabling verify.py** in any mode. Otherwise the agent inherits a broken verification primitive.
- **Calcification rules apply during the hybrid transition** (Tracks 2.3 → 4.3.2). From `2026-04-08-remote-trigger-convergence-design.md`:
  - Rule 1: Keep the agent prompt's input contract pure JSON. No `${{ github.* }}` context dependencies.
  - Rule 2: Don't add conventional-job logic that duplicates agent capabilities. Let the agent absorb new diagnostic responsibilities.
- **Follow CLAUDE.md rules 9–11** — search `studiob-knowledge` + recall before debugging.
- **Verify before claiming** — `@superpowers:verification-before-completion` before any success claim. Tonight I read step conclusions as success when `continue-on-error: true` was masking a real failure; don't repeat that.
- **Never push directly to main** — PR every change.
- **Never publish or modify any Acumatica customization project outside of a planned Track 2.4 / 4.3.2 / 4.3.3 / 4.3.4 dry run** — each of those requires explicit Kevin coordination first.
- **Never enter a password into Acumatica** — if a Chrome session is dead, stop and tell Kevin.

## Worktrees + git state

- **This session's handoff branch:** `docs/agentic-pipeline-v2-phase3-convergence` — PR #273 (draft). Contains the three plan documents.
- **Last prod deploy:** `a2d438b fix(SB501000): create UsrContainerCost table in AesthetikContainersInstall (#272)` — merged, deployed via manual `workflow_dispatch force_deploy=OVERRIDE`, browser-verified live on prod.
- **Last AcuOps Deploy run:** `24111687164` — conclusion `failure` due to pre-existing `Post-publish verification` 401 storm, but `Import and publish customization → success`. Fix is live on prod; the job red is a verify.py issue, not a deploy issue.
- **The musing-dewdney worktree is alive** at `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/musing-dewdney` and has a bunch of uncommitted files from tonight. If starting fresh, create a new worktree: `EnterWorktree name=phase3-convergence`.

## Absolute paths you will need

| Purpose | Path |
|---|---|
| Main checkout | `/Users/kevin/dev/acumatica-ci-cd` |
| Plan docs (after PR #273 merge) | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage-v2.md` |
| Track 4.1 audit | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-08-phase3-vs-reality-audit.md` |
| Track 4.2 design + decision | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-08-remote-trigger-convergence-design.md` |
| Agent prompt (runtime target) | `/Users/kevin/dev/acumatica-ci-cd/agents/deploy-agent.md` |
| Workflow file | `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` |
| webhook-router source | `/Users/kevin/dev/webhook-router` |
| Studiob monorepo | `/Users/kevin/dev/studiob` |
| AcuOps pipeline (PROPRIETARY) | `/Users/kevin/dev/acuops-pipeline` |
| Memory dir | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/` |
| Global rules | `/Users/kevin/.claude/CLAUDE.md` |
| `gh` CLI | `/opt/homebrew/bin/gh` |
| `railway` CLI | `/opt/homebrew/bin/railway` |
| `op` CLI | `/opt/homebrew/bin/op` |
| VM RDP | `34.46.34.153` as `kevin` (password in 1P `acumatica-test VM (Windows)`) |

## Reporting back

Use TodoWrite throughout the session. After each milestone:
- Post a brief summary in the conversation
- If Track 4.3.0 reveals the API is still broken, make the fallback decision and tell Kevin
- If Track 2.4 succeeds, post to Slack #ops: `✅ Phase 3 agent re-enabled. Safety Package A-F active. Dry run passed. INVOKE_AGENT_ENABLED=true.`
- If Track 4.3.4 succeeds (deploy job migrated), post: `🎉 Phase 3 complete. Agent owns full deploy lifecycle. Conventional sandbox-gate/deploy/post-deploy-validation jobs deleted.`

Good luck. Verify before you claim, search KB before you debug, ask before you barrel.
