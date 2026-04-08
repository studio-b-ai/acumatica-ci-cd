# Execute the Agentic Pipeline Next-Stage Plan

## Mission

Execute the implementation plan at `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` task-by-task.

The plan was produced by a sister session that just closed out. The design rationale lives at `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md`. Read both before doing anything.

**REQUIRED SUB-SKILL:** Use `superpowers:executing-plans` to execute this plan task-by-task with verification before completion.

## Your scope

You execute **Tracks 1, 2, and 3** of the plan. Track 0 (webhook-router STG_* investigation) is **already in flight** as `vm-agent.yml` run `24104724729`, dispatched at 2026-04-07 21:13 UTC. Do NOT re-dispatch Track 0. Check its status first:

```bash
gh run view 24104724729 --json status,conclusion,jobs
```

If the run completed before you start:
- Read its output: `gh run view 24104724729 --log | tail -200`
- Find findings posted to Slack #ops (check via slack_search_public)
- Proceed to Task 0.2 in the plan: present findings to Kevin and get his decision (a/b/c) on remediation
- Then execute Tasks 0.3, 0.4, 0.5 per the plan

If the run is still in_progress when you start:
- Begin Track 1 in parallel — it doesn't depend on Track 0
- Check Track 0.1 status periodically; pick it back up when complete

## Worktree

You're in a git worktree at:
```
/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman
```

The worktree was created by a sister session and is on branch `fix/after-hours-gate`. Per the plan, this branch will be CLOSED (PR #257) and replaced with 3 clean PRs (Tasks 1.1–1.3). The worktree itself stays alive — you cherry-pick onto fresh branches off main.

## Critical context — what was wrong, what's fixed, what's pending

### The 2026-04-07 incident

Production restarted 8 times in 14 hours because:
1. `ACUMATICA_SANDBOX_*` GH secrets pointed at the prod instance / Heritage Test tenant (one-shot `gh secret set` 2026-04-06 with copy-paste error)
2. Every "sandbox publish" recycled the prod IIS app pool
3. The AI Failure Recovery agent (`invoke-agent`) used Kevin's personal PAT (`GH_PAT_DISPATCH`), merged its own fix PRs, and triggered fresh `AcuOps Deploy` runs in a loop
4. Audit trail looked like Kevin caused the restarts

### What the parallel session shipped (PR #258, merged 19:59 UTC)

- Disabled `invoke-agent` via `if: false &&` in acuops-deploy.yml
- Added a host-assertion guard in `sandbox-gate` that hard-fails if `ACUMATICA_SANDBOX_URL` host ≠ `heritagefabrics-sandbox.acumatica.com` OR `ACUMATICA_SANDBOX_TENANT` = `Heritage Test`
- Corrected all 4 sandbox secrets via `gh secret set` (verified HTTP 204 login as `api-test`)
- Took sandbox out of maintenance mode

### What this session shipped before handing off

- VM bootstrap (Node + Claude Code + dev tools) on `acumatica-test` VM at `34.46.34.153`
- Self-hosted Windows runner online + Automatic startup (labels: `self-hosted, windows, acumatica-sdk`)
- `vm-agent.yml` workflow on main (PR #259) — Mode 2 dispatch ready
- `2026-04-08-prod-restart-followups.md` prompt on main (PR #260) — Track 0.1 fuel
- Studio B Anthropic workspace cap = $200/mo with $100/$160/$200 alerts
- Track 0.1 dispatched: vm-agent run `24104724729` (the webhook-router STG_* investigation)
- Design doc + implementation plan committed to `fix/after-hours-gate`

### What's still broken / pending

1. **SB501000 (Procurement Command Center) on production** — broken since Monday. Last successful prod publish was 4/6 8:07 PM ET. PR #252 has the fix (EnsureColumn for missing UsrContainer columns) and is supposedly in main, but the deploy never completed cleanly because sandbox-gate kept failing on the secret misconfig. Track 1.6 verifies SB501000 actually loads on prod after the Track 1 merges.
2. **PR #257 mess** — has 4 unrelated commits and conflicts with main. Track 1 splits it.
3. **webhook-router `ACUMATICA_STG_*`** — same trap pattern as the incident on a different label. Currently only OData GETs, but any future POST → instant outage. Track 0 fixes this.
4. **GH_PAT_DISPATCH still in use** — 6 `actions/checkout` references for `studio-b-ai/acuops-pipeline`. Track 2.1 retires via deploy keys.
5. **`invoke-agent` disabled** — the whole AI Failure Recovery value is lost until re-enabled. Track 2.3 re-enables with Safety Package A–F. Track 2.4 dry-runs.

## Operating discipline

- **Rule 9 (CLAUDE.md):** Operational knowledge lives in studiob-knowledge Qdrant. Query the collection BEFORE debugging anything.
- **Rule 10 (CLAUDE.md):** Search KB + recall BEFORE reading code. Most issues have prior art.
- **Rule 11 (CLAUDE.md):** Every Acumatica deploy restarts the prod app pool. Get it right before deploying.
- **`@superpowers:verification-before-completion`** before claiming any task done. Run the verification command, read the output, then make the claim.
- **`@superpowers:test-driven-development`** for any code change in Tasks 0.4 (host-assertion in webhook-router) and 2.5 (orphan CustProject sentinel).
- **After-hours window:** Task 1.5 (merging the 3 cleanup PRs) MUST wait until 6pm ET (verify with `TZ=America/New_York date`). The new after-hours gate from Task 1.1 will block any prod deploy before then.

## Stop conditions (ask Kevin, don't barrel through)

- Track 0.1 finds POST/PUT/DELETE consumers of `ACUMATICA_STG_*`. Changes the remediation calculus.
- Track 0.3 webhook-router redeploy fails or shows Acumatica errors after env var change.
- Track 1.5's PR merges trigger an unexpected pipeline failure (NOT the expected after-hours block — actual unexpected).
- Track 1.6's SB501000 still broken on prod after deploy. Investigate before re-deploying.
- Track 2.1's deploy-key smoke test fails (suggests deploy key permissions wrong).
- Track 2.4's dry run shows the agent over-reaching the file glob bounds.
- **Task 2.4 has an explicit decision point:** Kevin needs to choose dry-run mechanism — (i) push deliberate failure to main after-hours, OR (ii) add a `simulate_sandbox_failure` workflow input. Ask before proceeding.
- Any task takes more than 2x the expected wall time.

## Hard constraints

- **Never publish, unpublish, or modify any Acumatica customization project** during this work outside of the planned Track 1.5 merge window after 6pm ET.
- **Never enter a password into Acumatica.** If a Chrome session is dead, stop and tell Kevin.
- **Never delete a 1Password item.** Flag for Kevin instead.
- **Never create a GitHub account or GitHub App.** Use deploy keys, GITHUB_TOKEN, or existing identities.
- **Never push directly to main.** PR every change. The after-hours gate does not protect direct pushes; only PR merges go through the workflow.
- **Never `--no-verify` on git commits.** Pre-commit hooks exist for a reason.
- **Don't run `bash scripts/rotate-secrets.sh`** — wider blast radius than most followups need. Current GH secrets are correct and verified.
- **Track 3 multi-tenant code is BLOCKED until Track 2.4 (dry run) succeeds.** Hard rule — write design docs only.

## Reporting back

Use TodoWrite to track progress through the 6 tracks. After each track milestone:
- Post a brief summary to this conversation (Kevin will see it)
- If Track 0 reaches a decision point, ask Kevin in chat
- If Tracks 1.5 + 1.6 succeed, post celebration to Slack #ops: `✅ SB501000 live on production. After-hours gate active. PR #257 closed.`
- If Track 2.4 dry run succeeds, post to Slack #ops: `✅ AI Failure Recovery agent re-enabled with Safety Package. Dry run passed. Identity = github-actions[bot], cap = 3/24h, kill-switch = on.`

## Absolute paths you will need

| Purpose | Path |
|---|---|
| Worktree (cwd) | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman` |
| Implementation plan | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` |
| Design doc | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md` |
| Followups prompt (already on main) | `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-08-prod-restart-followups.md` |
| Workflow file | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/.github/workflows/acuops-deploy.yml` |
| `acuops.yaml` | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/acuops.yaml` |
| Memory dir | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/` |
| Followup project memory | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_2026_04_07_prod_restart_followups.md` |
| Acumatica environments memory | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_acumatica_environments.md` |
| Secrets infra memory | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_secrets_infrastructure.md` |
| Global rules | `/Users/kevin/.claude/CLAUDE.md` |
| Webhook-router source | `/Users/kevin/dev/webhook-router` |
| Studiob monorepo | `/Users/kevin/dev/studiob` |
| AcuOps pipeline (PROPRIETARY) | `/Users/kevin/dev/acuops-pipeline` |
| Main checkout (do NOT cd into for git ops) | `/Users/kevin/dev/acumatica-ci-cd` |
| `gh` CLI | `/opt/homebrew/bin/gh` |
| `railway` CLI | `/opt/homebrew/bin/railway` |
| `op` CLI | `/opt/homebrew/bin/op` |
| `gcloud` CLI | `/opt/homebrew/bin/gcloud` |
| Self-hosted runner status | `gh api repos/studio-b-ai/acumatica-ci-cd/actions/runners` |
| VM SSH | `gcloud compute ssh acumatica-test --zone=...` (or RDP via Chrome Remote Desktop) |

## First action

1. Read the implementation plan in full.
2. Check Track 0.1 status: `gh run view 24104724729 --json status,conclusion`
3. Begin Track 1 work in parallel (it doesn't depend on Track 0):
   - Task 1.1: cherry-pick `c3e3fb7` onto `fix/after-hours-gate-clean`
   - Task 1.2: cherry-pick `2fd8bb2` + `c8427a0` onto `feat/vm-bootstrap-windows`
   - Task 1.3: cherry-pick build-validate parts of `fb4b1a1` onto `feat/build-validate-windows`
   - Task 1.4: close PR #257
4. When Track 0.1 completes, present findings to Kevin and continue Track 0.
5. Wait until 6pm ET for Track 1.5 merges.

Good luck. Verify before you claim, search before you debug, ask before you barrel.
