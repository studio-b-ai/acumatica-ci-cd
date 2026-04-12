# PCC Usability Fixes Design

**Date:** 2026-04-12
**Screen:** SB501000 (Procurement Command Center)
**Source:** End-user testing feedback from Melanie (Imports Manager)
**Feedback doc:** `PO Command Center.docx`

## Problem

Mel cannot perform basic container management in PCC:
- Cannot create new containers (no Add Row button)
- Cannot edit or save detail fields / child tabs (Inquire skin blocks writes)
- No file attachment indicator for Import Forwarder CSV workflow
- Print Receiving Doc does nothing (stub)
- Toolbar has buttons she doesn't need (Plan Next Order)

## Scope

| # | Change | Type |
|---|--------|------|
| 1 | Enable container creation with auto-numbering | New capability |
| 2 | Fix detail panel / tabs not saving | Bug fix |
| 3 | Add file attachment indicator (paperclip) | Bug fix |
| 4 | Receive Goods — create PO Receipt from container | Replace stub |
| 5 | Auto-create Landed Cost after receipt release | New capability |
| 6 | Remove Plan Next Order button | Cleanup |

## Out of Scope (separate design sessions)

- **Ready Goods List** — email parsing of `imports@heritagefabrics.com`, carrier API integration (Maersk DCSA, CH Robinson), Ready Goods inbox view in PCC. Cross-repo: webhook-router + acumatica-ci-cd.
- **Container buying / scrap metal export partnership** — long-term logistics strategy.
- **PDF receiving slip** — future polish for Print Receiving Doc.

## Deliverables

- Updated ASPX + DLL for SB501000
- Numbering sequence for ContainerCD
- User guide for Melanie (post-development)

---

## 1. Enable Container Creation

### ASPX Changes
- `gridContainers`: `SkinID="Inquire"` -> `SkinID="DetailsInTab"`, add `AllowInsert="True"`
- Surfaces the **+** (Add Row) button on the grid toolbar

### Auto-Numbering
- Add `AutoNumberAttribute` to `UsrContainer.ContainerCD` DAC field
- Pattern: `CNT{0:D6}` (e.g., CNT000034)
- User can clear the auto-generated value and type their own (standard Acumatica override behavior)
- Create `Numbering` sequence record via `AesthetikContainersInstall` plugin

### Graph Changes
- Add `RowInserting` handler on `UsrContainer` to set defaults:
  - `Status` = "Booked"
  - `TransportMode` = "Ocean"
- Ensure `Container` detail view syncs to newly inserted row

### Both Creation Pathways
- **Add Row (+):** Manual container creation for edge cases (forwarder-booked containers, LCL consolidations)
- **Create from Ready Goods:** Future — Ready Goods List view lets Mel select ready PO lines and click "Create Container from Selected" (out of scope, separate design)

---

## 2. Fix Detail Panel / Tabs Not Saving

### Root Cause
`SkinID="Inquire"` on the parent grid makes child caches read-only. All tab grids (PO Links, Costs, Documents, ETA History, Lead Time) already use `SkinID="Details"` but are blocked by the parent Inquire mode.

### Fix
Changing the grid skin in item #1 fixes this automatically. No additional tab changes needed.

### Validation
After skin change, verify:
- Costs tab: inline editing and save
- Documents tab: add/edit document records
- PO Links tab: Add PO Line / Remove PO Line actions work
- ETA History tab: Snapshot Current ETA works
- Detail form fields: edit and save container header fields

---

## 3. Add File Attachment Indicator

### Fix
On `gridContainers`: `FilesIndicator="False"` -> `FilesIndicator="True"`

### Workflow
1. Mel clicks paperclip on a container row -> attaches forwarder CSV
2. Clicks **Import Forwarder CSV** -> processes the attached file

---

## 4. Receive Goods (Create PO Receipt)

### Rename
"Print Receiving Doc" -> "Receive Goods"

Update: `CallbackCommand` name, `PXButton` DisplayName, ASPX toolbar label.

### Behavior
1. Mel selects a container and clicks **Receive Goods**
2. **Validation:**
   - Container must have linked PO lines (PO Links tab)
   - Container status must be Arrived, Customs Hold, or Gated Out
3. **Creates PO Receipt** via `POReceiptEntry` graph:
   - Receipt Type: Receipt
   - Status: **On Hold** (finance releases after 3-way match with vendor invoice)
   - For each linked PO line: adds a receipt line with matching inventory/qty/UOM
   - If multiple vendors: creates **one receipt per vendor**
4. **Updates container:**
   - Stores `ReceiptNbr` (or comma-separated if multiple)
   - Status -> "Delivered"
   - Writes `GOODS_RECEIVED` event to Events tab
5. **Confirmation dialog:** shows receipt number(s) with link to PO302000

### What This Does NOT Do
- Does not release the receipt (finance controls 3-way match)
- Does not create AP Bills (those come from vendor invoices)
- Does not print a PDF (future polish)

---

## 5. Auto-Create Landed Cost After Receipt Release

### Why Not Immediate
The Acumatica LC document (`PO303000`) requires **released** receipt lines to allocate costs against. When Receive Goods creates the receipt On Hold, costs can't be allocated yet. Finance must release the receipt first.

### Approach (Option A -- event-driven)
When the PO Receipt is released by finance, PCC auto-detects and creates the Landed Cost document. Mel never clicks a separate button.

### Implementation
- Add `RowUpdated` event handler on `POReceipt` (via graph extension on `POReceiptEntry`) that fires when `Released` flips to `true`
- Check if the receipt's PO lines are linked to a container (via `UsrContainerPOLink`)
- If yes, and the container has costs in the Costs tab:
  - Create LC document via `POLandedCostDocEntry`
  - Add receipt lines to LC Details tab
  - Add cost lines from container's Costs tab, mapped to LC codes via `UsrContainerPrefs`
  - LC document created On Hold (finance releases to generate AP Bill + IN Adjustment)
- Store `LandedCostRefNbr` and `LandedCostStatus` on the container record

### LC Release Flow (native Acumatica)
When finance releases the LC document:
- **AP Bill** auto-generated for the landed cost vendor
- **IN Adjustment** auto-generated to update inventory cost per item
- GL entries post for cost allocation

### Toolbar
- **Remove** "Create Landed Cost" button from toolbar (automated now)
- Keep the graph action method for edge cases / manual override via generic inquiry

---

## 6. Remove Plan Next Order

### ASPX Changes
- Remove `PlanNextOrder` CallbackCommand from PXDataSource
- Remove toolbar listitem for Plan Next Order

### Graph
- Action method stays in DLL (no recompile needed for removal, no harm if unreferenced)

---

## Accounting Flow Summary

```
Mel clicks "Receive Goods"
    |
    v
PO Receipt created (On Hold)
    |
    v
Finance reviews, matches to vendor invoice (3-way match)
    |
    v
Finance releases PO Receipt
    |                              |
    v                              v
Inventory GL updated        LC Document auto-created (On Hold)
                                   |
                                   v
                            Finance releases LC Document
                                   |
                            +------+------+
                            v             v
                        AP Bill      IN Adjustment
                       generated     (cost allocation)
```

---

## Final Toolbar State

**Keep:**
- Refresh Tracking
- Mark Customs Cleared
- Mark Delivered
- Receive Goods (renamed)
- Import Forwarder CSV

**Remove:**
- Create Landed Cost (automated)
- Plan Next Order

**Hidden (tab-level only):**
- Add PO Line / Remove PO Line (PO Links tab)
- Attach Document (Documents tab)
- Snapshot Current ETA (ETA History tab)
