# Agentic Pipeline — Next Stage Design

**Date:** 2026-04-07
**Author:** Kevin + Claude (this session)
**Status:** Approved, awaiting implementation plan
**Horizon:** 2–3 weeks (Approach C — Studio B platform vision)
**Approach:** A2 — parallel tracks, dogfood the agentic pipeline immediately

## Context

This design closes out the work begun during the 2026-04-07 production restart incident. Five Claude Code sessions ran in parallel today across three projects. The parallel session on `claude/nifty-chatelet` identified the root cause of 8 production restarts and shipped PR #258 (host-assertion guard + invoke-agent disable + corrected sandbox secrets). This session built the VM agent infrastructure (self-hosted Windows runner, vm-agent.yml dispatch workflow, Studio B Anthropic budget cap) and produced PR #257 — which became messy with 4 unrelated commits and now needs to be split.

The platform vision behind this stage came from the 10:00 ET scheduled task `studio-b-repo-architecture-review`: Studio B is the agency / platform layer; Heritage Fabrics, Aesthetik, Weathervane Hill, and Wasala are tenants. The agentic pipeline we are hardening here is the first product surface that will be sold through the Acumatica VAR channel.

### What was wrong (the lesson driving this design)

1. **Sandbox secret drift went undetected.** `ACUMATICA_SANDBOX_URL` and `ACUMATICA_SANDBOX_TENANT` were set one-shot via `gh secret set` on 2026-04-06 with values pointing at the prod instance / Heritage Test tenant. The rotation script's `secrets-map.env` only managed `ACUMATICA_SANDBOX_PASSWORD` and sourced from the wrong 1Password item. No assertion existed to detect the drift.
2. **Identity attribution was wrong.** `invoke-agent` (the AI Failure Recovery agent) used `GH_PAT_DISPATCH` (Kevin's personal PAT). When the agent merged its own fix PRs, the dispatched runs showed `triggering_actor=kbibelhausen`. Audit trail looked like Kevin was the one publishing repeatedly.
3. **Bounds were not enforced.** The agent's internal "max 3 attempts" only bounded retries within a single recovery loop. New `git push` events triggered fresh `AcuOps Deploy` runs, each of which fired its own `invoke-agent` job. Eight dispatches in 14 hours.
4. **Investigation got the wrong answer twice.** This session's Claude looked at the URL in Kevin's open Chrome tab and concluded "sandbox is separate, our pipeline is innocent" without ever echoing the actual GitHub secret value in a workflow step. Global rule 10 (search KB before debugging) was not followed.

The combination produced an outage. Each control on its own would not have prevented it. The design below addresses all four failure modes plus adds monitoring, kill-switch, and bounded scope.

## Architecture principle

Three concurrent tracks with explicit milestone gates between them, plus an immediate-priority Track 0 for the only remaining HIGH-severity landmine. Track 0 runs in parallel with Track 1 and doubles as the dogfood test of the new VM agent infrastructure. Track 1 stabilizes incident damage and lands the safety controls already coded but stuck in PR #257. Track 2 hardens the agentic layer and re-enables the AI Failure Recovery agent CORRECTLY. Track 3 plans the Studio B-as-platform vision in design-only mode until Tracks 1 and 2 reach defined milestones.

The principle: **never ship multi-tenant code before the single-tenant agentic pipeline is self-policing.**

## Full agentic pipeline (target state at end of stage)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  HUMAN ↔ AGENT INTERFACES                                                    │
│   • Mac Claude Code (interactive, daily driver)                              │
│   • VM Claude Code via RDP (interactive, Kevin's subscription, free)         │
│   • Slack #ops + Kevin DM (notifications, escalation, kill-switch alerts)    │
│   • GitHub PRs (review surface for all agent changes)                        │
└────────────┬─────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────┐
│  AGENT DISPATCH SURFACES                                                     │
│   • vm-agent.yml (workflow_dispatch + repository_dispatch)                   │
│       runs-on: [self-hosted, windows, acumatica-sdk]                         │
│       claude-code-action with ANTHROPIC_API_KEY                              │
│       (Studio B workspace key, $200/mo cap, $100/$160/$200 alerts)           │
│   • invoke-agent (acuops-deploy.yml, RE-ENABLED with safety package)         │
│       triggers on sandbox-gate failure only                                  │
│       max 1 run per push, max 3 runs per 24h (hard cap, gh api enforced)     │
│       GITHUB_TOKEN (not personal PAT) → audit shows github-actions[bot]      │
│       Slack pre-notification before filing PR                                │
│       GH variable kill-switch (set to "off" → immediate disable, no code)    │
│       Bounded file glob (Customization/**, tests/**, acuops.yaml,            │
│         .github/workflows/acuops-deploy.yml only)                            │
│   • Mode-3 scheduled tasks on VM (Haiku, ~$1/mo)                             │
│       hourly: orphan CustProject scan                                        │
│       daily: KB freshness check, cost burn rate                              │
│       weekly: audit log diff for unexpected publishes                        │
└────────────┬─────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────┐
│  ACUMATICA DEPLOY PIPELINE (acuops-deploy.yml)                               │
│   build → build-validate → qualify → sandbox-gate → deploy → invoke-agent    │
│           [Acuminator]    [audit]   [host-assert] [after-hrs]  [bounded]     │
│           Track 1.3       existing  PR #258       Track 1.1    Track 2.5     │
└────────────┬─────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────┐
│  KNOWLEDGE & MEMORY LAYER                                                    │
│   studiob-knowledge (Qdrant) ← incident KB, runbooks, architecture           │
│   studiob-sessions (Qdrant) ← all session history, auto-synced via Stop hook │
│   memory files at ~/.claude/projects/.../memory/                             │
└────────────┬─────────────────────────────────────────────────────────────────┘
             │
┌────────────▼─────────────────────────────────────────────────────────────────┐
│  IDENTITY & SECRETS LAYER                                                    │
│   1Password (Studio B Infrastructure vault, single source of truth)          │
│   scripts/rotate-secrets.sh + scripts/secrets-map.env (56 mappings)          │
│   ─→ GitHub Actions secrets (acumatica-ci-cd repo)                           │
│   ─→ Railway env vars (5 services)                                           │
│   GH_PAT_DISPATCH RETIRED for cross-repo checkout (deploy keys instead)      │
│   GITHUB_TOKEN used for in-workflow gh calls (audited as bot)                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Track 0 — webhook-router STG_* trap (immediate, parallel with Track 1)

**Why this is Track 0:** the only HIGH-severity item left after PR #258. webhook-router currently has `ACUMATICA_STG_URL = https://heritagefabrics.acumatica.com` and `ACUMATICA_STG_COMPANY = Heritage Test` — the same trap pattern that caused today's outage, on a different label. webhook-router currently only does OData GETs through this codepath, but any future POST/PUT/DELETE wired up here will instantly recycle the prod app pool. Letting this sit while we do other cleanup means leaving the same incident pattern armed.

**Why it doubles as the agentic dogfood test:** we wanted to validate `vm-agent.yml` with a read-only, well-bounded prompt before trusting it with anything destructive. The STG_* investigation is exactly that — read source, characterize call sites, recommend remediation, no writes. If `vm-agent.yml` has a bug we discover it on a low-stakes investigation rather than during invoke-agent re-enable.

### Tasks

| # | Task | Surface | Verification |
|---|---|---|---|
| 0.1 | Dispatch `vm-agent.yml` with `docs/prompts/2026-04-08-prod-restart-followups.md` (the P1 section) as the first real test run. Read-only investigation: grep webhook-router and studiob source for `ACUMATICA_STG_*` consumers, characterize each call site (GET/POST/PUT/DELETE), identify which are read-only OData and which could become writes. | `gh workflow run vm-agent.yml ...` | Slack post with findings; `gh run view` exit 0 |
| 0.2 | Decision with Kevin: (a) redirect `STG_*` to actual sandbox (api-test on heritagefabrics-sandbox), (b) rename env vars to `ACUMATICA_PROD_TEST_*` so the misnaming stops being a trap, (c) remove entirely if no consumer code uses them. | Conversation | Kevin chooses path |
| 0.3 | Execute remediation as a small reversible Railway env var change. Update `scripts/secrets-map.env` if STG_* is renamed/removed. Verify webhook-router still functions (its OData reads must keep working). | Railway CLI + Mac | `railway logs --service webhook-router` shows no Acumatica errors after redeploy |
| 0.4 | Mirror PR #258's host-assertion guard pattern into any webhook-router code path that talks to Acumatica. Any future misconfiguration must fail loud at runtime instead of silently publishing to prod. | webhook-router code + PR | Unit test: set bad host, verify guard fires |
| 0.5 | Update `studiob-knowledge` with a new entry: `Sandbox/STG naming trap — host assertion pattern for any pipeline secret`. Update `reference_acumatica_environments.md` memory file with the broadened guidance. | Qdrant + memory file | Search returns the entry |

**Wall time estimate:** 1–3 hours from dispatch to closed loop. Blocks nothing in Track 1.

## Track 1 — Tactical cleanup (today, after-hours window for merges)

**Goal:** unblock production (SB501000 still broken since Monday), close out PR #257's mess, land the safety controls already coded but stuck in the bad branch.

| # | Task | Verification | Reversible? |
|---|---|---|---|
| 1.1 | Branch `fix/after-hours-gate-clean` off main, cherry-pick `c3e3fb7` only (the after-hours gate commit, nothing else), push as new PR. | `git log --oneline -1` shows only the gate commit | yes |
| 1.2 | Branch `feat/vm-bootstrap-windows` off main, cherry-pick `2fd8bb2` (runner service install fix) + `c8427a0` (Node.js + Claude Code install), push as new PR. | Bootstrap script idempotent on existing VM | yes |
| 1.3 | Branch `feat/build-validate-windows` off main, cherry-pick the build-validate parts of `fb4b1a1` (NOT vm-agent.yml — already on main from PR #259), push as new PR. | YAML parses, references self-hosted runner labels | yes |
| 1.4 | Close PR #257 with a comment pointing at the 3 new PRs and explaining the split. | n/a | yes |
| 1.5 | Merge PR 1.1, 1.2, 1.3 in order **after 6pm ET tonight**. Each merge runs the full pipeline. The after-hours gate from 1.1 means only post-6pm merges can reach prod. | All 3 green; `gh api repos/.../actions/runners` shows the runner picked up build-validate | yes |
| 1.6 | Verify SB501000 deploys to prod successfully (the original Monday issue). Open the screen in production browser, see the new columns from the EnsureColumn fix (PR #252). | Visual confirmation in production browser | yes until publish |

**Wall time estimate:** 30 min for PR splits (Mac), then wait until 6pm ET, then 30–60 min for merge + verification.

## Track 2 — Agentic hardening (this week)

**Goal:** retire the personal PAT, build the daily-dispatch cap mechanism, re-enable invoke-agent CORRECTLY with the full safety package, ship one Mode-3 scheduled sentinel as proof, autostop the VM nights and weekends.

| # | Task | Surface | Verification |
|---|---|---|---|
| 2.1 | Generate SSH deploy keypair with `ssh-keygen -t ed25519 -C "acuops-pipeline-deploy"`. Add the public half as a read-only deploy key on `studio-b-ai/acuops-pipeline` via `gh api`. Add the private half as `ACUOPS_PIPELINE_DEPLOY_KEY` GH secret on `acumatica-ci-cd`. Replace 6 `actions/checkout token: GH_PAT_DISPATCH` references with `ssh-key: secrets.ACUOPS_PIPELINE_DEPLOY_KEY`. | Mac + gh api | All 6 checkouts succeed in next workflow run; deploy key visible at github.com/studio-b-ai/acuops-pipeline/settings/keys |
| 2.2 | Build the daily-dispatch cap as a small reusable composite action `.github/actions/daily-dispatch-cap`. Inputs: `workflow`, `max_per_24h`. Implementation: `gh api repos/.../actions/runs?event=workflow_run&created=>$(date -d '24 hours ago' --iso-8601)` and count runs of the named workflow. Fail with clear error if count >= max. | Mac | Unit test: set cap to 0, verify it fails; set cap to 100, verify it passes |
| 2.3 | **Re-enable invoke-agent with the full Safety Package (see below)** | Mac | Failure dry-run test (2.4) |
| 2.4 | Failure dry-run: deliberately push a sandbox-gate-breaking change on a feature branch (e.g., add a syntax error to a customization), watch invoke-agent fire, file PR, then verify the daily cap stops the second attempt. Audit trail must show `github-actions[bot]` not Kevin. Slack pre-notification must appear before claude-code-action runs. Toggle the kill-switch variable mid-run, verify the next dispatch no-ops. | Mac + GitHub + Slack | One PR filed, second dispatch BLOCKED by cap, audit clean, Slack received, kill-switch verified |
| 2.5 | Mode-3 scheduled task on VM: orphan CustProject scan. Windows Task Scheduler, hourly, runs `claude -p --model claude-haiku-4-5-20251001 "scan SQL Server CustProject table for orphan rows where Project not in active customizations. Post to Slack #ops only if any found."`. Cost ceiling: $1–2/mo. | VM Task Scheduler | First run posts to Slack with "0 orphans found" or count |
| 2.6 | VM autostop schedule via Cloud Scheduler. Stop instance Fri 8pm ET, start Mon 5am ET. Document the pause in the deployment runbook so anyone trying to push to main on the weekend understands why build-validate is failing. | Mac (gcloud + Cloud Scheduler) | VM offline Sat morning, online Mon morning |

### 🛡️ Safety Package for invoke-agent re-enable (Task 2.3)

The original invoke-agent had three failure modes that compounded into the outage. The re-enable must address all three plus add monitoring and a kill-switch.

| Control | Implementation | Tested by |
|---|---|---|
| **A. Cause eliminated** | Sandbox secrets correct (done in PR #258) + host-assertion guard in `sandbox-gate` (done in PR #258). Verified by 2.4 dry run since a sandbox failure must not be a sandbox-secret-misconfig failure. | Existing assertion runs on every sandbox-gate execution |
| **B. Identity attributed** | Switch `GH_TOKEN: secrets.GH_PAT_DISPATCH` → `GH_TOKEN: secrets.GITHUB_TOKEN` in invoke-agent's two env blocks (lines 1306, 1351 in acuops-deploy.yml). Built-in token is same-repo scope, audit shows `github-actions[bot]`. | 2.4 dry run audit log shows bot identity |
| **C. Hard daily cap** | Composite action from 2.2 wired into invoke-agent as a step that runs BEFORE claude-code-action. Inputs: `workflow=AcuOps Deploy`, `max_per_24h=3`. If count >= 3, fail fast with clear error message. | 2.4 dry run: trip to count=3, verify 4th blocks |
| **D. Pre-notification** | New step BEFORE claude-code-action: post to Slack #ops with run URL, sandbox failure summary, and "agent will diagnose in 30s — reply 'cancel' in next 5 min to abort". The 30s delay is implemented as `sleep 30` after the Slack post. | 2.4 dry run: see Slack post, verify 30s delay |
| **E. Kill-switch (no code change)** | New step BEFORE the cap check: read GH variable `INVOKE_AGENT_ENABLED` via `gh api repos/.../actions/variables/INVOKE_AGENT_ENABLED`. If value is `false`, exit 0 with summary "kill-switch engaged, agent skipped". Variable can be flipped from GH UI in 5 seconds. Default: `true`. | Toggle variable to `false`, verify next run no-ops |
| **F. Bounded scope** | Update agent prompt: agent may ONLY edit files matching glob `Customization/**`, `tests/**`, `acuops.yaml`, `.github/workflows/acuops-deploy.yml`. May NOT edit `secrets-map.env`, may NOT edit other workflow files, may NOT push to main directly (PR only). Add this as a hard constraint section in the prompt. | 2.4 dry run: check filed PR diff stays within glob |

### Pre-conditions for Task 2.3 (must be true before flipping the bit)

1. Track 0 complete (webhook-router STG_* trap closed)
2. Track 1 complete (PRs 1.1–1.3 merged, after-hours gate live, build-validate live, SB501000 verified on prod)
3. Task 2.1 complete (deploy keys retire GH_PAT_DISPATCH from `actions/checkout`)
4. Task 2.2 complete (daily-dispatch-cap action built and unit-tested)
5. At least 1 successful `vm-agent.yml` dispatch beyond Track 0 (proves the dispatch path is reliable)

If any pre-condition is not met, the re-enable PR sits in draft.

## Track 3 — Studio B platform vision (planning only)

**Goal:** codify the platform-vs-tenant split in memory and design docs. No multi-tenant code lands until Track 2 milestone 2.4 (invoke-agent dry run successful) is complete.

| # | Task | Output |
|---|---|---|
| 3.1 | Find the 10am scheduled task `studio-b-repo-architecture-review` output in session log `2026-04-07_98f99883.md`. Read its findings table (current state, target state, dogfooding gaps, closest-to-product apps). | Notes |
| 3.2 | Codify Studio B / tenant separation in `~/.claude/CLAUDE.md` and create a new memory file `project_studiob_platform_vision.md`. Articulate: Studio B is the agency/platform, Heritage/Aesthetik/Wasala are tenants, the AcuOps pipeline is the first product surface. | CLAUDE.md edit + memory file |
| 3.3 | Scope multi-tenant abstractions for `acuops-pipeline` (proprietary repo). Identify which env vars / config values would need to become tenant-scoped: `acuops.yaml` per-tenant, `also_publish_test` per-tenant, secrets per-tenant, deploy targets per-tenant, notification channels per-tenant. NO code changes — design doc only. | `docs/plans/2026-04-XX-acuops-multi-tenant-design.md` in acuops-pipeline repo |
| 3.4 | Pick a pilot tenant (likely Heritage as alpha) and enumerate the migration work: what would change in their AcuOps deployment to look like a tenant of Studio B rather than the only customer? | Migration checklist in design doc |
| 3.5 | Trip-wire: any merge of multi-tenant code is BLOCKED until Track 2 milestone 2.4 (invoke-agent dry run successful). Document this in CLAUDE.md as a hard rule. | CLAUDE.md edit |

## Data flow (target state)

```
push to main
   │
   ▼
build (ubuntu, package + DLLs)
   │
   ▼
build-validate (self-hosted Windows, Acuminator)
   │
   ▼
qualify (audit checks)
   │
   ▼
sandbox-gate (host-assert + publish + UI tests)
   │
   ├── ✅ → after-hours-gate (block 6am-6pm ET) → deploy → post-deploy verify
   │
   └── ❌ → invoke-agent (kill-switch → daily-cap → slack pre-notify → bounded agent)
                  │
                  ▼
            files PR (no direct push to main)
                  │
                  ▼
            human reviews + merges
                  │
                  ▼
            new push triggers next pipeline run

ad-hoc investigation (Mode 2):
   gh workflow run vm-agent.yml -f prompt_file=docs/prompts/X.md
        → self-hosted runner picks up
        → claude-code-action runs prompt on VM
        → agent gathers facts, may file PR (if prompt allows), posts findings to Slack
        → Kevin reads Slack, decides next move

scheduled ops (Mode 3):
   Windows Task Scheduler → claude -p "..." --model haiku
        → cheap (~$1/mo) recurring sentinels
        → posts to Slack only on anomalies (no spam)
```

## Error handling

| Failure | Detection | Response |
|---|---|---|
| Sandbox secret drift | host-assertion in sandbox-gate | Fails fast in workflow, no publish, Slack alert |
| invoke-agent runaway | daily-dispatch-cap composite action | Blocks 4th+ dispatches in 24h, fails workflow with clear error |
| Wrong identity attribution | GITHUB_TOKEN scoped to same-repo | Audit trail shows `github-actions[bot]`, not human user |
| Agent over-reach (file scope) | Bounded glob in agent prompt + human PR review | Filed PR diff fails review if outside scope |
| Cost overrun | Anthropic console workspace cap | Hard $200/mo cap, alerts at $100/$160/$200 |
| Runner offline | 15-min timeout on build-validate | Fails the workflow loudly, Slack alert |
| VM down (autostop or crash) | Next push fails on build-validate | Existing Slack channel |
| Kevin needs to stop the agent fast | GH variable `INVOKE_AGENT_ENABLED` | Flip to `false` in GH UI in 5 seconds, no code change |
| Track 3 multi-tenant code merged prematurely | CLAUDE.md hard rule + PR review | PR review catches |

## Testing strategy

| Component | Test |
|---|---|
| Track 1 PR splits (1.1–1.3) | YAML parse + dry-run on PR check + post-merge sandbox-gate run on each |
| build-validate (Track 1.3) | Trigger on a PR that introduces a known PX1000 violation, verify Acuminator catches it |
| vm-agent.yml first dispatch (Track 0.1) | The webhook-router STG_* investigation IS the test |
| Deploy keys (Track 2.1) | Run an `actions/checkout` step in a feature branch workflow, verify clone succeeds without PAT |
| Daily dispatch cap (Track 2.2) | Set cap to 1 in a test workflow, fire two runs back-to-back, second must fail at the cap step |
| invoke-agent re-enable (Track 2.3) | Failure dry run (Track 2.4) end-to-end |
| Kill-switch (Track 2.4) | Toggle variable mid-test, dispatch deliberate failure, agent must no-op |
| Mode-3 sentinels (Track 2.5) | First scheduled run posts to Slack with status |

## Success criteria for "stage complete"

1. ✅ Track 0 complete: webhook-router STG_* trap eliminated, host-assertion mirrored into webhook-router code path
2. ✅ SB501000 visible and functional on production
3. ✅ All 4 sandbox secrets correct + host-assertion enforcing them (already done in PR #258)
4. ✅ PR #257 closed; after-hours gate live; build-validate live (Tracks 1.1–1.6)
5. ✅ GH_PAT_DISPATCH retired from `actions/checkout` (Track 2.1, deploy keys)
6. ✅ invoke-agent re-enabled with Safety Package A–F + dry-run proof (Tracks 2.3–2.4)
7. ✅ At least 3 successful `vm-agent.yml` dispatches (Track 0.1 counts as the first)
8. ✅ At least 1 Mode-3 sentinel running on VM (Track 2.5)
9. ✅ VM autostop schedule live (Track 2.6)
10. ✅ Studio B platform vision documented in memory + design doc (Track 3)
11. ✅ Pilot tenant (Heritage) scoped for multi-tenant migration (Track 3)

## Rollback plan

- **Track 0**: webhook-router env var change is reversible via Railway dashboard. host-assertion guard is a code change reversible via PR revert.
- **Track 1**: each new PR (1.1–1.3) is a small focused diff, individually revertible. After-hours gate has `force_business_hours=true` override for emergencies.
- **Track 2**: deploy keys can be removed and `GH_PAT_DISPATCH` re-added in 2 minutes if needed. invoke-agent re-enable is reversible via the kill-switch GH variable (5 seconds) or by re-adding `false &&` to the `if:` (1 commit). VM autostop schedule is reversible via Cloud Scheduler delete.
- **Track 3**: planning only, no code lands.

## Out of scope for this stage

- The full GH_PAT_DISPATCH retirement on Railway services (4 slots in studiob-platform). The followups prompt notes this requires a real PAT (GITHUB_TOKEN doesn't exist outside workflow context). Defer until Track 2 lands and we know what each Railway slot actually does via source grep.
- The 1Password vault hygiene work (P3 in followups). Add to Track 2 if there's bandwidth, otherwise defer.
- The studiob-api / heritage-wms tenant question (P2 in followups). Needs Kevin's domain knowledge, low risk because read-only. Defer.
- Multi-tenant code in acuops-pipeline. Track 3 produces design docs only.

## Open questions

- For Track 0.2, which option does Kevin prefer for STG_* — (a) redirect to actual sandbox, (b) rename to ACUMATICA_PROD_TEST_*, or (c) remove entirely? Decide after Track 0.1 findings.
- Which Mode-3 sentinel should we ship first — orphan CustProject scan, KB freshness check, or audit log diff? Currently choosing orphan scan because it touches Track 0's incident class.
- Track 3 pilot tenant: confirm Heritage Fabrics is the right alpha. Aesthetik or Wasala might be better for greenfield without legacy baggage.

## Approval

Approved 2026-04-07 by Kevin in this session, with explicit additions:
- Track 0 promoted to lead the entire stage (webhook-router STG_* is the only HIGH-severity item left)
- invoke-agent re-enable promoted to a featured Track 2 deliverable with the full Safety Package A–F
- 4-track structure (Track 0 + Tracks 1–3) ratified

Next step: invoke `superpowers:writing-plans` to produce the granular implementation plan.
