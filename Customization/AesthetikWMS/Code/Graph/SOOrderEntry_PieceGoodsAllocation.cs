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
    /// Single-bolt auto-allocation for PIECENBR items on PC/FO orders.
    ///
    /// Assigns the best available bolt to a line when it's added or changed.
    /// Uses SetValue (NOT SetValueExt) for lotSerialNbr to bypass
    /// INLotSerialNbrAttribute which corrupts aggregate counters.
    ///
    /// DOES NOT insert additional lines — multi-bolt splitting is handled
    /// externally via a second REST API PUT call with lots pre-assigned.
    /// Inserting lines from RowUpdated/RowInserted corrupts SOOrder aggregates.
    ///
    /// Selection: FIFO (oldest receipt date), tightest fit (smallest bolt).
    /// Fully unreserved bolts only (QtyAvail == QtyOnHand).
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        private readonly HashSet<string> _assignedSerials =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        protected void _(Events.RowInserted<SOLine> e)
        {
            TryAllocate(e.Row);
        }

        protected void _(Events.RowUpdated<SOLine> e)
        {
            TryAllocate(e.Row);
        }

        private void TryAllocate(SOLine line)
        {
            if (line == null) return;

            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Skip if lot already assigned
            if (!string.IsNullOrEmpty(line.LotSerialNbr)) return;

            // Need item and qty
            if (line.InventoryID == null || (line.OrderQty ?? 0) <= 0) return;

            // Only PIECENBR items
            if (!IsPieceGoodsItem(line.InventoryID)) return;

            int inventoryID = line.InventoryID.Value;
            int? siteID = line.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            // Rebuild assigned serials from other lines
            _assignedSerials.Clear();
            foreach (SOLine existing in Base.Transactions.Select())
            {
                if (existing.LineNbr == line.LineNbr) continue;
                if (!string.IsNullOrEmpty(existing.LotSerialNbr))
                    _assignedSerials.Add(existing.LotSerialNbr);
            }

            // Query available bolts
            var candidates = new List<BoltCandidate>();

            foreach (PXResult<INLotSerialStatus> row in SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID.Value))
            {
                var status = (INLotSerialStatus)row;
                if (status.LotSerialNbr == null) continue;
                if (_assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail = status.QtyAvail ?? 0;
                if (qtyOnHand <= 0) continue;
                if (qtyAvail != qtyOnHand) continue;

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyOnHand,
                    ReceiptDate = status.ReceiptDate,
                });
            }

            if (candidates.Count == 0) return;

            // FIFO + tightest fit
            var best = candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .First();

            PXTrace.WriteInformation(
                $"[AUTO-ALLOC] Ln{line.LineNbr}: {best.LotSerialNbr} qty={best.QtyOnHand}");

            // CRITICAL: SetValue for lot — bypasses INLotSerialNbrAttribute
            Base.Transactions.Cache.SetValue<SOLine.lotSerialNbr>(line, best.LotSerialNbr);
            Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, best.QtyOnHand);
        }

        protected void _(Events.RowDeleted<SOLine> e)
        {
            if (e.Row?.LotSerialNbr != null)
                _assignedSerials.Remove(e.Row.LotSerialNbr);
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
