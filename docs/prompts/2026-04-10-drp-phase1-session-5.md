# DRP Phase 1 — Session 5 (Pipeline Review + Test Fix)

**Prior session ended:** 2026-04-11 ~12:15 AM ET (Session 4)
**Session 4 outcome:** Production deploy succeeded. All 4 OData GIs confirmed 200 after unpublish+republish. Nightly DRP sync scheduled for 1 AM ET.

## Read in order before doing anything

1. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_drp_implementation.md`
2. `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/MEMORY.md`

## Session 4 completed items

| Item | Status |
|---|---|
| Production deploy (run 24272578342) | **Deployed** via force_deploy=OVERRIDE |
| PR #342 — GI field fix + access rights (Accessrights 0→4) | **Merged + deployed** |
| PR #344 — Strip XML comments | **Merged + deployed** |
| PR #346 — Toolbar button wait + timeout fix (AI Recovery) | **Merged** |
| PR #348 — PO301000 navigation test direct ASPX | **Merged** |
| OData DRP_VelocityHistory | **200** — real shipment data |
| OData DRP_OpenSOCommitments | **200** — required unpublish+republish (stale OData cache) |
| OData DRP_OpenPOLines | **200** |
| OData DRP_InventoryBySite | **200** |

## Session 5 priorities

### Priority 1: Review sandbox gate value in pipeline

Kevin asked: does it make sense to keep sandbox-gate given Acuminator + test environment?

Context:
- Session 4 had 3 consecutive sandbox-gate failures, all from pre-existing flaky tests
- Sandbox deploy + verify + smoke test passed every time
- Used `force_deploy=OVERRIDE` to bypass
- Flaky test: `test_container_tracking_navigates_to_sb501000` — PO3010PL SiteMap shadow in AesthetikWMS causes `acumatica_screen("PO301000")` to redirect

Data points:
- Sandbox gate adds ~15-20 min per pipeline run
- Acuminator catches compile errors at build time
- Post-publish verification catches schema/field issues
- `--no-merge` creates permanent verify failures for container fields (3 fails every run)
- PO3010PL screen shadow causes persistent test flakiness

Options (Kevin's to decide, my proposals labeled):
1. **Remove sandbox-gate entirely** — rely on Acuminator + post-deploy verify
2. **Make sandbox-gate non-blocking** (`continue-on-error: true`) — run tests for signal but don't block prod
3. **Fix the root flaky tests** — PO3010PL shadow, timeout issues (partially done in PRs #346/#348)
4. [My proposal] **Option 2 + 3** — make non-blocking now, fix flaky tests in parallel

### Priority 2: Fix PO301000 navigation test (PO3010PL shadow)

`test_container_tracking_navigates_to_sb501000` fails because:
- `acumatica_screen("PO301000")` navigates via SiteMap
- AesthetikWMS overrides SiteMap entry with ScreenID="PO3010PL"
- SiteMap navigation redirects instead of loading PO form
- PR #348 switched to direct ASPX but the CONTAINER TRACKING button click still navigates to error on sandbox

Root issue: AesthetikWMS managed code overriding base screen access — Kevin flagged this as a broader pattern.

### Priority 3: Design next work package

Review what's done, what's remaining, and design the next chunk of work.

## What's done (Phase 1 complete)

- Design doc locked (sections 0-19)
- Phase 0 plan (25 tasks, 9 streams, 5 repos)
- 4 DRP GIs deployed + OData confirmed
- Access rights fixed for all 18 custom entities
- aesthetik-platform nightly sync code deployed (PRs #117, #118)
- DRP migrations run (24 tables)
- Phase config seeded (phase=advisor, write_enabled=false)

## Deferred to future session

- Confirm nightly DRP sync succeeded (check `drp_agent_runs` table after 1 AM ET)
- Verify staff access: Melanie/Steve/Lauren on SB501000, Sarah on PO302000

## Repos in play

- `aesthetik-platform` at `/Users/kevin/dev/aesthetik-platform/`
- `acumatica-ci-cd` at `/Users/kevin/dev/acumatica-ci-cd/`

## Database connection

```
DATABASE_URL="postgresql://wms:41PNF7MJujb7I0yfikMUYdpV@nozomi.proxy.rlwy.net:38241/heritage_wms"
```
Use `/opt/homebrew/Cellar/postgresql@16/16.13/bin/psql` (not in PATH).

## What's NOT in scope

- PCC Acumatica redesign (SB501000/SB501100/SB501200)
- Phase 2 implementation
- Exogenous signals (HubSpot, Shopify)
- Accuracy tracking
