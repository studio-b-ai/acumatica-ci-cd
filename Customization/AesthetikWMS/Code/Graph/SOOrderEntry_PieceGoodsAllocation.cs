using System;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.CS;
using PX.Objects.IN;
using PX.Objects.SO;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Graph extension for SOOrderEntry (SO.30.10.00 — Sales Orders screen).
    ///
    /// Auto-allocates lot serial numbers for piece goods items when new lines
    /// are inserted. Works in both UI and REST API contexts.
    ///
    /// Behavior:
    ///   1. New SOLine inserted with a PIECENBR/PIECEGOODS lot class item
    ///   2. Queries available lots in the specified warehouse (FIFO)
    ///   3. Assigns the best lot's serial number to the line
    ///   4. Adjusts OrderQty to the lot's available quantity (full bolt)
    ///   5. Stamps [AUTO-ALLOC ACTIVE] on the order Description
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class SOOrderEntry_PieceGoodsAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        /// <summary>Re-entry guard to prevent recursive allocation.</summary>
        [ThreadStatic]
        private static bool _allocating;

        #region Event Handlers

        /// <summary>
        /// Fires when a new SOLine is inserted — both from UI interaction and REST API PUT.
        /// Checks if the item is a piece goods lot class, and if so, auto-assigns a lot.
        /// </summary>
        protected virtual void _(Events.RowInserted<SOLine> e)
        {
            if (_allocating) return;
            if (e.Row == null) return;

            SOLine line = e.Row;

            // Guard: skip if no inventory item set
            if (line.InventoryID == null) return;

            // Guard: skip if lot/serial already assigned by user
            if (!string.IsNullOrEmpty(line.LotSerialNbr)) return;

            // Guard: skip if no warehouse specified
            if (line.SiteID == null) return;

            // Check if this item uses a piece goods lot class
            if (!IsPieceGoodsItem(line.InventoryID.Value))
                return;

            try
            {
                _allocating = true;
                AllocateLotForLine(line);
            }
            finally
            {
                _allocating = false;
            }
        }

        #endregion

        #region Allocation Logic

        /// <summary>
        /// Finds the best available lot for a piece goods line and assigns it.
        /// Uses FIFO selection (oldest receipt date first), preferring fuller bolts.
        /// </summary>
        private void AllocateLotForLine(SOLine line)
        {
            // Query available lot/serial inventory for this item in the specified warehouse
            var availableLots = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>
                    .And<INLotSerialStatus.qtyOnHand.IsGreater<decimal>>>
                .OrderBy<INLotSerialStatus.receiptDate.Asc,
                         INLotSerialStatus.qtyOnHand.Desc>
                .View.ReadOnly.Select(Base, line.InventoryID, line.SiteID);

            if (availableLots == null || availableLots.Count == 0)
                return; // No inventory — skip silently

            // Take the first (oldest, fullest) lot
            var bestLot = (INLotSerialStatus)availableLots[0];
            string lotNbr = bestLot.LotSerialNbr;
            decimal availQty = bestLot.QtyOnHand ?? 0;

            if (string.IsNullOrEmpty(lotNbr) || availQty <= 0)
                return;

            // Update the line: assign lot and adjust quantity to full bolt
            var lineCache = Base.Transactions.Cache;
            lineCache.SetValueExt<SOLine.lotSerialNbr>(line, lotNbr);

            // Adjust quantity to full bolt (the lot's available quantity)
            if (availQty != (line.OrderQty ?? 0))
            {
                lineCache.SetValueExt<SOLine.orderQty>(line, availQty);
            }

            // Stamp the order Description with the allocation marker
            SOOrder order = Base.Document.Current;
            if (order != null)
            {
                string marker = $"[AUTO-ALLOC ACTIVE] Lot {lotNbr} ({availQty:F0} {line.UOM ?? "EA"})";
                string existingDesc = order.OrderDesc ?? "";

                // Don't duplicate the marker if already present
                if (!existingDesc.Contains("[AUTO-ALLOC"))
                {
                    string newDesc = string.IsNullOrEmpty(existingDesc)
                        ? marker
                        : $"{existingDesc} | {marker}";

                    Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order, newDesc);
                }
                else if (!existingDesc.Contains(lotNbr))
                {
                    // Multiple lines allocated — append this lot
                    string newDesc = $"{existingDesc} | Lot {lotNbr} ({availQty:F0} {line.UOM ?? "EA"})";
                    Base.Document.Cache.SetValueExt<SOOrder.orderDesc>(order, newDesc);
                }
            }
        }

        #endregion

        #region Helper Methods

        /// <summary>
        /// Checks if an inventory item uses a piece goods lot serial class.
        /// Supports both PIECENBR (production) and PIECEGOODS (constants) class IDs.
        /// </summary>
        private bool IsPieceGoodsItem(int inventoryID)
        {
            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, inventoryID);

            if (item == null) return false;

            string lotClass = ((InventoryItem)item).LotSerClassID?.Trim();

            if (string.IsNullOrEmpty(lotClass)) return false;

            return string.Equals(lotClass, "PIECENBR", StringComparison.OrdinalIgnoreCase)
                || string.Equals(lotClass, PieceGoodsConstants.LotSerialClassID, StringComparison.OrdinalIgnoreCase);
        }

        #endregion
    }
}
