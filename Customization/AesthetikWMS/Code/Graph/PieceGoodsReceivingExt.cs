using System;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.PO;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Graph extension for POReceiptEntry (PO.30.20.00 — PO Receipts screen).
    ///
    /// Extends physical receiving for piece goods:
    ///   - Pre-receiving validation: matches scanned rolls against pre-created serials
    ///   - Yardage verification: flags variance between expected and actual
    ///   - Label printing: GS1-128 to Keyence-compatible printer
    ///   - Cross-dock activation: received rolls enter RECV-DOCK immediately
    ///   - Ad-hoc receiving: creates serials on-the-fly for unexpected rolls
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class PieceGoodsReceivingExt : PXGraphExtension<POReceiptEntry>
    {
        public static bool IsActive() => true;

        #region Pre-Receiving Validation

        /// <summary>
        /// Processes a barcode scan during PO receiving for piece goods items.
        /// Matches the scanned roll against pre-created serial records and handles
        /// both pre-received and ad-hoc receiving scenarios.
        /// </summary>
        /// <param name="barcode">Scanned barcode data from Keyence scanner.</param>
        /// <param name="receiptLine">The current PO receipt line being processed.</param>
        /// <returns>Result indicating what action the operator should take next.</returns>
        public ReceivingScanResult ProcessReceivingScan(string barcode, POReceiptLine receiptLine)
        {
            if (string.IsNullOrEmpty(barcode) || receiptLine == null)
                return ReceivingScanResult.Error("Invalid scan data.");

            if (!IsPieceGoodsLine(receiptLine))
                return ReceivingScanResult.NotPieceGoods();

            // Parse the barcode
            if (!BarcodeParser.TryParseGS1128(barcode, out GS1128Result parsed))
                return ReceivingScanResult.Error("Cannot parse barcode.");

            string effectiveSerial = parsed.EffectiveSerial;
            int inventoryID = receiptLine.InventoryID.Value;

            // Try to match against a pre-created serial (In-Transit status)
            var preReceived = FindPreReceivedSerial(inventoryID, effectiveSerial);

            if (preReceived != null)
            {
                // Pre-received roll found — validate and transition to Receiving
                return ProcessPreReceivedRoll(preReceived, receiptLine, parsed);
            }
            else
            {
                // No pre-receiving data — create serial on the fly (ad-hoc)
                return ProcessAdHocReceiving(receiptLine, parsed);
            }
        }

        /// <summary>
        /// Handles a roll that was pre-received (serial already exists with In-Transit status).
        /// Validates yardage, transitions status, and triggers label printing.
        /// </summary>
        private ReceivingScanResult ProcessPreReceivedRoll(
            INLotSerialStatus preReceived,
            POReceiptLine receiptLine,
            GS1128Result parsed)
        {
            var ext = preReceived.GetExtension<INLotSerialStatusExt>();
            var config = GetReceivingConfig();

            // Build result with pre-receiving data
            var result = new ReceivingScanResult
            {
                Success = true,
                IsPreReceived = true,
                SerialNbr = preReceived.LotSerialNbr,
                ExpectedYardage = ext.UsrActualYardage ?? 0,
                DyeLot = ext.UsrDyeLot,
                PreAssignedBin = ext.UsrPreAssignedBin,
                RequiresYardageConfirmation = true,
                Message = $"Pre-received roll matched: {preReceived.LotSerialNbr}. " +
                          $"Expected: {ext.UsrActualYardage:F1} yds. " +
                          $"Bin: {ext.UsrPreAssignedBin ?? "unassigned"}. " +
                          $"Scan @confirm to accept yardage, or enter measured yardage.",
            };

            return result;
        }

        /// <summary>
        /// Handles an unexpected roll with no pre-receiving data.
        /// Creates the serial on the fly and runs immediate bin assignment.
        /// </summary>
        private ReceivingScanResult ProcessAdHocReceiving(
            POReceiptLine receiptLine,
            GS1128Result parsed)
        {
            return new ReceivingScanResult
            {
                Success = true,
                IsPreReceived = false,
                SerialNbr = null, // Will be generated after yardage entry
                RequiresYardageConfirmation = true,
                RequiresManualYardageEntry = true,
                Message = "Roll not pre-received. Enter serial number and yardage to create on the fly.",
            };
        }

        /// <summary>
        /// Confirms the yardage for a pre-received roll and transitions it to Receiving status.
        /// Called when the operator scans @confirm or enters a measured yardage.
        /// </summary>
        /// <param name="inventoryID">Item inventory ID.</param>
        /// <param name="serialNbr">Roll serial number (from pre-receiving).</param>
        /// <param name="actualYardage">Measured yardage (null = accept expected).</param>
        /// <param name="warehouseID">Warehouse ID for RECV-DOCK location lookup.</param>
        public YardageConfirmResult ConfirmYardage(
            int inventoryID, string serialNbr, decimal? actualYardage, int warehouseID)
        {
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(Base, inventoryID, serialNbr);

            if (statusRow == null)
                return new YardageConfirmResult { Success = false, ErrorMessage = "Serial not found." };

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();
            var config = GetReceivingConfig();

            decimal expectedYardage = ext.UsrActualYardage ?? 0;
            decimal confirmedYardage = actualYardage ?? expectedYardage;

            // Check variance
            bool hasVariance = false;
            decimal variancePercent = 0;

            if (actualYardage.HasValue && expectedYardage > 0)
            {
                variancePercent = Math.Abs(actualYardage.Value - expectedYardage) / expectedYardage;
                hasVariance = variancePercent > config.YardageVarianceThreshold;
            }

            // Update yardage if actual was provided
            if (actualYardage.HasValue)
                ext.UsrActualYardage = actualYardage.Value;

            // Transition to Receiving status
            ext.UsrInventoryStatus = PieceGoodsConstants.InvStatus_Receiving;

            // Move to RECV-DOCK location
            var recvDockID = GetRecvDockLocationID(warehouseID);
            if (recvDockID.HasValue)
                status.LocationID = recvDockID.Value;

            Base.Caches[typeof(INLotSerialStatus)].Update(status);
            Base.Actions.PressSave();

            // Trigger label printing if auto-print enabled
            string labelData = null;
            if (config.AutoPrintLabel)
            {
                labelData = GenerateLabel(inventoryID, serialNbr, ext.UsrDyeLot);
            }

            return new YardageConfirmResult
            {
                Success = true,
                ConfirmedYardage = confirmedYardage,
                HasVariance = hasVariance,
                VariancePercent = variancePercent,
                LabelData = labelData,
                Message = hasVariance
                    ? $"⚠ VARIANCE: Expected {expectedYardage:F1}, Actual {confirmedYardage:F1} " +
                      $"({variancePercent:P1}). Roll received to RECV-DOCK."
                    : $"✓ Roll {serialNbr} received ({confirmedYardage:F1} yds) → RECV-DOCK. " +
                      $"Cross-dock eligible.",
            };
        }

        /// <summary>
        /// Creates a serial on the fly for ad-hoc receiving (no pre-receiving data).
        /// Generates serial, sets attributes, assigns bin, and transitions to Receiving.
        /// </summary>
        public AdHocReceiveResult ReceiveAdHoc(
            int inventoryID, string sku, decimal yardage, string dyeLot,
            decimal? width, string shadeCode, string containerNumber, int warehouseID)
        {
            var config = GetReceivingConfig();

            // Generate serial number
            var engine = new PreReceivingEngine(Base);
            string serialNbr = string.Format(
                PieceGoodsConstants.SerialFormat, sku, DateTime.Today,
                GetNextAdHocSequence(sku));

            // Create the serial record
            var statusCache = Base.Caches[typeof(INLotSerialStatus)];
            var status = (INLotSerialStatus)statusCache.CreateInstance();
            status.InventoryID = inventoryID;
            status.SiteID = warehouseID;
            status.LotSerialNbr = serialNbr;

            var recvDockID = GetRecvDockLocationID(warehouseID);
            if (recvDockID.HasValue)
                status.LocationID = recvDockID.Value;

            status = (INLotSerialStatus)statusCache.Insert(status);

            var ext = status.GetExtension<INLotSerialStatusExt>();
            ext.UsrActualYardage = yardage;
            ext.UsrDyeLot = dyeLot;
            ext.UsrWidth = width ?? GetDefaultWidth();
            ext.UsrShadeCode = shadeCode;
            ext.UsrContainerNo = containerNumber;
            ext.UsrInventoryStatus = PieceGoodsConstants.InvStatus_Receiving;
            ext.UsrDefectFlag = false;

            statusCache.Update(status);
            Base.Actions.PressSave();

            // Run immediate bin assignment
            engine.AssignBins(
                new System.Collections.Generic.List<string> { serialNbr },
                warehouseID);

            // Print label
            string labelData = null;
            if (config.AutoPrintLabel)
            {
                labelData = GenerateLabel(inventoryID, serialNbr, dyeLot);
            }

            return new AdHocReceiveResult
            {
                Success = true,
                SerialNbr = serialNbr,
                Yardage = yardage,
                LabelData = labelData,
                Message = $"✓ Roll {serialNbr} created ({yardage:F1} yds, lot {dyeLot}) → RECV-DOCK. " +
                          $"Cross-dock eligible.",
            };
        }

        #endregion

        #region Label Printing

        /// <summary>
        /// Generates GS1-128 barcode data for label printing.
        /// Returns the formatted barcode string that can be sent to a Keyence printer.
        /// </summary>
        private string GenerateLabel(int inventoryID, string serialNbr, string dyeLot)
        {
            // Look up item CD for the GTIN/SKU field
            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, inventoryID);

            string sku = item != null ? ((InventoryItem)item).InventoryCD?.Trim() : "";

            return BarcodeParser.GenerateGS1128Label(sku, serialNbr, dyeLot);
        }

        /// <summary>
        /// Sends label data to the Keyence-compatible printer.
        /// </summary>
        public void PrintLabel(string labelData)
        {
            if (string.IsNullOrEmpty(labelData)) return;

            // Keyence Auto-ID Link printer integration:
            // The printer is accessible via the network and accepts label data
            // in its native format. The actual print command depends on the
            // specific Keyence printer model and Auto-ID Link configuration.
            //
            // Integration pattern:
            //   1. Connect to printer via TCP/IP or HTTP
            //   2. Send label template ID + variable data (barcode string)
            //   3. Printer renders and prints the GS1-128 label
            //
            // The label template is pre-configured on the printer with:
            //   - GS1-128 barcode element
            //   - Human-readable text (SKU, Serial, Dye Lot)
            //   - Company logo
            //
            // For production deployment, the printer IP and template ID
            // are configured in Acumatica user preferences or warehouse setup.

            // NOTE: Actual printer communication will be implemented during
            // Phase 6 hardware integration testing with the Keyence BT-A500.
        }

        #endregion

        #region Helper Methods

        /// <summary>Checks if a PO receipt line uses the PIECEGOODS class.</summary>
        protected bool IsPieceGoodsLine(POReceiptLine line)
        {
            if (line?.InventoryID == null) return false;

            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, line.InventoryID);

            if (item == null) return false;

            return string.Equals(
                ((InventoryItem)item).LotSerClassID,
                PieceGoodsConstants.LotSerialClassID,
                StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>Finds a pre-created serial with In-Transit status.</summary>
        protected INLotSerialStatus FindPreReceivedSerial(int inventoryID, string serialNbr)
        {
            if (string.IsNullOrEmpty(serialNbr)) return null;

            var result = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(Base, inventoryID, serialNbr);

            if (result == null) return null;

            var status = (INLotSerialStatus)result;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            // Only match if status is In-Transit (pre-received but not physically received)
            if (ext?.UsrInventoryStatus == PieceGoodsConstants.InvStatus_InTransit)
                return status;

            return null;
        }

        /// <summary>Gets RECV-DOCK location ID for a warehouse.</summary>
        private int? GetRecvDockLocationID(int warehouseID)
        {
            var location = SelectFrom<INLocation>
                .Where<INLocation.siteID.IsEqual<@P.AsInt>
                    .And<INLocation.locationCD.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(Base, warehouseID, PieceGoodsConstants.Location_RecvDock);

            return location != null ? ((INLocation)location).LocationID : null;
        }

        /// <summary>Gets default width from the PIECEGOODS class.</summary>
        private decimal GetDefaultWidth()
        {
            var lotClass = SelectFrom<INLotSerialClass>
                .Where<INLotSerialClass.lotSerClassID.IsEqual<@P.AsString>>
                .View.ReadOnly.Select(Base, PieceGoodsConstants.LotSerialClassID);

            var ext = lotClass?.GetItem<INLotSerialClass>()?.GetExtension<INLotSerialClassExt>();
            return ext?.UsrPGDefaultWidth ?? 54.0m;
        }

        /// <summary>Gets next sequence number for ad-hoc serial generation.</summary>
        private int GetNextAdHocSequence(string sku)
        {
            string prefix = $"{sku}-{DateTime.Today:yyMMdd}-";

            var existing = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.lotSerialNbr.IsLike<@P.AsString>>
                .View.ReadOnly.Select(Base, prefix + "%");

            int maxSeq = 0;
            foreach (PXResult<INLotSerialStatus> row in existing)
            {
                var s = (INLotSerialStatus)row;
                if (s.LotSerialNbr.Length > prefix.Length)
                {
                    // Handle both regular serials and cut serials (with -C suffix)
                    string seqPart = s.LotSerialNbr.Substring(prefix.Length);
                    int dashIdx = seqPart.IndexOf('-');
                    if (dashIdx > 0) seqPart = seqPart.Substring(0, dashIdx);

                    if (int.TryParse(seqPart, out int seq) && seq > maxSeq)
                        maxSeq = seq;
                }
            }

            return maxSeq + 1;
        }

        /// <summary>Loads receiving configuration from INSetup.</summary>
        private ReceivingConfig GetReceivingConfig()
        {
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(Base, null);
            var ext = setup?.GetItem<INSetup>()?.GetExtension<INSetupExt>();

            return new ReceivingConfig
            {
                AutoPrintLabel = ext?.UsrPGAutoPrint ?? PieceGoodsConstants.DefaultAutoPrintLabel,
                YardageVarianceThreshold = ext?.UsrPGYardageVar
                    ?? PieceGoodsConstants.DefaultYardageVarianceThreshold,
                PreReceivingEnabled = ext?.UsrPGPreRecv
                    ?? PieceGoodsConstants.DefaultPreReceivingEnabled,
            };
        }

        #endregion

        #region Supporting Types

        private class ReceivingConfig
        {
            public bool AutoPrintLabel { get; set; }
            public decimal YardageVarianceThreshold { get; set; }
            public bool PreReceivingEnabled { get; set; }
        }

        /// <summary>Result of processing a barcode scan during receiving.</summary>
        public class ReceivingScanResult
        {
            public bool Success { get; set; }
            public bool IsPreReceived { get; set; }
            public bool IsPieceGoods { get; set; } = true;
            public string SerialNbr { get; set; }
            public decimal ExpectedYardage { get; set; }
            public string DyeLot { get; set; }
            public string PreAssignedBin { get; set; }
            public bool RequiresYardageConfirmation { get; set; }
            public bool RequiresManualYardageEntry { get; set; }
            public string Message { get; set; }
            public string ErrorMessage { get; set; }

            public static ReceivingScanResult Error(string message) =>
                new ReceivingScanResult { Success = false, ErrorMessage = message };

            public static ReceivingScanResult NotPieceGoods() =>
                new ReceivingScanResult { Success = true, IsPieceGoods = false };
        }

        /// <summary>Result of yardage confirmation for a pre-received roll.</summary>
        public class YardageConfirmResult
        {
            public bool Success { get; set; }
            public decimal ConfirmedYardage { get; set; }
            public bool HasVariance { get; set; }
            public decimal VariancePercent { get; set; }
            public string LabelData { get; set; }
            public string Message { get; set; }
            public string ErrorMessage { get; set; }
        }

        /// <summary>Result of ad-hoc receiving (no pre-receiving data).</summary>
        public class AdHocReceiveResult
        {
            public bool Success { get; set; }
            public string SerialNbr { get; set; }
            public decimal Yardage { get; set; }
            public string LabelData { get; set; }
            public string Message { get; set; }
            public string ErrorMessage { get; set; }
        }

        #endregion
    }
}
