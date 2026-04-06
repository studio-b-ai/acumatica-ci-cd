# SB501000 Bucket B — Cost Tracking, Landed Costs, Invoice Linking

**Date:** 2026-04-06
**Goal:** Add cost tracking, landed cost document creation, and AP invoice linking to the Procurement Command Center.

## Phases

### Phase 1: Container Costs Tab

Self-contained cost tracking per container. No Acumatica module integration needed.

**New DAC: `UsrContainerCost`**

| Field | Type | Notes |
|-------|------|-------|
| CostID | int | Identity PK |
| ContainerID | int | FK → UsrContainer, PXParent |
| CostType | string(20) | Dropdown: SHIPPING, DUTY, TARIFF, BROKERAGE, OTHER |
| Description | string(100) | Free text |
| Amount | decimal | Cost amount |
| VendorID | int? | Optional PXSelector → BAccount/Vendor |
| ReferenceNbr | string(30) | Invoice or tracking number |

**Graph:** New `Costs` view on ContainerMaint, child of Container.

**ASPX:** New "Costs" tab on SB501000 detail panel (after PO Links tab). Editable grid with all fields. Up to 4 shipping rows + duty/tariff rows as user requested.

### Phase 2: Landed Cost Document Creation

Action button that creates Acumatica Landed Cost documents from container costs.

**Action:** "Create Landed Cost" button on SB501000 toolbar.

**Flow:**
1. Collect all `UsrContainerCost` rows for the selected container
2. Find PO Receipts linked via `UsrContainerPOLink` → POOrder → POReceipt (receipts must be released)
3. Create `POLandedCostDoc` via `POLandedCostDocEntry` graph
4. Allocate costs to receipt lines by quantity
5. Store LC document reference back on the container

**New fields on `UsrContainer`:**

| Field | Type | Notes |
|-------|------|-------|
| LandedCostRefNbr | string(15) | Reference to created LC doc, read-only |
| LandedCostStatus | string(20) | LC doc status, read-only |

**Prerequisite check:** PO receipts must be released before LC creation. Action warns if any linked receipts are unreleased.

**Integration with existing code:** `POReceiptLineExt` already has `UsrActualDutyAmt`, `UsrActualFreightAmt`, `UsrBrokerageAmt`, and `UsrLandedCostPerUnit` calculator. Phase 2 feeds these fields from container costs during LC creation.

### Phase 3: Invoice Linking

Link AP invoices to individual cost rows for full audit trail.

**New fields on `UsrContainerCost`:**

| Field | Type | Notes |
|-------|------|-------|
| APDocType | string(3) | AP document type |
| APRefNbr | string(15) | PXSelector → APInvoice |

Staff can link an AP invoice to each cost row. When "Create Landed Cost" runs, it pulls AP references to create the bill association automatically.

## Data Flow

```
Container (UsrContainer)
  ├── PO Links (UsrContainerPOLink) → POOrder → POReceipt → POReceiptLine
  ├── Costs (UsrContainerCost) → optional APInvoice link
  └── Landed Cost (LandedCostRefNbr) → POLandedCostDoc
        └── Allocates costs to POReceiptLines
              └── Updates UsrActualDutyAmt, UsrActualFreightAmt, etc.
```

## Implementation Order

1. Phase 1 first — self-contained, immediate user value
2. Phase 2 after Phase 1 is validated by users
3. Phase 3 after Phase 2 is validated

## Not In Scope

- Currency conversion (costs assumed in base currency)
- Automatic cost estimation or projection
- Integration with external freight rate APIs
- Multi-container cost splitting
