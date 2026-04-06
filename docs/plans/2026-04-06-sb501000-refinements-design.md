# SB501000 Procurement Command Center — Refinements Design

**Date:** 2026-04-06
**Scope:** Bucket A — Visibility improvements only (no cost/accounting)
**Target:** Push to stage for pipeline validation

## Goal

Enhance the Procurement Command Center with vendor visibility, PO line item details, transport mode tracking, and a SiteMap title fix. All changes are low-risk: one new persistent field, BQL joins to existing Acumatica tables, and UI column additions.

## Changes

### 1. TransportMode Field

New `string(10)` dropdown on `UsrContainer`:
- Values: `OCEAN`, `AIR`, `RAIL`, `TRUCK`
- Default: null (optional field)
- Separate from Status (which tracks lifecycle: BOOKED → DELIVERED)
- Shown in container grid + detail form

**DAC:** Add `TransportMode` to `UsrContainer.cs`
**ASPX:** Add column to grid, dropdown to detail form
**DB:** New column on `UsrContainer` table (handled by Acumatica publish)

### 2. Vendor Column in PO Links

Add vendor info to the PO Links grid by joining through existing Acumatica tables:
- `UsrContainerPOLink` → `POOrder` (on OrderType+OrderNbr) → `BAccount` (on VendorID)
- Display: `VendorName` (from BAccount.AcctName)

**Graph:** Update `POLinks` view with joined BQL selecting from POOrder and BAccount
**ASPX:** Add `VendorName` column to PO Links grid

### 3. PO Line Details in PO Links

Expand PO Links grid with line-level data from `POLine`:
- `InventoryID` — stock item (selector)
- `ItemDescr` — item description (from InventoryItem)
- `OrderQty` — quantity ordered
- `UOM` — unit of measure

Join: `UsrContainerPOLink` → `POLine` (on OrderType+OrderNbr+LineNbr) → `InventoryItem` (on InventoryID)

**Graph:** Extend the `POLinks` view join to include POLine and InventoryItem
**ASPX:** Add InventoryID, ItemDescr, OrderQty, UOM columns to PO Links grid

### 4. SiteMap Title Fix

Change `Title="Container Maintenance"` → `Title="Procurement Command Center"` in project.xml ScreenWithRights section.

## Architecture

### DAC Changes

| DAC | Change |
|-----|--------|
| `UsrContainer` | Add `TransportMode` field (string(10), dropdown) |
| `UsrContainerPOLink` | No schema changes — line data comes from BQL joins |

### Graph Changes (ContainerMaint.cs)

**POLinks view** — current:
```csharp
PXSelectFrom<UsrContainerPOLink>
  .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
```

Updated: Join to POOrder, BAccount, POLine, InventoryItem to pull vendor name, stock item, qty, UOM. Use `LeftJoin` since LineNbr may be null (container-level PO link without specific line).

**Containers view** — add TransportMode to grid columns (no view change needed, just ASPX).

### ASPX Changes (SB501000.aspx)

| Section | Change |
|---------|--------|
| Container grid (gridContainers) | Add `TransportMode` column |
| Detail form (frmDetail) | Add `TransportMode` dropdown |
| PO Links grid (gridPOLinks) | Add columns: VendorName, InventoryID, ItemDescr, OrderQty, UOM |

### project.xml Changes

| Section | Change |
|---------|--------|
| SB501000 CDATA | Sync with updated ASPX |
| ScreenWithRights | Title → "Procurement Command Center" |

## Not In Scope

- Cost/accounting (Bucket B): shipping rows, duty/tariff, landed costs, invoice linking
- Aggregated container contents tab
- Vendor summary in container header
- Color-coded status in grid
- KPI card clickability/filtering improvements

## Risk Assessment

- **TransportMode**: New DB column, but nullable with no default — zero impact on existing data
- **BQL joins**: Read-only joins to standard Acumatica tables (POOrder, POLine, BAccount, InventoryItem) — no write operations
- **ASPX changes**: Additional grid columns only — no layout restructuring
- **Pipeline validation**: The new ASPX verification from the overwrite investigation will confirm the screen deploys correctly
