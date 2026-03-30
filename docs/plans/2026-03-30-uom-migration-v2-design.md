# UOM Migration v2: PIECE -> YDS + PIECENBR -> BOLTID

**Date:** 2026-03-30
**Status:** Approved
**Predecessor:** v1 failed — see AAR below

## Background

Heritage Fabrics uses PIECE as the base UOM for fabric inventory. The correct UOM is YDS (yards). A v1 migration attempt on 2026-03-28 succeeded at renaming but then deleted all YDS->YDS self-conversion records from INUnit, bricking inventory operations. Eight SQL INSERT attempts to restore them failed — records were invisible to the ORM. Production was restored from snapshot.

## Root Cause (v1 failure)

Section 2 of the v1 plugin contained:

```sql
DELETE FROM INUnit WHERE FromUnit = 'YDS' AND ToUnit = 'YDS' AND UnitRate = 1
```

This was intended to clean up duplicate self-conversions after the rename. It was too aggressive — it deleted ALL YDS->YDS self-conversions, including ones items depend on. Raw SQL INSERTs could not restore ORM-visible records.

## What Changed in v2

| v1 | v2 |
|---|---|
| DELETE FROM INUnit (self-conversions) | Removed entirely — no YDS items exist, no duplicates to clean |
| Lot/Serial class renamed to BLTNBR | Renamed to BOLTID |
| Code references to PIECENBR unchanged | Updated in SOOrderEntry_AutoAllocation.cs and GI XML |

## Scope

### Package 1: UomRenamePieceToYds (one-time CustomizationPlugin)

Standalone customization published once via CI/CD, then removed. Not part of "also publish" chain.

**Database changes (all transactional, all scoped to Heritage Test for Phase 1):**

1. Core Item Configuration: InventoryItem.BaseUnit, SalesUnit; INItemClass.BaseUnit, SalesUnit
2. UOM Conversions: INUnit.FromUnit, INUnit.ToUnit — rename only, NO DELETE
3. Inventory Transactions: INTran.UOM, INTranSplit.UOM
4. Sales Orders & Shipments: SOLine, SOLineSplit, SOShipLine, SOShipLineSplit, SOPackageDetailEx
5. Purchase Orders & Receipts: POLine, POLineSplit, POReceiptLine, POReceiptLineSplit
6. AR/AP Transactions: ARTran.UOM, APTran.UOM
7. Price Lists: ARSalesPrice.UOM, APVendorPrice.UOM
8. Physical Inventory & Kits: INPIDetail, INKitSpecStkDet, INKitSpecNonStkDet
9. Inventory Planning: INItemPlan.UOM, INItemCustSalesStats.BaseUOM
10. Lot/Serial Class Rename: PIECENBR -> BOLTID (InventoryItem, INItemClass, INLotSerClassSegment, INLotSerClass)
11. Cleanup: Delete CSUnit record for PIECE if no references remain

**Safety features:**
- Transactional: all-or-nothing rollback on any error
- Pre-flight count: exits as no-op if 0 PIECE references (idempotent)
- Post-flight count: warns if any PIECE references remain
- Safe() method: skips missing tables/columns instead of failing
- Company scoping: TARGET_COMPANY constant for phased rollout

### Package 2: AesthetikWMS code updates (permanent)

Published normally through the regular customization pipeline.

- `SOOrderEntry_AutoAllocation.cs`: Change `private const string PieceGoodsClassID = "PIECENBR"` to `"BOLTID"`
- `GenericInquiryScreen_UnallocatedPieceGoods.xml`: Change WHERE clause `Value1="PIECENBR"` to `Value1="BOLTID"`

Note: `PIECEGOODS` lot/serial class is separate and unchanged.

## Deployment Order

1. Publish `UomRenamePieceToYds` to Heritage Test (renames DB records)
2. Publish updated `AesthetikWMS` to Heritage Test (code now references BOLTID)
3. Verify in Heritage Test: inventory items, conversions, auto-allocation, GI
4. Remove `UomRenamePieceToYds` package
5. Phase 2 (later): Set TARGET_COMPANY = null, repeat for all companies

## Guards

- `validate-project.py` blocks `DELETE FROM INUnit` and `INSERT INTO INUnit` — this migration uses neither
- Pre-flight idempotency: migration is a no-op if already run
- Transaction rollback on any error
