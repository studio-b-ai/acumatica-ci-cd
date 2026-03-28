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
    /// Auto-allocation for piece goods (PIECENBR lot class) on PC/FO orders.
    ///
    /// Fires on RowUpdated when InventoryID + SiteID are populated:
    ///   1. For each unallocated PIECENBR line, find best bolt >= line qty
    ///   2. If no single bolt covers it, split across multiple lines (120% overship cap)
    ///   3. Remainder → backorder line with POCreate = true
    ///   4. Sorting: FIFO (oldest receipt), then largest bolt (fewer lines)
    ///   5. Each line gets full bolt qty (whole bolt allocation)
    ///
    /// PC/FO orders are full-bolt by nature — qty override to actual bolt
    /// yardage is the correct behavior.
    /// </summary>
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m;

        #region RowUpdated — auto-fire on line change

        protected void _(Events.RowUpdated<SOLine> e)
        {
            SOLine line = e.Row;
            SOLine oldLine = e.OldRow;
            if (line == null) return;

            // Fire when InventoryID, SiteID, or OrderQty changed
            bool invChanged = line.InventoryID != oldLine?.InventoryID;
            bool siteChanged = line.SiteID != oldLine?.SiteID;
            bool qtyChanged = line.OrderQty != oldLine?.OrderQty;
            if (!invChanged && !siteChanged && !qtyChanged)
                return;

            // Gate: need InventoryID and a non-zero qty before allocating
            if (line.InventoryID == null) return;
            if ((line.OrderQty ?? 0m) <= 0m) return;

            SOOrder order = Base.Document.Current;
            if (order == null) return;

            int? siteID = line.SiteID ?? order.DefaultSiteID;
            if (siteID == null) return;

            // PC/FO orders only
            string orderType = order.OrderType;
            if (orderType != "PC" && orderType != "FO") return;

            // Already has a lot assigned — don't override manual selection
            if (!string.IsNullOrEmpty(line.LotSerialNbr)) return;

            // Must be a PIECENBR item
            if (!IsPieceGoodsItem(line.InventoryID)) return;

            // Collect already-assigned serials on this order
            var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (SOLine existing in Base.Transactions.Select())
            {
                if (existing.LineNbr == line.LineNbr) continue;
                if (!string.IsNullOrEmpty(existing.LotSerialNbr))
                    assignedSerials.Add(existing.LotSerialNbr);
            }

            int inventoryID = line.InventoryID.Value;
            decimal requestedQty = line.OrderQty ?? 0;
            decimal maxQty = requestedQty * OvershipFactor;
            string uom = line.UOM;

            // Get available bolts
            var bolts = GetAvailableBolts(inventoryID, siteID.Value, assignedSerials);

            if (bolts.Count == 0)
            {
                // No bolts — mark for PO
                Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(line, true);
                Base.Transactions.Update(line);
                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Ln{line.LineNbr}: no bolts — marked for PO");

                UpdateOrderDescription(order, assignedSerials, line, null, true);
                return;
            }

            // Try single bolt first (tightest fit within overship cap)
            var singleBolt = bolts
                .Where(b => b.QtyOnHand >= requestedQty && b.QtyOnHand <= maxQty)
                .OrderBy(b => b.ReceiptDate ?? DateTime.MaxValue)
                .ThenByDescending(b => b.QtyOnHand)
                .FirstOrDefault();

            if (singleBolt != null)
            {
                Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(line, singleBolt.LotSerialNbr);
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, singleBolt.QtyOnHand);
                Base.Transactions.Update(line);
                assignedSerials.Add(singleBolt.LotSerialNbr);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Ln{line.LineNbr}: single bolt {singleBolt.LotSerialNbr} " +
                    $"qty={singleBolt.QtyOnHand}");

                UpdateOrderDescription(order, assignedSerials, line, singleBolt.LotSerialNbr, false);
                return;
            }

            // Multi-bolt: split across lines
            var sorted = SortBolts(bolts);
            decimal totalAllocated = 0m;
            bool firstBolt = true;
            var allocatedLots = new List<string>();

            foreach (var bolt in sorted)
            {
                if (totalAllocated >= requestedQty) break;
                if (assignedSerials.Contains(bolt.LotSerialNbr)) continue;

                // Overship cap check — find a bolt that fits
                if (totalAllocated + bolt.QtyOnHand > maxQty)
                {
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
                    // Assign to the triggering line
                    Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(line, bolt.LotSerialNbr);
                    Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, bolt.QtyOnHand);
                    Base.Transactions.Update(line);
                    firstBolt = false;
                }
                else
                {
                    // Insert new line for additional bolt
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
                allocatedLots.Add(bolt.LotSerialNbr);

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] {(firstBolt ? "Ln" + line.LineNbr : "New line")}: " +
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

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Backorder: qty={remainder} POCreate=true");
                }
            }

            UpdateOrderDescription(order, assignedSerials, line, null, false);
        }

        #endregion

        #region Helpers

        private void UpdateOrderDescription(SOOrder order, HashSet<string> allSerials,
            SOLine triggerLine, string singleLot, bool noBolts)
        {
            // Build description stamp
            string stamp;
            if (noBolts)
                stamp = $"[AUTO-ALLOC] No bolts for Ln{triggerLine.LineNbr} — PO created";
            else if (singleLot != null)
                stamp = $"[AUTO-ALLOC] Ln{triggerLine.LineNbr}: {singleLot}";
            else
                stamp = $"[AUTO-ALLOC ACTIVE] {allSerials.Count} bolt(s) assigned";

            string desc = order.OrderDesc ?? "";
            if (!desc.Contains("[AUTO-ALLOC"))
                desc = string.IsNullOrEmpty(desc) ? stamp : desc + " | " + stamp;
            else
                desc = stamp; // Replace previous stamp

            Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order, desc);
            Base.Document.Update(order);
        }

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
                if (qtyAvail != qtyOnHand) continue; // Skip partially allocated bolts

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyOnHand,
                    ReceiptDate = status.ReceiptDate,
                });
            }

            return candidates;
        }

        private List<BoltCandidate> SortBolts(List<BoltCandidate> candidates)
        {
            // FIFO (oldest receipt) then largest bolt first (fewer lines)
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
