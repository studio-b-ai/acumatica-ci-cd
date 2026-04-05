using PX.Data;
using PX.Objects.IN;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class POReceiptEntry_LandedCostExt : PXGraphExtension<POReceiptEntry>
    {
        public static bool IsActive() => true;

        protected virtual void _(Events.RowInserted<POReceiptLine> e)
        {
            if (e.Row == null) return;
            var lineExt = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(e.Row);
            if (lineExt == null) return;
            var item = PXSelect<InventoryItem,
                Where<InventoryItem.inventoryID, Equal<Required<InventoryItem.inventoryID>>>>
                .Select(Base, e.Row.InventoryID);
            if (item == null) return;
            var itemExt = PXCache<InventoryItem>.GetExtension<StockItemExt>((InventoryItem)item);
            if (itemExt == null) return;
            e.Cache.Update(e.Row);
        }

        protected virtual void _(Events.RowSelected<POReceiptLine> e)
        {
            if (e.Row == null) return;
            var lineExt = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(e.Row);
            if (lineExt == null) return;
            decimal qty = e.Row.ReceiptQty.GetValueOrDefault();
            if (qty == 0) qty = 1;
            decimal unitCost = e.Row.UnitCost.GetValueOrDefault();
            decimal totalLandedCosts =
                lineExt.UsrActualDutyAmt.GetValueOrDefault() +
                lineExt.UsrActualFreightAmt.GetValueOrDefault() +
                lineExt.UsrBrokerageAmt.GetValueOrDefault();
            decimal landedPerUnit = unitCost + (totalLandedCosts / qty);
            e.Cache.SetValue<POReceiptLineExt.usrLandedCostPerUnit>(e.Row,
                System.Math.Round(landedPerUnit, 4));
        }
    }
}
