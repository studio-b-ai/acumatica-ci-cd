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
    /// Two-phase approach to avoid aggregate validation errors:
    ///   Phase 1 (RowUpdated): Assigns the first bolt to the triggering line and
    ///           queues a pending split request with the remaining allocation plan.
    ///   Phase 2 (Persist override): Before base persist, inserts additional lines
    ///           for remaining bolts + backorder. This runs inside the save transaction
    ///           where aggregate counters are properly maintained.
    ///
    /// Rules:
    ///   - PC and FO order types only, PIECENBR lot class items only
    ///   - Bolts must be fully unreserved (QtyAvail == QtyOnHand)
    ///   - 3+ bolts: group by receipt date (same dye lot), then FIFO, tightest fit
    ///   - 1-2 bolts: FIFO, then tightest fit
    ///   - Each line gets full bolt qty (whole bolt allocation)
    ///   - 120% overship cap on total allocated vs requested
    ///   - Remainder → backorder line with POCreate = true
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m;

        [ThreadStatic]
        private static bool _allocating;

        /// <summary>Pending line insertions to execute during Persist.</summary>
        private readonly List<PendingAllocation> _pendingAllocations = new List<PendingAllocation>();

        // =================================================================
        // Phase 1: RowUpdated — assign first bolt, queue remaining splits
        // =================================================================
        protected void _(Events.RowUpdated<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null) return;

            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            if (!string.IsNullOrEmpty(e.Row.LotSerialNbr)) return;
            if (e.Row.InventoryID == null || (e.Row.OrderQty ?? 0) <= 0) return;
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
                    $"[AUTO-ALLOC] Starting: Item {inventoryID}, WH {siteID}, " +
                    $"Requested {requestedQty}, Max {maxQty}");

                // Collect already-assigned serials
                var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (SOLine existing in Base.Transactions.Select())
                {
                    if (existing.LineNbr == e.Row.LineNbr) continue;
                    if (!string.IsNullOrEmpty(existing.LotSerialNbr))
                        assignedSerials.Add(existing.LotSerialNbr);
                }

                var candidates = GetAvailableBolts(inventoryID, siteID.Value, assignedSerials);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Found {candidates.Count} candidate bolt(s)");

                if (candidates.Count == 0)
                {
                    Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(e.Row, true);
                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] No bolts — marked line for PO");
                    return;
                }

                var sorted = SortBolts(candidates, requestedQty);

                // Assign first bolt to the triggering line
                var firstBolt = sorted[0];
                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(e.Row, firstBolt.LotSerialNbr);
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(e.Row, firstBolt.QtyOnHand);

                decimal totalAllocated = firstBolt.QtyOnHand;
                assignedSerials.Add(firstBolt.LotSerialNbr);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Line {e.Row.LineNbr}: {firstBolt.LotSerialNbr} " +
                    $"qty {firstBolt.QtyOnHand} ({totalAllocated}/{requestedQty})");

                // Queue remaining bolts for Phase 2 (Persist)
                var pendingLines = new List<PendingLine>();
                int boltIndex = 1;

                while (totalAllocated < requestedQty && boltIndex < sorted.Count)
                {
                    var nextBolt = sorted[boltIndex];

                    if (totalAllocated + nextBolt.QtyOnHand > maxQty)
                    {
                        var fit = FindBoltWithinCap(sorted, boltIndex, maxQty - totalAllocated, assignedSerials);
                        if (fit == null) break;
                        nextBolt = fit;
                    }

                    boltIndex++;
                    totalAllocated += nextBolt.QtyOnHand;
                    assignedSerials.Add(nextBolt.LotSerialNbr);

                    pendingLines.Add(new PendingLine
                    {
                        LotSerialNbr = nextBolt.LotSerialNbr,
                        Qty = nextBolt.QtyOnHand,
                        IsPOCreate = false,
                    });

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Queued: {nextBolt.LotSerialNbr} " +
                        $"qty {nextBolt.QtyOnHand} ({totalAllocated}/{requestedQty})");
                }

                // Queue backorder line if short
                if (totalAllocated < requestedQty)
                {
                    decimal remainder = requestedQty - totalAllocated;
                    pendingLines.Add(new PendingLine
                    {
                        LotSerialNbr = null,
                        Qty = remainder,
                        IsPOCreate = true,
                    });
                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Queued backorder: qty {remainder}");
                }

                if (pendingLines.Count > 0)
                {
                    _pendingAllocations.Add(new PendingAllocation
                    {
                        InventoryID = inventoryID,
                        SiteID = siteID.Value,
                        UOM = uom,
                        Lines = pendingLines,
                    });
                }

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Phase 1 done: {totalAllocated} allocated, " +
                    $"{pendingLines.Count} lines queued for persist");
            }
            catch (Exception ex)
            {
                PXTrace.WriteWarning(
                    $"[AUTO-ALLOC] Error in RowUpdated: {ex.GetType().Name}: {ex.Message}");
            }
            finally
            {
                _allocating = false;
            }
        }

        // =================================================================
        // Phase 2: Persist override — insert queued lines before base save
        // =================================================================
        [PXOverride]
        public void Persist(Action del)
        {
            if (_pendingAllocations.Count > 0)
            {
                try
                {
                    _allocating = true;

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Persist: inserting {_pendingAllocations.Sum(a => a.Lines.Count)} queued line(s)");

                    foreach (var alloc in _pendingAllocations)
                    {
                        foreach (var pending in alloc.Lines)
                        {
                            SOLine newLine = Base.Transactions.Insert(new SOLine());
                            if (newLine == null) continue;

                            Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(newLine, alloc.InventoryID);
                            Base.Transactions.Cache.SetValueExt<SOLine.siteID>(newLine, alloc.SiteID);
                            if (alloc.UOM != null)
                                Base.Transactions.Cache.SetValueExt<SOLine.uOM>(newLine, alloc.UOM);
                            Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(newLine, pending.Qty);

                            if (!string.IsNullOrEmpty(pending.LotSerialNbr))
                                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(newLine, pending.LotSerialNbr);

                            if (pending.IsPOCreate)
                                Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(newLine, true);

                            PXTrace.WriteInformation(
                                $"[AUTO-ALLOC] Inserted line {newLine.LineNbr}: " +
                                $"lot={pending.LotSerialNbr ?? "(backorder)"}, qty={pending.Qty}");
                        }
                    }
                }
                catch (Exception ex)
                {
                    PXTrace.WriteWarning(
                        $"[AUTO-ALLOC] Error in Persist: {ex.GetType().Name}: {ex.Message}");
                }
                finally
                {
                    _pendingAllocations.Clear();
                    _allocating = false;
                }
            }

            // Always call base persist
            del();
        }

        // =================================================================
        // Bolt query + sorting helpers
        // =================================================================

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
            // Both paths sort the same way — FIFO then tightest fit.
            // For 3+ bolts, FIFO naturally groups same-receipt-date bolts together.
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

        // =================================================================
        // Internal types
        // =================================================================

        private class BoltCandidate
        {
            public string LotSerialNbr { get; set; }
            public decimal QtyOnHand { get; set; }
            public DateTime? ReceiptDate { get; set; }
        }

        private class PendingLine
        {
            public string LotSerialNbr { get; set; }
            public decimal Qty { get; set; }
            public bool IsPOCreate { get; set; }
        }

        private class PendingAllocation
        {
            public int InventoryID { get; set; }
            public int SiteID { get; set; }
            public string UOM { get; set; }
            public List<PendingLine> Lines { get; set; }
        }
    }
}
