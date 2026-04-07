# Continuation — Agentic Pipeline Tracks 2 & 3

Pick up the agentic pipeline next-stage plan at Tracks 2 (agentic hardening) and 3 (Studio B platform vision). Tracks 0 and 1 closed out on 2026-04-07 — production is safe, SB501000 is live, the webhook-router STG_* trap is eliminated, build-validate runs on a self-hosted Windows runner. This handoff picks up where the 2026-04-07 session ended.

## Mission

Harden the agentic layer that was built, deployed, and turned off during the 2026-04-07 incident. The AI Failure Recovery agent (`invoke-agent` in acuops-deploy.yml) is currently disabled via `if: false &&` — the whole point of building it was autonomous recovery from sandbox failures. Leaving it disabled forever means the incident won. Re-enable it correctly with the full Safety Package A–F, prove it with a failure dry-run, then move to the platform vision work.

## Context loaded for you

### Memory files (auto-loaded)

- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — index
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_2026_04_07_prod_restart_followups.md` — original followup queue, some items closed (P1 webhook-router STG_* done, PR #257 cleanup done)
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_secrets_infrastructure.md` — rotation script + secrets map
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_acumatica_environments.md` — sandbox/prod/test-tenant topology + host assertion pattern

### Qdrant entries (search `studiob-knowledge` to load)

- `Incident 2026-04-07 — prod restart dispatch loop` — the original incident
- `Sandbox/STG naming trap — host assertion pattern (corrected 2026-04-07)` — includes the webhook-router CRUD correction
- `Acuminator baseline suppression pattern — first-run policy` — new entry from 2026-04-07 evening session
- `GH Actions self-hosted runner — user account vs NetworkService` — new entry
- `claude-code-action on self-hosted Windows runners — don't` — new entry

### Design + implementation plan

- `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md` — the design with the full agentic pipeline diagram and Safety Package A–F spec
- `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` — bite-sized implementation plan (Tracks 0–3). Tracks 0 and 1 are CLOSED. You're picking up Track 2.
- `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-07-execute-next-stage.md` — the original handoff prompt (read for historical context)

## What's already done (do NOT redo)

### Track 0 — webhook-router STG_* trap elimination — **DONE**

- Investigation found `src/workers/regression-runner.ts` does full CRUD (`updateRecord` for create/update, `deleteEntity` for delete) via the staging Acumatica client — NOT "OData GETs only" as the original followups prompt claimed
- Railway env vars on `studiob-platform/webhook-router` repointed: `ACUMATICA_STG_URL=https://heritagefabrics-sandbox.acumatica.com`, `COMPANY=Heritage Fabrics`, `USER=api-test`, `PASSWORD=<from 1P>`, `BRANCH=HERFAB` (unchanged)
- webhook-router **PR #64** (`fix: assert staging Acumatica config never points at prod`) opened with `assertStagingConfigSafe()` + 6 TDD tests. **Still OPEN, NOT merged yet** — verify and merge as Track 2.0 prerequisite
- `studiob-knowledge` KB updated with corrected finding

### Track 1 — PR #257 cleanup + SB501000 deploy — **DONE**

- PR #257 closed with 3 clean replacement PRs
- PRs merged today: #260 (followups prompt), #261 (vm-agent local claude -p), #262 (after-hours gate), #263 (VM bootstrap), #264 (build-validate job), #265 (build-validate GCS fallback), #266 (DLL-based gate), #268 (editorconfig demote PX1050/PX1053), #269 (baseline all PX→warning), #270 (force_deploy workflow input)
- SB501000 deployed to prod via workflow_dispatch with `force_deploy=OVERRIDE` — verified live, screen title = "Procurement Command Center", no errors

### VM agent infrastructure — **WORKING**

- Self-hosted Windows runner `acumatica-test` online, labels `self-hosted,windows,acumatica-sdk`, running as user `kevin` (NOT NetworkService)
- `vm-agent.yml` on main invokes `claude -p` locally (not `claude-code-action` — it's Linux-only, fails on Windows)
- New Anthropic API key `AcuOps CI-CD vm-agent (2026-04-07)` in Studio B workspace, $200/mo cap with $100/$160/$200 alerts
- GH secret `ANTHROPIC_API_KEY` rotated to the new key value
- VM password reset, saved to 1P as `acumatica-test VM (Windows)` in Studio B Infrastructure vault

### Production state

- SB501000 live
- Heritage Fabrics prod healthy
- 8 dispatches from the 2026-04-07 incident did not recur (invoke-agent still disabled, so it can't loop)

## Track 2 — Agentic hardening (your primary work)

### 2.0 Pre-flight (verify nothing drifted overnight)

- [ ] Query SB501000 in prod browser → confirm still loads (smoke sanity)
- [ ] `gh api repos/studio-b-ai/acumatica-ci-cd/actions/runners` → runner still online
- [ ] Verify webhook-router PR #64 is still open (merge it as Track 2.0 if not already merged)
- [ ] Read `docs/plans/2026-04-07-agentic-pipeline-next-stage.md` Tracks 2 + 3 in full before touching anything

### 2.1 Retire GH_PAT_DISPATCH from `actions/checkout` via deploy keys

Full detail in the implementation plan Task 2.1. Six references to `token: secrets.GH_PAT_DISPATCH` in `.github/workflows/acuops-deploy.yml` for cross-repo clone of `studio-b-ai/acuops-pipeline`. Replace with SSH deploy keypair + new secret `ACUOPS_PIPELINE_DEPLOY_KEY`.

**Hard constraint:** `studio-b-ai/acuops-pipeline` is proprietary product code for the Acumatica VAR channel. Do NOT make it public. Deploy keys are the right answer.

### 2.2 Build `daily-dispatch-cap` composite action

`.github/actions/daily-dispatch-cap/action.yml` — inputs: `workflow`, `max_per_24h`, `gh_token`. Uses `gh api repos/.../actions/runs?event=...` to count runs in the last 24h and fails hard if count ≥ cap. Full spec in plan Task 2.2 including test workflow pattern.

### 2.3 Re-enable invoke-agent with Safety Package A–F

This is the featured deliverable of Track 2. The 6 controls are:

- **A. Cause eliminated** — done (PR #258 sandbox host-assertion)
- **B. Identity attributed** — swap `GH_TOKEN: secrets.GH_PAT_DISPATCH` → `GH_TOKEN: secrets.GITHUB_TOKEN` in both env blocks (lines ~1306, 1351 in acuops-deploy.yml)
- **C. Hard daily cap** — wire the composite action from 2.2 as a step before claude-code-action, `max_per_24h=3`
- **D. Pre-notification** — Slack #ops post + `sleep 30` before firing the agent
- **E. Kill-switch** — GH variable `INVOKE_AGENT_ENABLED` (default `false` until dry-run passes). Add a step that reads it and exits 0 if not `true`
- **F. Bounded scope** — agent prompt hard constraints: file glob `Customization/**`, `tests/**`, `acuops.yaml`, `.github/workflows/acuops-deploy.yml` only. No direct push to main. No force-push. Max 1 attempt per loop

Finally remove the `false &&` from the job's `if:` condition. Leave the kill-switch variable at `false` until 2.4 proves the safety.

### 2.4 Failure dry-run

Deliberately break sandbox-gate on a feature branch and prove:
- invoke-agent fires
- Audit trail shows `github-actions[bot]` (not Kevin)
- Slack pre-notification lands
- Agent files a PR (not a direct push) within the file glob bounds
- Daily cap blocks the 4th dispatch in 24h
- Flipping `INVOKE_AGENT_ENABLED` to `false` mid-test no-ops the next run

**Decision point for Kevin:** the plan flags that the dry-run mechanism needs his input — (i) push a deliberate sandbox-gate-breaker to main after-hours, or (ii) add a `simulate_sandbox_failure` workflow input. Ask before executing.

Only after 2.4 passes end-to-end, flip `INVOKE_AGENT_ENABLED` to `true` in the GH variable UI.

### 2.5 Mode-3 scheduled sentinel (orphan CustProject scan)

Windows Task Scheduler on the VM → hourly `claude -p --model claude-haiku-4-5-20251001 "scan SQL Server CustProject table for orphan rows vs SM204505 active list. Post to Slack #ops only if anomalies."`. Cost ceiling ~$1–2/mo on Haiku.

### 2.6 VM autostop

Cloud Scheduler jobs:
- `acumatica-test-stop` — `0 20 * * 5` (Fri 8pm ET)
- `acumatica-test-start` — `0 5 * * 1` (Mon 5am ET)
~50% GCE compute savings. Document the weekend pause in the deploy runbook so anyone pushing Saturday understands why build-validate fails.

## Track 3 — Studio B platform vision (planning only)

**Hard rule: NO multi-tenant code merges until Track 2.4 dry-run passes.** Design docs only.

### 3.1 Read the 10am 2026-04-07 scheduled task output

Session export at `/Users/kevin/.claude/sessions-export/2026-04-07_98f99883.md` — `studio-b-repo-architecture-review` scheduled task. Extract: current state table, target state, dogfooding gaps, closest-to-product apps.

### 3.2 Codify platform-vs-tenant split

- Edit `/Users/kevin/.claude/CLAUDE.md` to add a "Platform architecture" section under Conventions stating Studio B is the platform, Heritage/Aesthetik/Weathervane/Wasala are tenants
- Create new memory file `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_studiob_platform_vision.md`

### 3.3 Scope multi-tenant abstractions for acuops-pipeline

Identify tenant-scoped values: `acuops.yaml` fields, `also_publish_test` list, GH secrets per tenant, deploy targets per tenant, notification channels per tenant. Write to `/Users/kevin/dev/acuops-pipeline/docs/plans/2026-04-XX-acuops-multi-tenant-design.md` in the proprietary repo. NO CODE CHANGES.

### 3.4 Pilot tenant migration checklist

Pick Heritage Fabrics as alpha. Enumerate: what changes about their AcuOps deployment when it becomes tenant-of-Studio-B rather than only-customer? Add to the design doc from 3.3.

### 3.5 Trip-wire rule

Add to `/Users/kevin/.claude/CLAUDE.md`: "No multi-tenant code merges to acuops-pipeline until Track 2.4 (invoke-agent dry run) is complete and verified."

## Other open follow-ups (not blocking Track 2 but should track)

- **acumatica-ci-cd#267** — 9+ pre-existing Acuminator PX errors. Baseline-suppressed in `.editorconfig`. Fix in batches, promote severity back to error per rule as you go
- **webhook-router#65** — case-sync worker hits Acumatica API budget (`cycle=602/500`). Pre-existing, unrelated to incident. Options: raise cycle budget from 500 → 1500, or fix `getCasesSince()` pagination
- **UNFILED: ContainerTracking endpoint XML** — the Contract-Based API endpoint for Container doesn't expose `TransportMode`, `LandedCostRefNbr`, `LandedCostStatus` even though the DAC has them. Affects API consumers only, not the screen itself. Update `Customization/AesthetikContainers/project.xml` to add the field mappings
- **UNFILED: detect_cust_changes bug** — `.github/workflows/acuops-deploy.yml` has `[ "push" = "workflow_dispatch" ]` which is a literal string comparison that's always false. Meant to be `[ "${{ github.event_name }}" = "workflow_dispatch" ]`. Doesn't currently break anything but is dead code
- **VM improvement** — install Acumatica ERP locally on `acumatica-test` so `build-validate` can use `C:\Program Files\Acumatica ERP\Bin` directly instead of the GCS fallback. Saves ~10s per build

## Hard constraints

- **Never publish, unpublish, or modify any Acumatica customization project** outside of the planned Track 2.4 dry-run (which must be coordinated with Kevin first)
- **Never enter a password into Acumatica.** If a Chrome session is dead, stop and tell Kevin
- **Never delete a 1Password item.** Flag for Kevin instead
- **Never create a GitHub account or GitHub App.** Use deploy keys, `GITHUB_TOKEN`, or existing identities
- **Never push directly to main.** PR every change. The after-hours gate does not protect direct pushes; only PR merges go through the workflow
- **Never `--no-verify` on git commits.** Pre-commit hooks exist for a reason
- **Don't run `bash scripts/rotate-secrets.sh acumatica`** — wider blast radius than most Track 2 work needs. Current GH secrets are correct and verified
- **No multi-tenant code merges until Track 2.4 succeeds.** Design docs only in Track 3
- **Follow `~/.claude/CLAUDE.md` rules 9–11** — search studiob-knowledge + recall BEFORE debugging
- **Verify before claiming** (`@superpowers:verification-before-completion`) — run the command, read the output, then make the claim

## Absolute paths you will need

| Purpose | Path |
|---|---|
| Main checkout | `/Users/kevin/dev/acumatica-ci-cd` |
| Worktree (this session's cwd) | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman` |
| Design doc | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md` |
| Implementation plan | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` |
| Original handoff | `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-07-execute-next-stage.md` |
| This prompt | `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-08-continuation-tracks-2-3.md` |
| Workflow file | `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` |
| Memory dir | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/` |
| Global rules | `/Users/kevin/.claude/CLAUDE.md` |
| webhook-router source | `/Users/kevin/dev/webhook-router` |
| Studiob monorepo | `/Users/kevin/dev/studiob` |
| AcuOps pipeline (PROPRIETARY) | `/Users/kevin/dev/acuops-pipeline` |
| `gh` CLI | `/opt/homebrew/bin/gh` |
| `railway` CLI | `/opt/homebrew/bin/railway` |
| `op` CLI | `/opt/homebrew/bin/op` |
| `gcloud` CLI | `/opt/homebrew/bin/gcloud` |
| VM RDP | `34.46.34.153` as `kevin` (password in 1P item `acumatica-test VM (Windows)`) |

## First actions

1. Read this entire prompt
2. Read the implementation plan at `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` Tracks 2 + 3
3. Verify webhook-router PR #64 state — merge if still open (Track 2.0 prerequisite)
4. Run the pre-flight checks from Track 2.0
5. Start Track 2.1 — generate SSH deploy keypair for `studio-b-ai/acuops-pipeline`, swap the 6 checkout references
6. When you reach Task 2.4 (failure dry-run), stop and ask Kevin which dry-run mechanism to use
7. Rigby close-out at end of session — produce a new continuation prompt at an absolute path, confirmed saved, no reminders
