using System;
using System.Collections;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;
using PX.Objects.SO.WMS;
using PX.BarcodeProcessing;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Graph extension for SOPickPackShip (SO.30.20.20 — Pick, Pack, Ship screen).
    ///
    /// Overrides the scan state machine to support:
    ///   - Auto-quantity mode: scan serial → qty auto-confirmed (no qty entry step)
    ///   - Roll attribute display: yardage, dye lot, width shown on scan confirmation
    ///   - Cut-to-order detection: when ordered qty &lt; roll qty, invokes CutToOrderEngine
    ///   - Cross-dock pick routing: routes picks to RECV-DOCK
    ///   - Compound GS1-128 barcode parsing via BarcodeParser helper
    ///
    /// The extension intercepts barcode processing for items assigned to the PIECEGOODS
    /// lot/serial class and provides textile-specific handling while falling through to
    /// standard WMS processing for all other items.
    ///
    /// Target: Acumatica 2024 R2 — PX.BarcodeProcessing framework
    /// </summary>
    public class PieceGoodsScanExtension : PXGraphExtension<SOPickPackShip>
    {
        public static bool IsActive() => true;

        #region Scan Mode State

        /// <summary>Current scan state for piece goods workflow.</summary>
        private PieceGoodsScanState _scanState = new PieceGoodsScanState();

        /// <summary>Lazy-initialized cut-to-order engine.</summary>
        private CutToOrderEngine _cutEngine;
        private CutToOrderEngine CutEngine =>
            _cutEngine ??= new CutToOrderEngine(Base);

        #endregion

        #region ProcessBarcode Override

        /// <summary>
        /// Intercepts barcode scans for PIECEGOODS items.
        ///
        /// State machine flow:
        ///   1. Parse barcode via BarcodeParser.TryParseGS1128()
        ///   2. If serial belongs to PIECEGOODS class:
        ///      a. Auto-confirm qty = 1 (skip quantity prompt)
        ///      b. Load and display roll attributes
        ///      c. Check for cut-to-order scenario
        ///   3. If not PIECEGOODS: fall through to standard processing
        /// </summary>
        protected virtual void ProcessPieceGoodsBarcode(string barcode)
        {
            // ── STEP 1: Parse barcode ──────────────────────────────────
            if (!BarcodeParser.TryParseGS1128(barcode, out GS1128Result parsed))
            {
                // Not a valid barcode — let standard processing handle it
                return;
            }

            string effectiveSerial = parsed.EffectiveSerial;
            if (string.IsNullOrEmpty(effectiveSerial))
                return;

            // ── STEP 2: Resolve serial to inventory record ─────────────
            var serialStatus = FindSerialStatus(effectiveSerial);
            if (serialStatus == null)
            {
                // Serial not found — could be an item barcode, fall through
                return;
            }

            int inventoryID = serialStatus.InventoryID.Value;

            // ── STEP 3: Check if this is a PIECEGOODS item ─────────────
            if (!IsPieceGoodsItem(inventoryID))
                return; // Fall through to standard WMS processing

            var rollAttrs = serialStatus.GetExtension<INLotSerialStatusExt>();
            if (rollAttrs == null) return;

            // ── STEP 4: Check for defect flag ──────────────────────────
            if (rollAttrs.UsrDefectFlag == true)
            {
                SetScanMessage(
                    $"WARNING: Roll {effectiveSerial} is flagged as DEFECTIVE. " +
                    $"Scan @override to use anyway, or scan a different roll.");
                _scanState.PendingDefectOverride = effectiveSerial;
                return;
            }

            // ── STEP 5: Check for cut-to-order ─────────────────────────
            decimal? orderedQty = GetCurrentPickLineQty();
            decimal rollYardage = rollAttrs.UsrActualYardage ?? 0;

            if (orderedQty.HasValue && orderedQty.Value < rollYardage && orderedQty.Value > 0)
            {
                // Cut-to-order scenario detected
                _scanState.PendingCut = new PendingCutInfo
                {
                    InventoryID = inventoryID,
                    SourceSerial = effectiveSerial,
                    OrderedYardage = orderedQty.Value,
                    RollYardage = rollYardage,
                    WarehouseID = serialStatus.SiteID.Value,
                    LocationID = serialStatus.LocationID.Value,
                };

                SetScanMessage(
                    $"CUT REQUIRED — Roll {effectiveSerial} has {rollYardage:F1} yds, " +
                    $"order needs {orderedQty.Value:F1} yds. " +
                    $"Scan @confirm to cut {orderedQty.Value:F1} yds, or enter custom yardage.");
                return;
            }

            // ── STEP 6: Full roll pick — auto-confirm qty ──────────────
            if (IsAutoQuantityEnabled())
            {
                ConfirmPickLine(inventoryID, effectiveSerial, serialStatus.SiteID.Value,
                    serialStatus.LocationID.Value, 1);
            }

            // ── STEP 7: Display roll attributes ────────────────────────
            DisplayRollAttributes(effectiveSerial, rollAttrs);
        }

        /// <summary>
        /// Handles @confirm and @override scan commands in the piece goods workflow.
        /// </summary>
        protected virtual void ProcessPieceGoodsCommand(string command)
        {
            if (string.Equals(command, PieceGoodsConstants.ScanCmd_Confirm,
                StringComparison.OrdinalIgnoreCase))
            {
                ProcessConfirmCommand();
            }
            else if (string.Equals(command, PieceGoodsConstants.ScanCmd_Override,
                StringComparison.OrdinalIgnoreCase))
            {
                ProcessOverrideCommand();
            }
        }

        /// <summary>
        /// Processes the @confirm command — executes pending cut-to-order.
        /// </summary>
        private void ProcessConfirmCommand()
        {
            if (_scanState.PendingCut == null)
            {
                SetScanMessage("Nothing to confirm.");
                return;
            }

            var cut = _scanState.PendingCut;

            // Validate the cut before executing
            var validation = CutEngine.ValidateCut(
                cut.InventoryID, cut.SourceSerial, cut.OrderedYardage);

            if (validation.SuggestFullRoll)
            {
                SetScanMessage(
                    $"Remnant would be {validation.RemnantYardage:F1} yds (below minimum). " +
                    $"Ship full roll? Scan @confirm again to ship full roll, " +
                    $"or scan @override to cut anyway.");
                _scanState.PendingFullRollConfirm = true;
                return;
            }

            // Execute the cut
            var result = CutEngine.ExecuteCut(
                cut.InventoryID, cut.SourceSerial, cut.OrderedYardage,
                cut.WarehouseID, cut.LocationID);

            if (result.Success)
            {
                // Assign the cut piece to the current pick line
                ConfirmPickLine(cut.InventoryID, result.CutPieceSerial,
                    cut.WarehouseID, cut.LocationID, 1);

                SetScanMessage(
                    $"CUT COMPLETE: {result.CutYardage:F1} yds from {cut.SourceSerial}. " +
                    $"Cut piece: {result.CutPieceSerial}. " +
                    $"Remnant: {result.RemnantYardage:F1} yds.");

                _scanState.PendingCut = null;
            }
            else
            {
                SetScanMessage($"CUT FAILED: {result.ErrorMessage}");
            }
        }

        /// <summary>
        /// Processes the @override command — overrides defect flag or full-roll suggestion.
        /// </summary>
        private void ProcessOverrideCommand()
        {
            if (_scanState.PendingFullRollConfirm && _scanState.PendingCut != null)
            {
                // Override: cut even though remnant is below minimum
                var cut = _scanState.PendingCut;
                var result = CutEngine.ExecuteCut(
                    cut.InventoryID, cut.SourceSerial, cut.OrderedYardage,
                    cut.WarehouseID, cut.LocationID);

                if (result.Success)
                {
                    ConfirmPickLine(cut.InventoryID, result.CutPieceSerial,
                        cut.WarehouseID, cut.LocationID, 1);

                    SetScanMessage(
                        $"CUT (override): {result.CutYardage:F1} yds. " +
                        $"Remnant: {result.RemnantYardage:F1} yds (below minimum).");
                }
                else
                {
                    SetScanMessage($"CUT FAILED: {result.ErrorMessage}");
                }

                _scanState.PendingCut = null;
                _scanState.PendingFullRollConfirm = false;
            }
            else if (!string.IsNullOrEmpty(_scanState.PendingDefectOverride))
            {
                // Override: use defective roll anyway
                string serial = _scanState.PendingDefectOverride;
                _scanState.PendingDefectOverride = null;

                // Re-process the barcode with defect check bypassed
                SetScanMessage($"Defect override accepted for {serial}. Processing...");

                var status = FindSerialStatus(serial);
                if (status != null && IsAutoQuantityEnabled())
                {
                    ConfirmPickLine(status.InventoryID.Value, serial,
                        status.SiteID.Value, status.LocationID.Value, 1);

                    var attrs = status.GetExtension<INLotSerialStatusExt>();
                    DisplayRollAttributes(serial, attrs);
                }
            }
        }

        #endregion

        #region Attribute Display

        /// <summary>
        /// Formats and displays roll attributes on the scan confirmation panel.
        /// Shows yardage, dye lot, width, shade, location, and defect status.
        /// </summary>
        private void DisplayRollAttributes(string serialNbr, INLotSerialStatusExt attrs)
        {
            if (attrs == null) return;

            string locationDisplay = attrs.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Receiving
                ? PieceGoodsConstants.Location_RecvDock
                : attrs.UsrPreAssignedBin ?? "—";

            string message =
                $"✓ {serialNbr} | " +
                $"{attrs.UsrActualYardage:F1} yds | " +
                $"Lot: {attrs.UsrDyeLot ?? "—"} | " +
                $"W: {attrs.UsrWidth:F0}\" | " +
                $"Shade: {attrs.UsrShadeCode ?? "—"} | " +
                $"Loc: {locationDisplay}";

            if (attrs.UsrDefectFlag == true)
                message += " | ⚠ DEFECT";

            SetScanMessage(message);
        }

        #endregion

        #region Helper Methods

        /// <summary>
        /// Checks whether the given inventory item uses the PIECEGOODS lot/serial class.
        /// </summary>
        protected bool IsPieceGoodsItem(int? inventoryID)
        {
            if (inventoryID == null) return false;

            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, inventoryID);

            if (item == null) return false;

            return string.Equals(
                ((InventoryItem)item).LotSerClassID,
                PieceGoodsConstants.LotSerialClassID,
                StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>
        /// Finds the INLotSerialStatus record for a given serial number.
        /// Searches across all warehouses if serial is globally unique.
        /// </summary>
        protected INLotSerialStatus FindSerialStatus(string serialNbr)
        {
            if (string.IsNullOrEmpty(serialNbr)) return null;

            var result = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>
                .View.ReadOnly.Select(Base, serialNbr);

            return result?.GetItem<INLotSerialStatus>();
        }

        /// <summary>
        /// Reads the auto-quantity mode setting from INSetup.
        /// </summary>
        protected bool IsAutoQuantityEnabled()
        {
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(Base, null);
            var ext = setup?.GetItem<INSetup>()?.GetExtension<INSetupExt>();
            return ext?.UsrPGAutoQtyMode == true;
        }

        /// <summary>
        /// Gets the ordered quantity for the current active pick line.
        /// Returns null if no active pick line or if the line is not for piece goods.
        /// </summary>
        protected decimal? GetCurrentPickLineQty()
        {
            // In Acumatica 2024 R2, the current pick line is tracked by the
            // SOPickPackShip state machine. Access via the scan header's
            // current pick list state.
            //
            // This implementation accesses the current shipment line's
            // ordered quantity (which represents the yardage for piece goods).

            // NOTE: The actual implementation depends on the exact SOPickPackShip
            // internal state. The scan header tracks the current line being picked.
            // Access pattern in 2024 R2:
            //   Base.HeaderView.Current.ScanState → gives current pick context
            //   From there, resolve the SOShipLine and its OpenQty

            // Placeholder — in production, wire to the actual SOPickPackShip state
            return null;
        }

        /// <summary>
        /// Confirms a pick line with the given serial and quantity.
        /// This is the action that would normally require qty entry;
        /// auto-quantity mode calls it with qty = 1 automatically.
        /// </summary>
        protected void ConfirmPickLine(
            int inventoryID, string serialNbr,
            int warehouseID, int locationID, decimal qty)
        {
            // In Acumatica 2024 R2 SOPickPackShip, confirming a pick involves:
            // 1. Setting the serial number on the current split line
            // 2. Setting the picked quantity
            // 3. Advancing the scan state machine to the next pick line
            //
            // The exact API depends on the ProcessBarcode() pipeline.
            // In 2024 R2, this is typically done via:
            //   ScanConfirm(serial, qty) or
            //   WriteScanResult(header, serial, qty)
            //
            // Cross-dock handling: if the roll is in RECV-DOCK, the location
            // on the split line should reference RECV-DOCK, not a bin.

            // Update cross-dock status if shipping from RECV-DOCK
            var statusRecord = FindSerialStatus(serialNbr);
            if (statusRecord != null)
            {
                var ext = statusRecord.GetExtension<INLotSerialStatusExt>();
                if (ext?.UsrInventoryStatus == PieceGoodsConstants.InvStatus_Receiving)
                {
                    // Cross-dock ship — notify the manager
                    var crossDock = Base.GetExtension<CrossDockManager>();
                    crossDock?.TransitionToShipped(inventoryID, serialNbr);
                }
            }
        }

        /// <summary>
        /// Sets the message displayed on the scanner screen.
        /// </summary>
        protected void SetScanMessage(string message)
        {
            // In Acumatica 2024 R2 PX.BarcodeProcessing, messages are set via:
            //   Base.ScanMessage = message;
            // or through the HeaderView's message/info fields.
            //
            // The exact mechanism depends on the scan framework version.
            // Keyence scanners display whatever text is in the scan response area.

            // This method will be wired to the actual scan message buffer
            // during integration testing with the Keyence hardware.
        }

        #endregion

        #region Scan State Types

        /// <summary>Tracks the current piece goods scan workflow state.</summary>
        private class PieceGoodsScanState
        {
            /// <summary>Pending cut-to-order operation awaiting confirmation.</summary>
            public PendingCutInfo PendingCut { get; set; }

            /// <summary>Whether the user has been advised to ship full roll instead of cutting.</summary>
            public bool PendingFullRollConfirm { get; set; }

            /// <summary>Serial of a defective roll awaiting override confirmation.</summary>
            public string PendingDefectOverride { get; set; }

            /// <summary>Resets all pending states.</summary>
            public void Reset()
            {
                PendingCut = null;
                PendingFullRollConfirm = false;
                PendingDefectOverride = null;
            }
        }

        /// <summary>Information about a pending cut-to-order operation.</summary>
        private class PendingCutInfo
        {
            public int InventoryID { get; set; }
            public string SourceSerial { get; set; }
            public decimal OrderedYardage { get; set; }
            public decimal RollYardage { get; set; }
            public int WarehouseID { get; set; }
            public int LocationID { get; set; }
        }

        #endregion
    }
}
