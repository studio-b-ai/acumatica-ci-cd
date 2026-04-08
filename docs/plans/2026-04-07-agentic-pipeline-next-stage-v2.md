# Agentic Pipeline — Next Stage Plan (v2, reality-adjusted)

> v2 rewrite of `docs/plans/2026-04-07-agentic-pipeline-next-stage.md` at 2026-04-07 ~19:40 ET, after reading the continuation prompt that was merged via PR #271, checking GH PR/run state, and reconciling with the actual architecture from KB + session history.
>
> **v1 assumptions that are dead:**
> 1. Track 0.1 still in flight → it FAILED (`claude` CLI not on PATH), was patched by PR #261, and the continuation prompt says Track 0 is CLOSED end-to-end
> 2. Track 1 not started → all 3 replacement PRs (#262, #263, #264) merged + cascade hotfixes #265–270
> 3. SB501000 still broken → deployed via `workflow_dispatch force_deploy=OVERRIDE`, verified live
> 4. Silence on production state → actually there's a NEW post-publish verification failure storm (AesthetikWMS, 4 failed AcuOps Deploy runs between 22:36–22:55 UTC) that post-dates the continuation prompt and needs triage as Track 2.0.a

## ACTUAL architecture (what's in production today)

### Two-repo split

```
studio-b-ai/acumatica-ci-cd             studio-b-ai/acuops-pipeline
  ├── .github/workflows/                  ├── scripts/
  │   ├── acuops-deploy.yml               │   ├── deploy.py
  │   └── vm-agent.yml                    │   ├── validate-publish.py
  │   └── sandbox-autoheal.yml            │   ├── verify.py
  ├── Customization/                      │   ├── smoke-e2e.py
  │   ├── AesthetikWMS/                   │   └── qualify.py
  │   ├── AesthetikContainers/            ├── acuops.yaml (template)
  │   └── SB501000/                       └── tests/
  ├── Tests/
  └── acuops.yaml                        (PROPRIETARY — VAR channel productization target)
```

- `acumatica-ci-cd` (public-ish, client-facing workflow + customizations + tests)
- `acuops-pipeline` (private, PROPRIETARY; sold via Acumatica VAR channel; checked out at runtime by the workflow via `actions/checkout` with `token: secrets.GH_PAT_DISPATCH` — 6 references, Track 2.1 retires the PAT)

### Pipeline job chain (current, post PR #233 + #258 + #262–270)

```
build → build-validate (self-hosted Windows, Acuminator) → qualify
  → sandbox-gate (publish to sandbox + UI tests + host-assertion guard)
  → deploy (production; after-hours gated via PR #262)
  → invoke-agent [DISABLED via `if: false &&` from PR #258]
  → post-deploy-validation
```

Notable shape facts that shipped but aren't obvious from the v1 plan:

- **Phase 3 PR #233 "AI deploy agent via remote trigger"** removed `test-tenant-gate`, `deploy` (old), `post-deploy-validation` (old) and added an `invoke-agent` job that was supposed to own the deploy lifecycle via the Claude Code remote trigger API. **What actually shipped is a compromise** — `deploy` came back as a conventional job (see PR #246 "refactor claude-code-action + remove test-tenant remnants"), and `invoke-agent` is scoped to sandbox failure recovery only, using `claude-code-action@v1` on `ubuntu-latest`. The "agent owns the full deploy lifecycle" vision from the 2026-04-06 design doc is NOT what's in main.
- **`build-validate` is Windows-only** because Acuminator uses named memory maps that don't work on Linux. That's why the self-hosted runner on `acumatica-test` VM exists.
- **`vm-agent.yml`** is a *separate* workflow from `invoke-agent` — it runs `claude -p` locally on the Windows runner (PR #261 fixed the v1 plan's failed 24104724729 dispatch by swapping `claude-code-action` → local CLI). `invoke-agent` still uses `claude-code-action` on Linux because KB entry "claude-code-action on self-hosted Windows runners — don't" learned that lesson the hard way.
- **Three agent surfaces exist, not one:**
  1. `invoke-agent` in `acuops-deploy.yml` — failure recovery, reactive, Linux + `claude-code-action`
  2. `vm-agent.yml` — generic on-demand dispatch for VM-bound tasks, self-hosted Windows + local `claude -p` CLI
  3. (planned, NOT built) Mode-3 sentinel — scheduled Task Scheduler on VM, `claude -p --model haiku` — Track 2.5 in v1 plan
- **Auto-ingestion pipeline is live**: every deploy failure/success hits `POST /ingest/incident` on AcuDev Railway service and lands in `studiob-knowledge` Qdrant. Any new incident from tonight's AesthetikWMS failures is already indexed — check it before debugging manually.

### What the plan says vs. what architecture will become

| Layer | Plan v1 says | Reality | Gap |
|---|---|---|---|
| Agent invocation | "Re-enable invoke-agent with Safety Package" | `claude-code-action@v1` on ubuntu-latest | Still the right short-term move. Long-term the 2026-04-06 remote trigger vision is cleaner; treat as Track 4 aspiration |
| PAT retirement | "Replace 6 `actions/checkout` with deploy keys" | 6 refs to `GH_PAT_DISPATCH` in cross-repo checkout of `acuops-pipeline` | Unchanged, still valid |
| Daily cap | "Build `daily-dispatch-cap` composite action" | Doesn't exist | Unchanged, still valid |
| Dry run | "Decision point Kevin chooses (i) push-to-main or (ii) workflow_dispatch input" | Still a decision point | Unchanged, still valid |
| Mode-3 sentinel | "Windows Task Scheduler → `claude -p` hourly" | Not built; orphan CustProject problem real (see KB) | Unchanged, still valid |
| VM autostop | "Cloud Scheduler Fri 8pm / Mon 5am" | Not built; VM runs 24/7 | Unchanged, still valid |
| Multi-tenant | "Design docs only, blocked on 2.4" | Design docs only, blocked on 2.4 | Unchanged |
| Remote trigger (Phase 3) | Not in plan | Shipped PR #233, partially retained in main | **NEW: acknowledge as Track 4 aspiration** |

---

## Closeout log — 2026-04-07 ~21:15 ET

This section captures what actually happened in the night session that picked up v2.

### Track 2.0 — DONE (different shape than the plan expected)

**2.0.a — Triage of the 4 "AesthetikWMS failure storm" runs**

Original framing was "is prod impaired? rollback or fix verification?" Reality was different:

- The 4 runs were **manual `workflow_dispatch` recovery attempts**, not auto-triggered failures. Kevin had been trying to push AesthetikWMS through `force_deploy=OVERRIDE` after the 2026-04-07 incident. PR #270 (`force_deploy` input declaration) at 22:55 UTC was the smoking gun that someone was actively trying to use it.
- For each "failed" run: `Import and publish customization → success` (no continue-on-error, conclusion is real). **AesthetikWMS landed on prod 4 times tonight** — one publish per attempted run.
- Sandbox-gate failed each time on `scripts/heritage/generate_ui_fixtures.py` → `workflow_extractor/fetcher.py:117` → `OData HTTP 404`. Pre-existing fixture-generation script bug, unrelated to AesthetikWMS content.
- `Post-publish verification` (verify.py) failed each time on **`auth broken — 401 Unauthorized`** for every Contract-Based API call, plus `aspx:export` warning explicitly mentioning **`API Login Limit`** (HTTP 500 from `PX.LicensePolicy.PXLicensePolicy.CheckApiUsersLimits`).
- I initially mis-read `gh run view --json jobs` step conclusions as success — the verify step has `continue-on-error: true`, which converts a real failure to `conclusion=success`. The `outcome` field reflects the truth. **Lesson noted in MEMORY:** when reading GH Actions step results for a step with `continue-on-error: true`, trust `outcome` not `conclusion`.

**Root cause of the 401 storm:** `studiob-api` Railway service is the gateway between webhook-router/AcuDev and prod Acumatica. Its env vars: `ACUMATICA_URL=https://heritagefabrics.acumatica.com`, `ACUMATICA_TENANT=Heritage Test`, `ACUMATICA_USERNAME=api-bot`. It runs a constant stream of `GET /api/v1/acumatica/query/SalesOrder` (verified in live `railway logs --service studiob-api`, dozens/min, all HTTP 200) and holds N concurrent sessions on the `api-bot` user. verify.py runs with the same/sibling credentials and gets crowded out — initial login returns 204, then subsequent calls 401 because Acumatica's License Policy invalidates the seat immediately. webhook-router itself reports `errors=0` because it goes through the gateway and the gateway is healthy from its perspective.

**2.0.b — webhook-router PR #64**

Still open as of session end. **Not merged tonight.** Defer to next session or rolled into the new "weekend cleanup" Track 2.0.x batch (see Deferred Backlog below).

**2.0.c — Browser smoke sanity → uncovered the real prod bug**

While verifying prod state in Chrome (CDP via `mcp__Claude_in_Chrome`), found the real surprise:
- ✅ Login as Kevin Bibelhausen / Heritage Fabrics works
- ✅ SO301000 (Sales Orders) loads clean
- ✅ IN202500 (Stock Items) loads clean with Heritage custom fields (Fiber Content)
- ✅ Container Tracking sidebar present with **"Procurement Command Center"** label (PR #221 sitemap rename live)
- ❌ **SB501000 hangs CDP tools** because of a native JS dialog: **`Invalid object name 'UsrContainerCost'`** — SQL Server complaint that the BQL select had no table to bind to

### Track 2.0.d (NEW, unplanned) — SB501000 missing-table fix → PR #272

Discovery → fix → ship → verify, all tonight. Captured here so the next session has the full chain.

- **Bug:** PR #232 (Bucket B Phase 1) added `src/StudioB.Containers/DACs/UsrContainerCost.cs` and `ContainerMaint.cs` BQL select against it, but **never added a matching `EnsureTable` call** to `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs` (the CustomizationPlugin that runs DDL on every publish). PR #252 fixed `EnsureColumn` for landed-cost columns but missed the entire table.
- **Why sandbox tests passed:** sandbox database had `UsrContainerCost` from a previous version (manually created or shadow from an earlier branch — provenance unknown). Prod didn't. Surfaced when I opened SB501000 for verification.
- **Fix (PR #272):** added `EnsureTable("UsrContainerCost", ...)` matching the DAC schema (CostID identity, ContainerID FK, CostType / Description / Amount / VendorID / ReferenceNbr / APDocType / APRefNbr, plus NoteID + audit suite + tstamp + multi-tenant PK on `(CompanyID, CostID)`), and `EnsureIndex` on `(CompanyID, ContainerID)`. Idempotent via `IF OBJECT_ID IS NULL`.
- **Workflow trap:** the merge **did not auto-trigger AcuOps Deploy** because the `push:` filter is `Customization/**` + the workflow file. `src/**/*.cs` is excluded. Source-only changes silently don't deploy.
- **Mitigation:** manually dispatched `gh workflow run acuops-deploy.yml -f environment=production -f force_deploy=OVERRIDE` (override needed because sandbox-gate is still red on the fixture-gen 404). Run `24111687164` — `Build → Build+Acuminator → Qualify → Deploy: Import and publish customization → success`. Plugin ran during publish, table created on prod.
- **Verification (browser):** SB501000 loads clean, container grid populated, `EVENTS | PO LINKS | COSTS` tabs all render. Clicked COSTS — grid shows all 7 DAC columns (`Cost Type / Description / Amount / Vendor / Reference Nbr / AP Doc Type / AP Ref Nbr`) — empty as expected for a fresh table. **Fix is verified end-to-end on prod.**
- **Prod app pool recycle count for the day:** ~13 (8 from the original incident + 4 from Kevin's recovery attempts + 1 from this fix). Ugly but contained.
- **Slack #ops post:** https://studiob-ai.slack.com/archives/C0AR2UW2S66/p1775610477602989

### Architecture validation moment

The Phase 3 (2026-04-06 design / PR #233) "agent owns deploy lifecycle via remote trigger" vision would have caught tonight's confusion much faster. The current GH Actions workflow:

1. Cannot distinguish "publish succeeded but post-publish verification couldn't talk to API because of license saturation" from "publish broke prod"
2. Cannot distinguish "deploy this customization file change" from "deploy this source file that compiles into the customization DLL" (path filter trap)
3. Treats `Alert on verification failure` step output as the truth instead of reading verify-result.json

An agent reading `verify-result.json` would have output: *"AesthetikWMS publish succeeded. Verification cannot complete: api-bot is hitting API Login Limit because studiob-api is holding N concurrent sessions. Recommend restart studiob-api OR use a different service account for verify.py."* That diagnostic took me + Kevin ~45 minutes of conversation to assemble manually.

**Concrete motivation for Track 4 (Phase 3 Convergence) — that's the next session's focus.**

---

## Status at entry to v2 (2026-04-07 ~19:40 ET) — superseded, see Closeout log above

### CLOSED

- ✅ **Track 0 (webhook-router STG_* trap)** — per PR #271 continuation prompt and my own check: Railway env vars repointed to sandbox, host-assertion pattern mirrored, KB entry updated. ⚠️ webhook-router **PR #64** is still OPEN and MERGEABLE — still pending merge end of 2026-04-07 night session
- ✅ **Track 1 (PR #257 cleanup + SB501000 deploy)** — 3 replacement PRs + 6 hotfixes all merged. PR #257 closed. SB501000 was deployed via `force_deploy=OVERRIDE` and verified live per continuation prompt
- ✅ **VM agent infrastructure (Task 0.1 + PR #261)** — local `claude -p` CLI replaces `claude-code-action`; `vm-agent.yml` is ready for next dispatch (but currently unused until Track 2.5)
- ✅ **Docs rescue (PR #271)** — design + plan + this continuation prompt all on main
- ✅ **Track 2.0 (Closeout 2026-04-07 night)** — see Closeout log above. AesthetikWMS publish chain on prod confirmed via direct browser verification + PR #272 fixed the latent SB501000 missing-table bug.

### Deferred backlog (carry-forward to next session)

Tonight surfaced a bunch of latent traps that don't block Tracks 2.1+ but should be addressed in priority order before they bite:

**P1 — affects pipeline reliability**

- 🔴 **`studiob-api` API Login Limit saturation** — gateway holds N concurrent `api-bot` sessions on prod, blocking verify.py and any other Heritage API consumer. **Fix:** audit `studiob-api`'s session-pool config (`/Users/kevin/dev/studiob/apps/api/...` or wherever the Acumatica client lives), reduce pool size or increase connection reuse. **Alternate fix:** create a dedicated `api-verify` Acumatica user so verify.py has its own license seat pool. **Best:** both.
- 🔴 **`scripts/heritage/generate_ui_fixtures.py` OData HTTP 404** — fetcher.py:117 hits a sandbox OData endpoint that doesn't exist (or schema changed). Blocks sandbox-gate on every run. **Quick fix:** wrap the step in `continue-on-error: true` so it warns instead of failing the gate. **Real fix:** identify which OData endpoint is 404'ing and either fix the URL or stop calling it. Last touched in PR #153, code is unchanged → environment side issue.
- 🔴 **Workflow `push:` path filter excludes `src/**`** — pure C# source-only changes (like PR #272) don't auto-trigger AcuOps Deploy. Manual workflow_dispatch worked but it's a trap. **Fix:** add `'src/**'` to the `paths:` array in `acuops-deploy.yml on.push.paths`.

**P2 — security/identity hygiene**

- 🟡 **`studiob-api` naming-trap regression** — env vars `ACUMATICA_URL=https://heritagefabrics.acumatica.com` + `ACUMATICA_TENANT=Heritage Test` is the same pattern Track 0 closed on webhook-router. The reads are intentional (Heritage Test is the documented test tenant on prod), but a future write would recycle prod. **Fix:** mirror `assertStagingConfigSafe()` from webhook-router PR #64 into studiob-api's Acumatica client; allow reads, fail-fast on writes through this config.
- 🟡 **webhook-router PR #64 still open** — host-assertion guard + 6 TDD tests pending merge. Should land before Track 2.1.

**P3 — cosmetic/data**

- 🟡 **SB501000 form title still says "Container Maintenance"** even though sitemap is renamed to "Procurement Command Center" (PR #221). Either the `.aspx` page title or the `[PXCacheName]` on the primary view in `ContainerMaint.cs` wasn't updated.
- 🟡 **Sandbox shadow `UsrContainerCost` table** — sandbox has the table from before PR #272 shipped DDL. Provenance unknown. Now harmless (plugin idempotent), but worth a note in the KB.

**P4 — pre-existing, lower priority**

- 🟡 **Known dead-code bug in acuops-deploy.yml** — `[ "push" = "workflow_dispatch" ]` literal comparison, always false, in `detect_cust_changes` step. Harmless today, will bite when relied on.
- 🟡 **ContainerTracking endpoint XML missing field mappings** for `TransportMode`, `LandedCostRefNbr`, `LandedCostStatus` — screen is fine, Contract-Based API consumers aren't.
- 🟡 **9+ pre-existing Acuminator PX errors** (#267) baseline-suppressed in `.editorconfig`; policy says fix in batches and promote rules back to error as you go.
- 🟡 **webhook-router#65** — case-sync worker hitting Acumatica API cycle budget 602/500.

### OPEN TRACKS

- ~~Track 2.0~~ — **CLOSED 2026-04-07 night** (see Closeout log + PR #272). Pre-flight done; SB501000 latent bug fixed as a 2.0.d unplanned addition.
- Track 2.1 — Retire `GH_PAT_DISPATCH` via deploy keys (unchanged)
- Track 2.2 — Build `daily-dispatch-cap` composite action (unchanged)
- Track 2.3 — Re-enable invoke-agent with Safety Package A–F (unchanged; still Linux + `claude-code-action`)
- Track 2.4 — Failure dry run (unchanged; Kevin decision point remains — recommendation stays at option (ii) `simulate_sandbox_failure` input)
- Track 2.5 — Mode-3 sentinel (unchanged)
- Track 2.6 — VM autostop (unchanged)
- Track 3 — Platform vision design docs (unchanged; blocked on 2.4)
- **Track 4 (NEW) — Phase 3 Convergence (Remote Trigger)** — align `invoke-agent` with the 2026-04-06 PR #233 vision. Tonight's failure storm was the canonical motivation. Design-only until 2.4 is green. **Next session focus.**

### Decision (2026-04-07 night): commit to (a) with API verification kill criterion

Tracks 4.1 + 4.2 complete end of 2026-04-07 night session:

- `docs/plans/2026-04-08-phase3-vs-reality-audit.md` — Track 4.1 audit
- `docs/plans/2026-04-08-remote-trigger-convergence-design.md` — Track 4.2 design + decision log

**Decision:** Option (a) Phase 3 Convergence (agent owns full deploy lifecycle via remote trigger). Rationale: (1) the biggest blocker (API auth) is testable in ~1 hour, (2) `agents/deploy-agent.md` is already a 599-line lifecycle prompt on main, (3) tonight's failure mode (conventional pipeline can't tell "publish OK + verify infra blocked" from "publish broken") is exactly the case (a) solves, (4) Studio B's VAR channel productization story requires "AI-managed Acumatica deploys," not "AI diagnoses errors on a conventional pipeline."

**Kill criterion:** Track 4.3.0 is a 1-hour API verification. If the remote trigger API is broken, automatic fallback to (c) Hybrid Formalized with zero wasted work (Tracks 2.1–2.3 + the deferred backlog ship in either direction).

### Next-session execution order

Full detail in `docs/plans/2026-04-08-remote-trigger-convergence-design.md` "Decision + execution plan" section. Summary:

1. **Track 4.3.0 (DO FIRST, ~1 hour)** — API verification via `RemoteTrigger list/create/run`. Gates everything else.
2. **P1 deferred backlog in parallel** (no-regret — ships in (a) or (c)):
   - Fixture-gen OData 404 (`continue-on-error: true` on the step)
   - Workflow `push:` path filter — add `src/**`
   - studiob-api session pool audit (root cause of tonight's verify.py 401 storm)
3. **Track 2.0.b** — merge webhook-router PR #64 (Track 0 formal close)
4. **Track 2.1** — retire `GH_PAT_DISPATCH` via deploy keys (identity hygiene, any direction)
5. **Track 2.2** — `daily-dispatch-cap` composite action
6. **Track 2.3** — Safety Package A–F wired into `invoke-agent` job, **with `agents/deploy-agent.md` loaded as the prompt** (not the current failure-recovery prompt). Kill switch off until 4.3.1+ pass.
7. **Track 4.3.1** — create Claude Code remote trigger with `agents/deploy-agent.md`, set `CLAUDE_TRIGGER_TOKEN` + `CLAUDE_TRIGGER_ID`, rewrite `invoke-agent` step to curl the trigger instead of `claude-code-action@v1`.
8. **Track 4.3.2** — sandbox-only dry run. Agent downloads artifacts, reads verify-result.json, posts diagnosis, opens fix PR, does NOT touch prod.
9. **Track 2.4** — full failure dry run against prod path with Safety Package + kill switch + daily cap. Kevin flips `INVOKE_AGENT_ENABLED=true` only after this passes end-to-end.
10. **Track 4.3.3** — migrate `sandbox-gate` logic into agent, delete the job.
11. **Track 4.3.4** — migrate `deploy` logic into agent, delete the job.
12. **Track 4.3.5** — delete `post-deploy-validation`, final cleanup. Pipeline ends at `build` + `build-validate` + `qualify` + `invoke-agent` (4 jobs).
13. **Tracks 2.5 / 2.6** — Mode-3 sentinel + VM autostop (after 2.4 green)
14. **Track 3** — Platform vision design docs (unblocked when 2.4 is green)

Rough estimate: 10–12 focused sessions for the full (a) implementation assuming 4.3.0 passes. Fallback to (c) is cheaper (~6 sessions) and inherits everything through step 6.

### Non-negotiables

- Track 4.3.0 runs BEFORE 4.3.1 (no trigger creation until API verified)
- Track 2.4 dry run MUST pass before `INVOKE_AGENT_ENABLED=true`
- studiob-api session pool root cause fixed before re-enabling verify.py
- Calcification rules from the convergence design doc apply during the hybrid transition (Tracks 2.3 → 4.3.2)

---

## Track 2.0 — Pre-flight + sandbox stabilization (BLOCKING)

**Why elevated:** 4 AcuOps Deploy failures in 20 minutes tonight means sandbox is not actually safe — every run publishes AesthetikWMS to sandbox (which is fine) but then `Deploy to production` runs anyway and post-publish verification fails (which is NOT fine — it means real publishes landed on prod). Track 2.1/2.2/2.3 must wait until this is understood and the bleeding stops.

### 2.0.a — Understand the 4 failures

1. **Read the auto-ingested KB entries first (Rule 9):**
   ```bash
   # Search studiob-knowledge for tonight's AesthetikWMS failures
   python3 -c "
   import requests, os
   q = 'AesthetikWMS post-publish verification failure OData 404 fixture'
   r = requests.post('https://api.voyageai.com/v1/embeddings',
       headers={'Authorization': f'Bearer {os.environ[\"VOYAGE_API_KEY\"]}', 'Content-Type': 'application/json'},
       json={'input': [q], 'model': 'voyage-3', 'input_type': 'query'})
   v = r.json()['data'][0]['embedding']
   s = requests.post(f'{os.environ[\"QDRANT_URL\"]}/collections/studiob-knowledge/points/search',
       json={'vector': v, 'limit': 5, 'score_threshold': 0.4, 'with_payload': True})
   for h in s.json()['result']:
       print(h['score'], h['payload'].get('title'))
       print(' ', h['payload'].get('text', '')[:400])
   "
   ```
2. **Characterize the two-part failure:**
   - Part 1: `Generate UI fixtures from audit data` → `HTTP 404` from OData. Which endpoint? Check the Python traceback line in `gh run view 24108389172 --log-failed`
   - Part 2: `Deploy to production → Alert on verification failure` for `AesthetikWMS`. Was verification failing because sandbox failed first and deploy proceeded on OVERRIDE? Or did prod publish actually succeed and verification hit a real issue?
3. **Check prod state directly:** load AesthetikWMS screens in browser, confirm app pool hasn't died
4. **Decision:** if prod is actually functional, this is a verification-step bug (noise). If prod is impaired, it's a real incident and Track 2 work pauses until it's fixed.

**STOP before Track 2.1 until 2.0.a yields a clear "prod healthy, verification script needs a fix" OR "prod impaired, rolling back".**

### 2.0.b — Merge webhook-router PR #64

```bash
cd ~/dev/webhook-router
/opt/homebrew/bin/gh pr view 64 --repo studio-b-ai/webhook-router
/opt/homebrew/bin/gh pr merge 64 --squash --delete-branch --repo studio-b-ai/webhook-router
```

This completes Track 0 formally — the host-assertion guard `assertStagingConfigSafe()` + 6 TDD tests land in webhook-router main.

### 2.0.c — Smoke sanity

```bash
# Runner online
/opt/homebrew/bin/gh api repos/studio-b-ai/acumatica-ci-cd/actions/runners --jq '.runners[] | "\(.name) \(.status) busy=\(.busy)"'
# SB501000 still loads on prod (Chrome MCP)
# AesthetikWMS still loads on prod (Chrome MCP)
# After-hours window status
TZ=America/New_York date
```

---

## Track 2.1 — Retire GH_PAT_DISPATCH from `actions/checkout`

Unchanged from v1 plan Task 2.1 (worktree-adjusted paths below). Re-read before executing.

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` (6 `actions/checkout` references to `studio-b-ai/acuops-pipeline`)
- New: SSH ed25519 keypair (temp)
- New: GH deploy key on `studio-b-ai/acuops-pipeline` (read-only)
- New: GH secret `ACUOPS_PIPELINE_DEPLOY_KEY` on `studio-b-ai/acumatica-ci-cd`
- **Do NOT touch** the two `GH_TOKEN: secrets.GH_PAT_DISPATCH` env blocks inside `invoke-agent` — those are Track 2.3's territory

**Workflow (paraphrased from v1 plan Task 2.1 steps 1-10):**
1. `ssh-keygen -t ed25519 -C "acuops-pipeline-deploy-2026-04-07" -f $TMPDIR/key -N ""`
2. `gh api repos/studio-b-ai/acuops-pipeline/keys -f title=... -f key="$(cat $TMPDIR/key.pub)" -f read_only=true`
3. `gh secret set ACUOPS_PIPELINE_DEPLOY_KEY --repo studio-b-ai/acumatica-ci-cd < $TMPDIR/key`
4. Shred/rm the temp keypair
5. Branch `chore/deploy-key-smoke-test` off `origin/main`, replace **one** checkout with `ssh-key:`, push, draft PR, watch run pass
6. If smoke passes, replace the other 5 checkouts, push, promote to ready, watch run, merge after 6pm ET (we're already past 6pm, so mergeable immediately)
7. Delete deploy key + secret if rollback needed

**Verification:** after merge, next AcuOps Deploy run shows every `Checkout AcuOps pipeline` step using `ssh-key:` — no `token:` references remain.

---

## Track 2.2 — Build `daily-dispatch-cap` composite action

Unchanged from v1 plan Task 2.2.

**Files:**
- New: `.github/actions/daily-dispatch-cap/action.yml`
- Temporary: `.github/workflows/test-daily-dispatch-cap.yml` (remove after verification)

Bash implementation inside composite action uses `gh api repos/.../actions/runs?created=>$SINCE` filtered by workflow name, counts, and fails if `count >= max_per_24h`. Emits a step summary table. v1 Task 2.2 steps 1–8 are correct as written — execute them verbatim.

---

## Track 2.3 — Re-enable invoke-agent with Safety Package A–F

Unchanged from v1 plan Task 2.3, **with one architectural note added**: the re-enable keeps `claude-code-action@v1` on `ubuntu-latest` because Windows incompatibility is a KB-documented fact. Do not try to move invoke-agent onto the self-hosted Windows runner — that's a different problem. If Kevin wants remote-trigger convergence, that's Track 4 and happens after 2.4.

**Safety Package recap (v1 correct, no changes):**
- **A** — sandbox host-assertion (done in PR #258)
- **B** — `GH_TOKEN: secrets.GITHUB_TOKEN` (not `GH_PAT_DISPATCH`) — two env blocks, both swapped
- **C** — `daily-dispatch-cap` step `max_per_24h=3` before `claude-code-action`
- **D** — Slack #ops pre-notification + `sleep 30` before agent fires (gives a human window to abort)
- **E** — Kill-switch via GH variable `INVOKE_AGENT_ENABLED` (default `false`, read at step start, `exit 0` if not `true`)
- **F** — Bounded-scope prompt (file globs `Customization/**`, `tests/**`, `acuops.yaml`, `.github/workflows/acuops-deploy.yml`; no direct push to main; no force-push; max 1 attempt/loop)

Finally remove `false &&` from the `invoke-agent` job's top-level `if:`. PR is DRAFT until 2.4 passes.

---

## Track 2.4 — Failure dry run (**decision point remains**)

**Decision still needed from Kevin:**
- **(i)** Push deliberate sandbox-gate-breaking change to main after-hours (realistic, end-to-end, but publishes something)
- **(ii)** Add `workflow_dispatch.inputs.simulate_sandbox_failure: bool` → `sandbox-gate` reads it and `exit 1` without publishing (safer, tests a slightly different code path)

**Recommendation:** given tonight's 4-failure storm, option (ii) is safer — Track 2.0.a may reveal that prod can't tolerate another real publish cycle.

Observations the dry run must capture (same as v1):
- Slack #ops pre-notification lands
- 30s delay fires
- `claude-code-action` runs
- Agent diagnoses the failure, files a PR (not a direct push)
- PR touches only files inside the glob bounds
- Audit log shows dispatch as `github-actions[bot]`
- Daily cap step count progresses 1 → 2 → 3
- A 4th deliberate failure in 24h gets blocked at the cap step (no agent invocation)
- Toggling `INVOKE_AGENT_ENABLED=false` mid-test produces "kill-switch engaged, skipping" on the next run

Clean up dry-run branch + any PRs the agent filed against it. Flip `INVOKE_AGENT_ENABLED=true` only after all 8 observations pass.

Post to Slack #ops: `✅ AI Failure Recovery agent re-enabled with Safety Package. Dry run passed. Identity = github-actions[bot], cap = 3/24h, kill-switch = on.`

Ingest a "invoke-agent dry run runbook" entry to `studiob-knowledge` (pattern from v1 Task 0.5 / 2.4 Step 8).

---

## Track 2.5 — Mode-3 sentinel (orphan CustProject scan)

Unchanged from v1 Task 2.5. Summary:

- `scripts/sentinels/scan_orphan_custproject.py` — connects to prod SQL Server (Windows auth from VM, read-only), joins `CustProject` against active customizations from `SM204505` OData, returns count of orphans
- Windows Task Scheduler on VM → hourly `claude -p --model claude-haiku-4-5-20251001 "Run scripts/sentinels/scan_orphan_custproject.py and post to Slack only if anomalies"`
- Haiku cost ceiling ~$1–2/mo
- TDD the script (KB entry `Orphaned ISV projects cause publish warnings on sandbox` is the prior-art evidence this is worth building)

**Contingency:** this task only starts after 2.4 is green.

---

## Track 2.6 — VM autostop

Unchanged from v1 Task 2.6. Cloud Scheduler jobs:

- `acumatica-test-stop` — `0 20 * * 5` (Fri 8pm ET) → stop VM
- `acumatica-test-start` — `0 5 * * 1` (Mon 5am ET) → start VM

Document in deploy runbook that Sat/Sun pushes will fail `build-validate` until Monday. ~50% GCE cost savings.

---

## Track 3 — Studio B platform vision (design-only, blocked on 2.4)

Unchanged from v1. Steps:

### 3.1 Read the 10am architecture review

`/Users/kevin/.claude/sessions-export/2026-04-07_98f99883.md` — `studio-b-repo-architecture-review` scheduled task output (confirmed present). Extract: current state table, target state, dogfooding gaps, closest-to-product apps.

### 3.2 Codify platform-vs-tenant split

- Edit `/Users/kevin/.claude/CLAUDE.md` — add "Platform architecture" section: Studio B is the platform, Heritage Fabrics / Aesthetik / Weathervane / Wasala are tenants
- Create memory file `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_studiob_platform_vision.md`

### 3.3 Multi-tenant abstraction design doc for acuops-pipeline

Identify tenant-scoped values:
- `acuops.yaml` fields (project list, co-publish, paths)
- GH secrets per tenant (ACUMATICA_URL, ACUMATICA_USER, ACUMATICA_PASS, ACUMATICA_COMPANY — per env per tenant)
- Deploy targets per tenant
- Notification channels per tenant (Slack channel mapping)
- KB collection namespacing (`client` tag on every entry)

Write to `/Users/kevin/dev/acuops-pipeline/docs/plans/2026-04-XX-acuops-multi-tenant-design.md`. **NO CODE CHANGES.** Hard rule.

### 3.4 Heritage Fabrics alpha migration checklist

What changes about Heritage's AcuOps deployment when it becomes tenant-of-Studio-B vs only-customer? Sketch the migration steps: secret namespacing, acuops.yaml → multi-tenant config, dashboard/KB namespacing, billing model. Add to the design doc from 3.3.

### 3.5 Trip-wire rule

Add to `/Users/kevin/.claude/CLAUDE.md`:

> Rule 12: No multi-tenant code merges to `acuops-pipeline` until Track 2.4 (invoke-agent dry run) is complete and verified. Design docs only in the interim.

---

## Track 4 (NEW) — Remote trigger convergence (design only, blocked on 2.4)

**Why new:** the 2026-04-06 Phase 3 design (PR #233) committed to "GH Actions becomes thin scaffolding; the deploy agent owns the lifecycle via Claude Code remote trigger API." What shipped is a compromise — `invoke-agent` uses `claude-code-action@v1` inside a GH Actions step, and `deploy`/`post-deploy-validation` are conventional jobs. The plan v1 re-enables the compromise without acknowledging the original direction. Track 4 closes that gap.

**Tasks (design only, no code until 2.4 is green):**

### 4.1 Audit the Phase 3 vision vs. reality

- Read `docs/plans/2026-04-05-acuops-ai-pipeline-design.md` (the full Phase 3 design)
- Read PR #233 commit message + diff
- Read PR #246 "refactor: claude-code-action + remove test-tenant remnants" commit
- Read PR #248 "feat: AI failure recovery — agent diagnoses and fixes sandbox failures"
- Diff "what design promised" vs "what main has today"
- Write `docs/plans/2026-04-08-phase3-vs-reality-audit.md` summarizing the gap

### 4.2 Decide: converge, abandon, or hybrid

Three options for Kevin:
- **(a) Converge** — rebuild `invoke-agent` on the Claude Code remote trigger API, dropping `claude-code-action`. Agent runs server-side, not in a GHA runner. Cleaner identity story (Anthropic workspace, not GitHub token). Requires rewriting the step to call the trigger API and poll for completion.
- **(b) Abandon** — keep `claude-code-action` indefinitely. Mark PR #233's remote-trigger vision as not-pursued. Simpler, lower risk.
- **(c) Hybrid** — use remote trigger for "heavy" agent work (full deploy lifecycle autonomy) and keep `claude-code-action` for "light" failure recovery. Matches what's actually in main.

Write options + trade-offs to `docs/plans/2026-04-08-remote-trigger-convergence-design.md`. Ask Kevin which path. NO CODE.

### 4.3 (conditional, only if Kevin picks a or c) Scope the convergence PR

Identify: which steps move to the trigger API, how the workflow polls for result, what happens if the trigger API is down, how the audit log works in the hybrid case, how Safety Package A–F maps onto remote-triggered execution.

**Hard rule — no code lands until Track 2.4 is green AND Kevin approves the Track 4 design doc.**

---

## Verification gates (updated)

| Gate | Required before | Verification |
|---|---|---|
| Track 2.0.a done | Any other Track 2 work | Clear answer on whether prod is healthy after tonight's AesthetikWMS failures + fix or rollback if not |
| Track 2.0.b done | Track 2.1 | webhook-router PR #64 merged, `assertStagingConfigSafe()` live on webhook-router main |
| Track 2.1 complete | Track 2.3 starts | All 6 checkouts use `ssh-key`, zero `token: secrets.GH_PAT_DISPATCH` in workflow file, one AcuOps Deploy run passes on the smoke-test branch |
| Track 2.2 complete | Track 2.3 starts | Test workflow passes at cap=999, fails at cap=0, composite action lives at `.github/actions/daily-dispatch-cap/action.yml` |
| Track 2.3 draft PR open | Track 2.4 | PR exists, marked DRAFT, `INVOKE_AGENT_ENABLED=false`, YAML validates |
| Track 2.4 dry run passes | Track 2.5, Track 3.3, Track 4.3 unblock | All 8 dry-run observations green + KB runbook entry searchable |
| Track 2.5 complete | "Stage complete" | First sentinel run posted "0 orphans" baseline + Task Scheduler entry visible on VM |
| Track 2.6 complete | "Stage complete" | VM offline Saturday morning, online Monday morning |
| Track 4.2 decision | Track 4.3 starts | Kevin picks a/b/c from the design doc |

## Stop conditions (ask Kevin, don't barrel)

- **Track 2.0.a** finds prod impaired by tonight's AesthetikWMS failures → halt all Track 2 work, rollback via backup snapshot, investigate
- Track 2.0.b merge fails CI on webhook-router
- Track 2.1 smoke test run fails on the deploy-key branch
- Track 2.3 YAML parse fails or removes `false &&` accidentally before Safety Package is complete
- Track 2.4 dry run shows the agent over-reaching file glob bounds, force-pushing, or merging its own PR
- Track 2.4 daily cap fails to block the 4th dispatch (means the `gh api` count logic is wrong)
- Any task takes more than 2x expected wall time
- **Any additional AcuOps Deploy failures tonight** — pause and diagnose, don't stack more changes on top of an unstable sandbox

## Hard constraints (inherited from v1 + continuation prompt)

- Never publish/unpublish any Acumatica customization outside of Track 2.4 dry run (coordinated with Kevin first)
- Never enter a password into Acumatica — if a Chrome session dies, stop and tell Kevin
- Never delete a 1Password item — flag for Kevin
- Never create a GitHub account or GitHub App — use deploy keys, `GITHUB_TOKEN`, existing identities
- Never push directly to main — PR every change
- Never `--no-verify` on commits
- Don't run `bash scripts/rotate-secrets.sh acumatica` — blast radius too wide
- No multi-tenant code merges until Track 2.4 passes
- Follow CLAUDE.md rules 9–11 (search KB + recall before debugging)
- Verify before claiming (`@superpowers:verification-before-completion`)

## Absolute paths

| Purpose | Path |
|---|---|
| Main checkout | `/Users/kevin/dev/acumatica-ci-cd` |
| This worktree | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/musing-dewdney` |
| Sister worktree (per continuation prompt) | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman` |
| v1 plan | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage.md` |
| v1 design doc | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md` |
| v2 plan (this file) | `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/musing-dewdney/docs/plans/2026-04-07-agentic-pipeline-next-stage-v2.md` |
| Continuation prompt | `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-08-continuation-tracks-2-3.md` |
| Phase 3 original design | `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-05-acuops-ai-pipeline-design.md` |
| Workflow file | `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` |
| webhook-router source | `/Users/kevin/dev/webhook-router` |
| acuops-pipeline (PROPRIETARY) | `/Users/kevin/dev/acuops-pipeline` |
| Memory dir | `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/` |
| Global rules | `/Users/kevin/.claude/CLAUDE.md` |
| `gh` CLI | `/opt/homebrew/bin/gh` |
| `railway` CLI | `/opt/homebrew/bin/railway` |
| VM RDP | `34.46.34.153` as `kevin` (password in 1P `acumatica-test VM (Windows)`) |

## First actions for the next session

1. **Read this v2 plan in full.**
2. **Track 2.0.a — triage the 4 tonight failures FIRST.** Check KB auto-ingest, check prod state, decide if we're in an incident or a verification-script bug. Don't touch anything else until this is resolved.
3. **Track 2.0.b — merge webhook-router PR #64** (closes Track 0 formally).
4. **Track 2.0.c — smoke sanity checks.**
5. **Only then** start Track 2.1 (deploy keys). After-hours window is open (it's past 6pm ET); merges allowed once PRs are green.
6. **When you reach Track 2.4, stop and ask Kevin** which dry-run mechanism to use. Recommend option (ii) `simulate_sandbox_failure` input given tonight's sandbox instability.
7. **Rigby close-out** at end of session — write a new continuation prompt at an absolute path, confirm saved.
