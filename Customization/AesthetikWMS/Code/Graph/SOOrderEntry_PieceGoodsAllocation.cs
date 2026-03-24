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
    /// Auto-allocates PIECENBR lot-tracked bolts to PC/FO sales order lines.
    ///
    /// Phase 1 (RowUpdated): Assigns the best bolt to the triggering line using
    ///         SetValue (NOT SetValueExt) for lotSerialNbr to bypass
    ///         INLotSerialNbrAttribute.FieldUpdated which corrupts aggregates.
    ///         Adjusts OrderQty to full bolt via SetValueExt (safe for qty).
    ///
    /// Phase 2 (RowUpdated continued): If more bolts needed, inserts additional
    ///         lines using the same SetValue pattern for lot assignment.
    ///
    /// CRITICAL: SetValueExt for lotSerialNbr triggers INLotSerialNbrAttribute
    /// which internally modifies OrderQty and corrupts SOOrder aggregate counters.
    /// Always use SetValue (cache-only, no event chain) for lot serial assignment.
    ///
    /// Rules:
    ///   - PC and FO order types only, PIECENBR lot class only
    ///   - Bolts must be fully unreserved (QtyAvail == QtyOnHand)
    ///   - 3+ bolts: group by receipt date (same dye lot), FIFO, tightest fit
    ///   - 1-2 bolts: FIFO, tightest fit
    ///   - Each line gets full bolt qty (whole bolt allocation)
    ///   - 120% overship cap
    ///   - Remainder → backorder line with POCreate = true
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m;

        [ThreadStatic]
        private static bool _allocating;

        protected void _(Events.RowInserted<SOLine> e)
        {
            AllocateBolts(e.Row);
        }

        protected void _(Events.RowUpdated<SOLine> e)
        {
            AllocateBolts(e.Row);
        }

        private void AllocateBolts(SOLine line)
        {
            if (_allocating) return;
            if (line == null) return;

            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            if (!string.IsNullOrEmpty(line.LotSerialNbr)) return;
            if (line.InventoryID == null || (line.OrderQty ?? 0) <= 0) return;
            if (!IsPieceGoodsItem(line.InventoryID)) return;

            int inventoryID = line.InventoryID.Value;
            int? siteID = line.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            decimal requestedQty = line.OrderQty ?? 0;
            decimal maxQty = requestedQty * OvershipFactor;
            string uom = line.UOM;

            try
            {
                _allocating = true;

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Start: item={inventoryID} wh={siteID} " +
                    $"req={requestedQty} max={maxQty}");

                // Collect already-assigned serials
                var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (SOLine existing in Base.Transactions.Select())
                {
                    if (existing.LineNbr == line.LineNbr) continue;
                    if (!string.IsNullOrEmpty(existing.LotSerialNbr))
                        assignedSerials.Add(existing.LotSerialNbr);
                }

                var candidates = GetAvailableBolts(inventoryID, siteID.Value, assignedSerials);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] {candidates.Count} bolt(s) available");

                if (candidates.Count == 0)
                {
                    // No bolts — mark for PO
                    Base.Transactions.Cache.SetValue<SOLine.pOCreate>(line, true);
                    PXTrace.WriteInformation("[AUTO-ALLOC] No bolts — marked for PO");
                    return;
                }

                var sorted = SortBolts(candidates, requestedQty);

                // === Assign first bolt to the triggering line ===
                var firstBolt = sorted[0];

                // CRITICAL: SetValue for lot — bypasses INLotSerialNbrAttribute
                Base.Transactions.Cache.SetValue<SOLine.lotSerialNbr>(line, firstBolt.LotSerialNbr);
                // SetValueExt for qty — safe, triggers proper recalcs
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, firstBolt.QtyOnHand);

                decimal totalAllocated = firstBolt.QtyOnHand;
                assignedSerials.Add(firstBolt.LotSerialNbr);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Ln{line.LineNbr}: {firstBolt.LotSerialNbr} " +
                    $"qty={firstBolt.QtyOnHand} ({totalAllocated}/{requestedQty})");

                // === Insert additional lines for remaining bolts ===
                int boltIndex = 1;
                while (totalAllocated < requestedQty && boltIndex < sorted.Count)
                {
                    var nextBolt = sorted[boltIndex];

                    // Overship cap check
                    if (totalAllocated + nextBolt.QtyOnHand > maxQty)
                    {
                        var fit = FindBoltWithinCap(sorted, boltIndex, maxQty - totalAllocated, assignedSerials);
                        if (fit == null) break;
                        nextBolt = fit;
                    }

                    boltIndex++;

                    SOLine newLine = Base.Transactions.Insert(new SOLine());
                    if (newLine == null) break;

                    Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(newLine, inventoryID);
                    Base.Transactions.Cache.SetValueExt<SOLine.siteID>(newLine, siteID);
                    if (uom != null)
                        Base.Transactions.Cache.SetValueExt<SOLine.uOM>(newLine, uom);

                    // CRITICAL: SetValue for lot — no attribute event chain
                    Base.Transactions.Cache.SetValue<SOLine.lotSerialNbr>(newLine, nextBolt.LotSerialNbr);
                    Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(newLine, nextBolt.QtyOnHand);

                    totalAllocated += nextBolt.QtyOnHand;
                    assignedSerials.Add(nextBolt.LotSerialNbr);

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] New Ln{newLine.LineNbr}: {nextBolt.LotSerialNbr} " +
                        $"qty={nextBolt.QtyOnHand} ({totalAllocated}/{requestedQty})");
                }

                // === Backorder remainder ===
                if (totalAllocated < requestedQty)
                {
                    decimal remainder = requestedQty - totalAllocated;

                    SOLine boLine = Base.Transactions.Insert(new SOLine());
                    if (boLine != null)
                    {
                        Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(boLine, inventoryID);
                        Base.Transactions.Cache.SetValueExt<SOLine.siteID>(boLine, siteID);
                        if (uom != null)
                            Base.Transactions.Cache.SetValueExt<SOLine.uOM>(boLine, uom);
                        Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(boLine, remainder);
                        Base.Transactions.Cache.SetValue<SOLine.pOCreate>(boLine, true);

                        PXTrace.WriteInformation(
                            $"[AUTO-ALLOC] Backorder Ln{boLine.LineNbr}: qty={remainder} POCreate=true");
                    }
                }

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Done: {totalAllocated}/{requestedQty} allocated");
            }
            catch (Exception ex)
            {
                // Never throw from row events
                PXTrace.WriteWarning(
                    $"[AUTO-ALLOC] Error: {ex.GetType().Name}: {ex.Message}");
            }
            finally
            {
                _allocating = false;
            }
        }

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
                if (assignedSerials.Contains(status.LotSerialNbr)) continue;

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

            return candidates;
        }

        private List<BoltCandidate> SortBolts(List<BoltCandidate> candidates, decimal requestedQty)
        {
            return candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .ToList();
        }

        private BoltCandidate FindBoltWithinCap(
            List<BoltCandidate> sorted, int startIndex,
            decimal remainingCap, HashSet<string> assignedSerials)
        {
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
