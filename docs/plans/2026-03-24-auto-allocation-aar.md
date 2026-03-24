# Auto-Allocation AAR — 2026-03-23

## What We Were Trying To Do
Automatically assign PIECENBR lot serial numbers to PC/FO sales order lines when items are added. Multi-bolt splitting across lines with 120% overship cap and backorder remainder.

## What Happened (Timeline)

| Time | Action | Result |
|------|--------|--------|
| ~4pm | PR #31: RowUpdated + single-bolt, `SetValueExt<lotSerialNbr>` + `SetValueExt<orderQty>` | Extension didn't fire (old code cached in Acumatica) |
| ~5pm | PR #32: Box label auto-print merged | CS1657 compilation error — `SMPrintJobMaint` types don't exist |
| ~6pm | Reverted box label, deployed stub | Compilation fixed |
| ~7pm | Tested item 28065 (PIECENBR, WH 99) | No lot assigned — `qtyOnHand < minQty` filter rejected all bolts (max bolt ~80, order 300) |
| ~8pm | v3: Multi-bolt splitting via `Base.Transactions.Insert()` in RowUpdated | **Aggregate Validation: SOOrder+openLineCntr** |
| ~8:30pm | Two-phase: RowUpdated queues, Persist override inserts | **Aggregate Validation: SOOrder+orderQty** |
| ~9pm | Single-bolt only, `SetValueExt<lotSerialNbr>` + `SetValueExt<orderQty>` | **Aggregate Validation: SOOrder+orderQty** |
| ~9:15pm | SetValue (not SetValueExt) for lot + SetValueExt for qty | **Aggregate Validation: SOOrder+orderQty** |
| ~9:30pm | Exact 3/21 code (`SOOrderEntry_AutoAllocation`) | CS1061: `SOOrder.Description` → fixed to remove it |
| ~9:40pm | 3/21 code with Description fix | **Aggregate Validation: SOOrder+orderQty** |
| ~9:50pm | SetValue for lot only, NO qty change at all | **Still Aggregate Validation** (or extension not firing — trace empty) |
| ~10pm | Disabled extension (`IsActive() => false`) | Orders save clean ✅ |

## Approaches That Failed

### 1. `SetValueExt<SOLine.lotSerialNbr>`
Triggers `INLotSerialNbrAttribute.FieldUpdated` which internally modifies `OrderQty` → corrupts `SOOrder+orderQty` aggregate.

### 2. `SetValueExt<SOLine.orderQty>`
Directly corrupts `SOOrder+orderQty` aggregate when called from RowUpdated.

### 3. `SetValue<SOLine.lotSerialNbr>` (cache-only)
Still corrupts aggregates. Even though `SetValue` bypasses field-level event handlers, the aggregate validation runs during persist and detects the cache was modified outside the normal flow.

### 4. `Base.Transactions.Insert(new SOLine())` from RowUpdated
Corrupts `SOOrder+openLineCntr` aggregate. Inserting lines from row events bypasses the parent aggregate counter maintenance.

### 5. Persist override with line insertion
Same aggregate corruption — the insert happens too late in the pipeline.

## Root Cause Analysis

`SOLine.LotSerialNbr` is **not a simple field**. It's managed by the **LSSOLine** (Lot/Serial) allocation subsystem. Acumatica's LS framework maintains:
- `SOLineSplit` records (the actual allocation details)
- Aggregate counters on `SOOrder` (orderQty, openLineCntr, etc.)
- Cross-references between `SOLine`, `SOLineSplit`, and `INLotSerialStatus`

**Any direct write to `SOLine.LotSerialNbr`** — whether `SetValue` or `SetValueExt` — bypasses the LS subsystem's internal bookkeeping. The aggregate validation at persist time detects the inconsistency.

The WMSynergy.ForceLotSalesOrder ISV package (which we're replacing) likely works through `SOLineSplit` or the `LSSOLine` handler's public API, not by writing `SOLine.LotSerialNbr` directly.

## Correct Approach (Research Needed)

### Option A: SOLineSplit Direct Insert
Insert a `SOLineSplit` record with the lot serial number. The LS framework should roll up to `SOLine.LotSerialNbr` automatically.

```csharp
// Pseudocode — needs validation
var split = new SOLineSplit();
split.LotSerialNbr = "000974252";
split.Qty = 43.70m;
// Insert into the Splits view
Base.splits.Insert(split);
```

### Option B: LSSOLine.CreateSplits()
Use the `LSSOLine` handler's allocation methods if they're publicly accessible.

### Option C: Action Button (not event handler)
Move allocation out of RowUpdated entirely. Use a PXAction that runs after the line is fully committed. The action has full graph control and can properly manipulate splits.

### Option D: RowPersisting with LSSOLine
Use `RowPersisting` on `SOLine` to create splits just before database write, using the LS subsystem's APIs.

## Research Tasks for Tomorrow

1. **Decompile WMSynergy.ForceLotSalesOrder** — see how the ISV assigns lots
2. **Research LSSOLine / LSSelect<SOLine, SOLineSplit>** — find public API for lot assignment
3. **Check Acumatica source for SOLineSplit views** on SOOrderEntry — `Base.splits` or similar
4. **Test SOLineSplit insert** via Playwright — create order, then PUT a split record
5. **Check if Acumatica REST API supports SOLineSplit** — may be accessible as a sub-entity of SalesOrder Details

## CI/CD Issues Fixed Tonight

- Sandbox validation: `continue-on-error` (ISV packages missing in test company)
- `force_qualify`: Added `always()` to deploy job `if` condition
- `deploy.py`: Error log filtering (only error/warning entries, not info spam)
- `ShipmentLabelAutoPrint.cs`: Stub file needed because Acumatica keeps imported code in DB
- Project.xml CDATA: Must update both .cs file AND inline CDATA in project.xml

## Current State

- **Extension: DISABLED** (`IsActive() => false`)
- **Orders: SAVING CLEAN** — no aggregate errors
- **Box label auto-print: TABLED** (stub in place, `IsActive() => false`)
- **Next step:** Research SOLineSplit approach, implement, test via Playwright before any manual testing
