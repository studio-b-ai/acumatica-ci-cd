# AesthetikHotfixDRPOrphans

One-shot cleanup of orphan GI metadata rows left behind by the failed DRP GI
install attempts in PRs #427 / #430 / #431 on 2026-04-16.

## Background

Three DRP GI install attempts ran against Heritage Fabrics prod on 2026-04-16
in rapid succession:

| PR | Approach | Result |
|---|---|---|
| [#427](https://github.com/studio-b-ai/acumatica-ci-cd/pull/427) | `<Sql>` blocks in `AesthetikContainers/project.xml` that INSERT GI rows | Ran once, then never re-ran (CLAUDE.md rule #24 — `<Sql>` blocks are tracked by Name, don't re-execute). 0/5 GIs made it live. |
| [#430](https://github.com/studio-b-ai/acumatica-ci-cd/pull/430) | Bumped `<Sql>` Names to `_v2` to force re-execution | Ran again, but not idempotent — likely left duplicate or partial rows. |
| [#431](https://github.com/studio-b-ai/acumatica-ci-cd/pull/431) | Moved install into C# `EnsureDRPGenericInquiries()` CustomizationPlugin | Referenced non-existent columns (`GIDesign.Description`, `GITable.IsActive`, `GIRelation.IsActive`, `GISort.IsDescending`). Silent-failed its SQL; may have left further partial rows. |

[PR #445](https://github.com/studio-b-ai/acumatica-ci-cd/pull/445) replaced
all three approaches with `<GenericInquiryScreen>` XML blocks that carry
canonical DesignIDs. Today `DRP_ItemWarehouseSettings` is the only DRP GI
reachable via OData (HTTP 403 access-denied, meaning the row exists);
`DRP_VelocityHistory`, `DRP_OpenSOCommitments`, `DRP_InventoryBySite`, and
`DRP_OpenPOLines` all return HTTP 404 (not registered).

The concern is that PRs #427/#430/#431 left **stale rows** — either whole
GIDesign rows with non-canonical DesignIDs, or orphan child rows (GITable,
GIResult, …) whose parent GIDesign has since been deleted. Rows of this
shape are exactly the 2026-03-29 outage pattern — see
[docs/AAR-2026-03-29-gi-sql-insert-outage.md](../../docs/AAR-2026-03-29-gi-sql-insert-outage.md).
Duplicate Name entries in GIDesign crash `PXGenericInqGrph+Definition`
prefetch on the next app-pool restart and are a plausible upstream cause of
the `UserRecordsDBUpdater.UpdateFavoriteRecordsCachedContentForAllUsers`
NRE path reported in the 2026-04-17 task prompt.

## What this package does

Single `<Sql>` block (`AesthetikHotfixDRPOrphans_v1`):

1. Discovers `CompanyID` from a known-present GI (`InventoryAllocationDetail`).
   Abort with warning if not found.
2. Builds a `@CanonDesigns` table of the five canonical DRP `(Name, DesignID)`
   pairs owned by PR #445.
3. Selects every GIDesign row whose `Name` is one of the five **but whose
   DesignID is not the canonical one**. If zero rows, prints "no orphan rows
   found" and exits.
4. If stale rows found, prints each `(Name, DesignID)` pair to the publish
   log, then inside an explicit transaction deletes matching rows from every
   child table (`GITable`, `GIResult`, `GIWhere`, `GISort`, `GIFilter`,
   `GIRelation`, `GIOn`, `GIGroupBy`) followed by the GIDesign rows themselves.
5. Every `DELETE` reports `@@ROWCOUNT` via `PRINT` so the publish log is a
   full audit trail.
6. Any error rolls back the transaction and rethrows so `publishEnd` reports
   `isFailed=true`. No silent partial cleanups.

The pattern is copied verbatim from the proven 2026-03-29 `UserAuditTrail`
cleanup (commit `ab35a0d`, `StudioBAcuOps/project.xml`). All target tables
are in `validate-project.py`'s `SAFE_DELETE_TABLES` allowlist.

## What this package does NOT do

- **Does not touch the five canonical DesignIDs.** Rows PR #445 owns are
  preserved. This is safe to run while PR #445 is already published.
- **Does not touch `CustProject`, `UserRecordsCache`, or `FavoriteRecord`.**
  My 2026-04-17 probe found no orphan CustProject rows via
  `/CustomizationApi/getProject`; if a future incident shows otherwise, use
  `ops/orphan-cleanup/cleanup-orphans.py` (API-based, proven). Platform
  tables like `UserRecordsCache` have undocumented schema owned by
  Acumatica — hand-rolled DELETE against them violates the
  `ops/orphan-cleanup/README.md` "no direct system-table SQL" convention.
- **Does not co-publish.** Not added to `acuops.yaml` `co_publish` or
  `also_publish_test`. Must be invoked manually through a one-shot deploy.
- **Does not re-execute.** `<Sql>` blocks are tracked by Name
  ([CLAUDE.md rule #24](../../CLAUDE.md)). After the first successful publish
  this package is a permanent no-op. Leaving it installed is harmless.

## Pre-deploy checklist

1. Run the read-only probe to confirm the package is still needed:
   ```bash
   python3 ops/orphan-cleanup/cleanup-orphans.py --env production --probe-only
   ```
   If the probe exits 0 **and** the four unpublished DRP GIs still 404 on
   OData, orphan GI rows are the most likely remaining explanation.

2. Verify the canonical DesignIDs in this `project.xml` still match the
   `<GenericInquiryScreen>` blocks in `Customization/AesthetikContainers/project.xml`.
   If PR #445 has been rebuilt with new DesignIDs, this package's
   `@CanonDesigns` table must be updated first.

3. Review publish timing — deploys restart the Acumatica app pool
   ([CLAUDE.md rule #11](../../CLAUDE.md)). Schedule after 6pm CT.

## Deploy

Manual `workflow_dispatch` of `acuops-deploy.yml` with
`CUSTOMIZATION_PROJECT_NAME=AesthetikHotfixDRPOrphans` (override the normal
`AesthetikContainers` primary via workflow inputs, or publish directly via
the Customization API with just this project name). Do **not** add this
package to `acuops.yaml` `publish.co_publish` — it's a one-shot, not a
standing co-publish target.

Sandbox run first. Check publish log for:

- `[AesthetikHotfixDRPOrphans] Stale DRP GIDesign rows to clean: N`
- Per-table `rows deleted: K` lines
- `[AesthetikHotfixDRPOrphans] DONE <timestamp>`

If `N=0` on sandbox, the production run will also be `N=0` (same project
content on both tenants). Safe to skip production in that case.

## Follow-up

After a successful production publish where any rows were actually deleted,
update
[docs/AAR-2026-04-17-custproject-nre-transient.md](../../docs/AAR-2026-04-17-custproject-nre-transient.md)
with the cleanup timestamp + totals. If N=0 on both sandbox and production,
update the AAR to record that the GI-orphan theory was also ruled out and
the incident was purely in-memory app-pool state (CLAUDE.md rule #18).
