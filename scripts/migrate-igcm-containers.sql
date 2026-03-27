-- ============================================================================
-- IGCM → UsrContainer Data Migration
-- ONE-TIME script — run AFTER AesthetikContainers publish creates the tables
-- Run via Acumatica SM302050 (Direct SQL) or SSMS
-- ============================================================================
-- Prerequisites:
--   1. AesthetikContainers published (UsrContainer, UsrContainerPOLink tables exist)
--   2. IIG packages still published (IGCMPOLandedCost, IGCMPOLandedCostLine still exist)
--
-- After running:
--   1. Verify data: SELECT COUNT(*) FROM UsrContainer; SELECT COUNT(*) FROM UsrContainerPOLink;
--   2. Verify GIs work with new tables
--   3. Then unpublish IIG packages from SM204505
-- ============================================================================

PRINT '=== IGCM → UsrContainer Migration ==='
PRINT 'Start: ' + CONVERT(varchar, GETUTCDATE(), 120)

-- Step 1: Migrate container headers (IGCMPOLandedCost → UsrContainer)
-- IGCMPOLandedCost is the container header with RefNbr as the key
INSERT INTO UsrContainer (
    CompanyID,
    ContainerCD,
    CarrierCode,
    BookingRef,
    Status,
    CreatedByID,
    CreatedByScreenID,
    CreatedDateTime,
    LastModifiedByID,
    LastModifiedByScreenID,
    LastModifiedDateTime
)
SELECT
    c.CompanyID,
    ISNULL(c.ContainerNbr, c.RefNbr),  -- Use ContainerNbr if available, else RefNbr
    'OTHER',                              -- Default carrier — update manually per container
    c.RefNbr,                             -- Preserve IIG RefNbr as booking ref
    CASE
        WHEN c.Released = 1 THEN 'DELIVERED'
        WHEN c.Hold = 1 THEN 'CUSTOMS_HOLD'
        ELSE 'IN_TRANSIT'
    END,
    c.CreatedByID,
    c.CreatedByScreenID,
    c.CreatedDateTime,
    c.LastModifiedByID,
    c.LastModifiedByScreenID,
    c.LastModifiedDateTime
FROM IGCMPOLandedCost c
WHERE NOT EXISTS (
    SELECT 1 FROM UsrContainer u
    WHERE u.CompanyID = c.CompanyID
    AND u.ContainerCD = ISNULL(c.ContainerNbr, c.RefNbr)
);

PRINT 'Containers migrated: ' + CAST(@@ROWCOUNT AS varchar);

-- Step 2: Migrate container-PO links (IGCMPOLandedCostLine → UsrContainerPOLink)
INSERT INTO UsrContainerPOLink (
    CompanyID,
    ContainerID,
    OrderType,
    OrderNbr,
    LineNbr
)
SELECT DISTINCT
    cl.CompanyID,
    u.ContainerID,
    cl.POOrderType,
    cl.PONbr,
    cl.POLineNbr
FROM IGCMPOLandedCostLine cl
INNER JOIN IGCMPOLandedCost c
    ON cl.CompanyID = c.CompanyID AND cl.RefNbr = c.RefNbr
INNER JOIN UsrContainer u
    ON u.CompanyID = c.CompanyID AND u.ContainerCD = ISNULL(c.ContainerNbr, c.RefNbr)
WHERE cl.PONbr IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM UsrContainerPOLink lk
    WHERE lk.CompanyID = cl.CompanyID
    AND lk.ContainerID = u.ContainerID
    AND lk.OrderType = cl.POOrderType
    AND lk.OrderNbr = cl.PONbr
    AND ISNULL(lk.LineNbr, -1) = ISNULL(cl.POLineNbr, -1)
);

PRINT 'PO links migrated: ' + CAST(@@ROWCOUNT AS varchar);

-- Step 3: Update PO headers — set UsrContainerRef from migrated container data
UPDATE po
SET po.UsrContainerRef = u.ContainerCD
FROM POOrder po
INNER JOIN UsrContainerPOLink lk
    ON lk.CompanyID = po.CompanyID AND lk.OrderType = po.OrderType AND lk.OrderNbr = po.OrderNbr
INNER JOIN UsrContainer u
    ON u.CompanyID = lk.CompanyID AND u.ContainerID = lk.ContainerID
WHERE po.UsrContainerRef IS NULL;

PRINT 'PO headers updated with container ref: ' + CAST(@@ROWCOUNT AS varchar);

PRINT '=== Migration Complete ==='
PRINT 'End: ' + CONVERT(varchar, GETUTCDATE(), 120)
PRINT ''
PRINT 'NEXT STEPS:'
PRINT '  1. SELECT COUNT(*) FROM UsrContainer — verify row count matches IGCMPOLandedCost'
PRINT '  2. SELECT COUNT(*) FROM UsrContainerPOLink — verify links exist'
PRINT '  3. Open InventoryQuantityDetail GI — verify Container Number column shows data'
PRINT '  4. Unpublish IIGHFContainerMods + IIGGlobalContainerMgmt from SM204505'
