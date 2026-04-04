# UOM Migration Phase 2 — PIECE→YDS All Companies

## Context

Read these files before doing anything:
- `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_uom_migration_v2.md` — v2 migration status
- `/Users/kevin/.claude/projects/-Users-kevin-Library-CloudStorage-OneDrive-HeritageFabrics-LLC/memory/context/aar-2026-03-29-uom-migration-outage.md` — P0 outage AAR with full timeline and failure analysis
- `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` — current customization (for reference on CustomizationPlugin patterns)

Phase 1 (Heritage Test only) completed as PR #94. Phase 2 extends to all companies by setting TARGET_COMPANY = null. The v1 outage on 2026-03-29 took production down for hours. This migration MUST NOT repeat that.

## What Went Wrong Last Time (non-negotiable lessons)

1. **Migration was deployed to production without testing on Heritage Test.** Heritage Test was blocked by a WMSynergy compile error. Instead of fixing staging first, migration went directly to prod. Result: immediate P0.

2. **No pre-flight validation.** No SQL script checked the state of INUnit, InventoryItem.SalesUnit, or open SO/PO lines before running. The migration assumed clean data and got dirty data.

3. **No pre-tested rollback.** Rollback zip was built under pressure during the outage. It had two packaging bugs (wrong internal filename, empty level attribute). It never uploaded successfully.

4. **Debugging was guess-and-deploy.** 20+ hotfix iterations deployed to production without first running diagnostic SELECTs. Each iteration consumed API logins. After 20+ attempts, the api-bot daily login quota was exhausted and CI/CD was dead.

5. **The true root cause was never confirmed.** Best hypothesis: InventoryItem.SalesUnit was null after migration, causing SOLine.UOM to default to null → UnitVerifying(null). But the UPDATE fix didn't resolve it — possibly due to cached DACs or already-persisted null UOM on open SO lines.

## Mandatory Gates — Do NOT Skip Any

### Gate 1: Heritage Test Must Be Clean
Before touching Phase 2, verify Heritage Test publishes cleanly:
```bash
# Trigger a test publish and confirm success
gh workflow run "AcuOps Deploy" --repo studio-b-ai/acumatica-ci-cd -f environment=staging
```
If Heritage Test publish fails for ANY reason, STOP. Fix it first. Do not proceed.

### Gate 2: Pre-Migration Validation Script
Write `scripts/pre-uom-migration-check.py` that runs read-only SQL against the target instance. It must verify ALL of the following before the migration runs:

```sql
-- 1. Every active InventoryItem has non-null BaseUnit, SalesUnit, PurchaseUnit
SELECT COUNT(*) AS null_units FROM InventoryItem
WHERE ItemStatus IN ('AC','NP') AND (BaseUnit IS NULL OR SalesUnit IS NULL OR PurchaseUnit IS NULL);
-- Must return 0

-- 2. INUnit self-conversion records exist for current BaseUnit
SELECT i.InventoryCD, i.BaseUnit FROM InventoryItem i
WHERE i.ItemStatus IN ('AC','NP')
AND NOT EXISTS (
    SELECT 1 FROM INUnit u WHERE u.FromUnit = i.BaseUnit AND u.ToUnit = i.BaseUnit AND u.InventoryID = i.InventoryID
);
-- Must return 0 rows

-- 3. No open SO lines with null UOM
SELECT COUNT(*) AS null_uom_so FROM SOLine l
INNER JOIN SOOrder o ON l.OrderType = o.OrderType AND l.OrderNbr = o.OrderNbr
WHERE o.Status IN ('N','H','O','B') AND l.UOM IS NULL;
-- Must return 0

-- 4. No open PO lines with null UOM
SELECT COUNT(*) AS null_uom_po FROM POLine l
INNER JOIN POOrder o ON l.OrderType = o.OrderType AND l.OrderNbr = o.OrderNbr
WHERE o.Status IN ('N','H','O') AND l.UOM IS NULL;
-- Must return 0

-- 5. INUnit record counts for PIECE and YDS (baseline)
SELECT FromUnit, ToUnit, UnitType, COUNT(*) AS cnt FROM INUnit
WHERE FromUnit IN ('PIECE','YDS') OR ToUnit IN ('PIECE','YDS')
GROUP BY FromUnit, ToUnit, UnitType ORDER BY FromUnit, ToUnit, UnitType;
-- Document baseline counts
```

Run this against Heritage Test first, then production (read-only). Both must pass. If any check fails, fix the data BEFORE deploying the migration.

### Gate 3: Pre-Tested Rollback Package
Before deploying the migration:
1. Build the rollback CustomizationPlugin (YDS→PIECE reverse)
2. Package it as a valid .zip
3. Validate the zip:
   ```bash
   unzip -l rollback.zip | grep project.xml  # Must show project.xml
   unzip -p rollback.zip project.xml | grep 'level="0"'  # Must show level="0"
   ```
4. Upload the rollback to Heritage Test and publish it
5. Verify Heritage Test works after rollback
6. Re-apply the migration to Heritage Test and verify it works again
7. Only THEN schedule the production deploy

### Gate 4: Diagnosis First, Not Fix First
If the migration breaks production:
1. DO NOT deploy a hotfix
2. Run the pre-migration validation SQL again to see what changed
3. Run these additional diagnostics:
   ```sql
   -- Check what happened to INUnit
   SELECT TOP 50 * FROM INUnit WHERE FromUnit = 'YDS' OR ToUnit = 'YDS' ORDER BY UnitType, InventoryID;

   -- Check InventoryItem state
   SELECT TOP 20 InventoryCD, BaseUnit, SalesUnit, PurchaseUnit FROM InventoryItem WHERE BaseUnit IS NULL OR SalesUnit IS NULL;

   -- Check for the specific SOLine error
   SELECT TOP 10 o.OrderNbr, l.LineNbr, l.UOM, l.InventoryID FROM SOLine l
   INNER JOIN SOOrder o ON l.OrderType = o.OrderType AND l.OrderNbr = o.OrderNbr
   WHERE l.UOM IS NULL AND o.Status IN ('N','H','O');
   ```
4. Only after confirming the exact rows/values causing the failure → deploy a targeted fix
5. Max 3 CI/CD deploy attempts before switching to manual browser upload

### Gate 5: After-Hours Only + Login Budget
- Deploy after business hours (Heritage Fabrics: after 6 PM CT)
- Budget max 3 CI/CD attempts for the migration
- If migration fails 3 times, deploy the pre-tested rollback (which you already validated in Gate 3)

## The Migration Itself

The v2 migration (PR #94) does:
1. Rename UOM code: PIECE→YDS in INUnit, InventoryItem, INItemClass, open SO/PO lines
2. Rename lot/serial class: PIECENBR→BOLTID
3. Update hardcoded references in customization code

Phase 2 change: set `TARGET_COMPANY = null` to run across all companies instead of just Heritage Test.

Key safety from v2: the v1 `DELETE FROM INUnit WHERE FromUnit='YDS' AND ToUnit='YDS'` was REMOVED. v2 never deletes INUnit records.

## Playwright Tests

After migration, run existing UOM tests:
```bash
pytest tests/ui/test_uom_migration.py -v
```

These verify:
- Stock items show YDS as base UOM
- INUnit conversions exist
- Unallocated Piece Goods GI loads
- Sales orders can be created with BOLTID items

## Sequence

1. Write pre-migration validation script
2. Run validation against Heritage Test → must pass
3. Run validation against production (read-only) → must pass
4. Build and test rollback package on Heritage Test
5. Deploy migration to Heritage Test (Phase 2: all companies)
6. Run Playwright UOM tests against Heritage Test → must pass
7. Run pre-migration validation against Heritage Test post-migration → must pass
8. Schedule production deploy (after hours)
9. Deploy to production
10. Run Playwright UOM tests against production → must pass
11. If ANY step fails, STOP and diagnose. Do not guess-and-deploy.
