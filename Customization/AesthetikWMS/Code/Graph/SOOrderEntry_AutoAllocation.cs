using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace Aesthetik.WMS
{
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        // Track assigned serials within the current order to prevent double-assignment
        private readonly HashSet<string> _assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        protected virtual void SOLine_RowUpdated(PXCache cache, PXRowUpdatedEventArgs e)
        {
            SOLine row = (SOLine)e.Row;
            if (row == null) return;

            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;

            // DEBUG: trace every RowUpdated call
            PXTrace.WriteInformation($"[AUTO-ALLOC] RowUpdated fired. OrderType={orderType}, InvID={row.InventoryID}, Qty={row.OrderQty}, Lot={row.LotSerialNbr}");

            // TEST: temporarily include SO for testing (remove after debug)
            if (orderType != "PC" && orderType != "FO" && orderType != "SO") return;

            // Guard: skip if lot already assigned
            if (!string.IsNullOrEmpty(row.LotSerialNbr))
            {
                PXTrace.WriteInformation("[AUTO-ALLOC] Skipped: lot already assigned");
                return;
            }

            // Need both item and qty to proceed
            if (row.InventoryID == null || (row.OrderQty ?? 0) <= 0)
            {
                PXTrace.WriteInformation($"[AUTO-ALLOC] Skipped: no item or qty <= 0 (InvID={row.InventoryID}, Qty={row.OrderQty})");
                return;
            }

            // Only process PIECENBR items
            bool isPiece = IsPieceGoodsItem(row.InventoryID);
            PXTrace.WriteInformation($"[AUTO-ALLOC] IsPieceGoodsItem={isPiece}");
            if (!isPiece) return;

            decimal minQty = row.OrderQty ?? 0;
            int inventoryID = row.InventoryID.Value;
            int? siteID = row.SiteID ?? order.DefaultSiteID;

            if (siteID == null)
            {
                PXTrace.WriteInformation("[AUTO-ALLOC] Skipped: siteID is null");
                return;
            }

            // Rebuild assigned serials from other lines in this order
            RebuildAssignedSerials(row.LineNbr);

            // Query INLotSerialStatus for available bolts
            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID.Value);

            PXTrace.WriteInformation($"[AUTO-ALLOC] Query returned {allSerials.Count} serial records for InvID={inventoryID}, SiteID={siteID}");

            // Filter and score candidates
            var candidates = new List<BoltCandidate>();

            foreach (PXResult<INLotSerialStatus> result in allSerials)
            {
                var status = (INLotSerialStatus)result;
                if (status.LotSerialNbr == null) continue;
                if (_assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail = status.QtyAvail ?? 0;

                if (qtyOnHand < minQty) continue;
                if (qtyAvail != qtyOnHand) continue;

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyOnHand,
                    ReceiptDate = status.ReceiptDate ?? status.LastModifiedDateTime?.Date,
                });
            }

            PXTrace.WriteInformation($"[AUTO-ALLOC] {candidates.Count} candidates after filtering (minQty={minQty})");

            if (candidates.Count == 0) return;

            // Sort: FIFO first (oldest receipt date), then tightest fit
            var best = candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .First();

            PXTrace.WriteInformation($"[AUTO-ALLOC] Selected bolt {best.LotSerialNbr} (Qty={best.QtyOnHand}, Date={best.ReceiptDate})");

            // TEST 1: Assign lot ONLY — no qty change.
            Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(row, best.LotSerialNbr);
            // Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(e.Row, best.QtyOnHand);

            PXTrace.WriteInformation($"[AUTO-ALLOC] Lot assigned: {best.LotSerialNbr}");
        }

        protected void _(Events.RowDeleted<SOLine> e)
        {
            if (e.Row?.LotSerialNbr != null)
                _assignedSerials.Remove(e.Row.LotSerialNbr);
        }

        private void RebuildAssignedSerials(int? excludeLineNbr)
        {
            _assignedSerials.Clear();
            foreach (SOLine line in Base.Transactions.Select())
            {
                if (line.LineNbr == excludeLineNbr) continue;
                if (!string.IsNullOrEmpty(line.LotSerialNbr))
                    _assignedSerials.Add(line.LotSerialNbr);
            }
        }

        private bool IsPieceGoodsItem(int? inventoryID)
        {
            if (inventoryID == null) return false;

            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, inventoryID);

            if (item == null) return false;

            string lotClass = ((InventoryItem)item).LotSerClassID;
            PXTrace.WriteInformation($"[AUTO-ALLOC] Item LotSerClassID='{lotClass}' (expected '{PieceGoodsClassID}')");

            return string.Equals(lotClass, PieceGoodsClassID, StringComparison.OrdinalIgnoreCase);
        }

        private class BoltCandidate
        {
            public string LotSerialNbr { get; set; }
            public decimal QtyOnHand { get; set; }
            public DateTime? ReceiptDate { get; set; }
        }
    }
}
