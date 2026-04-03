using System;
using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace HeritageFabrics.PO
{
    public class POReceiptEntry_Extension : PXGraphExtension<POReceiptEntry>
    {
        public static bool IsActive() => true;

        public PXAction<POReceipt> PrintPurchaseReceiptLabels;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Print Purchase Receipt Labels", MapEnableRights = PXCacheRights.Select)]
        protected virtual IEnumerable printPurchaseReceiptLabels(PXAdapter adapter)
        {
            PXReportRequiredException ex = null;
            var row = Base.Caches[typeof(POReceipt)].Current as POReceipt;
            if (row != null)
            {
                var parameters = new Dictionary<string, string>();
                parameters["ReceiptType"] = row.ReceiptType?.ToString();
                parameters["ReceiptNbr"] = row.ReceiptNbr?.ToString();
                ex = new PXReportRequiredException(parameters, "PO646901");
            }
            if (ex != null) throw ex;
            return adapter.Get();
        }
    }
}
