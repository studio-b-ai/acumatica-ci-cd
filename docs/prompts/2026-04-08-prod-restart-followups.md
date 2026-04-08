# Continuation: 2026-04-07 prod restart incident — followup execution

## Mission

PR #258 (merged 2026-04-07 19:59 UTC, commit `b9e242d`) stopped the AI Failure Recovery dispatch loop and added a sandbox host-assertion guard. Production is safe right now. This document is the handoff for the **followup queue** — the cleanup work needed to prevent recurrence and close the related landmines exposed during the incident response.

Read this entire document before taking any action. Search the studiob-knowledge Qdrant collection for `2026-04-07 prod restart` to load the four ingested KB entries (incident, runbook, two architecture).

## Context loaded for you

### Memory files (auto-loaded)
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md` — index, includes pointer to followup project file
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_2026_04_07_prod_restart_followups.md` — full followup queue
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_secrets_infrastructure.md` — secrets infrastructure status, updated with the incident
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_acumatica_environments.md` — environment topology, updated with the sandbox naming trap warning
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/feedback_precise_scope_claims.md` — be precise about what a fix solves vs doesn't (lesson from the deploy-keys exchange)

### Qdrant entries (search studiob-knowledge to load)
- `Incident 2026-04-07 — prod restart dispatch loop` (domain=acumatica, client=aesthetik, source=incident)
- `Sandbox naming trap — SANDBOX != Heritage Test tenant` (domain=acumatica, client=studiob, source=runbook)
- `Studio B Railway fleet — single api-bot identity reuse` (domain=infrastructure, client=studiob, source=architecture)
- `Auto-dispatcher PAT attribution — agents look like Kevin` (domain=infrastructure, client=studiob, source=architecture)

### Original incident investigation prompt
- `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/prompts/2026-04-07-prod-restart-investigation.md` (the prompt that kicked off the original 3-hour investigation; useful as reference but not as a task list)

## What's already done (do NOT redo)

1. **PR #258 merged.** `invoke-agent` job in `.github/workflows/acuops-deploy.yml` is disabled via `if: false &&`. Sandbox-gate has a host-assertion step that hard-fails if `ACUMATICA_SANDBOX_URL` host is not `heritagefabrics-sandbox.acumatica.com` or if `ACUMATICA_SANDBOX_TENANT` is `Heritage Test`. Verified with post-merge run `24101613009` (success in 30s).
2. **Four GH secrets corrected** in `studio-b-ai/acumatica-ci-cd`:
   - `ACUMATICA_SANDBOX_URL = https://heritagefabrics-sandbox.acumatica.com`
   - `ACUMATICA_SANDBOX_TENANT = Heritage Fabrics`
   - `ACUMATICA_SANDBOX_USERNAME = api-test`
   - `ACUMATICA_SANDBOX_PASSWORD = <real value, verified HTTP 204 login>`
3. **Sandbox out of maintenance mode** (Kevin manual).
4. **`api-test` user provisioned** on the sandbox instance (Kevin manual). Password lives in 1P item `acumatica-api-test` (Studio B Infrastructure vault) — schema updated with `host` and `tenant` custom fields, password set to working value.
5. **`scripts/secrets-map.env` sandbox section fixed** (in the main checkout, file is untracked local tooling). Now sources from `acumatica-api-test` for url/tenant/username/password. Dry-run shows 18/18 acumatica entries parse, 0 failures.
6. **Memory + Qdrant updated** with incident, runbook, architecture entries.

## Followup queue — execute in priority order

### 🔴 P1 — webhook-router `ACUMATICA_STG_*` mislabel

**The ask:** webhook-router currently has these env vars on Railway (`studiob-platform/webhook-router` in production env):
- `ACUMATICA_STG_URL = https://heritagefabrics.acumatica.com` (PROD host, mislabeled as STG)
- `ACUMATICA_STG_COMPANY = Heritage Test` (test tenant on prod instance)
- `ACUMATICA_STG_USER = api-bot`
- `ACUMATICA_STG_PASSWORD = <prod api-bot password>`

This is the **same trap pattern** that caused the 2026-04-07 outage, just on a different label. webhook-router currently only does OData GETs through this codepath (verified in 2026-04-07 Railway log capture), so it hasn't tripped — but any future POST/PUT/DELETE wired up here will hit Heritage Test on the prod instance and recycle the prod app pool.

**Decision needed from Kevin first:** Should `ACUMATICA_STG_*` be:
- (a) **Redirected** to the actual sandbox (`heritagefabrics-sandbox.acumatica.com` / `Heritage Fabrics` / `api-test`)? Then webhook-router talks to real sandbox.
- (b) **Renamed** in code to `ACUMATICA_PROD_TEST_*` so the misnaming stops being a trap, leaving the values as-is? Then webhook-router talks to test tenant on prod, but the name is honest.
- (c) **Removed entirely** if no consumer code actually reads it?

Before changing any env var, **grep webhook-router source for `ACUMATICA_STG_`** at `/Users/kevin/dev/webhook-router/src` and `/Users/kevin/dev/studiob/packages/*/src` to identify all consumers. If consumers are read-only OData and you're removing or rerouting them, the change is low-risk. If consumers POST/PUT/DELETE, treat as a code change requiring its own PR + tests.

### 🟡 P2 — Tenant question for studiob-api / heritage-wms

Both services authenticate as `api-bot` into `Heritage Test` tenant on `https://heritagefabrics.acumatica.com`. The studiob-api gateway is `ACUMATICA_GATEWAY_URL` for several services, so its tenant choice propagates. Possibilities:
- Intentional: tests/staging pattern, deliberate use of test tenant
- Bug: should be `Heritage Fabrics` (the prod tenant)
- Migration in progress

Ask Kevin. Don't change env vars without his answer — this affects whether real heritage-wms users see real Heritage Fabrics data or test data.

### 🟡 P2 — Migrate `Sandbox API` (Employee vault) → delete duplicate

The canonical 1P item `acumatica-api-test` (Studio B Infrastructure / `4bof76csvq3oqde33z3wzdkttq`) already has the working credentials and the new `host` + `tenant` custom fields. The duplicate `Sandbox API` item in the **Employee** vault should be deleted by Kevin (Claude cannot delete 1P items per safety rules).

When Kevin deletes it, verify nothing else in the codebase or scripts references the Employee/`Sandbox API` path: `op://Employee/Sandbox API/...`.

### 🟡 P2 — `GH_PAT_DISPATCH` cleanup, modest version

Eight uses of `GH_PAT_DISPATCH` on origin/main of acumatica-ci-cd `.github/workflows/acuops-deploy.yml`:

| Lines | Purpose | Replacement |
|---|---|---|
| 109, 445, 492, 731, 1376, 1500 (six total) | `actions/checkout@v4` for `studio-b-ai/acuops-pipeline` (cross-repo private clone) | **Deploy keys.** Generate SSH keypair, add public half as a read-only deploy key on `studio-b-ai/acuops-pipeline`, store private half as `ACUOPS_PIPELINE_DEPLOY_KEY` in `acumatica-ci-cd` GH secrets, change each `token: secrets.GH_PAT_DISPATCH` to `ssh-key: secrets.ACUOPS_PIPELINE_DEPLOY_KEY`. Read-only access. No user attribution. |
| 1306, 1351 (in invoke-agent, currently disabled) | `GH_TOKEN: secrets.GH_PAT_DISPATCH` for the recovery agent's `gh` calls | When invoke-agent is re-enabled (after this whole queue), switch to `GH_TOKEN: secrets.GITHUB_TOKEN` (built-in, same-repo only, audit shows github-actions[bot]) |

**Important constraints:**
- `studio-b-ai/acuops-pipeline` contains **proprietary product code** — DO NOT make it public to avoid the token requirement
- Do NOT create a GitHub user/account or GitHub App in this session — Claude cannot create accounts per safety rules. Deploy keys are creatable via `gh api` and don't require new identities.

**Plus 4 Railway env-var slots** (`studiob-platform/acudev`, `webhook-router`, `studiob-api`) — need source-code grep first to characterize what each does. If same-repo only → swap to `secrets.GITHUB_TOKEN` (note: GH built-in token only exists in GH Actions context; for Railway services calling GH API, you still need a real PAT). For Railway-side, the modest fix is to keep `GH_PAT_DISPATCH` as-is for now since the loop is dead.

### 🟡 P2 — PR #257 cleanup

PR #257 (`fix/after-hours-gate` branch in `quirky-perlman` worktree) has:
- 1 useful commit: `c3e3fb7 fix: hard-gate prod/staging deploys during business hours` (the after-hours gate for the `deploy` job)
- 4 unrelated commits: VM bootstrap, Windows runner, Node.js install, vm-agent dispatch workflow
- A merge conflict against current main (introduced when PR #258 + the recent VM-bootstrap PRs landed)

**Plan:** Cherry-pick `c3e3fb7` onto a fresh branch off current `main` (e.g. `fix/after-hours-gate-clean`), push as PR #259, close PR #257. Deal with the 4 VM bootstrap commits in their own separate PR. Don't try to resolve conflicts on the existing branch — too much unrelated state.

**Skipped from the original followup list:** extending the after-hours gate to `sandbox-gate` itself. Kevin's call: PR #258's host-assertion check already covers the worst case (publishing to prod via misconfigured sandbox secrets), and gating sandbox publishes during business hours adds engineering friction without much added safety.

### 🟢 P3 — Re-enable AI Failure Recovery

Only after all of the above. Edit `.github/workflows/acuops-deploy.yml`:
1. Remove the `false &&` from the `invoke-agent` job's `if:` condition
2. Switch `GH_TOKEN: secrets.GH_PAT_DISPATCH` to `GH_TOKEN: secrets.GITHUB_TOKEN` in both env blocks (1306, 1351)
3. Add a hard daily-dispatch cap externally (not in the agent's prompt — the agent's "max 3 attempts" doesn't bound new dispatched runs). Suggested mechanism: a workflow-level concurrency group with a max-runs-per-day check via `gh api`.

### 🟢 P3 — 1P vault hygiene

From the audit on 2026-04-07 (no writes were made):

| Category | Items | Action |
|---|---|---|
| Empty notes (10 OK rotation items) | `anthropic-org-acudev`, `anthropic-org-acuops-cicd`, `anthropic-org-heritage-wms`, `anthropic-org-studiob-agents`, `anthropic-org-webhook-router`, `ci-metrics-token`, `github-pat-dispatch`, `npm-pkg-token`, `regression-webhook-secret`, `voyage-ai-key` | Add 1-2 sentence purpose notes via `op item edit ... notesPlain=...` |
| Not in rotation map (8 carriers) | Averitt Express, Estes Express, FedEx Freight, Saia LTL, ShipEngine, TForce Freight, carrier-odfl, carrier-sefl | Add a `carriers` category to `secrets-map.env` mapping each to `aesthetik-production/heritage-wms` env vars |
| Not in rotation map (other) | Heritage WMS JWT Secret, phantombuster-api-key | Add to `secrets-map.env` (`auth` and `marketing` categories) |
| Naming overlap | `anthropic-key-*` vs `anthropic-org-*` per service | Decide canonical, delete the loser (Kevin manual) |
| Wrong format | `slack-kevin-user-id`, `slack-studiob-channels` (LOGIN format storing metadata) | Move to plain config (CLAUDE.md or similar), delete the 1P items |

Highest-cost dependency in the orphan list: `phantombuster-api-key` ($352/mo plan). Should be in the safety net.

## Hard constraints

- **Never publish, unpublish, or modify any Acumatica customization project** during followup work. Read-only queries except where explicitly changing webhook-router/Railway env vars after Kevin approves.
- **Never enter a password into Acumatica.** If a Chrome session is dead, stop and tell Kevin.
- **Never delete a 1Password item.** Flag for Kevin instead.
- **Never create a GitHub account or GitHub App.** Use deploy keys, GITHUB_TOKEN, or existing identities.
- **Do not run `bash scripts/rotate-secrets.sh acumatica` without explicit go-ahead** — it touches 18 entries across GH + Railway, wider blast radius than most followups need. The current GH secrets are correct and verified; the next rotation will land the same values.
- **Follow `~/.claude/CLAUDE.md` rules 9-11** — search studiob-knowledge + recall BEFORE debugging.

## Absolute paths you will need

| Purpose | Path |
|---|---|
| Main repo checkout | `/Users/kevin/dev/acumatica-ci-cd` |
| Workflow file | `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` |
| Rotation script (untracked local tooling) | `/Users/kevin/dev/acumatica-ci-cd/scripts/rotate-secrets.sh` |
| Secrets map (untracked local tooling, FIXED 2026-04-07) | `/Users/kevin/dev/acumatica-ci-cd/scripts/secrets-map.env` |
| Followup memory | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_2026_04_07_prod_restart_followups.md` |
| Memory dir | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/` |
| Original investigation prompt (reference only) | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/prompts/2026-04-07-prod-restart-investigation.md` |
| webhook-router source | `/Users/kevin/dev/webhook-router` |
| Studiob monorepo | `/Users/kevin/dev/studiob` |
| AcuOps pipeline (PROPRIETARY — keep private) | `/Users/kevin/dev/acuops-pipeline` |
| Global rules | `/Users/kevin/.claude/CLAUDE.md` |
| `op` CLI | `/opt/homebrew/bin/op` |
| `gh` CLI | `/opt/homebrew/bin/gh` |
| `railway` CLI | `/opt/homebrew/bin/railway` |

## Suggested first steps

1. Read this entire prompt
2. Read the followup memory file to confirm priorities haven't changed
3. Search `studiob-knowledge` for `2026-04-07 prod restart` and read the four ingested entries
4. Confirm with Kevin which P1/P2 item to start with — recommend webhook-router STG_* since it's the only HIGH-priority item left. Get his decision on (a)/(b)/(c) before touching anything
5. For the chosen task, follow the same operating pattern from the original incident: read-only investigation first, then a small reversible change with verification, then commit/PR with clear scope claims (don't overstate impact — see `feedback_precise_scope_claims.md`)
