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
    ///
    /// Behavior:
    ///   1. RowUpdated fires when a line is added or changed
    ///   2. Queries available bolts: fully unreserved (QtyAvail == QtyOnHand), QtyOnHand > 0
    ///   3. Sorting: 3+ bolts → group by receipt date (same dye lot), then FIFO, then tightest fit
    ///              1-2 bolts → FIFO, then tightest fit
    ///   4. Assigns bolt lot to line, sets line qty to full bolt QtyOnHand
    ///   5. If remainder > 0, inserts new lines until requested qty covered (120% overship cap)
    ///   6. If bolts run out, inserts backorder line with MarkForPO = true
    ///
    /// Uses RowUpdated (not RowInserted) because RowInserted fires before InventoryID
    /// and OrderQty are populated.
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m; // 120% max

        /// <summary>Re-entry guard to prevent recursive allocation.</summary>
        [ThreadStatic]
        private static bool _allocating;

        protected void _(Events.RowUpdated<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null) return;

            // Only for PC and FO order types
            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Guard: skip if lot already assigned (prevents re-trigger from qty/lot update)
            if (!string.IsNullOrEmpty(e.Row.LotSerialNbr)) return;

            // Need both item and qty to proceed
            if (e.Row.InventoryID == null || (e.Row.OrderQty ?? 0) <= 0) return;

            // Only process PIECENBR items
            if (!IsPieceGoodsItem(e.Row.InventoryID)) return;

            int inventoryID = e.Row.InventoryID.Value;
            int? siteID = e.Row.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            decimal requestedQty = e.Row.OrderQty ?? 0;
            decimal maxQty = requestedQty * OvershipFactor;
            string uom = e.Row.UOM;

            try
            {
                _allocating = true;

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Starting: Item {e.Row.InventoryID}, WH {siteID}, " +
                    $"RequestedQty {requestedQty}, MaxQty {maxQty}");

                // Collect serials already assigned to other lines on this order
                var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (SOLine existing in Base.Transactions.Select())
                {
                    if (existing.LineNbr == e.Row.LineNbr) continue;
                    if (!string.IsNullOrEmpty(existing.LotSerialNbr))
                        assignedSerials.Add(existing.LotSerialNbr);
                }

                // Query all lot/serial inventory for this item + warehouse
                var candidates = GetAvailableBolts(inventoryID, siteID.Value, assignedSerials);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Found {candidates.Count} candidate bolt(s)");

                if (candidates.Count == 0)
                {
                    // No bolts at all — mark entire line for PO
                    Base.Transactions.Cache.SetValueExt<SOLine.markForPO>(e.Row, true);
                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] No bolts available — marked line for PO");
                    return;
                }

                // Sort candidates based on how many we'll need
                var sorted = SortBolts(candidates, requestedQty);

                // Assign first bolt to the triggering line
                decimal totalAllocated = 0m;
                int boltIndex = 0;

                var firstBolt = sorted[boltIndex];
                boltIndex++;

                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(e.Row, firstBolt.LotSerialNbr);
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(e.Row, firstBolt.QtyOnHand);
                totalAllocated += firstBolt.QtyOnHand;
                assignedSerials.Add(firstBolt.LotSerialNbr);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Line {e.Row.LineNbr}: assigned {firstBolt.LotSerialNbr} " +
                    $"qty {firstBolt.QtyOnHand} (total: {totalAllocated}/{requestedQty})");

                // Insert additional lines for remaining bolts
                while (totalAllocated < requestedQty && boltIndex < sorted.Count)
                {
                    var nextBolt = sorted[boltIndex];

                    // Check overship cap: would adding this bolt exceed 120%?
                    if (totalAllocated + nextBolt.QtyOnHand > maxQty)
                    {
                        // Try to find a smaller bolt that fits within cap
                        var fittingBolt = FindBoltWithinCap(sorted, boltIndex, maxQty - totalAllocated, assignedSerials);
                        if (fittingBolt == null) break; // No bolt fits — stop allocating
                        nextBolt = fittingBolt;
                    }

                    boltIndex++;

                    // Insert a new SOLine for this bolt
                    SOLine newLine = Base.Transactions.Insert(new SOLine());
                    if (newLine == null) break;

                    Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(newLine, inventoryID);
                    Base.Transactions.Cache.SetValueExt<SOLine.siteID>(newLine, siteID);
                    if (uom != null)
                        Base.Transactions.Cache.SetValueExt<SOLine.uOM>(newLine, uom);
                    Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(newLine, nextBolt.LotSerialNbr);
                    Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(newLine, nextBolt.QtyOnHand);

                    totalAllocated += nextBolt.QtyOnHand;
                    assignedSerials.Add(nextBolt.LotSerialNbr);

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] New line {newLine.LineNbr}: assigned {nextBolt.LotSerialNbr} " +
                        $"qty {nextBolt.QtyOnHand} (total: {totalAllocated}/{requestedQty})");
                }

                // If still short, insert backorder line for remainder
                if (totalAllocated < requestedQty)
                {
                    decimal remainder = requestedQty - totalAllocated;

                    SOLine backorderLine = Base.Transactions.Insert(new SOLine());
                    if (backorderLine != null)
                    {
                        Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(backorderLine, inventoryID);
                        Base.Transactions.Cache.SetValueExt<SOLine.siteID>(backorderLine, siteID);
                        if (uom != null)
                            Base.Transactions.Cache.SetValueExt<SOLine.uOM>(backorderLine, uom);
                        Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(backorderLine, remainder);
                        Base.Transactions.Cache.SetValueExt<SOLine.markForPO>(backorderLine, true);

                        PXTrace.WriteInformation(
                            $"[AUTO-ALLOC] Backorder line {backorderLine.LineNbr}: " +
                            $"qty {remainder}, MarkForPO=true");
                    }
                }

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Complete: allocated {totalAllocated} of {requestedQty} requested");
            }
            catch (Exception ex)
            {
                // Never throw from RowUpdated — log and let the order save normally
                PXTrace.WriteWarning(
                    $"[AUTO-ALLOC] Error: {ex.GetType().Name}: {ex.Message}");
            }
            finally
            {
                _allocating = false;
            }
        }

        /// <summary>
        /// Queries INLotSerialStatus for available bolts. Filters to fully unreserved
        /// bolts with positive qty, excluding already-assigned serials.
        /// </summary>
        private List<BoltCandidate> GetAvailableBolts(
            int inventoryID, int siteID, HashSet<string> assignedSerials)
        {
            var candidates = new List<BoltCandidate>();

            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID);

            foreach (PXResult<INLotSerialStatus> row in allSerials)
            {
                var status = (INLotSerialStatus)row;
                if (status.LotSerialNbr == null) continue;

                // Skip already assigned to another line in this order
                if (assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail = status.QtyAvail ?? 0;

                // Must have positive quantity
                if (qtyOnHand <= 0) continue;

                // Must be fully unreserved (entire bolt available)
                if (qtyAvail != qtyOnHand) continue;

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyOnHand,
                    ReceiptDate = status.ReceiptDate,
                });
            }

            return candidates;
        }

        /// <summary>
        /// Sorts bolts based on how many are needed to fulfill the order.
        /// 3+ bolts: group by receipt date (same dye lot/container), then FIFO, then tightest fit.
        /// 1-2 bolts: FIFO (oldest first), then tightest fit (smallest qty).
        /// </summary>
        private List<BoltCandidate> SortBolts(List<BoltCandidate> candidates, decimal requestedQty)
        {
            // Estimate how many bolts needed using average qty
            decimal avgQty = candidates.Average(c => c.QtyOnHand);
            int estimatedBolts = avgQty > 0 ? (int)Math.Ceiling(requestedQty / avgQty) : 1;

            if (estimatedBolts >= 3)
            {
                // Group by receipt date — prefer bolts from the same shipment/dye lot.
                // Within each date group: tightest fit (smallest qty first).
                // Date groups ordered FIFO (oldest first).
                return candidates
                    .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                    .ThenBy(c => c.QtyOnHand)
                    .ToList();

                // Note: OrderBy on ReceiptDate naturally groups same-date bolts together
                // and orders groups FIFO. ThenBy QtyOnHand gives tightest fit within group.
            }

            // 1-2 bolts: FIFO then tightest fit
            return candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .ToList();
        }

        /// <summary>
        /// Searches remaining sorted bolts for one that fits within the overship cap.
        /// Returns null if no bolt fits.
        /// </summary>
        private BoltCandidate FindBoltWithinCap(
            List<BoltCandidate> sorted, int startIndex,
            decimal remainingCap, HashSet<string> assignedSerials)
        {
            // Search from startIndex forward for the largest bolt that fits
            BoltCandidate best = null;

            for (int i = startIndex; i < sorted.Count; i++)
            {
                var bolt = sorted[i];
                if (assignedSerials.Contains(bolt.LotSerialNbr)) continue;
                if (bolt.QtyOnHand <= remainingCap)
                {
                    if (best == null || bolt.QtyOnHand > best.QtyOnHand)
                        best = bolt;
                }
            }

            return best;
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
