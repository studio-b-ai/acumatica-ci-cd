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

        // Prevents our FieldUpdated<orderQty> from running during lot-serial's
        // own internal SetValueExt<orderQty> calls.
        private bool _allocating = false;

        // Passes bolt from FieldVerifying → FieldUpdated (keyed by LineNbr).
        private readonly Dictionary<int, BoltCandidate> _pendingBolt =
            new Dictionary<int, BoltCandidate>();

        // Prevents double-assignment within the same order.
        private readonly HashSet<string> _assignedSerials =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// FieldVerifying fires BEFORE the cache stores the new value.
        /// We substitute e.NewValue with the bolt qty here — so the cache always
        /// stores the bolt qty as if the user typed it.  RowUpdated fires once with
        /// the bolt qty; SumCalc recalculates SOOrder.orderQty correctly.
        /// No nested event chains, no stale aggregate.
        /// </summary>
        protected void _(Events.FieldVerifying<SOLine, SOLine.orderQty> e)
        {
            if (_allocating) return;
            if (e.Row == null || e.NewValue == null) return;

            // Only on PC / FO orders
            SOOrder order = Base.Document.Current;
            if (order == null) return;
            if (order.OrderType != "PC" && order.OrderType != "FO") return;

            // Skip if lot already assigned on this line
            if (!string.IsNullOrEmpty(e.Row.LotSerialNbr)) return;

            // Parse the incoming qty
            decimal newQty;
            try { newQty = Convert.ToDecimal(e.NewValue); }
            catch { return; }
            if (newQty <= 0) return;

            if (e.Row.InventoryID == null) return;
            if (!IsPieceGoodsItem(e.Row.InventoryID)) return;

            int? siteID = e.Row.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            RebuildAssignedSerials(e.Row.LineNbr);

            var bolt = FindBestBolt(e.Row.InventoryID.Value, siteID.Value, newQty);
            if (bolt == null) return;

            // Store bolt for FieldUpdated (lot-serial assignment)
            _pendingBolt[e.Row.LineNbr ?? -1] = bolt;

            // Substitute: cache stores bolt qty, not the user's typed value.
            // RowUpdated then fires once with the correct qty → SumCalc is clean.
            e.NewValue = bolt.QtyOnHand;
        }

        /// <summary>
        /// FieldUpdated fires after the cache has stored the (already-substituted)
        /// bolt qty.  We assign the lot serial via SetValueExt here so the full
        /// Acumatica lot-serial event chain runs (split creation etc.) with the
        /// correct qty already committed.
        /// _allocating blocks re-entry if INLotSerialNbrAttribute internally calls
        /// SetValueExt<orderQty> during split creation.
        /// </summary>
        protected void _(Events.FieldUpdated<SOLine, SOLine.orderQty> e)
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
        /// Cleans up both tracking structures when a line is removed.
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
                if (qtyAvail != qtyOnHand) continue;   // must be fully unreserved

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
