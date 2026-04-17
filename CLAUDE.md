# Acumatica CI/CD — Repo-Specific Rules

Repo-level extract of the Non-Negotiable rules most relevant to Acumatica customization deploys. Canonical source is the global `~/.claude/CLAUDE.md`; this file exists so repo-committed AARs and PR bodies can link to stable anchors that resolve on GitHub. Rules are verbatim — do not paraphrase or "improve" here. Keep numbering aligned with the global file so cross-references stay intact.

## Rules — Non-Negotiable

11. **Every Acumatica deploy restarts the app pool.** Real users at Heritage Fabrics get disrupted. There is no "one more quick fix." Get it right before deploying.

18. **Acumatica Import NullRef from `UserRecordsDBUpdater` is in-memory app-pool state corruption, not DB corruption.** Self-clears in 20-30 min. Diagnostic: import an empty `<Customization>` with a valid new name — if that succeeds while other imports fail, it's the in-memory cache. Do NOT retry Import in a tight loop — each failed transaction commits partial state that poisons the next attempt. Wait or switch to `merge=true` publishBegin (which uses a different code path and can succeed while Import is broken). **Corollary (2026-04-17 incident): if the NRE persists past one hour, the self-clear assumption has been falsified — the cloud pool isn't recycling in this window (observed: ~24h on Heritage Fabrics, since the last recycle trigger happens on scheduled cadence, not per-request).** Recovery: force a full publish with `isOnlyDbUpdates=false` of any managed package (e.g. `AesthetikContainers`) — the website-copy phase triggers a real app-pool restart, the in-memory DAC/UserRecords registry rebuilds from disk, and the NRE clears. Do NOT wait longer. Do NOT retry Imports. Users-logged-out is the ideal window; after 6 PM CT otherwise. See `docs/AAR-2026-04-17-custproject-nre-transient.md` on acumatica-ci-cd main.

20. **For Acumatica UI test failures, verify the symptom against the live sandbox via Playwright BEFORE proposing C#/customization fixes.** Test bugs and customization bugs look identical from a pytest failure log. The 2026-04-15 PCC follow-up incident burned >1 hour proposing a `ContainerMaint.Initialize()` PrimaryView override fix that was completely wrong — live sandbox check immediately showed `htmlKPITiles` and `htmlTimeline` rendering 10KB+ of correct HTML inside their iframes. The actual bugs were (a) Playwright's `text_content()` doesn't descend into PXHtmlView's sandboxed `iframe.htmlviewinner` (test bug) and (b) `AesthetikContainersInstall` whitelist missing `'SB501200'` (real bug, but never would've been found by the wrong fix). Reach for Playwright before the editor.

22. **Keep the co-publish list to Aesthetik-owned projects only.** `ALSO_PUBLISH_PROJECTS` should NOT include ISV packages (Ramp, FusionWMS, Pacejet, KNC, WMSynergy). With `merge=true`, already-published ISV packages stay published without being in `projectNames`. Including them inflates the ASPX page count that `PXPageIndexingService` must scan, causing `ThreadAbortException` on prod (~75s server-side timeout). The 2026-04-15 PCC outage was caused by a co-publish list of 11 projects; recovery succeeded with single-project publishes (90s each). If an ISV package needs a fresh publish, publish it alone with `merge=true` in a separate `publishBegin` call.

24. **Acumatica `<Sql>` scripts in project.xml do NOT re-execute on subsequent `merge=true` publishes of already-published packages.** Acumatica tracks executed scripts by Name; bumping the Name (e.g. `_v2`) does not force re-execution — the scripts don't appear in the publishEnd log at all. For GI installation that must survive every publish, use the C# `CustomizationPlugin` (`PXDatabase.Execute()` in the Install graph, e.g. `AesthetikContainersInstall.cs`), not `<Sql>` elements. The `<Sql>` approach from PR #427 failed across 3 deploy attempts on 2026-04-16. StudioBAuditTrail (in StudioBAcuOps) works only because its SQL scripts ran on its first-ever publish.

26. **Recall + verify before writing plans or SOPs.** Before writing any plan, SOP, or implementation that touches an existing Studio B system (Amplify, studiob-api, webhook-router, PhantomBuster, Heritage Fabrics stack), run `/recall` on the topic AND verify at least one load-bearing assumption against the live system (API query, file read, grep). The 2026-04-07 Amplify session logged 6 failures from pattern-matched assumptions in a single session: wrote an SOP telling the director to create Google Sheets that already existed; wrote an 850-line gateway plan that contradicted the knowledge base's architecture decision; spent 15+ min clicking through PhantomBuster in Chrome before remembering the API key was in env vars; extrapolated "all phantoms wired" from N=1 when 10 of 11 were misconfigured. Rule #10 ("search before investigating") covers errors — this rule extends it to the plan-writing phase. Verification steps are seconds; the alternative is hours of rework. When an API exists for a task, default to the API. Chrome UI automation is a last resort.

## "Rigby" — End-of-Session Documentation + Hardening Sweep

When Kevin says **"rigby"**: full documentation sweep AND encode lessons as automated guards.

### Part 1: Documentation
1. **Lessons learned** → `memory/context/lessons-learned.md` (new technical lessons, API quirks, architectural decisions).
2. **Project memory files** → update relevant `memory/project_*.md` (status, what changed, what's next).
3. **MEMORY.md index** → update project list/status. Move completed → Stable References.
4. **CLAUDE.md** → update if architecture/endpoints/env vars/infrastructure changed.
5. **Review structure** → scan updated `.md` for stale content, duplicates, formatting issues.

### Part 2: Hardening (NON-NEGOTIABLE)
6. **Encode every "NEVER do X" as a code guard** (validate-project.py, qualify.py, CI). A lesson without a guard is a wish.
7. **Open PR with guards.** Documentation without code is incomplete.
8. **Verify guards catch the failure** against the code that caused the incident. If not, the guard is wrong.

### Part 3: Acumatica Customization Checks (when session touches .cs / project.xml)
9. `validate-project.py --strict` on all changed project.xml. Warnings = future outages.
10. Every new `[PXDBx]` field needs matching `<Sql>` ALTER TABLE — auto-column creation broken on cloud (1.5-hr outage 2026-04-02). In-memory only? Use `[PXDecimal]`/`[PXString]`.
11. project.xml CDATA must match .cs source files — CDATA is what deploys. Diff them.
12. `deploy.py` and `emergency-deploy-basic-auth.py` publish params must match. Divergence = 20-min hang (2026-04-02).
13. `System.TypeCode` must be fully qualified in all `PXDefault`. Unqualified = CS0104.
