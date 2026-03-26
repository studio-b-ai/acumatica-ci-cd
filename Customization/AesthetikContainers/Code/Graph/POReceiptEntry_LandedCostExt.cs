using PX.Data;
using PX.Objects.IN;
using PX.Objects.PO;

namespace StudioB.Containers
{
    /// <summary>
    /// Graph extension for POReceiptEntry (PO302000).
    /// Auto-populates landed cost fields from StockItem defaults when receipt lines are added.
    /// Computes UsrLandedCostPerUnit on RowSelected.
    /// </summary>
    public class POReceiptEntry_LandedCostExt : PXGraphExtension<POReceiptEntry>
    {
        #region Event Handlers

        /// <summary>
        /// When a receipt line is inserted, copy tariff info from the StockItem
        /// and auto-calculate duty based on the default duty rate.
        /// </summary>
        protected virtual void _(Events.RowInserted<POReceiptLine> e)
        {
            if (e.Row == null) return;

            var lineExt = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(e.Row);
            if (lineExt == null) return;

            // Look up StockItem for tariff defaults
            var item = PXSelect<InventoryItem,
                Where<InventoryItem.inventoryID, Equal<Required<InventoryItem.inventoryID>>>>
                .Select(Base, e.Row.InventoryID);

            if (item == null) return;

            var itemExt = PXCache<InventoryItem>.GetExtension<StockItemExt>((InventoryItem)item);
            if (itemExt == null) return;

            // Copy tariff data from item (snapshot at receipt time)
            lineExt.UsrHTSCode = itemExt.UsrHTSCode;
            lineExt.UsrCountryOfOrigin = itemExt.UsrCountryOfOrigin;

            // Auto-calculate duty: line extended cost * duty rate
            if (itemExt.UsrDutyRate.GetValueOrDefault() > 0 && e.Row.ExtCost.GetValueOrDefault() > 0)
            {
                lineExt.UsrActualDutyAmt = e.Row.ExtCost.Value * (itemExt.UsrDutyRate.Value / 100m);
            }

            e.Cache.Update(e.Row);
        }

        /// <summary>
        /// When extended cost changes (qty or unit cost updated), recalculate duty.
        /// </summary>
        protected virtual void _(Events.FieldUpdated<POReceiptLine, POReceiptLine.extCost> e)
        {
            if (e.Row == null) return;

            var lineExt = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(e.Row);
            if (lineExt == null) return;

            // Look up duty rate from item
            var item = PXSelect<InventoryItem,
                Where<InventoryItem.inventoryID, Equal<Required<InventoryItem.inventoryID>>>>
                .Select(Base, e.Row.InventoryID);

            if (item == null) return;

            var itemExt = PXCache<InventoryItem>.GetExtension<StockItemExt>((InventoryItem)item);
            if (itemExt == null || itemExt.UsrDutyRate.GetValueOrDefault() == 0) return;

            // Recalculate duty only if it matches the auto-calculated value (not manually overridden)
            var oldExtCost = (decimal?)e.OldValue ?? 0m;
            var oldAutoCalcDuty = oldExtCost * (itemExt.UsrDutyRate.Value / 100m);

            // If current duty matches what auto-calc would have been, update it
            if (lineExt.UsrActualDutyAmt == null ||
                System.Math.Abs(lineExt.UsrActualDutyAmt.Value - System.Math.Round(oldAutoCalcDuty, 2)) < 0.01m)
            {
                lineExt.UsrActualDutyAmt = e.Row.ExtCost.GetValueOrDefault() * (itemExt.UsrDutyRate.Value / 100m);
                lineExt.UsrActualDutyAmt = System.Math.Round(lineExt.UsrActualDutyAmt.Value, 2);
            }
        }

        /// <summary>
        /// Compute UsrLandedCostPerUnit on every RowSelected.
        /// Landed cost per unit = (unit cost + (duty + freight + brokerage) / qty)
        /// </summary>
        protected virtual void _(Events.RowSelected<POReceiptLine> e)
        {
            if (e.Row == null) return;

            var lineExt = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(e.Row);
            if (lineExt == null) return;

            decimal qty = e.Row.ReceiptQty.GetValueOrDefault();
            if (qty == 0) qty = 1; // Avoid divide by zero

            decimal unitCost = e.Row.UnitCost.GetValueOrDefault();
            decimal totalLandedCosts =
                lineExt.UsrActualDutyAmt.GetValueOrDefault() +
                lineExt.UsrActualFreightAmt.GetValueOrDefault() +
                lineExt.UsrBrokerageAmt.GetValueOrDefault();

            decimal landedPerUnit = unitCost + (totalLandedCosts / qty);

            e.Cache.SetValue<POReceiptLineExt.usrLandedCostPerUnit>(e.Row,
                System.Math.Round(landedPerUnit, 4));
        }

        #endregion
    }
}
