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
    ///   3. If bolts don't cover full request, create unallocated remainder split
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
                    PXTrace.WriteError($"[AUTO-ALLOC] Failed: {ex.Message}\n{ex.StackTrace}");

                    // Revert any partial cache mutations from failed allocation
                    // by rolling back Inserted/Updated/Deleted splits for this order
                    RevertPendingSplitChanges(order);
                }
            }

            baseMethod();
        }

        #endregion

        #region UI Warnings

        protected void _(Events.RowSelected<SOLine> e)
        {
            if (e.Row == null) return;
            SOLine line = e.Row;

            // Gate on order description as a cheap pre-filter before querying splits.
            // Note: this couples to the alloc stamp format — if the stamp text changes,
            // update this check too. The split query is the source of truth.
            SOOrder order = Base.Document.Current;
            if (order?.OrderDesc != null && order.OrderDesc.Contains("unallocated"))
            {
                // Check if this specific line has unallocated splits
                bool hasUnallocated = false;
                bool hasAllocated = false;
                foreach (SOLineSplit split in
                    SelectFrom<SOLineSplit>
                        .Where<SOLineSplit.orderType.IsEqual<@P.AsString>
                            .And<SOLineSplit.orderNbr.IsEqual<@P.AsString>>
                            .And<SOLineSplit.lineNbr.IsEqual<@P.AsInt>>>
                        .View.ReadOnly.Select(Base, line.OrderType, line.OrderNbr, line.LineNbr))
                {
                    if (split.IsAllocated == true && !string.IsNullOrEmpty(split.LotSerialNbr))
                        hasAllocated = true;
                    if (split.IsAllocated != true && string.IsNullOrEmpty(split.LotSerialNbr))
                        hasUnallocated = true;
                }

                if (hasAllocated && hasUnallocated)
                {
                    PXUIFieldAttribute.SetWarning<SOLine.orderQty>(
                        e.Cache, line,
                        "Partially allocated — not enough bolts in stock to cover full quantity. " +
                        "Remainder is unallocated.");
                }
            }
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

                // Only auto-allocate newly added lines — if a user modifies an
                // existing line (e.g. rejects a bolt), leave it alone for DRP
                var lineStatus = Base.Transactions.Cache.GetStatus(line);
                if (lineStatus != PXEntryStatus.Inserted)
                    continue;

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

                // Strategy: prefer single bolt that covers the full request
                // 1. Tightest fit >= requestedQty within overship cap, then FIFO
                // 2. Fall back to multi-bolt FIFO if no single bolt works
                decimal totalAllocated = 0m;
                var assignedBolts = new List<BoltCandidate>();

                // Try single bolt first: >= requestedQty, <= maxQty, tightest fit, then FIFO
                var singleBolt = bolts
                    .Where(b => b.QtyOnHand >= requestedQty && b.QtyOnHand <= maxQty)
                    .OrderBy(b => b.QtyOnHand)                       // tightest fit first
                    .ThenBy(b => b.ReceiptDate ?? DateTime.MaxValue)  // then FIFO
                    .FirstOrDefault();

                if (singleBolt != null)
                {
                    assignedBolts.Add(singleBolt);
                    usedSerials.Add(singleBolt.LotSerialNbr);
                    totalAllocated = singleBolt.QtyOnHand;
                }
                else
                {
                    // Multi-bolt fallback: FIFO, accumulate up to overship cap
                    var sorted = SortBolts(bolts);
                    foreach (var bolt in sorted)
                    {
                        if (totalAllocated >= requestedQty) break;

                        if (totalAllocated + bolt.QtyOnHand > maxQty)
                        {
                            // Try to find a smaller bolt that fits the remaining cap
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
                }

                if (assignedBolts.Count == 0) continue;

                // Resolve InvtMult and Operation from order type config (PC/FO may leave these null)
                string lineOperation = line.Operation ?? SOOperation.Issue;
                short lineInvtMult = line.InvtMult ?? ResolveInvtMult(line.OrderType, lineOperation);

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
                    split.Operation = lineOperation;
                    split.InvtMult = lineInvtMult;

                    Base.Caches[typeof(SOLineSplit)].Insert(split);

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Ln{line.LineNbr}: split {bolt.LotSerialNbr} qty={bolt.QtyOnHand}");
                }

                // If bolts don't cover full request, create unallocated remainder split
                if (totalAllocated < requestedQty)
                {
                    decimal remainder = requestedQty - totalAllocated;
                    var remainderSplit = (SOLineSplit)Base.Caches[typeof(SOLineSplit)].CreateInstance();
                    remainderSplit.OrderType = line.OrderType;
                    remainderSplit.OrderNbr = line.OrderNbr;
                    remainderSplit.LineNbr = line.LineNbr;
                    remainderSplit.InventoryID = line.InventoryID;
                    remainderSplit.SubItemID = line.SubItemID;
                    remainderSplit.SiteID = line.SiteID;
                    remainderSplit.LocationID = line.LocationID;
                    remainderSplit.Qty = remainder;
                    remainderSplit.UOM = line.UOM;
                    remainderSplit.IsAllocated = false;
                    remainderSplit.Operation = lineOperation;
                    remainderSplit.InvtMult = lineInvtMult;

                    Base.Caches[typeof(SOLineSplit)].Insert(remainderSplit);

                    PXTrace.WriteInformation(
                        $"[AUTO-ALLOC] Ln{line.LineNbr}: remainder split qty={remainder} (unallocated)");
                }
                // Do NOT override SOLine.OrderQty — preserve user's requested quantity

                totalBoltsAssigned += assignedBolts.Count;
                string partialNote = totalAllocated < requestedQty
                    ? $" (partial — {requestedQty - totalAllocated} unallocated)"
                    : "";
                allocSummary.Add($"Ln{line.LineNbr}: {assignedBolts.Count} bolt(s), {totalAllocated} {line.UOM}{partialNote}");

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
                if (string.IsNullOrEmpty(status.LotSerialNbr)) continue;
                if (assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail = status.QtyAvail ?? 0;

                // Use QtyAvail (not QtyOnHand) as the allocatable amount —
                // QtyAvail accounts for existing allocations on other orders
                if (qtyAvail <= 0) continue;

                // Skip bolts where availability doesn't match on-hand
                // (partially allocated to other orders)
                if (qtyAvail != qtyOnHand) continue;

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyAvail,  // Use QtyAvail as the allocatable amount
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

        private short ResolveInvtMult(string orderType, string operation)
        {
            SOOrderTypeOperation opConfig = SelectFrom<SOOrderTypeOperation>
                .Where<SOOrderTypeOperation.orderType.IsEqual<@P.AsString>
                    .And<SOOrderTypeOperation.operation.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(Base, orderType, operation);

            return opConfig?.InvtMult ?? (short)1;
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

        /// <summary>
        /// Revert any cache mutations made during a failed allocation attempt.
        /// This prevents partial/corrupt split data from being persisted.
        /// Covers SOLineSplit (inserted/deleted) and SOLine (updated POCreate).
        /// </summary>
        private void RevertPendingSplitChanges(SOOrder order)
        {
            var splitCache = Base.Caches[typeof(SOLineSplit)];

            // Collect refs first to avoid modifying collection during iteration
            var toRevert = new List<SOLineSplit>();

            foreach (SOLineSplit split in splitCache.Inserted)
            {
                if (split.OrderType == order.OrderType && split.OrderNbr == order.OrderNbr)
                    toRevert.Add(split);
            }

            foreach (var split in toRevert)
            {
                splitCache.Remove(split);
            }

            // Also revert any deleted default splits
            var toRestore = new List<SOLineSplit>();
            foreach (SOLineSplit split in splitCache.Deleted)
            {
                if (split.OrderType == order.OrderType && split.OrderNbr == order.OrderNbr)
                    toRestore.Add(split);
            }

            foreach (var split in toRestore)
            {
                splitCache.SetStatus(split, PXEntryStatus.Notchanged);
            }

            // Revert SOLine updates (e.g. POCreate set during no-bolts path)
            var lineCache = Base.Transactions.Cache;
            var linesToRevert = new List<SOLine>();
            foreach (SOLine line in lineCache.Updated)
            {
                if (line.OrderType == order.OrderType && line.OrderNbr == order.OrderNbr)
                    linesToRevert.Add(line);
            }

            foreach (var line in linesToRevert)
            {
                lineCache.SetStatus(line, PXEntryStatus.Notchanged);
            }

            PXTrace.WriteWarning(
                $"[AUTO-ALLOC] Reverted {toRevert.Count} inserted + {toRestore.Count} deleted splits + {linesToRevert.Count} updated lines after failure");
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
