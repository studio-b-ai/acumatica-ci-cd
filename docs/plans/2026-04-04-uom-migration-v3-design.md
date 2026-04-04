# UOM Migration v3: INSERT-then-flip

**Date:** 2026-04-04
**Status:** Approved
**Predecessors:** v1 (deleted INUnit self-conversions, P0 outage), v2 (collided on INUnit unique keys 2x)

## Problem

Heritage Fabrics uses PIECE as base UOM but needs YDS. Two prior migration attempts failed because renaming/deleting INUnit records collided with existing YDS conversion records.

## Key Discovery

The INUnit table already has extensive YDS records:
- 577 items with YDS→YDS self-conversions (Type=1)
- 15,060 items with YDS→PIECE cross-conversions (Type=1)
- 5+6 class-level and global-level YDS records

A single item can have BOTH PIECE→PIECE and YDS→YDS self-conversions without conflict (different FromUnit = different unique key entry).

## Strategy: INSERT missing records, then flip the labels

**Do NOT rename, update, or delete anything in INUnit.**

Instead:
1. INSERT missing YDS→YDS self-conversions by copying from existing PIECE→PIECE records
2. UPDATE InventoryItem/INItemClass BaseUnit and SalesUnit from PIECE to YDS
3. UPDATE UOM on open transaction lines (SO, PO, AR, AP, IN)
4. Rename PIECENBR → BOLTID lot/serial class

Old PIECE records become orphans — harmless, cleaned up later in a separate migration.

## Two Phases

### Phase A: Proof of Concept (single item)

The v1 AAR documented that raw SQL INSERT into INUnit created ORM-invisible records. Phase A tests whether copying CompanyMask from an existing visible record produces a visible result.

1. Diagnostic plugin inserts ONE YDS→YDS record for a known item
2. Playwright verifies the conversion appears on the Stock Items screen (IN202500)
3. If visible → proceed to Phase B
4. If invisible → STOP, INSERT approach doesn't work

### Phase B: Full Migration (CustomizationPlugin)

**Section 1: INSERT missing YDS→YDS self-conversions**

```sql
INSERT INTO INUnit (CompanyID, UnitType, ItemClassID, InventoryID,
                    FromUnit, ToUnit, UnitRate, UnitMultDiv,
                    PriceAdjustmentMultiplier, CompanyMask,
                    CreatedByID, CreatedByScreenID, CreatedDateTime,
                    LastModifiedByID, LastModifiedByScreenID, LastModifiedDateTime)
SELECT CompanyID, UnitType, ItemClassID, InventoryID,
       'YDS', 'YDS', UnitRate, UnitMultDiv,
       PriceAdjustmentMultiplier, CompanyMask,
       CreatedByID, CreatedByScreenID, GETUTCDATE(),
       LastModifiedByID, LastModifiedByScreenID, GETUTCDATE()
FROM INUnit src
WHERE src.FromUnit = 'PIECE' AND src.ToUnit = 'PIECE'
AND NOT EXISTS (
    SELECT 1 FROM INUnit dup
    WHERE dup.CompanyID = src.CompanyID
    AND dup.UnitType = src.UnitType
    AND dup.ItemClassID = src.ItemClassID
    AND dup.InventoryID = src.InventoryID
    AND dup.FromUnit = 'YDS' AND dup.ToUnit = 'YDS'
)
```

Handles all UnitTypes (1=item, 2=class, 3=global) in one statement.

**Section 2: Flip BaseUnit and SalesUnit**

```sql
UPDATE InventoryItem SET BaseUnit = 'YDS' WHERE BaseUnit = 'PIECE'
UPDATE InventoryItem SET SalesUnit = 'YDS' WHERE SalesUnit = 'PIECE'
UPDATE INItemClass SET BaseUnit = 'YDS' WHERE BaseUnit = 'PIECE'
UPDATE INItemClass SET SalesUnit = 'YDS' WHERE SalesUnit = 'PIECE'
```

**Sections 3-9: Transaction table UOM rename**

Same as v2 — update SOLine, POLine, INTran, ARTran, APTran, etc.

**Section 10: Lot/Serial class rename**

PIECENBR → BOLTID across InventoryItem, INItemClass, INLotSerClass, INLotSerClassSegment.

**Section 11: Skip CSUnit cleanup**

Leave PIECE in CSUnit for now.

## What's NOT in this migration

- No DELETE from INUnit
- No UPDATE on INUnit (no renaming conversion records)
- No touching YDS→PIECE cross-conversions (orphaned, harmless)
- No touching old PIECE→PIECE self-conversions (orphaned, harmless)
- No YARDS cleanup (5 items — separate migration)
- No CSUnit cleanup

## Success Criteria

1. Migration SQL completes with zero errors in publish log
2. Post-flight: zero items with BaseUnit=PIECE, every active item has YDS→YDS self-conversion
3. Playwright e2e smoke tests ALL pass:
   - Stock item (IN202500): BaseUnit = YDS
   - Stock item conversions: YDS→YDS self-conversion visible
   - Unit Conversions screen (IN209000): YDS records present
   - Unallocated Piece Goods GI: loads with BOLTID filter
   - Existing PC sales order: loads with line details, no UOM errors
   - New PC order with BOLTID/YDS: saves, auto-allocation fires
   - Test order cleanup (delete)

## Rollback

Restore from snapshot. The inserted YDS→YDS records are harmless even if left.

## INUnit Data Reference (Heritage Test, 2026-04-04)

| From | To | Type=1 | Type=2 | Type=3 |
|---|---|---|---|---|
| PIECE | PIECE | 15,127 | 380 | 7 |
| YDS | YDS | 577 | 5 | 6 |
| YDS | PIECE | 15,060 | 368 | 6 |
| CUT | PIECE | 15,043 | 368 | — |
| CUT | YDS | — | — | 6 |
| IN | YDS | 567 | 5 | — |
| BOX | PIECE | 4 | 2 | 1 |
| HALF | PIECE | 280 | 30 | — |
| PIECE | YDS | — | — | 6 |
| PIECE | YARDS | 5 | — | — |
| YARDS | PIECE | 5 | — | — |
