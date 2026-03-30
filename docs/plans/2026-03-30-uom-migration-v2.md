# UOM Migration v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename base UOM from PIECE to YDS and lot/serial class from PIECENBR to BOLTID across Heritage Test, fixing the v1 failure that deleted INUnit self-conversions.

**Architecture:** One-time CustomizationPlugin (`UomRenamePieceToYds`) performs transactional SQL UPDATEs across 30+ tables. Separate permanent code changes update hardcoded PIECENBR references in AesthetikWMS. Plugin is published once via CI/CD, verified, then removed.

**Tech Stack:** Acumatica CustomizationPlugin (C#), raw SQL via SqlConnection, CI/CD pipeline

**Design doc:** `docs/plans/2026-03-30-uom-migration-v2-design.md`

---

### Task 1: Create the UomRenamePieceToYds CustomizationPlugin

**Files:**
- Create: `Customization/UomRenamePieceToYds/project.xml`

**Context:** This is based on the v1 plugin from commit `140ece2` on branch `deploy/uom-rename-piece-to-yds`. The key difference from v1: Section 2 (INUnit) has NO DELETE statement. Section 10 renames to BOLTID instead of BLTNBR.

**Step 1: Create the plugin from v1 with fixes applied**

Create `Customization/UomRenamePieceToYds/project.xml` with the full CustomizationPlugin. The changes from v1 are:

1. **Section 2 (INUnit Conversions):** Remove the line:
   ```csharp
   total += Safe(conn, txn, $"DELETE FROM INUnit WHERE FromUnit = 'YDS' AND ToUnit = 'YDS' AND UnitRate = 1{companyFilter}", "INUnit.SelfRef.Cleanup");
   ```
   Keep only the two UPDATE statements (FromUnit and ToUnit rename).

2. **Section 10 (Lot/Serial Class Rename):** Replace all instances of `'BLTNBR'` with `'BOLTID'`:
   ```csharp
   total += Safe(conn, txn, $"UPDATE InventoryItem SET LotSerClassID = 'BOLTID' WHERE LotSerClassID = 'PIECENBR'{companyFilter}", "InventoryItem.LotSerClassID");
   total += Safe(conn, txn, $"UPDATE INItemClass SET LotSerClassID = 'BOLTID' WHERE LotSerClassID = 'PIECENBR'{companyFilter}", "INItemClass.LotSerClassID");
   total += Safe(conn, txn, $"UPDATE INLotSerClassSegment SET LotSerClassID = 'BOLTID' WHERE LotSerClassID = 'PIECENBR'{companyFilter}", "INLotSerClassSegment.LotSerClassID");
   total += Safe(conn, txn, $"UPDATE INLotSerClass SET LotSerClassID = 'BOLTID' WHERE LotSerClassID = 'PIECENBR'{companyFilter}", "INLotSerClass.LotSerClassID");
   ```

Everything else (Sections 1, 3-9, 11, helper methods, transaction wrapping, pre/post-flight counts) is identical to v1.

**Step 2: Validate the plugin**

Run: `python3 scripts/validate-project.py Customization/UomRenamePieceToYds/project.xml`

Expected: PASS (no DELETE FROM INUnit, no INSERT INTO INUnit, uses ConfigurationManager not WebConfigurationManager, has try/catch and null check)

**Step 3: Commit**

```bash
git add Customization/UomRenamePieceToYds/project.xml
git commit -m "feat: UOM migration v2 — PIECE→YDS, PIECENBR→BOLTID (Heritage Test scoped)

Fixes v1 failure: removes DELETE FROM INUnit that killed self-conversions.
Lot/serial class renamed to BOLTID (was BLTNBR in v1).
Phase 1: scoped to Heritage Test only."
```

---

### Task 2: Update SOOrderEntry_AutoAllocation.cs — PIECENBR to BOLTID

**Files:**
- Modify: `Customization/AesthetikWMS/Code/Graph/SOOrderEntry_AutoAllocation.cs:29`

**Step 1: Update the constant**

Change line 29 from:
```csharp
private const string PieceGoodsClassID = "PIECENBR";
```
to:
```csharp
private const string PieceGoodsClassID = "BOLTID";
```

**Step 2: Update comments referencing PIECENBR**

Lines 13, 16 — update comments from "PIECENBR" to "BOLTID":
- Line 13: `/// Auto-allocation for piece goods (BOLTID lot class) on PC/FO orders.`
- Line 16: `/// For each unallocated BOLTID line:`

**Step 3: Commit**

```bash
git add Customization/AesthetikWMS/Code/Graph/SOOrderEntry_AutoAllocation.cs
git commit -m "fix: update auto-allocation lot class constant PIECENBR → BOLTID"
```

---

### Task 3: Update GenericInquiryScreen_UnallocatedPieceGoods.xml — PIECENBR to BOLTID

**Files:**
- Modify: `Customization/AesthetikWMS/GenericInquiryScreen_UnallocatedPieceGoods.xml:71-72`

**Step 1: Update the WHERE clause**

Change line 71-72 from:
```xml
          <!-- WHERE: PIECENBR lot class -->
          <GIWhere LineNbr="6" IsActive="1" DataFieldName="InventoryItem.LotSerClassID" Condition="EQ" Value1="PIECENBR" />
```
to:
```xml
          <!-- WHERE: BOLTID lot class -->
          <GIWhere LineNbr="6" IsActive="1" DataFieldName="InventoryItem.LotSerClassID" Condition="EQ" Value1="BOLTID" />
```

**Step 2: Validate AesthetikWMS project**

Run: `python3 scripts/validate-project.py Customization/AesthetikWMS/project.xml`

Expected: PASS (existing warnings OK, no new failures)

**Step 3: Commit**

```bash
git add Customization/AesthetikWMS/GenericInquiryScreen_UnallocatedPieceGoods.xml
git commit -m "fix: update Unallocated Piece Goods GI filter PIECENBR → BOLTID"
```

---

### Task 4: Final review and PR

**Step 1: Verify no remaining PIECENBR references (except PIECEGOODS)**

Run: `grep -r "PIECENBR" Customization/`

Expected: Zero results. (PIECEGOODS is a different string and should NOT match.)

**Step 2: Verify no DELETE FROM INUnit**

Run: `grep -ri "DELETE FROM INUnit" Customization/`

Expected: Zero results.

**Step 3: Run full validation suite**

Run:
```bash
python3 scripts/validate-project.py Customization/UomRenamePieceToYds/project.xml
python3 scripts/validate-project.py Customization/AesthetikWMS/project.xml
```

Expected: Both PASS.

**Step 4: Create PR**

Target: `main`
Title: `UOM migration v2: PIECE→YDS + PIECENBR→BOLTID (Heritage Test)`
Body: Reference design doc and AAR. Note the v1 fix (removed DELETE).
