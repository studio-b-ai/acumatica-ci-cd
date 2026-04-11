# Sandbox Reliability — Session 6 (Post-Merge Verification)

**Prior session:** 2026-04-11 ~1:00 AM ET (Session 5)
**Session 5 outcome:** PR #353 — 3 workstreams implemented (PO3010PL fix, --no-merge suppression, sandbox entity sync). Not yet merged.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md`
3. `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-11-sandbox-reliability-design.md`

## Session 5 delivered

| Item | Status |
|---|---|
| PR #353 — PO3010PL→PO301000 fix | **Ready for merge** |
| PR #353 — verify.py --no-merge-expected flag | **Ready for merge** |
| PR #353 — Sandbox entity sync workflow | **Ready for merge** |
| IIG orphan cleanup SQL documented | **docs/reference/iig-orphan-cleanup.md** |
| Access rights (Melanie/Steve/Lauren/Sarah) | **Verified — wildcard covers all** |

## Session 6 priorities

### Priority 1: Merge PR #353 and verify pipeline

1. Merge PR #353 to main
2. Monitor the AcuOps Deploy pipeline run
3. Verify sandbox-gate passes (PO301000 tests + verify suppression)
4. Verify production deploy succeeds

### Priority 2: Run first sandbox entity sync

1. Trigger `sync-sandbox.yml` via workflow_dispatch
2. Confirm entities synced successfully
3. If successful, execute Task 3.3: remove `skip_on_sandbox` from CRUD tests

### Priority 3: Diagnose nightly DRP sync failure

The first nightly DRP sync (2026-04-10 06:00 UTC) failed:
> `Worker did not call orchestrator; GIs not deployed to target Acumatica instance`

This is an aesthetik-platform issue. The OData GIs ARE deployed to production (confirmed 200 in Session 4). Likely the worker is pointing at wrong instance or has stale config.

**Repo:** `/Users/kevin/dev/aesthetik-platform/`

### Priority 4: Refine no_merge_expected list

The `acuops.yaml` currently lists only `aspx:Pages/SB/SB501000.aspx`. After a pipeline run, check the verify output for all 3 ASPX mismatches and add any missing entries.

## Repos in play

- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/`
- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/` (DRP sync issue)

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).
