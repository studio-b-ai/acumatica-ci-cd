using System;
using System.Collections;
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
    /// Adds an "Allocate Bolts" toolbar button to SO301000 for PC/FO orders.
    ///
    /// The button assigns PIECENBR lot serial numbers to unallocated lines
    /// using FIFO + tightest-fit bolt selection. Works on already-persisted
    /// lines — avoids aggregate validation errors that occur when setting
    /// LotSerialNbr during RowUpdated/RowInserted events.
    ///
    /// Flow:
    ///   1. User adds lines and saves the order normally
    ///   2. User clicks "Allocate Bolts" on the toolbar
    ///   3. Action queries INLotSerialStatus for available bolts
    ///   4. Assigns best bolt to each unallocated PIECENBR line via SetValueExt
    ///   5. Saves the order with lots assigned
    ///
    /// Multi-bolt: each line gets one bolt. User adds multiple lines for
    /// multi-bolt orders. The action allocates all unassigned lines at once.
    /// </summary>
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        #region Action Declaration

        public PXAction<SOOrder> AllocateBolts;

        [PXButton(CommitChanges = true)]
        [PXUIField(
            DisplayName = "Allocate Bolts",
            MapEnableRights = PXCacheRights.Update,
            MapViewRights = PXCacheRights.Select)]
        protected virtual IEnumerable allocateBolts(PXAdapter adapter)
        {
            SOOrder order = Base.Document.Current;
            if (order == null)
                return adapter.Get();

            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO")
            {
                throw new PXException("Allocate Bolts is only available for PC and FO orders.");
            }

            // Collect already-assigned serials
            var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var unallocatedLines = new List<SOLine>();

            foreach (SOLine line in Base.Transactions.Select())
            {
                if (!string.IsNullOrEmpty(line.LotSerialNbr))
                {
                    assignedSerials.Add(line.LotSerialNbr);
                    continue;
                }

                // Only PIECENBR items with inventory and warehouse
                if (line.InventoryID == null) continue;
                if (line.SiteID == null && order.DefaultSiteID == null) continue;
                if (!IsPieceGoodsItem(line.InventoryID)) continue;

                unallocatedLines.Add(line);
            }

            if (unallocatedLines.Count == 0)
            {
                throw new PXException("No unallocated piece goods lines found on this order.");
            }

            int allocated = 0;
            int skipped = 0;

            foreach (SOLine line in unallocatedLines)
            {
                int inventoryID = line.InventoryID.Value;
                int siteID = line.SiteID ?? order.DefaultSiteID ?? 0;
                if (siteID == 0) { skipped++; continue; }

                // Query available bolts for this item + warehouse
                var candidates = new List<BoltCandidate>();

                foreach (PXResult<INLotSerialStatus> row in SelectFrom<INLotSerialStatus>
                    .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                        .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                    .View.ReadOnly.Select(Base, inventoryID, siteID))
                {
                    var status = (INLotSerialStatus)row;
                    if (status.LotSerialNbr == null) continue;
                    if (assignedSerials.Contains(status.LotSerialNbr)) continue;

                    decimal qtyOnHand = status.QtyOnHand ?? 0;
                    decimal qtyAvail = status.QtyAvail ?? 0;

                    if (qtyOnHand <= 0) continue;
                    if (qtyAvail != qtyOnHand) continue; // Fully unreserved only

                    candidates.Add(new BoltCandidate
                    {
                        LotSerialNbr = status.LotSerialNbr,
                        QtyOnHand = qtyOnHand,
                        ReceiptDate = status.ReceiptDate,
                    });
                }

                if (candidates.Count == 0)
                {
                    skipped++;
                    PXTrace.WriteInformation(
                        $"[ALLOC] Ln{line.LineNbr}: no bolts available for item {inventoryID} in WH {siteID}");
                    continue;
                }

                // FIFO + tightest fit
                var best = candidates
                    .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                    .ThenBy(c => c.QtyOnHand)
                    .First();

                // Assign lot and qty — safe on persisted lines
                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(line, best.LotSerialNbr);
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, best.QtyOnHand);
                Base.Transactions.Update(line);

                assignedSerials.Add(best.LotSerialNbr);
                allocated++;

                PXTrace.WriteInformation(
                    $"[ALLOC] Ln{line.LineNbr}: {best.LotSerialNbr} qty={best.QtyOnHand}");
            }

            // Save
            Base.Actions.PressSave();

            if (skipped > 0)
            {
                PXProcessing.SetWarning(
                    $"Allocated {allocated} line(s). {skipped} line(s) skipped (no bolts available).");
            }

            return adapter.Get();
        }

        #endregion

        #region RowSelected — button visibility

        protected void _(Events.RowSelected<SOOrder> e)
        {
            if (e.Row == null) return;

            string orderType = e.Row.OrderType;
            bool isPcFo = orderType == "PC" || orderType == "FO";

            AllocateBolts.SetVisible(isPcFo);
            AllocateBolts.SetEnabled(isPcFo && e.Row.Status == "N" || e.Row.Status == "O" || e.Row.Hold == true);
        }

        #endregion

        #region Helpers

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

        #endregion
    }
}
