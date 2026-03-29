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
    /// Runs in Persist() override — after all user edits, before DB write.
    /// For each unallocated PIECENBR line:
    ///   1. Find available bolts from INLotSerialStatus (FIFO, then largest)
    ///   2. Create SOLineSplit rows for each bolt (native allocation pattern)
    ///   3. Override SOLine.OrderQty to actual bolt total (120% overship cap)
    ///   4. If no bolts available, mark line POCreate = true
    ///
    /// Uses SOLineSplit (not SOLine splitting) to avoid openLineCntr aggregate
    /// corruption that occurs when inserting SOLine rows in event handlers.
    /// </summary>
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";
        private const decimal OvershipFactor = 1.20m;

        #region Persist Override

        public delegate void PersistDelegate();

        [PXOverride]
        public void Persist(PersistDelegate baseMethod)
        {
            SOOrder order = Base.Document.Current;
            if (order != null
                && (order.OrderType == "PC" || order.OrderType == "FO")
                && Base.Document.Cache.GetStatus(order) != PXEntryStatus.Deleted)
            {
                try
                {
                    AllocateBoltsForOrder(order);
                }
                catch (Exception ex)
                {
                    PXTrace.WriteError($"[AUTO-ALLOC] Failed: {ex.Message}");
                    // Don't block save — log and continue
                }
            }

            baseMethod();
        }

        #endregion

        #region Core Allocation Logic

        private void AllocateBoltsForOrder(SOOrder order)
        {
            // Collect all lot serials already assigned across the entire order
            var usedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (SOLineSplit existingSplit in
                SelectFrom<SOLineSplit>
                    .Where<SOLineSplit.orderType.IsEqual<@P.AsString>
                        .And<SOLineSplit.orderNbr.IsEqual<@P.AsString>>>
                    .View.ReadOnly.Select(Base, order.OrderType, order.OrderNbr))
            {
                if (!string.IsNullOrEmpty(existingSplit.LotSerialNbr))
                    usedSerials.Add(existingSplit.LotSerialNbr);
            }

            int totalBoltsAssigned = 0;
            bool anyNoBolts = false;
            var allocSummary = new List<string>();

            foreach (SOLine line in Base.Transactions.Select())
            {
                if (line.InventoryID == null) continue;
                if ((line.OrderQty ?? 0m) <= 0m) continue;
                if (!IsPieceGoodsItem(line.InventoryID)) continue;

                // Skip lines that already have allocated splits with lot serials
                if (LineHasAllocatedSplits(line, order))
                    continue;

                int? siteID = line.SiteID ?? order.DefaultSiteID;
                if (siteID == null) continue;

                decimal requestedQty = line.OrderQty ?? 0m;
                decimal maxQty = requestedQty * OvershipFactor;

                // Find available bolts
                var bolts = GetAvailableBolts(line.InventoryID.Value, siteID.Value, usedSerials);

                if (bolts.Count == 0)
                {
                    // No bolts — mark for PO
                    Base.Transactions.Cache.SetValueExt<SOLine.pOCreate>(line, true);
                    Base.Transactions.Cache.Update(line);
                    anyNoBolts = true;
                    allocSummary.Add($"Ln{line.LineNbr}: no bolts — PO");

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Ln{line.LineNbr}: no bolts for {line.InventoryID} — marked POCreate");
                    continue;
                }

                // Sort bolts FIFO, then largest
                var sorted = SortBolts(bolts);

                // Allocate bolts up to overship cap
                decimal totalAllocated = 0m;
                var assignedBolts = new List<BoltCandidate>();

                foreach (var bolt in sorted)
                {
                    if (totalAllocated >= requestedQty) break;

                    // Check overship cap
                    if (totalAllocated + bolt.QtyOnHand > maxQty)
                    {
                        // Try to find a smaller bolt that fits
                        var fit = sorted.FirstOrDefault(b =>
                            !usedSerials.Contains(b.LotSerialNbr) &&
                            !assignedBolts.Any(a => a.LotSerialNbr == b.LotSerialNbr) &&
                            b.QtyOnHand <= (maxQty - totalAllocated) &&
                            b.QtyOnHand > 0);
                        if (fit == null) break;

                        assignedBolts.Add(fit);
                        usedSerials.Add(fit.LotSerialNbr);
                        totalAllocated += fit.QtyOnHand;
                    }
                    else
                    {
                        assignedBolts.Add(bolt);
                        usedSerials.Add(bolt.LotSerialNbr);
                        totalAllocated += bolt.QtyOnHand;
                    }
                }

                if (assignedBolts.Count == 0) continue;

                // Delete the default auto-created split (Acumatica creates one on line insert)
                DeleteDefaultSplits(line, order);

                // Create SOLineSplit for each bolt
                foreach (var bolt in assignedBolts)
                {
                    var split = (SOLineSplit)Base.Caches[typeof(SOLineSplit)].CreateInstance();
                    split.OrderType = line.OrderType;
                    split.OrderNbr = line.OrderNbr;
                    split.LineNbr = line.LineNbr;
                    split.InventoryID = line.InventoryID;
                    split.SubItemID = line.SubItemID;
                    split.SiteID = line.SiteID;
                    split.LocationID = line.LocationID;
                    split.LotSerialNbr = bolt.LotSerialNbr;
                    split.Qty = bolt.QtyOnHand;
                    split.UOM = line.UOM;
                    split.IsAllocated = true;

                    Base.Caches[typeof(SOLineSplit)].Insert(split);

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Ln{line.LineNbr}: split {bolt.LotSerialNbr} qty={bolt.QtyOnHand}");
                }

                // Override line qty to actual bolt total
                Base.Transactions.Cache.SetValueExt<SOLine.orderQty>(line, totalAllocated);
                Base.Transactions.Cache.Update(line);

                totalBoltsAssigned += assignedBolts.Count;
                allocSummary.Add($"Ln{line.LineNbr}: {assignedBolts.Count} bolt(s), {totalAllocated} {line.UOM}");

                PXTrace.WriteInformation(
                    $"[AUTO-ALLOC] Ln{line.LineNbr}: {assignedBolts.Count} bolts, " +
                    $"total={totalAllocated}/{requestedQty} (max={maxQty})");
            }

            // Update order description
            if (totalBoltsAssigned > 0 || anyNoBolts)
            {
                string stamp = totalBoltsAssigned > 0
                    ? $"[AUTO-ALLOC] {totalBoltsAssigned} bolt(s) assigned"
                    : "[AUTO-ALLOC] No bolts — PO created";

                if (allocSummary.Count > 0 && allocSummary.Count <= 3)
                    stamp += " | " + string.Join(", ", allocSummary);

                string desc = order.OrderDesc ?? "";
                desc = desc.Contains("[AUTO-ALLOC")
                    ? System.Text.RegularExpressions.Regex.Replace(desc, @"\[AUTO-ALLOC[^\]]*\].*", stamp)
                    : (string.IsNullOrEmpty(desc) ? stamp : desc + " | " + stamp);

                Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order, desc);
                Base.Document.Cache.Update(order);
            }
        }

        #endregion

        #region Helpers

        /// <summary>
        /// Check if a line already has allocated splits with lot serials.
        /// If so, skip — already allocated from prior save or manual entry.
        /// </summary>
        private bool LineHasAllocatedSplits(SOLine line, SOOrder order)
        {
            foreach (SOLineSplit split in
                SelectFrom<SOLineSplit>
                    .Where<SOLineSplit.orderType.IsEqual<@P.AsString>
                        .And<SOLineSplit.orderNbr.IsEqual<@P.AsString>>
                        .And<SOLineSplit.lineNbr.IsEqual<@P.AsInt>>>
                    .View.ReadOnly.Select(Base, order.OrderType, order.OrderNbr, line.LineNbr))
            {
                if (!string.IsNullOrEmpty(split.LotSerialNbr))
                    return true;
            }
            return false;
        }

        /// <summary>
        /// Delete the default split that Acumatica auto-creates when a line is inserted.
        /// We replace it with our bolt-specific splits.
        /// </summary>
        private void DeleteDefaultSplits(SOLine line, SOOrder order)
        {
            var splitsToDelete = new List<SOLineSplit>();
            foreach (SOLineSplit split in
                SelectFrom<SOLineSplit>
                    .Where<SOLineSplit.orderType.IsEqual<@P.AsString>
                        .And<SOLineSplit.orderNbr.IsEqual<@P.AsString>>
                        .And<SOLineSplit.lineNbr.IsEqual<@P.AsInt>>>
                    .View.Select(Base, order.OrderType, order.OrderNbr, line.LineNbr))
            {
                // Delete splits without lot serial (default auto-created ones)
                if (string.IsNullOrEmpty(split.LotSerialNbr))
                    splitsToDelete.Add(split);
            }

            foreach (var split in splitsToDelete)
            {
                Base.Caches[typeof(SOLineSplit)].Delete(split);
            }
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
            // FIFO (oldest receipt) then largest bolt first (fewer splits)
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
