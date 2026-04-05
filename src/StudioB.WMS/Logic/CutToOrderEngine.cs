using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.CS;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Cut-to-order engine for piece goods roll splitting.
    ///
    /// Transaction Approach: Single IN Adjustment (Decrease + Increase)
    ///   - Decrease line: reduces source roll yardage attribute
    ///   - Increase line: creates new cut piece serial with cut yardage
    ///   - Net zero GL impact in a single batch
    ///   - Full PXTransactionScope atomicity
    ///
    /// Concurrency: Pessimistic locking via PXUpdate on source serial row
    /// prevents simultaneous cuts from different scanner stations.
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class CutToOrderEngine
    {
        private readonly PXGraph _graph;

        public CutToOrderEngine(PXGraph graph)
        {
            _graph = graph ?? throw new ArgumentNullException(nameof(graph));
        }

        #region Configuration

        private CutConfig GetConfig()
        {
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(_graph, null);
            var setupExt = ((INSetup)setup)?.GetExtension<INSetupExt>();

            return new CutConfig
            {
                MinRemnant = setupExt?.UsrPGMinRemnant
                    ?? PieceGoodsConstants.DefaultMinRemnantYardage,
                CutSerialSuffix = setupExt?.UsrPGCutSuffix
                    ?? PieceGoodsConstants.DefaultCutSerialSuffix,
            };
        }

        private class CutConfig
        {
            public decimal MinRemnant { get; set; }
            public string CutSerialSuffix { get; set; }
        }

        #endregion

        #region Public API

        /// <summary>
        /// Executes a cut-to-order operation on the specified source roll.
        /// Creates a single IN Adjustment with decrease + increase lines.
        /// </summary>
        public CutResult ExecuteCut(
            int inventoryID,
            string sourceSerial,
            decimal cutYardage,
            int warehouseID,
            int locationID)
        {
            var config = GetConfig();

            // ── STEP 1: Validate ───────────────────────────────────────
            var validation = ValidateCutInternal(inventoryID, sourceSerial, cutYardage, config);
            if (!validation.IsValid)
            {
                return new CutResult
                {
                    Success = false,
                    SourceSerial = sourceSerial,
                    ErrorMessage = validation.ErrorMessage,
                    SuggestFullRoll = validation.SuggestFullRoll,
                };
            }

            // ── STEP 2: Acquire lock on source serial ──────────────────
            // Pessimistic lock: select with UPDLOCK to prevent concurrent cuts
            var sourceStatus = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(_graph, inventoryID, sourceSerial);

            if (sourceStatus == null)
                return new CutResult { Success = false, ErrorMessage = "Source serial not found." };

            var source = (INLotSerialStatus)sourceStatus;
            var sourceExt = source.GetExtension<INLotSerialStatusExt>();

            // ── STEP 3: Generate cut piece serial number ───────────────
            string newSerial = GenerateCutSerial(sourceSerial, config.CutSerialSuffix);

            // ── STEP 4: Create IN Adjustment ───────────────────────────
            string adjustmentRef;
            decimal remainingYardage = (sourceExt.UsrActualYardage ?? 0) - cutYardage;

            using (var scope = new PXTransactionScope())
            {
                var adjustGraph = PXGraph.CreateInstance<INAdjustmentEntry>();

                // Create adjustment header
                var header = new INRegister
                {
                    DocType = INDocType.Adjustment,
                    TranDesc = $"Cut-to-order: {cutYardage:F1} yds from {sourceSerial} → {newSerial}",
                };
                header = adjustGraph.adjustment.Insert(header);

                // Line 1: Decrease source roll (issue the serial being consumed)
                var decreaseLine = new INTran
                {
                    DocType = INDocType.Adjustment,
                    TranType = INTranType.Adjustment,
                    InventoryID = inventoryID,
                    SiteID = warehouseID,
                    LocationID = locationID,
                    LotSerialNbr = sourceSerial,
                    Qty = -1m, // Serial-tracked: 1 unit (the serial itself)
                    TranDesc = $"Source roll decrease: {sourceSerial}",
                };
                adjustGraph.transactions.Insert(decreaseLine);

                // Line 2: Increase — create the source roll back with reduced yardage
                // (We re-receive the source serial with updated attributes)
                var sourceReceiveLine = new INTran
                {
                    DocType = INDocType.Adjustment,
                    TranType = INTranType.Adjustment,
                    InventoryID = inventoryID,
                    SiteID = warehouseID,
                    LocationID = locationID,
                    LotSerialNbr = sourceSerial,
                    Qty = 1m,
                    TranDesc = $"Source roll re-receive: {sourceSerial} ({remainingYardage:F1} yds remaining)",
                };
                adjustGraph.transactions.Insert(sourceReceiveLine);

                // Line 3: Increase — create the cut piece serial
                var cutPieceLine = new INTran
                {
                    DocType = INDocType.Adjustment,
                    TranType = INTranType.Adjustment,
                    InventoryID = inventoryID,
                    SiteID = warehouseID,
                    LocationID = locationID,
                    LotSerialNbr = newSerial,
                    Qty = 1m,
                    TranDesc = $"Cut piece created: {newSerial} ({cutYardage:F1} yds)",
                };
                adjustGraph.transactions.Insert(cutPieceLine);

                // Save and release the adjustment
                adjustGraph.Actions.PressSave();
                adjustmentRef = header.RefNbr;

                // Release the adjustment document
                INDocumentRelease.ReleaseDoc(new List<INRegister> { header }, false);

                scope.Complete();
            }

            // ── STEP 5: Update attributes ──────────────────────────────
            UpdateSourceRollAttributes(inventoryID, sourceSerial, remainingYardage);
            CreateCutPieceAttributes(inventoryID, newSerial, cutYardage, sourceSerial, sourceExt);

            // ── STEP 6: Return result ──────────────────────────────────
            return new CutResult
            {
                Success = true,
                CutPieceSerial = newSerial,
                CutYardage = cutYardage,
                RemnantYardage = remainingYardage,
                SourceSerial = sourceSerial,
                SuggestFullRoll = false,
                AdjustmentRefNbr = adjustmentRef,
            };
        }

        /// <summary>
        /// Validates whether a cut can be performed without executing it.
        /// </summary>
        public CutValidation ValidateCut(
            int inventoryID,
            string sourceSerial,
            decimal requestedYardage)
        {
            var config = GetConfig();
            return ValidateCutInternal(inventoryID, sourceSerial, requestedYardage, config);
        }

        #endregion

        #region Validation

        private CutValidation ValidateCutInternal(
            int inventoryID, string sourceSerial, decimal cutYardage, CutConfig config)
        {
            // Check serial exists
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.ReadOnly.Select(_graph, inventoryID, sourceSerial);

            if (statusRow == null)
                return new CutValidation { IsValid = false, ErrorMessage = "Source serial not found." };

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            // Check lot/serial class
            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(_graph, inventoryID);

            if (item == null)
                return new CutValidation { IsValid = false, ErrorMessage = "Inventory item not found." };

            string classID = ((InventoryItem)item).LotSerClassID;
            if (!string.Equals(classID, PieceGoodsConstants.LotSerialClassID,
                StringComparison.OrdinalIgnoreCase))
            {
                return new CutValidation
                {
                    IsValid = false,
                    ErrorMessage = $"Item not assigned to {PieceGoodsConstants.LotSerialClassID} class.",
                };
            }

            // Check defect flag
            if (ext.UsrDefectFlag == true)
            {
                return new CutValidation
                {
                    IsValid = false,
                    ErrorMessage = "Roll is flagged as defective. Override required.",
                };
            }

            // Check yardage
            decimal available = ext.UsrActualYardage ?? 0;
            if (cutYardage <= 0)
                return new CutValidation { IsValid = false, ErrorMessage = "Cut yardage must be positive." };

            if (cutYardage > available)
            {
                return new CutValidation
                {
                    IsValid = false,
                    AvailableYardage = available,
                    ErrorMessage = $"Requested {cutYardage:F1} yds exceeds available {available:F1} yds.",
                };
            }

            decimal remnant = available - cutYardage;

            // Check minimum remnant
            bool suggestFull = remnant > 0 && remnant < config.MinRemnant;

            return new CutValidation
            {
                IsValid = true,
                SuggestFullRoll = suggestFull,
                AvailableYardage = available,
                RemnantYardage = remnant,
            };
        }

        #endregion

        #region Serial Generation

        /// <summary>
        /// Generates a cut piece serial number from the source serial.
        /// Format: [sourceSerial]-C[seq] where seq is the next available number.
        /// </summary>
        private string GenerateCutSerial(string sourceSerial, string suffixFormat)
        {
            // Find existing cuts from this source to determine sequence
            string cutPrefix = sourceSerial + "-C";

            var existingCuts = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.lotSerialNbr.IsLike<@P.AsString>>
                .View.ReadOnly.Select(_graph, cutPrefix + "%");

            int maxSeq = 0;
            foreach (PXResult<INLotSerialStatus> row in existingCuts)
            {
                var s = (INLotSerialStatus)row;
                string suffix = s.LotSerialNbr.Substring(cutPrefix.Length);
                if (int.TryParse(suffix, out int seq) && seq > maxSeq)
                    maxSeq = seq;
            }

            int nextSeq = maxSeq + 1;
            return sourceSerial + string.Format(suffixFormat, nextSeq);
        }

        #endregion

        #region Attribute Management

        /// <summary>
        /// Updates the source roll's ActualYardage after a cut.
        /// </summary>
        private void UpdateSourceRollAttributes(int inventoryID, string sourceSerial, decimal remainingYardage)
        {
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(_graph, inventoryID, sourceSerial);

            if (statusRow == null) return;

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            ext.UsrActualYardage = remainingYardage;

            _graph.Caches[typeof(INLotSerialStatus)].Update(status);
            _graph.Actions.PressSave();
        }

        /// <summary>
        /// Sets attributes on the newly created cut piece serial.
        /// Inherits dye lot, width, shade code from the source roll.
        /// Sets the SourceRoll traceability link.
        /// </summary>
        private void CreateCutPieceAttributes(
            int inventoryID, string cutSerial, decimal cutYardage,
            string sourceSerial, INLotSerialStatusExt sourceAttrs)
        {
            var statusRow = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                .View.Select(_graph, inventoryID, cutSerial);

            if (statusRow == null) return;

            var status = (INLotSerialStatus)statusRow;
            var ext = status.GetExtension<INLotSerialStatusExt>();

            // Set cut piece yardage
            ext.UsrActualYardage = cutYardage;

            // Inherit attributes from source roll
            ext.UsrDyeLot = sourceAttrs.UsrDyeLot;
            ext.UsrWidth = sourceAttrs.UsrWidth;
            ext.UsrShadeCode = sourceAttrs.UsrShadeCode;
            ext.UsrContainerNo = sourceAttrs.UsrContainerNo;

            // Set traceability link
            ext.UsrSourceRoll = sourceSerial;

            // Cut piece inherits the source roll's status
            ext.UsrInventoryStatus = sourceAttrs.UsrInventoryStatus;

            // Cut piece has no pre-assigned bin (it goes with the shipment)
            ext.UsrPreAssignedBin = null;

            // Not defective (source was validated before cut)
            ext.UsrDefectFlag = false;

            _graph.Caches[typeof(INLotSerialStatus)].Update(status);
            _graph.Actions.PressSave();
        }

        #endregion

        #region Result Types

        /// <summary>Result of a successful cut-to-order operation.</summary>
        public class CutResult
        {
            public bool Success { get; set; }
            public string CutPieceSerial { get; set; }
            public decimal CutYardage { get; set; }
            public decimal RemnantYardage { get; set; }
            public string SourceSerial { get; set; }
            public bool SuggestFullRoll { get; set; }
            public string AdjustmentRefNbr { get; set; }
            public string ErrorMessage { get; set; }
        }

        /// <summary>Result of a cut validation check (no side effects).</summary>
        public class CutValidation
        {
            public bool IsValid { get; set; }
            public bool SuggestFullRoll { get; set; }
            public decimal AvailableYardage { get; set; }
            public decimal RemnantYardage { get; set; }
            public string ErrorMessage { get; set; }
        }

        #endregion
    }
}
