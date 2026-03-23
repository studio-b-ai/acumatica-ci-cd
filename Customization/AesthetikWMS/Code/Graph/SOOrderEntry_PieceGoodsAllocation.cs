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
    /// <summary>
    /// Auto-allocates lot/serial (bolt) to PIECENBR items on PC and FO sales orders.
    /// Fires on RowUpdated — when a line is added or its fields change, finds the best
    /// available bolt via FIFO + tightest-fit and assigns it.
    ///
    /// Uses RowUpdated (not RowInserted) because RowInserted fires before InventoryID
    /// and OrderQty are populated on the line, causing guard clauses to bail out.
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        /// <summary>Re-entry guard to prevent recursive allocation.</summary>
        [ThreadStatic]
        private static bool _allocating;

        // Track assigned serials within the current order to prevent double-assignment
        private readonly HashSet<string> _assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        protected void _(Events.RowUpdated<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null) return;

            // Only for PC and FO order types
            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Guard: skip if lot already assigned (prevents re-trigger from qty update)
            if (!string.IsNullOrEmpty(e.Row.LotSerialNbr)) return;

            // Need both item and qty to proceed
            if (e.Row.InventoryID == null || (e.Row.OrderQty ?? 0) <= 0) return;

            // Only process PIECENBR items (Piece Number - Lot Tracked)
            if (!IsPieceGoodsItem(e.Row.InventoryID)) return;

            decimal minQty = e.Row.OrderQty ?? 0;
            int inventoryID = e.Row.InventoryID.Value;
            int? siteID = e.Row.SiteID ?? order.DefaultSiteID;

            if (siteID == null) return;

            try
            {
                _allocating = true;

                // Rebuild assigned serials from other lines in this order
                RebuildAssignedSerials(e.Row.LineNbr);

                // Query INLotSerialStatus for available bolts
                var allSerials = SelectFrom<INLotSerialStatus>
                    .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                        .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                    .View.ReadOnly.Select(Base, inventoryID, siteID.Value);

                // Filter and score candidates
                var candidates = new List<BoltCandidate>();

                foreach (PXResult<INLotSerialStatus> row in allSerials)
                {
                    var status = (INLotSerialStatus)row;
                    if (status.LotSerialNbr == null) continue;

                    // Skip already assigned to another line in this order
                    if (_assignedSerials.Contains(status.LotSerialNbr)) continue;

                    decimal qtyOnHand = status.QtyOnHand ?? 0;
                    decimal qtyAvail = status.QtyAvail ?? 0;

                    // Must have enough quantity to meet minimum
                    if (qtyOnHand < minQty) continue;

                    // Must be fully unreserved (entire bolt available)
                    if (qtyAvail != qtyOnHand) continue;

                    candidates.Add(new BoltCandidate
                    {
                        LotSerialNbr = status.LotSerialNbr,
                        QtyOnHand = qtyOnHand,
                        ReceiptDate = status.ReceiptDate ?? status.LastModifiedDateTime?.Date,
                    });
                }

                if (candidates.Count == 0) return; // No bolt meets minimum — leave unallocated

                // Sort: FIFO first (oldest receipt date), then tightest fit (smallest qty >= minimum)
                var best = candidates
                    .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                    .ThenBy(c => c.QtyOnHand)
                    .First();

                // Assign lot and update quantity to full bolt
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

        /// <summary>
        /// Rebuilds the set of serials already assigned to other lines in this order.
        /// Excludes the current line being processed.
        /// </summary>
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

        /// <summary>Checks if an item uses the PIECENBR lot/serial class.</summary>
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
