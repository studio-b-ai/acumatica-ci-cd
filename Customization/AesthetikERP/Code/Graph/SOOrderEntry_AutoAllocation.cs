using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        // Prevents recursion when we call SetValueExt<orderQty> ourselves
        private bool _allocating = false;

        // Track assigned serials within the current order to prevent double-assignment
        private readonly HashSet<string> _assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// Override Persist() to recalculate SOOrder.OrderQty from actual line values
        /// before Acumatica's aggregate validator runs. This is necessary because
        /// programmatic qty changes (auto-matching bolt qty to line) can leave the
        /// in-memory SOOrder aggregate stale, causing "Aggregate Validation: SOOrder+orderQty".
        /// </summary>
        [PXOverride]
        public void Persist(Action base_Persist)
        {
            SOOrder order = Base.Document.Current;
            if (order != null && Base.Document.Cache.GetStatus(order) != PXEntryStatus.Notchanged)
            {
                decimal total = 0m;
                foreach (SOLine line in Base.Transactions.Select())
                    total += line.OrderQty ?? 0m;

                if (order.OrderQty != total)
                    Base.Document.Cache.SetValue<SOOrder.orderQty>(order, total);
            }

            base_Persist();
        }

        /// <summary>
        /// Trigger on qty entry: find tightest-fit bolt (FIFO), assign lot serial,
        /// and update qty to the full bolt quantity.
        /// </summary>
        protected void _(Events.FieldUpdated<SOLine, SOLine.orderQty> e)
        {
            if (_allocating) return;
            if (e.Row == null || e.NewValue == null) return;

            // Only for PC and FO order types
            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Guard: skip if lot already assigned
            if (!string.IsNullOrEmpty(e.Row.LotSerialNbr)) return;

            // Need both item and a positive qty
            if (e.Row.InventoryID == null || (e.Row.OrderQty ?? 0) <= 0) return;

            // Only process PIECENBR items (Piece Number - Lot Tracked)
            if (!IsPieceGoodsItem(e.Row.InventoryID)) return;

            decimal minQty = e.Row.OrderQty ?? 0;
            int inventoryID = e.Row.InventoryID.Value;
            int? siteID = e.Row.SiteID ?? order.DefaultSiteID;

            if (siteID == null) return;

            // Rebuild assigned serials from other lines in this order
            RebuildAssignedSerials(e.Row.LineNbr);

            // Query INLotSerialStatus for available bolts
            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID.Value);

            var candidates = new List<BoltCandidate>();

            foreach (PXResult<INLotSerialStatus> row in allSerials)
            {
                var status = (INLotSerialStatus)row;
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

            if (candidates.Count == 0) return;

            var best = candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .First();

            try
            {
                _allocating = true;
                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(e.Row, best.LotSerialNbr);
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(e.Row, best.QtyOnHand);
            }
            finally
            {
                _allocating = false;
            }
        }

        /// <summary>
        /// When a line is deleted, remove its serial from the tracking set.
        /// </summary>
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

            return string.Equals(
                ((InventoryItem)item).LotSerClassID,
                PieceGoodsClassID,
                StringComparison.OrdinalIgnoreCase);
        }

        private class BoltCandidate
        {
            public string LotSerialNbr { get; set; }
            public decimal QtyOnHand { get; set; }
            public DateTime? ReceiptDate { get; set; }
        }
    }
}
