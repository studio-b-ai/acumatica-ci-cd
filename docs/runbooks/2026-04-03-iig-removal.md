# IIG Container Package Removal — Runbook

**Date:** Friday 2026-04-03, after 6:00 PM CT
**Duration:** ~30 minutes
**Risk:** Medium — data migration + package removal on production
**Rollback:** Snapshot taken before step 1. Restore via SM204505 Import.

## Background

AesthetikContainers replaces two IIG packages:
- `IIGHFContainerMods` — Heritage Fabrics container customizations
- `IIGCONTAINERMGMT[24.204.0004][R19]1` — IIG's global container management

AesthetikContainers was deployed to production 2026-03-30 (PR #95). This runbook covers data migration, IIG removal, and REST endpoint activation.

Key artifacts in PR #109 (`fix/iig-removal`):
- `EntityEndpoint_24_200_001_ContainerTracking.xml` — fixes REST endpoint entity names (`UsrContainer`, `UsrContainerEvent`, `UsrContainerPOLink`)
- Updated `ALSO_PUBLISH_PROJECTS` — removes IIG packages from co-publish list
- `isMergeWithExistingPackages=True` — prevents unpublishing other ISV packages

## Pre-Flight Checklist

- [ ] AesthetikContainers is published on production (confirmed 2026-03-30)
- [ ] `UsrContainer` and `UsrContainerPOLink` tables exist on production
- [ ] IIG packages still on the instance
- [ ] No active users (Friday after 6pm CT)
- [ ] PR #109 (`fix/iig-removal`) reviewed and ready to merge

## Step 1: Snapshot (SM204505)

1. Open SM204505 (Customization Projects)
2. Click **Export** on the currently published project set
3. Save the .zip locally as `pre-iig-removal-backup-2026-04-03.zip`
4. Confirm download completed

**Checkpoint:** Snapshot saved locally.

## Step 2: Verify IIG Data Exists

Run via SM302050 (Direct SQL) or SSMS:

```sql
SELECT 'IGCMPOLandedCost' AS tbl, COUNT(*) AS cnt FROM IGCMPOLandedCost
UNION ALL
SELECT 'IGCMPOLandedCostLine', COUNT(*) FROM IGCMPOLandedCostLine;
```

**Checkpoint:** Record the counts. These must match post-migration.

## Step 3: Run Data Migration

Run `scripts/migrate-igcm-containers.sql` via SM302050 or SSMS.

The script:
1. Migrates `IGCMPOLandedCost` -> `UsrContainer` (container headers)
2. Migrates `IGCMPOLandedCostLine` -> `UsrContainerPOLink` (container-PO links)
3. Updates `POOrder.UsrContainerRef` with migrated container references

The script is idempotent (`NOT EXISTS` guards on all inserts).

**Checkpoint:** Verify output shows non-zero row counts for containers and PO links.

## Step 4: Verify Migration

```sql
-- Container count should match IGCMPOLandedCost
SELECT COUNT(*) AS containers FROM UsrContainer;

-- PO link count should be close to IGCMPOLandedCostLine (minus nulls)
SELECT COUNT(*) AS po_links FROM UsrContainerPOLink;

-- Spot-check a known container
SELECT TOP 5 * FROM UsrContainer ORDER BY CreatedDateTime DESC;

-- Verify PO headers got container refs
SELECT COUNT(*) FROM POOrder WHERE UsrContainerRef IS NOT NULL;
```

**Checkpoint:** Counts match step 2. Container data looks correct.

## Step 5: Merge PR #109 and Deploy via CI/CD

1. **Merge PR #109** (`fix/iig-removal`) to `main`
2. **Update `ALSO_PUBLISH_PROJECTS`** in GitHub Actions variables — remove `IIGCONTAINERMGMT[24.204.0004][R19]1` and `IIGHFContainerMods` from the comma-separated list
3. **Trigger deploy** (auto-deploys on merge to main, or manual dispatch):

```bash
gh workflow run deploy-customization.yml \
  --repo studio-b-ai/acumatica-ci-cd \
  --ref main \
  -f environment=production \
  -f skip_countdown=true
```

The deploy will:
- Package AesthetikContainers (including `EntityEndpoint_24_200_001_ContainerTracking.xml`)
- Import + publish WITHOUT IIG packages in the co-publish list
- `isMergeWithExistingPackages=True` prevents unpublishing other ISV packages
- App pool restarts (~2-5 minutes)

**Checkpoint:** Pipeline completes successfully. No publish errors in deploy log.

## Step 6: Verify Post-Removal

### 6a: Screen Verification
1. **Login** — confirm you can log into Acumatica after app pool restart
2. **Container Maintenance (SB501000)** — open the screen, verify it loads, data is visible
3. **Purchase Orders (PO301000)** — open a PO, verify Container/BOL Ref + Exp/Act Arrival Date fields
4. **Stock Items (IN202500)** — verify Duty Rate, Fiber Content, Preferential Tariff, Freight Class fields
5. **PO Receipts (PO302000)** — verify Actual Duty, Freight Allocated, Brokerage, Landed Cost/Unit columns
6. **Vendor (AP303000)** — verify Default In-Transit Warehouse and Default Carrier fields
7. **Shipments (SO302000)** — verify Include In Container field
8. **Inventory Allocation (IN402000)** — verify Exp. Arrival Date column
9. **InventoryQuantityDetail GI** — verify Container Number column shows data

### 6b: REST Endpoint Verification
Confirm the EntityEndpoint XML fix took effect — correct entity names return HTTP 200:

```bash
python3 scripts/configure-container-endpoint.py --verify
```

Expected: `UsrContainer`, `UsrContainerEvent`, `UsrContainerPOLink` all return HTTP 200.

If the old IIG entity names (`Container`, `ContainerEvent`, `ContainerPOLink`) still return 200, the EntityEndpoint XML was not processed — check the deploy log for errors.

### 6c: SiteMap Verification
Confirm SB501000 is accessible in the Acumatica navigation menu. If not visible, the `AesthetikContainersInstall` plugin's `SetSiteMapGraphType` SQL may need to re-run (triggered on next publish).

**Checkpoint:** All screens load. REST entities return 200. SB501000 in site map.

## Step 7: Activate Container Tracking on Webhook Router

Set the feature flag in Railway:

```bash
railway variables set CONTAINER_TABLE_TRACKING_ENABLED=true \
  --service webhook-router \
  --environment production
```

Then redeploy webhook-router to pick up the new env var.

> **Note:** This enables the webhook-router to read/write `UsrContainer`, `UsrContainerEvent`, and `UsrContainerPOLink` via the ContainerTracking REST endpoint. Carrier API auto-tracking (CHR, Maersk, OTS) requires separate carrier credentials — those are a future enhancement, not a blocker.

**Checkpoint:** Webhook-router health endpoint confirms `containerTrackingEnabled: true`.

## Step 8: Notify Team

- Post to `#deployments` in Slack: IIG packages removed, AesthetikContainers is the sole container management system
- Notify imports team: Container screen is now at **SB501000 (Container Maintenance)** — search for "Container Maintenance" in Acumatica

## Rollback

If anything fails after step 5 (deploy):

1. Open SM204505
2. Import `pre-iig-removal-backup-2026-04-03.zip`
3. Publish — this restores IIG packages
4. App pool restart, verify
5. Revert PR #109 merge on GitHub
6. Re-add IIG packages to `ALSO_PUBLISH_PROJECTS`

Data migration (steps 3-4) is safe to leave in place even after rollback — the `NOT EXISTS` guards prevent duplicates.

## Post-Removal Cleanup

### GI / Report Audit
Check for orphaned references to IIG field names:

```sql
-- Check GI definitions for IGCM field references
SELECT gd.Name, gr.Field
FROM GIDesign gd
JOIN GIResult gr ON gd.DesignID = gr.DesignID
WHERE gr.Field LIKE '%IGCM%' OR gr.Field LIKE '%IIG%';

-- Check GI filters
SELECT gd.Name, gf.Field
FROM GIDesign gd
JOIN GIFilter gf ON gd.DesignID = gf.DesignID
WHERE gf.Field LIKE '%IGCM%' OR gf.Field LIKE '%IIG%';
```

Any results need manual cleanup — update the GI to use AesthetikContainers field names.

### Orphaned IIG Field
`UsrIGCMCustomClassificationNbr` on StockItem — confirmed unused (all values null in production). Column remains in the `InventoryItem` table but is no longer surfaced on any screen. No action needed unless the column causes issues.

### IIG Package Deletion (Optional)
After 2 weeks of stable operation, delete the unpublished IIG packages from SM204505 to remove them from the instance entirely.
