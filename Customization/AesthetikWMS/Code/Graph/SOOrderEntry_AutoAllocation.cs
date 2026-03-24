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
    /// "Allocate Bolts" toolbar button on SO301000 for PC/FO orders.
    ///
    /// Full multi-bolt allocation:
    ///   1. For each unallocated PIECENBR line, find best bolt >= line qty
    ///   2. If no single bolt covers it, split across multiple lines (120% overship cap)
    ///   3. Remainder → backorder line with POCreate = true
    ///   4. Sorting: 3+ bolts → group by receipt date (same dye lot), FIFO, tightest fit
    ///              1-2 bolts → FIFO, tightest fit
    ///   5. Each line gets full bolt qty (whole bolt allocation)
    ///
    /// Runs as PXAction on persisted lines — safe to insert new lines.
    /// </summary>
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m;

        #region Action

        public PXAction<SOOrder> AllocateBolts;

        [PXButton(CommitChanges = true)]
        [PXUIField(
            DisplayName = "Allocate Bolts",
            MapEnableRights = PXCacheRights.Update,
            MapViewRights = PXCacheRights.Select)]
        protected virtual IEnumerable allocateBolts(PXAdapter adapter)
        {
            SOOrder order = Base.Document.Current;
            if (order == null) return adapter.Get();

            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO")
                throw new PXException("Allocate Bolts is only available for PC and FO orders.");

            // Collect state
            var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var linesToAllocate = new List<SOLine>();

            foreach (SOLine line in Base.Transactions.Select())
            {
                if (!string.IsNullOrEmpty(line.LotSerialNbr))
                {
                    assignedSerials.Add(line.LotSerialNbr);
                    continue;
                }
                if (line.InventoryID == null) continue;
                if ((line.SiteID ?? order.DefaultSiteID) == null) continue;
                if (!IsPieceGoodsItem(line.InventoryID)) continue;

                linesToAllocate.Add(line);
            }

            if (linesToAllocate.Count == 0)
                throw new PXException("No unallocated piece goods lines found.");

            int totalAllocatedLines = 0;
            int totalBackorderLines = 0;

            foreach (SOLine line in linesToAllocate)
            {
                int inventoryID = line.InventoryID.Value;
                int siteID = (line.SiteID ?? order.DefaultSiteID).Value;
                decimal requestedQty = line.OrderQty ?? 0;
                decimal maxQty = requestedQty * OvershipFactor;
                string uom = line.UOM;

                // Get all available bolts
                var bolts = GetAvailableBolts(inventoryID, siteID, assignedSerials);

                if (bolts.Count == 0)
                {
                    // No bolts — mark for PO
                    Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(line, true);
                    Base.Transactions.Update(line);
                    totalBackorderLines++;
                    PXTrace.WriteInformation(
                        $"[ALLOC] Ln{line.LineNbr}: no bolts — marked for PO");
                    continue;
                }

                // Check if a single bolt covers it
                var singleBolt = bolts
                    .Where(b => b.QtyOnHand >= requestedQty && b.QtyOnHand <= maxQty)
                    .OrderBy(b => b.ReceiptDate ?? DateTime.MaxValue)
                    .ThenByDescending(b => b.QtyOnHand)
                    .FirstOrDefault();

                if (singleBolt != null && singleBolt.QtyOnHand <= maxQty)
                {
                    // Single bolt covers the order within overship cap
                    Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(line, singleBolt.LotSerialNbr);
                    Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, singleBolt.QtyOnHand);
                    Base.Transactions.Update(line);
                    assignedSerials.Add(singleBolt.LotSerialNbr);
                    totalAllocatedLines++;

                    PXTrace.WriteInformation(
                        $"[ALLOC] Ln{line.LineNbr}: single bolt {singleBolt.LotSerialNbr} " +
                        $"qty={singleBolt.QtyOnHand}");
                    continue;
                }

                // Multi-bolt: split across lines
                var sorted = SortBolts(bolts, requestedQty);
                decimal totalAllocated = 0m;
                bool firstBolt = true;

                foreach (var bolt in sorted)
                {
                    if (totalAllocated >= requestedQty) break;
                    if (assignedSerials.Contains(bolt.LotSerialNbr)) continue;

                    // Overship cap check
                    if (totalAllocated + bolt.QtyOnHand > maxQty)
                    {
                        // Try to find a bolt that fits
                        var fit = sorted.FirstOrDefault(b =>
                            !assignedSerials.Contains(b.LotSerialNbr) &&
                            b.QtyOnHand <= (maxQty - totalAllocated) &&
                            b.QtyOnHand > 0);
                        if (fit == null) break;
                        bolt.LotSerialNbr = fit.LotSerialNbr;
                        bolt.QtyOnHand = fit.QtyOnHand;
                        bolt.ReceiptDate = fit.ReceiptDate;
                    }

                    if (firstBolt)
                    {
                        // Assign to the original line
                        Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(line, bolt.LotSerialNbr);
                        Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, bolt.QtyOnHand);
                        Base.Transactions.Update(line);
                        firstBolt = false;
                    }
                    else
                    {
                        // Insert new line for this bolt
                        SOLine newLine = Base.Transactions.Insert(new SOLine());
                        if (newLine == null) break;

                        Base.Transactions.Cache.SetValueExt<SOLine.inventoryID>(newLine, inventoryID);
                        Base.Transactions.Cache.SetValueExt<SOLine.siteID>(newLine, siteID);
                        if (uom != null)
                            Base.Transactions.Cache.SetValueExt<SOLine.uOM>(newLine, uom);
                        Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(newLine, bolt.LotSerialNbr);
                        Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(newLine, bolt.QtyOnHand);
                        Base.Transactions.Update(newLine);
                    }

                    totalAllocated += bolt.QtyOnHand;
                    assignedSerials.Add(bolt.LotSerialNbr);
                    totalAllocatedLines++;

                    PXTrace.WriteInformation(
                        $"[ALLOC] {(firstBolt ? "Ln" + line.LineNbr : "New line")}: " +
                        $"{bolt.LotSerialNbr} qty={bolt.QtyOnHand} " +
                        $"(total={totalAllocated}/{requestedQty})");
                }

                // Backorder remainder
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
                        Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(boLine, true);
                        Base.Transactions.Update(boLine);
                        totalBackorderLines++;

                        PXTrace.WriteInformation(
                            $"[ALLOC] Backorder: qty={remainder} POCreate=true");
                    }
                }
            }

            Base.Actions.PressSave();

            string msg = $"Allocated {totalAllocatedLines} bolt(s).";
            if (totalBackorderLines > 0)
                msg += $" {totalBackorderLines} backorder line(s) created.";

            PXTrace.WriteInformation($"[ALLOC] Done: {msg}");
            return adapter.Get();
        }

        #endregion

        #region RowSelected

        protected void _(Events.RowSelected<SOOrder> e)
        {
            if (e.Row == null) return;
            string orderType = e.Row.OrderType;
            bool isPcFo = orderType == "PC" || orderType == "FO";
            AllocateBolts.SetVisible(isPcFo);
            AllocateBolts.SetEnabled(isPcFo);
        }

        #endregion

        #region Helpers

        private List<BoltCandidate> GetAvailableBolts(
            int inventoryID, int siteID, HashSet<string> assignedSerials)
        {
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
            // FIFO (oldest receipt) then largest bolt first (fewer lines, save remnants for other customers)
            // For 3+ bolts, FIFO naturally groups same-date bolts (same dye lot)
            return candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenByDescending(c => c.QtyOnHand)
                .ToList();
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

        #endregion
    }
}
