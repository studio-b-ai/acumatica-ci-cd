using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Absorbed from WMSynergy.ForceLotSalesOrder.
    /// Warns at persist time if an SO line lacks a lot/serial assignment
    /// when the item has more than 25 units available at the warehouse.
    /// This prevents open orders from shipping without lot traceability
    /// on items that are in stock and ready to allocate.
    /// </summary>
    public class SOOrderEntry_ForceLot : PXGraphExtension<PX.Objects.SO.SOOrderEntry>
    {
        public static bool IsActive() => true;

        #region Event Handlers

        protected virtual void _(Events.RowPersisting<SOLine> e)
        {
            if (e.Row == null) return;
            if (e.Operation != PXDBOperation.Insert && e.Operation != PXDBOperation.Update) return;

            var line = e.Row;

            INLotSerClass lotSerClass = PXSelectJoin<INLotSerClass,
                InnerJoin<InventoryItem,
                    On<InventoryItem.lotSerClassID, Equal<INLotSerClass.lotSerClassID>>>,
                Where<InventoryItem.inventoryID, Equal<Required<InventoryItem.inventoryID>>>>
                .Select(Base, line.InventoryID);

            if (lotSerClass == null) return;

            INSiteStatus itemStatus = PXSelect<INSiteStatus,
                Where<INSiteStatus.inventoryID, Equal<Required<INSiteStatus.inventoryID>>,
                    And<INSiteStatus.siteID, Equal<Required<INSiteStatus.siteID>>>>>
                .Select(Base, line.InventoryID, line.SiteID);

            if (itemStatus?.QtyAvail > 25)
            {
                bool hasLotSerial = PXSelect<SOLineSplit,
                    Where<SOLineSplit.orderType, Equal<Required<SOLineSplit.orderType>>,
                        And<SOLineSplit.orderNbr, Equal<Required<SOLineSplit.orderNbr>>,
                        And<SOLineSplit.lineNbr, Equal<Required<SOLineSplit.lineNbr>>,
                        And<SOLineSplit.lotSerialNbr, IsNotNull,
                        And<SOLineSplit.lotSerialNbr, NotEqual<Required<SOLineSplit.lotSerialNbr>>>>>>>>
                    .Select(Base, line.OrderType, line.OrderNbr, line.LineNbr, string.Empty).Count > 0;

                if (!hasLotSerial)
                {
                    PXUIFieldAttribute.SetWarning<SOLine.inventoryID>(e.Cache, line,
                        "Lot/Serial number must be selected if Qty Available > 25.");
                }
            }
        }

        #endregion
    }
}
