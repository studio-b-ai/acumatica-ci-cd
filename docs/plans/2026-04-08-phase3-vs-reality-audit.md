# Phase 3 Vision vs. Reality — Audit

> **Track 4.1 deliverable** (from `2026-04-07-agentic-pipeline-next-stage-v2.md`).
> Written 2026-04-07 night session, after the SB501000 + 401 storm closeout that exposed how poorly the current workflow distinguishes "publish succeeded" from "verification couldn't run". Goal: an honest diff between what the 2026-04-06 Phase 3 design promised and what's actually in `acuops-deploy.yml` on main today, so Track 4.2 can present Kevin a converge/abandon/hybrid decision with eyes open.

## Source documents

| Path | What it is |
|---|---|
| `docs/plans/2026-04-05-acuops-ai-pipeline-design.md` | Phases 2–5 vision document — sets the agent-owned-deploy direction |
| `docs/plans/2026-04-06-phase3-deploy-agent-design.md` | The canonical Phase 3 architecture (this is the one to compare against) |
| `docs/plans/2026-04-06-phase3-deploy-agent-impl.md` | 7-task implementation plan |
| `docs/prompts/acuops-ai-pipeline-2027.md` | The original 2027 vision prompt |
| `agents/deploy-agent.md` | The deploy agent prompt that Phase 3 said to write (verify it exists) |
| PR #233 | "feat: Phase 3 — AI deploy agent via remote trigger" |
| PR #246 | "refactor: claude-code-action + remove test-tenant remnants" |
| PR #248 | "feat: AI failure recovery — agent diagnoses and fixes sandbox failures" |
| PR #258 | "hotfix: kill AI Failure Recovery dispatch loop + sandbox host assertion" |

## Phase 3 Design (what was promised) — 2026-04-06

### Workflow shape

```
Push to main
  │
  ├── build (package zips, validate)
  ├── qualify (static checks)
  └── invoke-agent (POST to remote trigger + upload deploy-context.json)
      │
      └── Agent (cloud VM, Anthropic-hosted) takes over:
          ├── Download artifacts via gh CLI
          ├── Pre-deploy KB query (studiob-knowledge)
          ├── Deploy to sandbox (deploy.sh + verify.py)
          ├── Wait 20 min countdown (skip if [urgent])
          ├── Pre-deploy snapshot
          ├── Deploy to prod (deploy.sh + verify.py)
          ├── Tag deploy/prod/YYYYMMDD-HHMMSS
          ├── Auto-ingest to KB
          └── DM Kevin success/failure
```

### Explicit deletions in Phase 3 design

- ❌ `test-tenant-gate` job — agent owns sandbox publish
- ❌ `deploy` job — agent owns prod publish
- ❌ `validate` (PR job) — optional standalone, "if needed"
- ❌ Email notifications — entirely removed, Slack-only
- ❌ Maintenance countdown emails to HF staff

### Key properties of the agent in the design

- **Identity:** Anthropic cloud VM, runs on remote trigger session
- **Lifecycle scope:** owns the FULL deploy lifecycle (sandbox → countdown → snapshot → prod → verify → tag → ingest)
- **Communication:** Slack only, conversational DM threads with poll/reply
- **Escalation:** DM Kevin and wait up to 2 hours for natural-language reply
- **Autonomy:** can deploy sandbox and prod (from main), tag, ingest, post #ops; must escalate on schema/ISV/3-failure/low-confidence
- **Auth:** `CLAUDE_TRIGGER_TOKEN` for invocation, agent's own env has Acumatica/Slack/GH/Qdrant secrets

### Stated risks (from the design doc)

1. Remote trigger session lifetime unknown
2. Remote trigger environment capability unclear
3. **Auth setup broken** — "Unable to resolve organization UUID" on first test
4. Artifact handoff via `gh` CLI from inside the trigger session

## What actually shipped (current `main` as of 2026-04-07)

### Workflow shape (real)

```
Push to main / workflow_dispatch
  │
  ├── build (package zips, validate)               ← unchanged
  ├── build-validate (Acuminator, Windows runner)  ← NEW post-design (PR #264)
  ├── validate (PR-only, staging)                   ← still present
  ├── qualify (static checks)                       ← unchanged
  ├── sandbox-gate (sandbox publish + UI tests)     ← STILL EXISTS (design said delete)
  ├── deploy (prod publish + verify + alert)        ← STILL EXISTS (design said delete)
  ├── invoke-agent "AI Failure Recovery (DISABLED)" ← exists but disabled via `if: false &&`
  └── post-deploy-validation                        ← still present
```

7 jobs, not 3.

### What `invoke-agent` actually is on main

From `acuops-deploy.yml` lines 1502–1592:

- **Name:** `AI Failure Recovery (DISABLED)` (per the disable hotfix)
- **Trigger condition:** `false && always() && needs.build.result == 'success' && needs.sandbox-gate.result == 'failure'` — only when sandbox-gate fails (NOT every push as the design specified)
- **Runner:** `ubuntu-latest` (NOT cloud trigger / Anthropic VM)
- **Implementation:** `uses: anthropics/claude-code-action@v1` (NOT a curl POST to a remote trigger API)
- **Scope:** Reads sandbox-gate logs + verify-result, queries Qdrant, opens a fix PR for the sandbox failure. **Does NOT own deploy lifecycle.** Pipeline still has separate `sandbox-gate` and `deploy` jobs that publish.
- **Auth:** `GH_TOKEN: secrets.GH_PAT_DISPATCH` (Kevin's personal PAT) — this is what made the 2026-04-07 dispatch loop look like Kevin caused the prod restarts
- **Limit:** `max_turns: 30, timeout_minutes: 20` — bounded but no daily-dispatch cap
- **Currently disabled:** PR #258 hotfix prefixed `if:` with `false &&` after the dispatch loop

### Diff table: design vs reality

| Property | Phase 3 Design | Current Main | Status |
|---|---|---|---|
| Number of jobs | 3 (build, qualify, invoke-agent) | 7 (build, build-validate, validate, qualify, sandbox-gate, deploy, invoke-agent, post-deploy-validation) | ❌ Diverged |
| `test-tenant-gate` | Deleted | Not present (was deleted) | ✅ Matches |
| `deploy` job | Deleted | **Still present** | ❌ Diverged |
| `sandbox-gate` job | Doesn't exist (agent does sandbox) | **Still present**, publishes + UI tests | ❌ Diverged |
| `post-deploy-validation` | Deleted | **Still present** | ❌ Diverged |
| Agent runtime | Anthropic cloud VM via remote trigger | GH Actions ubuntu-latest via `claude-code-action@v1` | ❌ Diverged |
| Agent invocation | `curl POST /v1/code/triggers/$ID/run` | `uses: anthropics/claude-code-action@v1` | ❌ Diverged |
| Agent scope | Full deploy lifecycle (sandbox + countdown + prod + verify + finalize) | Failure recovery only — read logs, open fix PR | ❌ Narrowed |
| Agent triggered when | Every push to main (after build+qualify) | Only when sandbox-gate fails | ❌ Diverged |
| Identity in audit log | Cloud trigger session (Anthropic) | `GH_PAT_DISPATCH` (Kevin's personal PAT) → looks like Kevin | ❌ Worse than design — design said deploy-bot identity |
| Slack DM threads | Conversational poll/reply, 2h timeout | One-shot DM on failure (no threading/polling) | ❌ Diverged |
| 20-min prod countdown | In agent | In `deploy` job (`Send maintenance countdown warnings` step) | ⚠️ Different location, exists |
| Pre-deploy snapshot | In agent | In `deploy` job (`Pre-deploy snapshot` step) | ⚠️ Different location, exists |
| Auto-ingest to KB | Agent does it on success/failure | `deploy` job has `Auto-ingest deploy incident` and `Auto-ingest deploy success` steps | ⚠️ Different location, exists |
| Deploy tagging | Agent | `deploy` job has `Tag successful deploy` step | ⚠️ Different location, exists |
| Email notifications | Removed entirely | Removed (✅) | ✅ Matches |
| `CLAUDE_TRIGGER_TOKEN` secret | Required new secret | Not set (no trigger to call) | ➖ N/A — design path not taken |
| `agents/deploy-agent.md` | Created in PR #233 | **Exists on main, 599 lines** — full lifecycle prompt as designed. Just nothing currently calls it (the `invoke-agent` step's `claude-code-action` uses an inline failure-recovery prompt instead) | ✅ Shipped, ⚠️ orphaned |
| Daily dispatch cap | Not in design (assumed safe) | Not implemented; Track 2.2 will add it | ➖ Both missing |
| Kill switch | Not in design | `if: false &&` (binary hack from PR #258) | ⚠️ Workaround |

### Why the divergence (timeline reconstruction)

1. **2026-04-06:** Phase 3 design + impl plan written. Goal: agent owns deploy lifecycle via remote trigger.
2. **PR #233 merged:** Adds `invoke-agent` job that POSTs to remote trigger. Tasks 6+7 (create the trigger, E2E test) **deferred** because the remote trigger API returned "Unable to resolve organization UUID" — auth bug, blocking.
3. The trigger never got created → `invoke-agent` had nothing to call → entire Phase 3 vision blocked.
4. **PR #246 merged:** "refactor: claude-code-action + remove test-tenant remnants" — replaced the trigger curl call with `claude-code-action@v1` as a workaround. Pipeline still had `deploy` and friends because nothing was orchestrating the agent end-to-end. So the team kept the conventional jobs AND added an agent step.
5. **PR #248 merged:** "feat: AI failure recovery — agent diagnoses and fixes sandbox failures." This is the key narrowing — the `invoke-agent` job's prompt was rewritten to scope it to "fix sandbox failures by opening PRs" instead of "own deploy lifecycle". Different job, same name. Triggered only on `sandbox-gate.result == 'failure'`. Used `GH_PAT_DISPATCH` so its commits/dispatches showed as Kevin in the audit log.
6. **2026-04-07 incident:** AI Failure Recovery agent caught a sandbox-gate failure (caused by `ACUMATICA_SANDBOX_*` secrets pointing at prod), fixed nothing, dispatched a new run, hit the same failure, dispatched again. 8 prod restarts in 14 hours. Audit log looked like Kevin because of `GH_PAT_DISPATCH`.
7. **PR #258 hotfix:** Disabled invoke-agent via `if: false &&` + added sandbox host-assertion guard.
8. The vision doc stayed checked in but the actual workflow drifted into a hybrid that nobody designed deliberately.

### Other things on main that don't exist in the design

- **`build-validate` job (PR #264)** — Acuminator gating on a self-hosted Windows runner. Catches DAC/BQL bugs before sandbox. Post-design addition. Reasonable.
- **`vm-agent.yml`** — separate workflow for on-demand `claude -p` on the VM runner. Different shape from invoke-agent. Used by Mode 2 dispatches.
- **After-hours gate (PR #262)** — hard gate on prod publishes during business hours. Not in Phase 3 design but reasonable.
- **`force_deploy=OVERRIDE` workflow_dispatch input (PR #270)** — emergency bypass for sandbox-gate failure. Manual recovery tool.
- **EnsureColumn / EnsureTable plugin pattern** — `AesthetikContainersInstall` runs DDL on every publish. Tonight's PR #272 just added `UsrContainerCost` to it. Not Phase 3 related, just orthogonal infra.

## Honest assessment

What's in main today is **neither the Phase 3 vision nor the pre-Phase-3 conventional pipeline**. It's a hybrid that grew accidentally:

- The conventional `deploy` + `sandbox-gate` jobs do all the actual deploying
- A separate `claude-code-action` step exists but is scoped down to "open a fix PR if sandbox fails" and is currently disabled
- The pipeline has the costs of both approaches and the benefits of neither

**What the hybrid loses vs. each pure path:**

vs. **Pure conventional (no agent):**
- Carries the disabled invoke-agent stub + its config + its risk surface
- Has `GH_PAT_DISPATCH` plumbing it doesn't use today but can't remove without breaking the disabled job
- Still has the dispatch-loop risk if invoke-agent is ever re-enabled without the Safety Package

vs. **Pure Phase 3 (agent owns lifecycle):**
- 4 extra jobs the agent should own
- Cannot distinguish "publish succeeded but verify can't talk to API" from "publish broke prod" — exactly what bit us tonight
- Cannot reach into verify-result.json to make a smart "succeeded with warnings" call vs the binary step-conclusion that fired the false alarm
- Email/slack/notification logic scattered across `deploy` job steps instead of in agent prompt

**What the hybrid does keep that's actually valuable:**

- `build-validate` (Acuminator) — Phase 3 design predates this and didn't anticipate the value of an Acuminator gate. Worth keeping regardless of which direction Track 4.2 chooses.
- After-hours gate — survives any future direction
- `EnsureTable`/`EnsureColumn` plugin pattern — orthogonal, survives
- The `studiob-api` gateway pattern (separate from this audit but related) — webhook-router / AcuDev / verify.py would all benefit from going through a session-pooled gateway

## Questions Track 4.2 must answer

1. **Is Phase 3's "agent owns full deploy lifecycle" still the right end state?** Or has the hybrid converged on a more pragmatic shape that we should formalize instead?
2. **If we converge on the design:** what do we do about (a) the remote trigger API bug from 2026-04-06, (b) the `deploy.py` / `verify.py` scripts that already do the publish work, (c) the `sandbox-gate` UI test infrastructure?
3. **If we abandon the design:** how do we delete the `invoke-agent` stub without losing the option of bringing it back? Document the decision. Update the 2027 vision doc. Mark `agents/deploy-agent.md` as historical.
4. **If we hybrid:** where exactly is the line? "Agent only handles failure recovery" (current shape) vs "Agent handles deploy + conventional jobs are fallback" vs "Agent handles diagnosis only, conventional jobs do all the work"?
5. **What about Mode 2 (`vm-agent.yml`)?** It's a third agent surface. Does it converge with invoke-agent or stay separate?
6. **Identity:** even in the hybrid, `GH_PAT_DISPATCH` must die. Track 2.1 retires it for cross-repo checkout but invoke-agent has its own copies of `GH_TOKEN: secrets.GH_PAT_DISPATCH`. Track 2.3 swaps those to `GITHUB_TOKEN`. Track 4 needs to confirm this is sufficient or recommend a deploy-bot account.

These map to Track 4.2's a/b/c options.

## Files to read for Track 4.2

- ✅ `agents/deploy-agent.md` — confirmed exists on main, 599 lines, full lifecycle prompt as Phase 3 designed (just orphaned right now)
- `.github/workflows/vm-agent.yml` — Mode 2 surface, needed to understand if it converges with invoke-agent
- `pipeline/scripts/deploy.py` (in `acuops-pipeline` private repo — proprietary, the publish primitive any direction would call)
- `pipeline/scripts/verify.py` (same)
- The Anthropic remote trigger docs — current state of the API + auth flow as of 2026-04-07 (was broken when Phase 3 shipped; re-test before basing a converge decision on it)

## Important update from this audit pass

**`agents/deploy-agent.md` already exists on main as a 599-line full-lifecycle prompt.** This significantly changes the Track 4.2 cost analysis for option (a) Converge:

- The agent prompt is already written and reviewed
- The `invoke-agent` job already exists, just needs its inline failure-recovery prompt swapped for `agents/deploy-agent.md` content + `claude-code-action` swapped for the remote-trigger curl
- The conventional `deploy` and `sandbox-gate` jobs need to be deleted (or moved into the agent's tool-call surface)
- The blocker is still the remote trigger API auth bug from 2026-04-06 — re-test it before committing to (a)

This means **(a) Converge is closer to "wire up the existing pieces" than "build from scratch"**, which materially changes the Kevin-decision math. Track 4.2 should reflect this.

## Next: write Track 4.2 design doc with three options

Document at `docs/plans/2026-04-08-remote-trigger-convergence-design.md` presenting:
- **(a) Converge** — implement Phase 3 as designed, replace conventional jobs with agent
- **(b) Abandon** — delete invoke-agent stub, accept conventional pipeline, mark Phase 3 vision historical
- **(c) Hybrid (formalized)** — keep conventional deploy + a sharply-scoped agent for diagnosis OR failure recovery, with the line drawn explicitly

For each: trade-offs, what changes, what stays, who needs to do what, blockers.
