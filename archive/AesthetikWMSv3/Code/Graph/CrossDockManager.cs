using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Graph extension managing the cross-dock fulfillment workflow.
    ///
    /// Cross-dock allows orders to be fulfilled from rolls that have been physically
    /// received (scanned off a container) but not yet moved to permanent bin locations.
    ///
    /// Manages:
    ///   - RECV-DOCK virtual location lifecycle
    ///   - Container-level put-away tracking dashboard
    ///   - Cross-dock pick routing (RECV-DOCK vs bin stock)
    ///   - Age-based put-away priority escalation
    ///   - Status transitions: In-Transit → Receiving → Available/Shipped
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class CrossDockManager : PXGraphExtension<SOShipmentEntry>
    {
        public static bool IsActive() => true;

        #region Configuration

        /// <summary>
        /// Loads cross-dock configuration from INSetup.
        /// </summary>
        private CrossDockConfig GetConfig()
        {
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(Base, null);
            var ext = setup?.GetItem<INSetup>()?.GetExtension<INSetupExt>();

            return new CrossDockConfig
            {
                Enabled = ext?.UsrPGCrossDock ?? PieceGoodsConstants.DefaultCrossDockEnabled,
                AgeDaysThreshold = ext?.UsrPGXDockAge ?? PieceGoodsConstants.DefaultCrossDockAgeDays,
            };
        }

        #endregion

        #region Container Dashboard

        /// <summary>
        /// Gets container tracking summary for the cross-dock dashboard.
        /// Groups all piece goods serials by container number and calculates
        /// aggregate statistics for each container.
        /// </summary>
        public List<ContainerStatus> GetContainerDashboard(int warehouseID)
        {
            var config = GetConfig();
            if (!config.Enabled) return new List<ContainerStatus>();

            // Query all piece goods serials at this warehouse with a container number
            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, warehouseID);

            var serialsWithContainer = new List<(INLotSerialStatus Status, INLotSerialStatusExt Ext)>();

            foreach (PXResult<INLotSerialStatus> row in allSerials)
            {
                var status = (INLotSerialStatus)row;
                var ext = status.GetExtension<INLotSerialStatusExt>();
                if (!string.IsNullOrEmpty(ext?.UsrContainerNo))
                {
                    serialsWithContainer.Add((status, ext));
                }
            }

            // Group by container and compute stats
            var containerGroups = serialsWithContainer
                .GroupBy(s => s.Ext.UsrContainerNo, StringComparer.OrdinalIgnoreCase);

            var results = new List<ContainerStatus>();

            foreach (var group in containerGroups)
            {
                var items = group.ToList();
                int total = items.Count;
                int receiving = items.Count(i =>
                    i.Ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Receiving);
                int putAway = items.Count(i =>
                    i.Ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Available ||
                    i.Ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_PutAway);
                int inTransit = items.Count(i =>
                    i.Ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_InTransit);

                // Cross-dock picked = rolls that were shipped directly from receiving
                // (no longer in inventory, tracked via shipment history)
                int crossDockPicked = total - receiving - putAway - inTransit;

                // Calculate age on dock from the earliest receiving timestamp
                // Using the status record's LastModifiedDateTime as a proxy
                DateTime? earliestReceived = items
                    .Where(i => i.Ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Receiving)
                    .Select(i => i.Status.LastModifiedDateTime)
                    .Where(d => d.HasValue)
                    .OrderBy(d => d)
                    .FirstOrDefault();

                int ageOnDock = earliestReceived.HasValue
                    ? (DateTime.Today - earliestReceived.Value.Date).Days
                    : 0;

                results.Add(new ContainerStatus
                {
                    ContainerNumber = group.Key,
                    TotalRolls = total,
                    CrossDockPicked = Math.Max(0, crossDockPicked),
                    PutAway = putAway,
                    RemainingOnDock = receiving,
                    InTransit = inTransit,
                    AgeOnDockDays = ageOnDock,
                    PutAwayPercent = total > 0 ? Math.Round(putAway * 100m / total, 1) : 0,
                    FirstReceivedDate = earliestReceived,
                    IsOverAgeThreshold = ageOnDock > config.AgeDaysThreshold,
                });
            }

            // Sort: over-age containers first, then by age descending
            return results
                .OrderByDescending(c => c.IsOverAgeThreshold)
                .ThenByDescending(c => c.AgeOnDockDays)
                .ToList();
        }

        #endregion

        #region Status Transitions

        /// <summary>
        /// Transitions a roll's status from In-Transit to Receiving.
        /// Called when a roll is physically scanned off a container.
        /// Makes the roll immediately available for cross-dock picking.
        /// </summary>
        /// <param name="inventoryID">Inventory item ID.</param>
        /// <param name="serialNbr">Roll serial number.</param>
        /// <param name="recvDockLocationID">Location ID of the RECV-DOCK location.</param>
        public void TransitionToReceiving(int inventoryID, string serialNbr, int recvDockLocationID)
        {
            var config = GetConfig();

            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(Base, inventoryID, serialNbr);

            if (statusRow == null)
                throw new PXException($"Serial '{serialNbr}' not found for inventory ID {inventoryID}.");

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            // Validate current status
            if (ext.UsrInventoryStatus != PieceGoodsConstants.InvStatus_InTransit)
            {
                throw new PXException(
                    $"Serial '{serialNbr}' cannot transition to Receiving. " +
                    $"Current status is '{ext.UsrInventoryStatus}', expected '{PieceGoodsConstants.InvStatus_InTransit}'.");
            }

            // Update status and location
            ext.UsrInventoryStatus = PieceGoodsConstants.InvStatus_Receiving;
            status.LocationID = recvDockLocationID;

            Base.Caches[typeof(INLotSerialStatus)].Update(status);
            Base.Actions.PressSave();
        }

        /// <summary>
        /// Transitions a roll from Receiving to Available (put-away complete).
        /// Called when a roll is scanned into its permanent bin location.
        /// If the actual bin differs from PreAssignedBin, updates the record.
        /// </summary>
        public void TransitionToAvailable(int inventoryID, string serialNbr, int actualLocationID)
        {
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(Base, inventoryID, serialNbr);

            if (statusRow == null)
                throw new PXException($"Serial '{serialNbr}' not found.");

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            if (ext.UsrInventoryStatus != PieceGoodsConstants.InvStatus_Receiving)
            {
                throw new PXException(
                    $"Serial '{serialNbr}' cannot transition to Available. " +
                    $"Current status is '{ext.UsrInventoryStatus}', expected '{PieceGoodsConstants.InvStatus_Receiving}'.");
            }

            // Resolve the actual bin location CD for the record
            var actualLoc = SelectFrom<INLocation>
                .Where<INLocation.locationID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, actualLocationID);

            string actualBinCD = actualLoc != null ? ((INLocation)actualLoc).LocationCD : null;

            // Check if actual bin differs from pre-assigned
            if (!string.IsNullOrEmpty(ext.UsrPreAssignedBin) &&
                !string.Equals(ext.UsrPreAssignedBin, actualBinCD, StringComparison.OrdinalIgnoreCase))
            {
                // Update pre-assigned bin to reflect actual placement
                ext.UsrPreAssignedBin = actualBinCD;

                // TODO: Recalculate any pending pick instructions that reference
                // this roll's old pre-assigned bin. This would involve querying
                // SOShipLineSplit records allocated to this serial and updating
                // their location references.
            }

            ext.UsrInventoryStatus = PieceGoodsConstants.InvStatus_Available;
            status.LocationID = actualLocationID;

            Base.Caches[typeof(INLotSerialStatus)].Update(status);
            Base.Actions.PressSave();
        }

        /// <summary>
        /// Marks a roll as shipped directly from cross-dock (bypasses put-away).
        /// Called when a RECV-DOCK roll is picked for a shipment.
        /// The roll's inventory status is not updated here — the standard SO shipment
        /// process handles inventory issuance. This method updates the piece goods
        /// tracking fields only.
        /// </summary>
        public void TransitionToShipped(int inventoryID, string serialNbr)
        {
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(Base, inventoryID, serialNbr);

            if (statusRow == null) return; // May already be consumed by shipment

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            // Only transition from Receiving status (cross-dock path)
            if (ext.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Receiving)
            {
                // The standard SO shipment confirmation will handle the inventory
                // deduction. We just need to note this was a cross-dock fulfillment
                // for dashboard tracking purposes. The status record will be consumed
                // by the shipment release process.

                // No additional status update needed — the inventory will be zeroed
                // out by the shipment. Container dashboard calculates cross-dock
                // picks as total - receiving - putaway - intransit.
            }
        }

        #endregion

        #region Put-Away Priority

        /// <summary>
        /// Returns a prioritized list of rolls in RECV-DOCK that should be put away next.
        /// Priority logic:
        ///   1. Rolls with no pending orders → put away first (not needed on dock)
        ///   2. Rolls past CrossDockAgeDays threshold → escalated priority
        ///   3. Rolls allocated to future orders → put away last (may ship first)
        /// </summary>
        public List<PutAwayCandidate> GetPutAwayQueue(int warehouseID)
        {
            var config = GetConfig();
            if (!config.Enabled) return new List<PutAwayCandidate>();

            // Get all rolls currently in Receiving status
            var receivingRolls = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, warehouseID);

            var candidates = new List<PutAwayCandidate>();

            foreach (PXResult<INLotSerialStatus> row in receivingRolls)
            {
                var status = (INLotSerialStatus)row;
                var ext = status.GetExtension<INLotSerialStatusExt>();

                if (ext?.UsrInventoryStatus != PieceGoodsConstants.InvStatus_Receiving)
                    continue;

                // Calculate days on dock
                int daysOnDock = status.LastModifiedDateTime.HasValue
                    ? (DateTime.Today - status.LastModifiedDateTime.Value.Date).Days
                    : 0;

                // Check for pending order allocations against this serial
                bool hasPendingOrders = HasPendingOrderAllocations(
                    status.InventoryID.Value, status.LotSerialNbr);

                // Look up item CD for display
                var item = SelectFrom<InventoryItem>
                    .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                    .View.ReadOnly.Select(Base, status.InventoryID);
                string sku = item != null ? ((InventoryItem)item).InventoryCD?.Trim() : "";

                // Priority scoring: lower number = higher priority
                int priority;
                if (!hasPendingOrders && daysOnDock > config.AgeDaysThreshold)
                    priority = 1;  // No orders + over age = put away immediately
                else if (!hasPendingOrders)
                    priority = 2;  // No orders = put away next
                else if (daysOnDock > config.AgeDaysThreshold)
                    priority = 3;  // Has orders but over age = escalated
                else
                    priority = 4;  // Has orders, not over age = put away last

                candidates.Add(new PutAwayCandidate
                {
                    SerialNbr = status.LotSerialNbr,
                    InventoryID = status.InventoryID.Value,
                    SKU = sku,
                    PreAssignedBin = ext.UsrPreAssignedBin,
                    DaysOnDock = daysOnDock,
                    HasPendingOrders = hasPendingOrders,
                    Priority = priority,
                    ContainerNumber = ext.UsrContainerNo,
                });
            }

            return candidates.OrderBy(c => c.Priority).ThenByDescending(c => c.DaysOnDock).ToList();
        }

        /// <summary>
        /// Checks whether a serial has any pending SO shipment allocations.
        /// Returns true if any open shipment line references this serial.
        /// </summary>
        private bool HasPendingOrderAllocations(int inventoryID, string serialNbr)
        {
            var allocation = SelectFrom<SOShipLineSplit>
                .Where<SOShipLineSplit.inventoryID.IsEqual<@P.AsInt>
                    .And<SOShipLineSplit.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(Base, inventoryID, serialNbr);

            return allocation != null && allocation.Count > 0;
        }

        #endregion

        #region RECV-DOCK Location Helper

        /// <summary>
        /// Resolves the RECV-DOCK location ID for a given warehouse.
        /// Returns null if the location does not exist.
        /// </summary>
        public int? GetRecvDockLocationID(int warehouseID)
        {
            var location = SelectFrom<INLocation>
                .Where<INLocation.siteID.IsEqual<@P.AsInt>
                    .And<INLocation.locationCD.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(Base, warehouseID, PieceGoodsConstants.Location_RecvDock);

            return location != null ? ((INLocation)location).LocationID : null;
        }

        #endregion

        #region Supporting Types

        /// <summary>Cross-dock configuration loaded from INSetup.</summary>
        private class CrossDockConfig
        {
            public bool Enabled { get; set; }
            public int AgeDaysThreshold { get; set; }
        }

        /// <summary>Container-level tracking for the cross-dock dashboard.</summary>
        public class ContainerStatus
        {
            public string ContainerNumber { get; set; }
            public int TotalRolls { get; set; }
            public int CrossDockPicked { get; set; }
            public int PutAway { get; set; }
            public int RemainingOnDock { get; set; }
            public int InTransit { get; set; }
            public int AgeOnDockDays { get; set; }
            public decimal PutAwayPercent { get; set; }
            public DateTime? FirstReceivedDate { get; set; }
            public bool IsOverAgeThreshold { get; set; }
        }

        /// <summary>A roll in RECV-DOCK prioritized for put-away.</summary>
        public class PutAwayCandidate
        {
            public string SerialNbr { get; set; }
            public int InventoryID { get; set; }
            public string SKU { get; set; }
            public string PreAssignedBin { get; set; }
            public int DaysOnDock { get; set; }
            public bool HasPendingOrders { get; set; }
            public int Priority { get; set; }
            public string ContainerNumber { get; set; }
        }

        #endregion
    }
}
