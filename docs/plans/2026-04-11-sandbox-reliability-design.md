# Sandbox Reliability — Design Doc

**Date:** 2026-04-11
**Status:** Approved
**Context:** Sandbox-gate has blocked every deploy since Session 4 (2026-04-10). Three root causes identified: PO3010PL SiteMap shadow, --no-merge permanent verify failures, and stale sandbox data.

## Workstream 1: Fix PO3010PL SiteMap Shadow

**Root cause:** AesthetikWMS registers a SiteMap entry with `ScreenID="PO3010PL"` pointing to `~/Pages/PO/PO301000.aspx`. This shadows the stock PO301000 registration, causing `/Main?ScreenId=PO301000` to redirect to home instead of loading the PO form. Added in commit `a1b86d4` to restore access after a corrupt publish — used a custom ScreenID instead of the stock one.

**Fix:** Change `ScreenID="PO3010PL"` → `ScreenID="PO301000"` in `Customization/AesthetikWMS/project.xml`. The `RolesInGraph` entries are stock defaults, not custom overrides.

**Cleanup after fix:**
- Revert `skipif(sandbox)` on `test_container_tracking_navigates_to_sb501000` (PR #353)
- Revert direct-ASPX pattern in `test_container_tracking_button_exists` — use `acumatica_screen("PO301000")` fixture
- Remove direct-ASPX pattern in `test_container_tracking_navigates_to_sb501000`
- Update docstrings referencing PO3010PL shadow workaround

**Deploy:** Next pipeline run publishes to sandbox + prod. One app pool restart.

## Workstream 2: --no-merge Verify Failure Suppression (Until September)

**Root cause:** Orphaned IIG metadata in the Acumatica publish registry causes `merge=true` to crash. Workaround: `--no-merge` (`isMergeWithExistingPackages: false`), which skips ASPX extraction for co-published projects. This produces 3 permanent verify failures every pipeline run.

**Timeline:** Acumatica quoted an SOW for cleanup. Heritage Fabrics gets DB access in September 2026. `--no-merge` stays until then.

### Part A: Orphan Row Map for September Cleanup

Create `/docs/reference/iig-orphan-cleanup.md` documenting:

Orphaned projects:
- `IIGCONTAINERMGMT[24.204.0004][R19]1`
- `IIGHFContainerMods[24.204.0004][R04]`
- `AesthetikContainerGIs`

Tables to clean: `CustProject`, `CustProjectMeta`, `CustPublishedProject` (and related).

Include ready-to-run SQL DELETE statements for when DB access is available.

### Part B: verify.py --no-merge Awareness

Add `--no-merge-expected` flag to `verify.py` that:
1. Reads the list of known ASPX mismatch screens caused by `--no-merge`
2. Downgrades matching ASPX mismatch errors from FAIL → WARN
3. Still reports them in output (visibility preserved)
4. Does not count them toward the failure total

Source the expected failure list from `acuops.yaml` or a dedicated config section.

### Part C: Access Rights Verification

Verify that users Melanie, Steve, and Lauren have access to:
- SB501000 (Container Maintenance)
- Related container tracking screens

Sarah's access to PO302000 should also be verified (deferred from Session 4).

## Workstream 3: Sandbox Data Freshness via Entity Sync

**Problem:** Sandbox has stale/empty data. CRUD tests skipped, GIs render empty grids.

**Approach:** Extend `scripts/heritage/entity-sync.py` to target sandbox in addition to test tenant.

### Entities

Already synced (prod → test):
- Customer (with MainContact)
- StockItem (with Attributes)
- Vendor
- Employee

Add for container/DRP coverage:
- PurchaseOrder (headers)
- SalesOrder (headers)
- Shipment (for DRP_VelocityHistory GI)

### Schedule

- Nightly, after existing prod → test sync
- Also available on-demand via `workflow_dispatch`
- Separate from deploy pipeline — data freshness does not gate deploys

### What This Enables

- Remove `skip_on_sandbox` from CRUD tests
- GI column xfail tests may start passing (rows to render)
- Verify checks run against prod-like data

### What This Does NOT Replace

Customization publish in sandbox-gate still handles GI definitions, DACs, ASPX files. Entity sync only fills in business data.

## Dependencies Between Workstreams

- Workstream 1 (PO3010PL) is independent — can ship immediately
- Workstream 2 (--no-merge) is independent — can ship in parallel
- Workstream 3 (entity sync) benefits from Workstream 1 being complete (tests that currently use direct-ASPX workarounds get simplified first)

## Not In Scope

- PCC Acumatica redesign (SB501000/SB501100/SB501200)
- Full tenant snapshot via Playwright (SM301000)
- Phase 2 DRP implementation
- Removing sandbox-gate from pipeline
