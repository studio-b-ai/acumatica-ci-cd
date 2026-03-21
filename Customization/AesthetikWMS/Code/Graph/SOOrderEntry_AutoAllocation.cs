using System;
using PX.Data;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        // Simplest possible test — write to Description when ANY SOLine event fires
        protected void _(Events.RowInserted<SOLine> e)
        {
            if (e.Row == null) return;
            PXTrace.WriteInformation("[AUTO-ALLOC] RowInserted<SOLine> FIRED");

            // Write a visible marker to the order description
            SOOrder order = Base.Document.Current;
            if (order != null && string.IsNullOrEmpty(order.OrderDesc))
            {
                Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order, "[AUTO-ALLOC ACTIVE]");
            }
        }

        protected void _(Events.FieldUpdated<SOLine, SOLine.orderQty> e)
        {
            if (e.Row == null) return;
            PXTrace.WriteInformation($"[AUTO-ALLOC] FieldUpdated<orderQty> FIRED qty={e.Row.OrderQty}");

            SOOrder order = Base.Document.Current;
            if (order != null)
            {
                string desc = order.OrderDesc ?? "";
                if (!desc.Contains("QTY="))
                {
                    Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order,
                        desc + $" QTY={e.Row.OrderQty}");
                }
            }
        }
    }
}
