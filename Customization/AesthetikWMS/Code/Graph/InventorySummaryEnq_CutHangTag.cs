using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;

namespace HeritageFabrics.IN
{
    /// <summary>
    /// Absorbed from WMSynergy.HF.CutHangTagLabel.
    /// Adds a Print Tag toolbar action to the Inventory Summary screen (IN401000).
    /// Launches report WM302001 (Cut Hang Tag) pre-populated with the selected
    /// inventory item, location, lot/serial number, and quantity on hand.
    /// </summary>
    public class InventorySummaryEnq_CutHangTag : PXGraphExtension<InventorySummaryEnq>
    {
        public static bool IsActive() => true;

        #region Actions

        public PXAction<InventorySummaryEnquiryResult> PrintTag;
        public SelectFrom<InventorySummaryEnquiryResult>.View SummaryResult;

        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Print Tag",
            MapEnableRights = PXCacheRights.Select,
            MapViewRights = PXCacheRights.Select)]
        protected virtual IEnumerable printTag(PXAdapter adapter)
        {
            var row = SummaryResult.Current;
            if (row != null)
            {
                var parameters = new Dictionary<string, string>
                {
                    ["InventoryID"] = row.InventoryID?.ToString(),
                    ["LocationID"]  = row.LocationID?.ToString(),
                    ["LotNbr"]      = row.LotSerialNbr,
                    ["QTY"]         = ((decimal?)row.QtyOnHand)?.ToString("F2") ?? "0.00"
                };
                throw new PXReportRequiredException(parameters, "WM302001", "Print Hang Tag");
            }
            return adapter.Get();
        }

        #endregion
    }
}
