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
    /// Graph extension for SOShipmentEntry that replaces the default FIFO/FEFO
    /// pick suggestion logic with textile-aware allocation.
    ///
    /// Evaluates all available rolls — including RECV-DOCK and In-Transit — and
    /// ranks them using a configurable weighted scoring algorithm:
    ///   - Exact Match (50):    Roll yardage == ordered qty
    ///   - Minimize Remnant (30): Closest yardage above ordered qty
    ///   - Dye Lot Match (15):    Same dye lot as other order lines
    ///   - Location Pref (10):    Bin stock preferred over RECV-DOCK
    ///   - FIFO Age (5):          Older rolls score higher (tiebreaker)
    ///
    /// Runs at shipment creation. Warehouse staff can override during picking.
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class TextilePickOptimizer : PXGraphExtension<SOShipmentEntry>
    {
        public static bool IsActive() => true;

        #region Allocation Override

        /// <summary>
        /// Generates textile-aware pick suggestions for all PIECEGOODS lines
        /// on the current shipment. Returns a list of allocation results
        /// that can be applied to SOShipLineSplit records.
        /// </summary>
        public List<AllocationResult> GeneratePickSuggestions(SOShipment shipment)
        {
            if (shipment == null) return new List<AllocationResult>();

            var weights = LoadWeights();
            var results = new List<AllocationResult>();

            // Load all shipment lines for PIECEGOODS items
            var shipLines = SelectFrom<SOShipLine>
                .Where<SOShipLine.shipmentNbr.IsEqual<@P.AsString>>
                .View.ReadOnly.Select(Base, shipment.ShipmentNbr)
                .Select(r => (SOShipLine)r)
                .Where(l => IsPieceGoodsItem(l.InventoryID))
                .ToList();

            if (shipLines.Count == 0) return results;

            // Track assignments to prevent double-allocation
            var assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            // Track dye lot assignments for multi-line matching
            var dyeLotByItem = new Dictionary<int, string>();

            // Sort lines by quantity (larger orders first for better fit)
            var sortedLines = shipLines.OrderByDescending(l => l.ShippedQty ?? l.OrigOrderQty ?? 0);

            foreach (var line in sortedLines)
            {
                if (line.InventoryID == null) continue;

                decimal orderedQty = line.ShippedQty ?? line.OrigOrderQty ?? 0;
                if (orderedQty <= 0) continue;

                int inventoryID = line.InventoryID.Value;

                // Determine target dye lot if other lines for this item already assigned
                string targetDyeLot = null;
                dyeLotByItem.TryGetValue(inventoryID, out targetDyeLot);

                // Get all candidate rolls
                var candidates = GetCandidateRolls(inventoryID, line.SiteID);

                // Remove already-assigned serials
                candidates = candidates.Where(c => !assignedSerials.Contains(c.LotSerialNbr)).ToList();

                if (candidates.Count == 0)
                {
                    results.Add(new AllocationResult
                    {
                        ShipLineNbr = line.LineNbr,
                        AssignedSerial = null,
                        Score = 0,
                        ErrorMessage = "No eligible rolls available",
                    });
                    continue;
                }

                // Score each candidate
                var scored = candidates
                    .Select(c => new
                    {
                        Candidate = c,
                        Score = ScoreRoll(c, orderedQty, targetDyeLot, weights),
                    })
                    .Where(s => s.Score >= 0) // Exclude disqualified rolls
                    .OrderByDescending(s => s.Score)
                    .ToList();

                if (scored.Count == 0)
                {
                    results.Add(new AllocationResult
                    {
                        ShipLineNbr = line.LineNbr,
                        AssignedSerial = null,
                        Score = 0,
                        ErrorMessage = "No rolls with sufficient yardage",
                    });
                    continue;
                }

                var best = scored.First();
                bool requiresCut = best.Candidate.ActualYardage > orderedQty;

                // Track assignment
                assignedSerials.Add(best.Candidate.LotSerialNbr);

                // Track dye lot for multi-line matching
                if (!string.IsNullOrEmpty(best.Candidate.DyeLot))
                    dyeLotByItem[inventoryID] = best.Candidate.DyeLot;

                results.Add(new AllocationResult
                {
                    ShipLineNbr = line.LineNbr,
                    AssignedSerial = best.Candidate.LotSerialNbr,
                    AssignedYardage = best.Candidate.ActualYardage,
                    RequiresCut = requiresCut,
                    ExpectedRemnant = requiresCut
                        ? best.Candidate.ActualYardage - orderedQty
                        : (decimal?)null,
                    Score = best.Score,
                    SourceLocation = best.Candidate.InventoryStatus ==
                        PieceGoodsConstants.InvStatus_Receiving
                            ? PieceGoodsConstants.Location_RecvDock
                            : best.Candidate.LocationCD,
                    DyeLot = best.Candidate.DyeLot,
                });
            }

            return results;
        }

        /// <summary>
        /// Applies pick suggestions to the shipment by updating SOShipLineSplit records.
        /// </summary>
        public void ApplyPickSuggestions(SOShipment shipment, List<AllocationResult> suggestions)
        {
            if (shipment == null || suggestions == null) return;

            foreach (var suggestion in suggestions.Where(s => s.AssignedSerial != null))
            {
                // Find the corresponding split record for this shipment line
                var splits = SelectFrom<SOShipLineSplit>
                    .Where<SOShipLineSplit.shipmentNbr.IsEqual<@P.AsString>
                        .And<SOShipLineSplit.lineNbr.IsEqual<@P.AsInt>>>
                    .View.Select(Base, shipment.ShipmentNbr, suggestion.ShipLineNbr);

                if (splits == null || splits.Count == 0) continue;

                var split = (SOShipLineSplit)splits;
                split.LotSerialNbr = suggestion.AssignedSerial;

                Base.Caches[typeof(SOShipLineSplit)].Update(split);
            }

            Base.Actions.PressSave();
        }

        #endregion

        #region Candidate Loading

        /// <summary>
        /// Loads all candidate rolls for a given item at a specific warehouse.
        /// Includes Available, Receiving (cross-dock), and In-Transit rolls.
        /// Excludes defective rolls.
        /// </summary>
        private List<RollCandidate> GetCandidateRolls(int inventoryID, int? siteID)
        {
            var candidates = new List<RollCandidate>();

            var allSerials = siteID.HasValue
                ? SelectFrom<INLotSerialStatus>
                    .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                        .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                    .View.ReadOnly.Select(Base, inventoryID, siteID.Value)
                : SelectFrom<INLotSerialStatus>
                    .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>>
                    .View.ReadOnly.Select(Base, inventoryID);

            foreach (PXResult<INLotSerialStatus> row in allSerials)
            {
                var status = (INLotSerialStatus)row;
                var ext = status.GetExtension<INLotSerialStatusExt>();

                if (ext == null) continue;

                // Skip defective rolls
                if (ext.UsrDefectFlag == true) continue;

                // Skip rolls not in a pickable status
                string invStatus = ext.UsrInventoryStatus;
                if (invStatus != PieceGoodsConstants.InvStatus_Available &&
                    invStatus != PieceGoodsConstants.InvStatus_Receiving &&
                    invStatus != PieceGoodsConstants.InvStatus_InTransit &&
                    invStatus != PieceGoodsConstants.InvStatus_PutAway)
                    continue;

                // Skip rolls with zero yardage
                if ((ext.UsrActualYardage ?? 0) <= 0) continue;

                // Resolve location CD for display
                string locationCD = null;
                if (status.LocationID.HasValue)
                {
                    var loc = SelectFrom<INLocation>
                        .Where<INLocation.locationID.IsEqual<@P.AsInt>>
                        .View.ReadOnly.Select(Base, status.LocationID);
                    locationCD = loc != null ? ((INLocation)loc).LocationCD : null;
                }

                candidates.Add(new RollCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    InventoryID = status.InventoryID.Value,
                    SiteID = status.SiteID.Value,
                    LocationID = status.LocationID ?? 0,
                    LocationCD = locationCD,
                    ActualYardage = ext.UsrActualYardage ?? 0,
                    DyeLot = ext.UsrDyeLot,
                    ShadeCode = ext.UsrShadeCode,
                    Width = ext.UsrWidth,
                    DefectFlag = ext.UsrDefectFlag ?? false,
                    InventoryStatus = invStatus,
                    ReceiptDate = status.LastModifiedDateTime?.Date,
                    ContainerNumber = ext.UsrContainerNo,
                });
            }

            return candidates;
        }

        #endregion

        #region Scoring Engine

        /// <summary>
        /// Scores a candidate roll for a given order line.
        /// Higher score = better candidate. Returns -1 to disqualify.
        /// </summary>
        public decimal ScoreRoll(
            RollCandidate candidate,
            decimal orderedQty,
            string targetDyeLot,
            OptimizerWeights weights)
        {
            // Disqualify if roll doesn't have enough yardage
            if (candidate.ActualYardage < orderedQty)
                return -1;

            decimal score = 0;

            // ── Exact match (roll yardage ≈ ordered qty within 0.1 yd) ──
            if (Math.Abs(candidate.ActualYardage - orderedQty) <= 0.1m)
            {
                score += weights.ExactMatch;
            }
            else
            {
                // ── Minimize remnant ────────────────────────────────────
                decimal remnant = candidate.ActualYardage - orderedQty;
                // Inverse: smaller remnant = higher score
                // Scale: a 1-yd remnant scores near max; 100+ yd remnant scores near 0
                decimal remnantScore = Math.Max(0, 1 - (remnant / Math.Max(candidate.ActualYardage, 1)));
                score += weights.MinimizeRemnant * remnantScore;
            }

            // ── Dye lot match ───────────────────────────────────────────
            if (!string.IsNullOrEmpty(targetDyeLot) &&
                string.Equals(candidate.DyeLot, targetDyeLot, StringComparison.OrdinalIgnoreCase))
            {
                score += weights.DyeLotMatch;
            }

            // ── Location preference ─────────────────────────────────────
            switch (candidate.InventoryStatus)
            {
                case PieceGoodsConstants.InvStatus_Available:
                case PieceGoodsConstants.InvStatus_PutAway:
                    score += weights.LocationPreference;
                    break;
                case PieceGoodsConstants.InvStatus_Receiving:
                    score += weights.LocationPreference * 0.5m;
                    break;
                case PieceGoodsConstants.InvStatus_InTransit:
                    score += weights.InTransitPenalty; // Typically negative
                    break;
            }

            // ── FIFO age (tiebreaker) ───────────────────────────────────
            if (candidate.ReceiptDate.HasValue)
            {
                int ageDays = Math.Max(0, (DateTime.Today - candidate.ReceiptDate.Value).Days);
                decimal ageFactor = Math.Min(ageDays / 365m, 1m);
                score += weights.FIFOAge * ageFactor;
            }

            return score;
        }

        #endregion

        #region Configuration

        /// <summary>Loads optimizer weights from INSetup.</summary>
        private OptimizerWeights LoadWeights()
        {
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(Base, null);
            var ext = setup?.GetItem<INSetup>()?.GetExtension<INSetupExt>();
            return OptimizerWeights.FromSetup(ext);
        }

        /// <summary>Checks if an item uses the PIECEGOODS class.</summary>
        private bool IsPieceGoodsItem(int? inventoryID)
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

        #endregion

        #region Supporting Types

        /// <summary>Candidate roll for pick allocation.</summary>
        public class RollCandidate
        {
            public string LotSerialNbr { get; set; }
            public int InventoryID { get; set; }
            public int SiteID { get; set; }
            public int LocationID { get; set; }
            public string LocationCD { get; set; }
            public decimal ActualYardage { get; set; }
            public string DyeLot { get; set; }
            public string ShadeCode { get; set; }
            public decimal? Width { get; set; }
            public bool DefectFlag { get; set; }
            public string InventoryStatus { get; set; }
            public DateTime? ReceiptDate { get; set; }
            public string ContainerNumber { get; set; }
        }

        /// <summary>Configurable weights loaded from INSetupExt.</summary>
        public class OptimizerWeights
        {
            public int ExactMatch { get; set; } = PieceGoodsConstants.DefaultWeight_ExactMatch;
            public int MinimizeRemnant { get; set; } = PieceGoodsConstants.DefaultWeight_MinimizeRemnant;
            public int DyeLotMatch { get; set; } = PieceGoodsConstants.DefaultWeight_DyeLotMatch;
            public int LocationPreference { get; set; } = PieceGoodsConstants.DefaultWeight_LocationPref;
            public int FIFOAge { get; set; } = PieceGoodsConstants.DefaultWeight_FIFOAge;
            public int InTransitPenalty { get; set; } = PieceGoodsConstants.DefaultInTransitAllocWeight;

            public static OptimizerWeights FromSetup(INSetupExt ext)
            {
                if (ext == null) return new OptimizerWeights();

                return new OptimizerWeights
                {
                    ExactMatch = ext.UsrPGWtExact ?? PieceGoodsConstants.DefaultWeight_ExactMatch,
                    MinimizeRemnant = ext.UsrPGWtRemnant ?? PieceGoodsConstants.DefaultWeight_MinimizeRemnant,
                    DyeLotMatch = ext.UsrPGWtDyeLot ?? PieceGoodsConstants.DefaultWeight_DyeLotMatch,
                    LocationPreference = ext.UsrPGWtLocation ?? PieceGoodsConstants.DefaultWeight_LocationPref,
                    FIFOAge = ext.UsrPGWtFIFO ?? PieceGoodsConstants.DefaultWeight_FIFOAge,
                    InTransitPenalty = ext.UsrPGInTransitWt ?? PieceGoodsConstants.DefaultInTransitAllocWeight,
                };
            }
        }

        /// <summary>Result of an allocation run for a single shipment line.</summary>
        public class AllocationResult
        {
            public int? ShipLineNbr { get; set; }
            public string AssignedSerial { get; set; }
            public decimal AssignedYardage { get; set; }
            public bool RequiresCut { get; set; }
            public decimal? ExpectedRemnant { get; set; }
            public decimal Score { get; set; }
            public string SourceLocation { get; set; }
            public string DyeLot { get; set; }
            public string ErrorMessage { get; set; }
        }

        #endregion
    }
}
