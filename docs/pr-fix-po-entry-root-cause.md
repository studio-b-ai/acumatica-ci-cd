# Fix: Cannot enter PO — Root Cause (re-entrancy + BQL + Relations + LoadOnDemand)

## Summary
Fixes the root cause of the PO entry failure in Acumatica.

## Changes

### Fix A: Re-entrancy Guard (POOrderEntry_Extension.cs)
- Added `_isProcessing` flag to prevent cascading event handler execution
- All RowSelected/FieldUpdated/etc. handlers now check guard before executing

### Fix B: RelationsExt Scoping (RelationsExt.cs)
- Scoped or guarded CRRelation-based views to prevent incompatible CRM DAC usage on POOrderEntry graph
- Known Acumatica limitation: CRM DACs are incompatible with non-CRM graphs

### Fix C: BQL Scoping (POOrderEntry_Extension.cs)
- Added null checks before all `Current<>` references
- Added `Where<>` clauses to unscoped BQL queries

### Fix D: ASPX LoadOnDemand (PO301000.aspx)
- Added `LoadOnDemand="True"` to custom/Relations tabs
- Prevents eager-loading of views that trigger problematic queries on page load

## Related Tickets
- Research & Branch Setup: #44390572375
- C# Root Cause Fixes (A & C): #44383633429
- View Performance Fixes (B & D): #44389635000
- PR & Review Gate: #44388393277

## Testing
1. Deploy to Acumatica via CI/CD (AFTER HOURS ONLY — 6pm-6am CT)
2. Navigate to PO301000 (Purchase Orders)
3. Click "+" to create a new PO
4. Verify the form loads without errors
5. Enter a PO with line items and save
6. Verify Relations tab loads on-demand without errors
7. Check Acumatica System Monitor for any trace errors

## ⚠️ Deployment Notes
- **AFTER-HOURS ONLY** — Publishing restarts the Acumatica app pool
- Co-publish with all active packages: AesthetikWMS, AesthetikContainers, StudioBAcuOps
- Use `workflow_dispatch` on the deploy workflow with scheduled timing
