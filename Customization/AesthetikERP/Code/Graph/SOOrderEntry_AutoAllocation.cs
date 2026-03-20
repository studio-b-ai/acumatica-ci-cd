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

        // Guard: prevents lot-serial SetValueExt loop in RowUpdated
        private bool _allocating = false;

        // Passes bolt data from RowUpdating → RowUpdated (keyed by LineNbr)
        private readonly Dictionary<int, BoltCandidate> _pendingBolt =
            new Dictionary<int, BoltCandidate>();

        // Track assigned serials within the current order to prevent double-assignment
        private readonly HashSet<string> _assignedSerials =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// RowUpdating fires BEFORE the row is committed to cache.
        ///
        /// We set e.NewRow.OrderQty as a direct property assignment (not SetValueExt).
        /// This means the cache commits the bolt qty as the authoritative value.
        /// RowUpdated then fires ONCE with the correct final qty, so SumCalc
        /// recalculates SOOrder.orderQty cleanly — no nested FieldUpdated events,
        /// no stale aggregate.
        ///
        /// LotSerialNbr is NOT set here because direct property set bypasses the
        /// lot-serial event chain (split creation etc.). We store the bolt in
        /// _pendingBolt and assign it via SetValueExt in RowUpdated instead.
        /// </summary>
        protected void _(Events.RowUpdating<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null || e.NewRow == null) return;

            // Only for PC and FO order types
            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Skip if lot already assigned on the incoming row
            if (!string.IsNullOrEmpty(e.NewRow.LotSerialNbr)) return;

            // Need an item and a positive qty
            if (e.NewRow.InventoryID == null) return;
            decimal newQty = e.NewRow.OrderQty ?? 0;
            if (newQty <= 0) return;

            // Only process PIECENBR items
            if (!IsPieceGoodsItem(e.NewRow.InventoryID)) return;

            int? siteID = e.NewRow.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            // Rebuild assigned serials from other lines
            RebuildAssignedSerials(e.NewRow.LineNbr);

            // Find the tightest-fit, FIFO-ordered, fully-unreserved bolt
            var bolt = FindBestBolt(e.NewRow.InventoryID.Value, siteID.Value, newQty);
            if (bolt == null) return;

            // Store for RowUpdated — lot serial is assigned there via SetValueExt
            _pendingBolt[e.NewRow.LineNbr ?? -1] = bolt;

            // Direct property assignment: cache commits this value, RowUpdated fires
            // once with the correct bolt qty, SumCalc updates SOOrder.orderQty cleanly.
            e.NewRow.OrderQty = bolt.QtyOnHand;
        }

        /// <summary>
        /// RowUpdated fires AFTER the row (with bolt qty) is committed to cache.
        /// SOOrder.orderQty has already been recalculated by SumCalc at this point.
        /// Now assign the lot serial via SetValueExt so the full lot-serial event
        /// chain runs (split creation etc.) with the correct qty already in place.
        /// </summary>
        protected void _(Events.RowUpdated<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null) return;

            int key = e.Row.LineNbr ?? -1;
            if (!_pendingBolt.TryGetValue(key, out var bolt)) return;
            _pendingBolt.Remove(key);

            _allocating = true;
            try
            {
                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(e.Row, bolt.LotSerialNbr);
            }
            finally
            {
                _allocating = false;
            }
        }

        /// <summary>
        /// When a line is deleted, clean up both tracking structures.
        /// </summary>
        protected void _(Events.RowDeleted<SOLine> e)
        {
            if (e.Row?.LotSerialNbr != null)
                _assignedSerials.Remove(e.Row.LotSerialNbr);

            if (e.Row?.LineNbr != null)
                _pendingBolt.Remove(e.Row.LineNbr.Value);
        }

        private BoltCandidate FindBestBolt(int inventoryID, int siteID, decimal minQty)
        {
            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID);

            var candidates = new List<BoltCandidate>();

            foreach (PXResult<INLotSerialStatus> row in allSerials)
            {
                var status = (INLotSerialStatus)row;
                if (status.LotSerialNbr == null) continue;
                if (_assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail  = status.QtyAvail  ?? 0;

                if (qtyOnHand < minQty) continue;
                if (qtyAvail != qtyOnHand) continue; // must be fully unreserved

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand    = qtyOnHand,
                    ReceiptDate  = status.ReceiptDate ?? status.LastModifiedDateTime?.Date,
                });
            }

            if (candidates.Count == 0) return null;

            return candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .First();
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
            public string    LotSerialNbr { get; set; }
            public decimal   QtyOnHand    { get; set; }
            public DateTime? ReceiptDate  { get; set; }
        }
    }
}
