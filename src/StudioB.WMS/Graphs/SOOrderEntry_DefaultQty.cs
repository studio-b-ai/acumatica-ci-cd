using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Absorbed from WMSynergy.DefaultQty.
    /// When a lot/serial number is assigned on an SO line split, defaults the split
    /// quantity to the available yardage on that lot at the selected warehouse.
    /// </summary>
    public class SOOrderEntry_DefaultQty : PXGraphExtension<PX.Objects.SO.SOOrderEntry>
    {
        public static bool IsActive() => true;

        #region Event Handlers

        protected virtual void _(Events.FieldUpdated<SOLineSplit, SOLineSplit.locationID> e)
        {
            if (e.Row == null) return;
            var row = e.Row;

            if (row.InventoryID == null || row.SiteID == null || row.LotSerialNbr == null)
                return;

            var lotStats = PXSelectReadonly<INSiteLotSerial,
                Where<INSiteLotSerial.inventoryID, Equal<Required<INSiteLotSerial.inventoryID>>,
                    And<INSiteLotSerial.siteID, Equal<Required<INSiteLotSerial.siteID>>,
                    And<INSiteLotSerial.lotSerialNbr, Equal<Required<INSiteLotSerial.lotSerialNbr>>>>>>
                .Select(Base, row.InventoryID, row.SiteID, row.LotSerialNbr);

            decimal availableQty = 0m;
            foreach (INSiteLotSerial stat in lotStats)
                availableQty += stat.QtyAvail.GetValueOrDefault();

            if (availableQty > 0)
                e.Cache.SetValueExt<SOLineSplit.qty>(row, availableQty);
        }

        #endregion
    }
}
