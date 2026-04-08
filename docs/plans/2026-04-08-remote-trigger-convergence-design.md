# Remote Trigger Convergence — Design Doc (Track 4.2)

> **Track 4.2 deliverable** from `2026-04-07-agentic-pipeline-next-stage-v2.md`. Reads alongside `2026-04-08-phase3-vs-reality-audit.md` (Track 4.1).
>
> **DECISION (2026-04-07 night session): Option (a) — Converge on Phase 3 — with a 1-hour API verification kill criterion gating the commitment.**
>
> **KILL CRITERION FIRED (2026-04-08 early AM session): API still broken — same `Unable to resolve organization UUID` error as 2026-04-06. Automatic fallback to option (c) Hybrid Formalized is now active.** See `docs/plans/2026-04-08-remote-trigger-api-status.md` for the verification result.
>
> **Active direction: (c) Hybrid Formalized.** Tracks 2.1 → 2.2 → 2.3 → 2.4 proceed with `invoke-agent` scoped to diagnosis-only and `claude-code-action@v1` as the runtime. Tracks 4.3.1 / 4.3.2 / 4.3.3 / 4.3.4 / 4.3.5 are **deferred indefinitely** pending upstream API fix. A quarterly re-test is scheduled — when the API recovers, (a) cutover can be revisited.
>
> **No implementation code changes to (c) path until:** Track 2.4 dry run is green.

## What this doc decides

The pipeline today is a hybrid that nobody designed. Phase 3 (2026-04-06) committed to "agent owns deploy lifecycle via remote trigger" but the implementation diverged into "claude-code-action does failure recovery only, conventional `deploy` and `sandbox-gate` jobs do the actual deploying" — and even that is currently disabled by `if: false &&` from the 2026-04-07 incident hotfix.

This doc presents three paths forward and a recommendation. Kevin picks one before any Track 4 code lands.

## The forces

From tonight's experience + the 4.1 audit:

1. **The conventional pipeline cannot distinguish "publish succeeded but verify can't reach API" from "publish broke prod."** Tonight's 4 false-failure runs proved this. An agent reading verify-result.json would have called it correctly.
2. **The remote trigger API was broken on 2026-04-06** ("Unable to resolve organization UUID"). Has it been fixed? Unknown — needs re-test before option (a) can be committed to.
3. **`agents/deploy-agent.md` already exists on main as a 599-line full-lifecycle prompt.** The expensive part of (a) is already done.
4. **The conventional `deploy.py` / `verify.py` scripts in `acuops-pipeline` are the proven publish primitive.** Any direction will call them. They aren't being thrown away.
5. **`build-validate` (Acuminator gating, Windows runner) is a post-Phase-3 addition that's clearly valuable** and not in the 2026-04-06 design. Whatever direction we pick must keep it.
6. **Identity is broken regardless of direction.** `GH_PAT_DISPATCH` made tonight's incident look like Kevin caused the restarts. Track 2.1 and 2.3 solve it for cross-repo checkout and the agent step, but the broader question — "what identity does the orchestrator run as?" — is still open.
7. **Kevin's tolerance for false alarms is limited.** Tonight's 4 false-failure DM-spam events plus 12+ prod app pool restarts is the cost of the current shape. Convergence has to net reduce that.

## Option (a) — Converge on Phase 3

**Vision restated:** GH Actions = `build` + `qualify` + `invoke-agent` (3 jobs). The agent runs in Anthropic's cloud VM via remote trigger, reads `agents/deploy-agent.md`, owns the full sandbox → countdown → prod → verify → tag → ingest → DM lifecycle. Conventional `deploy`, `sandbox-gate`, `post-deploy-validation` jobs are deleted.

### What changes
- Re-test the remote trigger API auth (`Unable to resolve organization UUID` blocker from 2026-04-06)
- Create the trigger via web UI or API with `agents/deploy-agent.md` as the prompt body
- Set `CLAUDE_TRIGGER_TOKEN` and `CLAUDE_TRIGGER_ID` GH secrets
- Rewrite `invoke-agent` job: replace `uses: anthropics/claude-code-action@v1 ...` with a `curl POST /v1/code/triggers/$ID/run` step that uploads `deploy-context.json` artifact and triggers the agent
- Move job dependency from `needs: [build, qualify, sandbox-gate]` (current) to `needs: [build, qualify]` (design)
- **Delete jobs:** `sandbox-gate`, `deploy`, `post-deploy-validation` (or move their step contents into the agent's prompt as tool calls)
- Provision agent environment with Acumatica/Slack/Qdrant/GH/AcuDev secrets (the agent runs server-side, not in GH Actions runner)
- Verify the agent can `gh run download` artifacts from the cloud VM
- Verify the agent can `git push --tags` and write back to the repo

### What stays
- `build` — unchanged
- `build-validate` — unchanged (Acuminator gating, predates this design but valuable)
- `qualify` — unchanged
- `agents/deploy-agent.md` — unchanged, finally invoked
- `deploy.py` / `verify.py` in `acuops-pipeline` — agent calls them as shell tools
- `studiob-knowledge` Qdrant collection + auto-ingestion endpoint — unchanged
- Slack DM model — agent owns it
- After-hours gate — moves into the agent prompt as a guard ("if it's business hours, post to #ops and wait")

### Blockers
- 🔴 **Remote trigger API auth bug.** Last status (2026-04-06): "Unable to resolve organization UUID". Must be re-tested before this option is even possible. If still broken, (a) is blocked indefinitely.
- 🔴 **Remote trigger session lifetime.** Unknown. If sessions die after N minutes, the 20-minute prod countdown + escalation polling needs a way to resume via session memory (recall skill?). Validate via test trigger before committing.
- 🔴 **Cloud VM tool capability.** Can the trigger session run `bash`, `python3`, `gh`, `curl`, `git`? Can it install packages? Can it talk to the studiob-api gateway and the prod Acumatica directly? Validate before committing.
- 🟡 **Identity for the cloud agent.** The agent's `GH_TOKEN` needs to be NOT Kevin's PAT — needs a deploy-bot account or fine-grained PAT scoped to this repo with minimum perms. Audit log story matters.
- 🟡 **Concurrent dispatch protection.** Phase 3 design didn't include a daily-dispatch cap or kill switch — those are Track 2.2/2.3. Either bake them into the agent itself or keep the GH Actions step as a thin guard before invoking.
- 🟡 **Failure modes not in the design.** Tonight's failure shape — verify.py blocked by API Login Limit on a healthy publish — isn't in the 2026-04-06 design's escalation taxonomy. Need to add: "if verify.py returns 401 on every call but login succeeded, recommend studiob-api session pool audit, don't rollback."

### Effort estimate (rough)
- Re-test remote trigger API + auth: 1 session (read API docs, run experiments)
- Wire up trigger + secrets + invoke-agent rewrite: 1 session
- Delete `sandbox-gate` / `deploy` / `post-deploy-validation`, move steps into agent: 2 sessions (high blast radius — needs sandbox dry-run + careful migration)
- Test the lifecycle end-to-end with `[urgent]` + sandbox-only deploys: 1 session
- **Total:** ~5 focused sessions, assuming the API works. Much more if the API is still broken.

### When (a) is the right choice
- Remote trigger API is healthy and well-documented
- Kevin trusts the agent enough to own prod publish (high-stakes, irreversible)
- Tonight's failure shape (verify.py blocked) becomes the agent's primary diagnostic responsibility — this is what Track 4 is FOR
- We want to ship the 2026-04-06 vision honestly instead of a hybrid that pretends to be it

### When (a) is the wrong choice
- Remote trigger API is still broken or has hard usage limits
- Kevin isn't ready to delegate prod publish to a server-side agent he can't watch in real time
- The cloud VM session can't reach Heritage's prod Acumatica (network/firewall) without complex setup

---

## Option (b) — Abandon Phase 3, formalize the conventional pipeline

**Vision restated:** Accept that the agent vision didn't pan out. The pipeline is `build` → `build-validate` → `qualify` → `sandbox-gate` → `deploy` → `post-deploy-validation`. Kill the disabled `invoke-agent` job entirely. Document the decision so future sessions don't reanimate it.

### What changes
- Delete the `invoke-agent` job from `acuops-deploy.yml` (the entire DISABLED block, lines 1502–1592)
- Delete `agents/deploy-agent.md`
- Delete the `CLAUDE_TRIGGER_TOKEN` / `CLAUDE_TRIGGER_ID` secrets if they exist
- Delete `vm-agent.yml` (or scope it to non-deploy work only — Mode 3 sentinel candidate)
- Mark `2026-04-06-phase3-deploy-agent-design.md` and `2026-04-06-phase3-deploy-agent-impl.md` as historical/superseded with a banner at the top
- Update `acuops-ai-pipeline-2027.md` to remove Phase 3 from the roadmap (or rewrite as "Phase 3 — Conventional pipeline hardening" with a different scope)
- Track 2.3 (re-enable invoke-agent with Safety Package) becomes a no-op — there's nothing to re-enable
- Track 2.4 (failure dry run) becomes a no-op
- Track 4 closes immediately after this decision

### What stays
- Everything that does the actual work today: `build`, `build-validate`, `qualify`, `sandbox-gate`, `deploy`, `post-deploy-validation`, after-hours gate, EnsureColumn/EnsureTable plugin pattern, Slack DM on failure (one-shot, not threaded)
- `studiob-knowledge` + auto-ingestion (still useful for human debugging)
- `vm-agent.yml` — if kept, scoped to Mode 3 sentinel + on-demand ad-hoc work, NEVER touches deploy

### Blockers
- 🟡 **Identity story unresolved.** `GH_PAT_DISPATCH` still in cross-repo checkout (Track 2.1 fixes this regardless of direction). The "agent identity" question goes away if there's no agent.
- 🟡 **Tonight's failure shape isn't fixed by this option.** The conventional pipeline is what produced the false-alarm storm. (b) doesn't address verify.py treating API Login Limit as a publish failure. We'd need separate fixes for fixture-gen 404 + verify.py session reuse + alert-step truth-checking. (Those fixes are in the v2 backlog already.)
- 🟡 **Kevin loses the agentic ambition.** This is the option that says "the dream is dead, ship what works."

### Effort estimate
- Delete invoke-agent stub + secrets + docs: 1 session
- Update the 2027 vision doc + 4.1 audit conclusion: 1 session
- Address the v2 backlog items individually (fixture-gen 404, verify.py 401 root cause, alert step bug): 2-3 sessions
- **Total:** 3-4 sessions

### When (b) is the right choice
- Remote trigger API is genuinely broken and Anthropic isn't fixing it on a useful timeline
- Kevin's tolerance for "another agent experiment" is exhausted after tonight's incident
- The conventional pipeline + targeted fixes (fixture-gen, verify.py, alert step) would solve 80% of tonight's pain at 20% of (a)'s cost
- Studio B's commercial focus (productizing acuops-pipeline for the VAR channel) prefers a deterministic pipeline over an agentic one — VAR partners may not have an Anthropic workspace

### When (b) is the wrong choice
- Tonight's failure shape (verify.py blocked, conventional pipeline can't tell publish from verification) recurs because the conventional fixes are partial and the agent would catch what scripts can't
- The "agent owns lifecycle" vision is core to Studio B's product positioning (AI-managed Acumatica) and abandoning it undermines the pitch

---

## Option (c) — Hybrid, formalized (RECOMMENDED)

**Vision restated:** Stop pretending the hybrid is temporary. Draw the line deliberately: **conventional pipeline owns deploy, agent owns diagnosis + recovery**. Both are first-class. The agent's scope is sharply bounded so it can't loop. Path to (a) stays open as a future migration once trust is built.

### Where the line goes

| Concern | Owner |
|---|---|
| Build customization package | Conventional `build` job |
| Acuminator (Windows-only) | Conventional `build-validate` job |
| Static qualification checks | Conventional `qualify` job |
| Sandbox publish | Conventional `sandbox-gate` job (publishes via `deploy.py`) |
| Sandbox UI tests | Conventional `sandbox-gate` job |
| Production publish | Conventional `deploy` job (publishes via `deploy.py`) |
| Pre-deploy snapshot | Conventional `deploy` job |
| Post-publish verification (verify.py) | Conventional `deploy` job, with **agent reading verify-result.json to make the "real failure vs. infra noise" call** (NEW) |
| 20-min countdown | Conventional `deploy` job |
| Tagging deploy/prod/* | Conventional `deploy` job |
| Auto-ingest to KB | Conventional `deploy` job |
| **Diagnosis when verify.py fails** | **Agent** — reads verify-result.json + Qdrant + sandbox-gate logs, posts a DM to Kevin with diagnosis (publish OK but API blocked / publish broken / unknown) |
| **Failure recovery PR** | Agent — only when diagnosis says "fixable code change" |
| Slack DM threads (conversational) | Agent (in diagnosis path), conventional one-shot for clear failures |
| Daily dispatch cap | Conventional GH Actions step before invoke-agent fires (Track 2.2 composite action) |
| Kill switch | GH variable `INVOKE_AGENT_ENABLED` (Track 2.3 Safety Package) |

### What changes from current main
- Keep `claude-code-action@v1` on `ubuntu-latest` (it works, predates the remote trigger bug, no env setup needed)
- **Rewrite the agent prompt** in the `invoke-agent` step. Move from PR #248's "fix sandbox failures by opening PRs" to a tighter scope: "Read verify-result.json + sandbox-gate logs. Output a structured diagnosis: PUBLISH_OK / PUBLISH_BROKEN / VERIFY_INFRA / UNKNOWN. If PUBLISH_OK, post 'verify failed but publish succeeded' to #ops and to Kevin DM, do NOT open a PR. If PUBLISH_BROKEN, post diagnosis + open a fix PR if you can confidently identify the cause. Else escalate."
- Add the Safety Package A–F (already in v1 plan Track 2.3) — kill switch, daily cap, pre-notification, identity attribution, bounded scope
- Triggered when: `sandbox-gate.result == 'failure' OR (deploy.result == 'success' AND steps.verify.outcome == 'failure')` — i.e., not just sandbox failures, also post-deploy verification failures
- **Critical:** the agent is read-only by default. It can post to Slack and open PRs. It cannot publish to Acumatica, restart the app pool, or modify the workflow file
- `agents/deploy-agent.md` becomes the agent's KB resource (it can read it for context on Slack patterns / Qdrant queries) but it does NOT execute the full lifecycle described there
- Document the decision in the 2027 vision doc + a new memory file `project_phase3_hybrid_formalized.md`

### What stays
- All conventional jobs unchanged in shape (just no longer chasing deletion)
- `agents/deploy-agent.md` stays as a reference / future-state target
- 2026-04-06 design docs stay as historical "what we wanted, deferred"
- After-hours gate, EnsureColumn/EnsureTable plugin, Slack notifications — all unchanged

### Blockers
- 🟡 **Tonight's verify.py 401 storm root cause** (studiob-api session pool saturation). The agent can DIAGNOSE this — "verify.py login succeeded then 401 on entity calls = API Login Limit" — but the FIX is in studiob-api, not the agent. So this option still requires the studiob-api session-pool audit (P1 deferred backlog).
- 🟡 **Identity for the agent.** Track 2.3 Safety Package B swaps `GH_PAT_DISPATCH` → `GITHUB_TOKEN` for the agent's GH interactions. That's necessary regardless. (c) inherits it.
- 🟡 **Daily dispatch cap implementation.** Track 2.2 (composite action) is required before re-enabling. (c) inherits the dependency on Tracks 2.1/2.2/2.3.
- 🟡 **Track 2.4 dry run still required.** Cannot flip `INVOKE_AGENT_ENABLED=true` without proving the Safety Package works. (c) inherits this gate.

### Effort estimate
- Rewrite agent prompt for sharper scope (~2 hours): 1 session
- Implement Tracks 2.1, 2.2, 2.3 (deploy keys, daily cap, Safety Package): existing v2 plan, 3-4 sessions
- Track 2.4 dry run: 1 session
- Audit doc + decision write-up + memory file: 1 session
- **Total:** 6-7 sessions to ship Track 2 + (c). This is essentially the existing v2 plan with the Track 4 question answered by "stop here, formalize this shape, defer (a) until trust is built."

### When (c) is the right choice
- We want to keep the agentic option alive without betting the deploy pipeline on it
- The conventional path is brittle in known ways (tonight's 4 false alarms) but the bugs are diagnosable, not architectural
- Kevin needs to ship Track 2 + the deferred backlog before any larger architectural change
- Studio B's commercial story can be "agent diagnoses, conventional pipeline executes" — both are real, both add value, neither is single-point-of-failure
- Tonight's lesson is "the conventional pipeline can't read JSON output well" — that's exactly what an agent SHOULD be doing. (c) puts the agent in that role specifically.

### When (c) is the wrong choice
- Kevin wants to stop maintaining two parallel orchestration models
- The conventional `deploy` job's logic genuinely IS broken (not just the verify step's interpretation) and needs the agent to own the publish too

## Recommendation: (c) Hybrid, formalized

**Why:**

1. **Tonight's actual failure mode is exactly the case (c) targets.** The publish step succeeded, the verify step's *interpretation* of API Login Limit was wrong, and the alert step fired on a false signal. An agent reading verify-result.json would have caught it. (c) puts the agent in that exact role.

2. **(a) is high-stakes and currently blocked.** Remote trigger API may still be broken. Cloud VM environment unverified. Kevin would be delegating prod publish to a system he can't watch. After tonight's 12+ restarts, the appetite for "trust the agent with publish" is low.

3. **(b) discards a built asset.** `agents/deploy-agent.md` is 599 lines of validated lifecycle prompt. Throwing it away means the next time we have this conversation, we start from zero.

4. **(c) inherits the existing v2 plan unchanged.** Tracks 2.1 → 2.2 → 2.3 → 2.4 are already designed for exactly this scope. (c) just commits to "this is the end state for now," not "this is temporary scaffolding."

5. **(c) keeps a path to (a).** Once the studiob-api session pool is fixed + Safety Package is proven via 2.4 dry run + daily cap is battle-tested + remote trigger API is verified working, the migration from (c) to (a) is "swap claude-code-action for the trigger curl and migrate the conventional deploy steps into the agent prompt." Future Track 4 can do that as a clean follow-up rather than a from-scratch rewrite.

6. **(c) makes the v2 plan deferred backlog matter more.** Most of the P1 items (fixture-gen 404, verify.py 401 root cause, workflow path filter, studiob-api naming-trap regression) are required for either (b) or (c) to actually work. They're not blocked on this decision. We can ship them in parallel.

## (c) is a stepping stone, not a dead end — migration path to (a)

Kevin asked the right question: *"Can we expand the scope if we want in the future? I imagine that feature will eventually be resolved in API and we'll be fine."* The answer is yes, by design. This section makes the migration path explicit so future sessions don't have to re-derive it.

### What carries forward from (c) to (a) for free

| Asset | Already done in (c) | Reused unchanged in (a) |
|---|---|---|
| `agents/deploy-agent.md` (599 lines, full lifecycle prompt) | ✅ on main today | ✅ same file, finally invoked |
| `deploy.py` / `verify.py` publish primitives | ✅ called by conventional jobs | ✅ called by agent as shell tools |
| `studiob-knowledge` Qdrant + auto-ingestion endpoint | ✅ live | ✅ same |
| Slack DM model + bot scopes | ✅ live | ✅ same, threading added |
| Safety Package A–F (kill switch, daily cap, identity attribution, bounded scope, pre-notification, cause-eliminated host assertion) | ✅ Tracks 2.1–2.3 | ✅ same primitives, recalibrated for wider blast radius |
| `build` + `build-validate` + `qualify` jobs | ✅ unchanged | ✅ unchanged |
| After-hours gate | ✅ in `deploy` job | ⚠️ moves into agent prompt as a guard |
| Auto-ingest, deploy tagging, snapshot | ✅ in `deploy` job steps | ⚠️ moves into agent prompt as tool calls |

### What changes in the (c) → (a) migration

| Change | Effort |
|---|---|
| Re-test remote trigger API auth — must succeed before migration | 1 session of API exploration |
| Create the trigger via web UI or API with `agents/deploy-agent.md` as prompt body | 1 session |
| Set `CLAUDE_TRIGGER_TOKEN` + `CLAUDE_TRIGGER_ID` GH secrets (Track 4 will document this) | Trivial |
| Rewrite `invoke-agent` step: `uses: anthropics/claude-code-action@v1` → `curl POST /v1/code/triggers/$ID/run` | Half-session |
| Move `sandbox-gate` job logic into the agent prompt (or keep it as the agent's "tool" via `bash` calls into the existing job's script content) | 1 session (not destructive — agent calls the same scripts) |
| Move `deploy` job logic into the agent prompt similarly | 1 session |
| Delete the now-unused conventional jobs (or keep them as `workflow_dispatch`-only manual fallbacks for incident recovery) | Half-session + sandbox dry run |
| Re-validate the Safety Package against the wider blast radius (agent now owns publish, so the daily cap might need adjustment, the kill switch needs to be reachable from a remote trigger session, etc.) | 1 session + dry run |
| End-to-end test with `[urgent]` commit + sandbox-only deploys | 1 session |
| **Total migration cost from (c) to (a):** | **5–6 focused sessions, assuming the API works** |

This is essentially the original (a) cost — the migration doesn't pay for (c) twice. (c) just lets us defer the API blocker without losing built work.

### Calcification avoidance rules — keep (c) migratable

If we let (c) accumulate the wrong kind of complexity, the migration to (a) becomes a rewrite instead of a refactor. Two rules to avoid that:

**Rule 1 — Keep the agent prompt's input contract pure JSON.**

The (c) agent's job is "read verify-result.json + sandbox-gate logs and emit a structured diagnosis." Its inputs should be:

- `verify-result.json` (already produced by `deploy` job)
- Sandbox-gate stdout (already captured)
- Optional: Qdrant query results (agent fetches itself)

It should **NOT** depend on `${{ github.event.* }}` context variables, `${{ steps.<id>.outputs.* }}` references, or `${{ needs.<job>.outputs.* }}` plumbing it doesn't strictly need. Why: when the agent moves to a remote trigger session, none of that context exists. Anything the agent reads from GH Actions context becomes a thing the migration has to rewire.

**Rule 2 — Don't add conventional-job logic that duplicates agent capabilities.**

If a conventional `deploy` step needs smarter "is this a real failure or infra noise" logic, add it to the agent prompt instead of putting Python in `deploy`. Why: every line of "smart" bash/python in the conventional jobs is a line we'll regret twice — once maintaining it, once deleting it for (a). The agent runs fast and cheap; let it absorb new diagnostic responsibilities.

Concrete examples of what NOT to do in (c):

- ❌ Add a `deploy` step that parses `verify-result.json` to decide whether to alert. **Do instead:** alert on every verify failure, let the agent's diagnosis trigger a "false alarm — clear it" Slack message + suppress the alert in studiob-knowledge.
- ❌ Add a `sandbox-gate` step that hits an OData endpoint to "smartly" generate fixtures. **Do instead:** make fixture generation `continue-on-error: true`, let the agent flag "fixtures unavailable, sandbox tests degraded" if it matters.
- ❌ Build a Python helper in `acuops-pipeline` that classifies `verify.py` failures into categories. **Do instead:** the agent does the classification on the JSON output.

### Migration trigger checklist

Revisit (c) → (a) when ≥3 of these are true:

- [ ] **Remote trigger API auth confirmed working** (re-test quarterly via `RemoteTrigger list`; if successful, that's a strong signal)
- [ ] **Track 2.4 dry run is green and the Safety Package has been battle-tested for at least 30 days** in the (c) shape without false alarms or the kill switch being needed
- [ ] **studiob-api session pool root cause fixed** (verify.py reliable, no API Login Limit storms)
- [ ] **At least one prod failure where the (c) agent diagnosed correctly but couldn't ACT** — concrete proof that (a) would deliver value the conventional pipeline + (c) diagnostic agent can't
- [ ] **Studio B's commercial story benefits from the agent-owned-deploy narrative** (VAR pitch, customer demand)

When this fires, Track 4.3 reopens as "(c) → (a) migration" and the design above becomes the spec. The conversation stays at the architectural level — no rebuilding from scratch.

### What this means for tonight's decision

Picking (c) now is a low-regret move. We're not making (a) impossible; we're paying the (c) cost (which is mostly the same as the v2 plan's existing Track 2 cost) and earning the option to migrate later. If the remote trigger API stays broken for 6 months, (c) is also a complete shippable end state — not a half-finished thing waiting for (a).

If the API is fixed in 3 weeks, the (c) → (a) migration is 5-6 sessions of mostly mechanical work. That's a deferred Track 4.3 we can schedule when the prerequisites line up.

The two calcification rules above are the only thing protecting future-us from a worse migration story. Both are cheap to follow.

## Decision + execution plan — (a) with kill criterion

**Decision date:** 2026-04-07 night session
**Decision:** Option (a) — Converge on Phase 3 (agent owns full deploy lifecycle via remote trigger)
**Kill criterion:** Track 4.3.0 — 1-hour API verification. If the remote trigger API is broken, fall back to (c) automatically. No work wasted because Tracks 2.1–2.3 + the deferred backlog ship in either direction.

### Why (a) over (c) — updated reasoning

The initial recommendation was (c) Hybrid Formalized on the theory that "the remote trigger API is broken, we can't commit to (a) until that's fixed." On re-reading: the API status is **testable in one hour**, not a multi-week investigation. That collapses the biggest (a) blocker into a fast kill criterion. The rest of the (c) argument was conservatism:

- "Agent-owned prod publish is high stakes" — true for (c) too. (c)'s agent eventually opens fix PRs that get merged and publish. The trust question is the same, just one indirection further.
- "599 lines of lifecycle prompt is built but unused" — argument FOR (a), not against. We already paid the prompt-writing cost; (c) defers using it.

And the product story is decisive: **Studio B is productizing `acuops-pipeline` for the Acumatica VAR channel.** "AI-managed Acumatica deploys" sells in (a). "AI diagnoses errors on a conventional pipeline" is a much harder pitch.

Tonight's 2026-04-07 failure mode is the canonical (a) case — the conventional pipeline can't distinguish "publish OK + verify infra blocked" from "publish broken." (c) makes the agent a post-hoc commentator on that JSON output. (a) lets it make the call.

### Execution order (next-session ready)

**Track 4.3.0 — API verification (DO THIS FIRST, ~1 hour)**

Re-test the remote trigger API auth before committing resources to anything else:

```
1. RemoteTrigger list    → does it return without "Unable to resolve organization UUID"?
2. If yes: RemoteTrigger create with a trivial echo prompt
3. RemoteTrigger run against the test trigger
4. Verify the run completes and produces output
5. Document the result in docs/plans/2026-04-08-remote-trigger-api-status.md
```

**If API works → commit fully to (a).** Proceed with the execution order below.

**If API still broken → fall back to (c) automatically.** Update this doc's decision header, start quarterly API re-test cron, and the execution order below becomes the (c) work (which is the existing v2 plan Tracks 2.1–2.4 unchanged).

### (a) execution order — assumes API verification passes

Estimated 10–12 focused sessions, staged so each phase has a gate before the next:

| # | Track | Scope | Gate before next |
|---|---|---|---|
| 1 | 4.3.0 | API verification (above) | API works OR fallback to (c) |
| 2 | Backlog | Deferred P1 backlog in parallel: fixture-gen 404, workflow path filter, studiob-api session pool audit | No-regret — ships regardless |
| 3 | 2.0.b | Merge webhook-router PR #64 (Track 0 formal close) | PR green |
| 4 | 2.1 | Retire `GH_PAT_DISPATCH` from cross-repo checkout via deploy keys | 6 checkouts use `ssh-key`, pipeline green |
| 5 | 2.2 | Build `daily-dispatch-cap` composite action | Unit test passes at cap=999, fails at cap=0 |
| 6 | 2.3 | Wire Safety Package A–F into `invoke-agent` job. **Load `agents/deploy-agent.md` as the prompt (not the current failure-recovery prompt).** Leave `INVOKE_AGENT_ENABLED=false` until 4.3.1 passes. | YAML valid, draft PR open |
| 7 | 4.3.1 | Create the Claude Code remote trigger with `agents/deploy-agent.md` content. Set `CLAUDE_TRIGGER_TOKEN` + `CLAUDE_TRIGGER_ID` GH secrets. Rewrite `invoke-agent` job's claude-code-action step with a `curl POST /v1/code/triggers/$ID/run` step. | Trigger reachable from GH Actions |
| 8 | 4.3.2 | **Sandbox-only dry run.** Dispatch invoke-agent with `environment=sandbox-only` input, deliberate sandbox-gate-breaker. Agent must: download artifacts, read verify-result.json, post Slack diagnosis, open a fix PR, NOT touch prod. | All 8 observations from v1 Track 2.4 pass |
| 9 | 2.4 | **Full failure dry run against prod path.** With kill switch + daily cap + bounded scope, agent runs the full lifecycle against a deliberately broken sandbox publish, diagnoses, escalates, and the Safety Package catches overreach. Kill switch toggle tested mid-run. | Kevin flips `INVOKE_AGENT_ENABLED=true` only after this passes end-to-end |
| 10 | 4.3.3 | Migrate `sandbox-gate` job logic into the agent. Agent now owns sandbox publish via `deploy.py` tool call. Delete `sandbox-gate` job from `acuops-deploy.yml`. | One sandbox publish through the agent succeeds end-to-end |
| 11 | 4.3.4 | Migrate `deploy` job (prod publish + snapshot + countdown + verify + tag + ingest + DM) into the agent. Delete `deploy` job. | One prod publish through the agent succeeds end-to-end |
| 12 | 4.3.5 | Delete `post-deploy-validation` job (merged into agent's verify step). Final cleanup: unused secrets, dead GH variables, stale comments. | Pipeline has `build` + `build-validate` + `qualify` + `invoke-agent` — 4 jobs total |
| 13 | 2.5 | Mode-3 sentinel (orphan CustProject scan) on VM via hourly Task Scheduler | First run posts baseline to #ops |
| 14 | 2.6 | VM autostop schedule (Fri 8pm stop, Mon 5am start) | VM offline Saturday, online Monday |
| 15 | 3.x | Track 3 platform vision design docs unblock (were blocked on 2.4) | Design-only, no code |

### Things that stay the same regardless of (a) commitment

- Track 2.1 / 2.2 / 2.3 are unchanged — same deploy keys, same cap, same Safety Package primitives
- Track 2.4 is unchanged in intent, broader in scope (full lifecycle instead of diagnosis only)
- `build` + `build-validate` + `qualify` jobs are not touched
- `deploy.py` / `verify.py` in `acuops-pipeline` are the agent's tool-call surface — no code changes to them
- `studiob-knowledge` + auto-ingestion — unchanged
- After-hours gate logic — moves from `deploy` job into the agent prompt as a guard
- `agents/deploy-agent.md` — **finally invoked** (this is the only file whose status changes from "orphaned asset" to "active runtime")

### Non-negotiables

- **Track 4.3.0 MUST run before 4.3.1.** No trigger creation until the API is verified working.
- **Track 2.4 dry run MUST pass before `INVOKE_AGENT_ENABLED=true`.** Zero exceptions.
- **studiob-api session pool root cause MUST be fixed before re-enabling verify.py.** Otherwise the agent inherits a broken verification primitive.
- **Calcification rules (above) apply during the hybrid transition period** (Tracks 2.3 → 4.3.2). While the conventional jobs still exist alongside the agent, don't add bash/python logic to them that duplicates agent capabilities.

### Fallback to (c) if API verification fails

If Track 4.3.0 shows the remote trigger API is still broken:

1. Update this doc's decision header to reflect the fallback
2. Track 4.3.1 becomes "rewrite the `invoke-agent` prompt for diagnosis-only scope, keep `claude-code-action@v1`"
3. Tracks 4.3.2 / 4.3.3 / 4.3.4 / 4.3.5 become "follow-up work, deferred to when the API is fixed"
4. Tracks 2.5 / 2.6 / 3.x proceed unchanged
5. Quarterly re-test of the API via a scheduled task; when it passes, Track 4 reopens as the (c) → (a) migration

**Both paths ship something valuable. The kill criterion just decides which.**

## What does NOT depend on this decision

These items in the v2 plan deferred backlog should ship in parallel with whichever option Kevin picks:

- **P1:** fixture-gen OData 404 fix (small + low-risk + unblocks sandbox-gate green runs)
- **P1:** workflow `push:` path filter — add `src/**` (small + low-risk + tonight's source-only PR proved this is a trap)
- **P1:** studiob-api API Login Limit / session pool audit (root cause of tonight's verify.py 401 storm — affects every direction)
- **P2:** webhook-router PR #64 merge (Track 0 formal close)
- **P2:** studiob-api naming-trap regression — mirror `assertStagingConfigSafe()` (security hygiene, every direction)
- **P3:** SB501000 form title rename — cosmetic (any direction)

These are the "no-regret moves" that make the next morning better regardless of the Track 4 choice.
