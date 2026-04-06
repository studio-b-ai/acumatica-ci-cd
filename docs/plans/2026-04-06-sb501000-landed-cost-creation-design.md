# SB501000 Phase 2 — Landed Cost Document Creation

**Date:** 2026-04-06
**Goal:** "Create Landed Cost" action on SB501000 that generates native Acumatica POLandedCostDoc from container costs, with full GL and AP integration.

## Prerequisite

Phase 1 (Container Costs tab) must be deployed. Acumatica Landed Cost Codes must be configured in PO201500 for each cost type.

## Action: "Create Landed Cost"

Button on SB501000 toolbar. Enabled when a container is selected with costs entered.

### Flow

**Step 1 — Validate preconditions:**
- Container must have at least one `UsrContainerCost` row with Amount > 0
- Container must have at least one `UsrContainerPOLink` with a linked PO
- Linked POs must have at least one **released** PO Receipt (Acumatica requires released receipts for LC allocation)
- If any precondition fails, show a user-friendly error

**Step 2 — Create POLandedCostDoc:**
- `PXGraph.CreateInstance<POLandedCostDocEntry>()` — separate graph, separate unit of work
- Create header: vendor from first cost row (or container's primary vendor), doc date = today
- For each `UsrContainerCost` row, create a `POLandedCostDetail` line:
  - `LandedCostCodeID` — mapped from CostType via Landed Cost Code configuration
  - `CuryLineAmt` — Amount from the cost row
  - Allocation method: by quantity (standard for import costs)
- Link to PO Receipt lines via `UsrContainerPOLink` → POOrder → POReceipt → POReceiptLine
- Persist the LC document

**Step 3 — Store reference:**
- Save `POLandedCostDoc.RefNbr` → `UsrContainer.LandedCostRefNbr`
- Update `UsrContainer.LandedCostStatus` with LC doc status

**Step 4 — Update custom fields:**
- After LC doc creation, update `UsrActualDutyAmt` / `UsrActualFreightAmt` / `UsrBrokerageAmt` on the linked POReceiptLine rows so the existing per-unit calculator reflects allocated amounts

### Cost Type → Landed Cost Code Mapping

| Container CostType | Acumatica LC Code | Notes |
|---------------------|-------------------|-------|
| SHIPPING | FREIGHT | Must exist in PO201500 |
| DUTY | DUTY | Must exist in PO201500 |
| TARIFF | TARIFF | Must exist in PO201500 |
| BROKERAGE | BROKER | Must exist in PO201500 |
| OTHER | OTHER | Must exist in PO201500 |

Mapping stored in `UsrContainerPrefs` (singleton settings DAC) or hardcoded constants. Prefs is more flexible — allows each Heritage Fabrics instance to configure their own LC codes without code changes.

## New Fields

**UsrContainer (2 new fields):**

| Field | Type | Notes |
|-------|------|-------|
| LandedCostRefNbr | string(15) | Reference to created LC doc, read-only |
| LandedCostStatus | string(20) | LC doc status, read-only |

**UsrContainerPrefs (5 new fields for LC code mapping):**

| Field | Type | Notes |
|-------|------|-------|
| LCCodeShipping | string(15) | LC code for SHIPPING costs |
| LCCodeDuty | string(15) | LC code for DUTY costs |
| LCCodeTariff | string(15) | LC code for TARIFF costs |
| LCCodeBrokerage | string(15) | LC code for BROKERAGE costs |
| LCCodeOther | string(15) | LC code for OTHER costs |

## ASPX Changes

- "Create Landed Cost" button added to SB501000 toolbar (PXDSCallbackCommand)
- `LandedCostRefNbr` and `LandedCostStatus` shown in container detail form (read-only, links to LC doc)
- Container Preferences screen (SB302030) updated with LC code mapping fields

## Error Handling

| Condition | Behavior |
|-----------|----------|
| No costs on container | Error: "Add costs before creating a Landed Cost document" |
| No PO links | Error: "Link at least one PO to this container" |
| No released receipts | Error: "All linked PO receipts must be released" |
| LC doc already created | Warning: "Landed Cost {RefNbr} already exists. Create another?" |
| LC code not configured | Error: "Configure Landed Cost Codes in Container Preferences" |
| POLandedCostDocEntry fails | Show Acumatica's error message |

## Risks

- **Graph-to-graph creation**: Creating documents via `POLandedCostDocEntry` from `ContainerMaint` requires careful transaction management. Standard Acumatica pattern but needs thorough testing.
- **LC module availability**: Heritage Fabrics must have the Landed Costs feature enabled in Acumatica (Enable/Disable Features screen CS100000).
- **Receipt line matching**: When a PO has multiple receipts, the action must determine which receipt lines to allocate costs to. Default: allocate to all receipt lines proportionally by quantity.
