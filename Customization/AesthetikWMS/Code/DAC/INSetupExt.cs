using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// DAC extension for INSetup (Inventory Preferences).
    /// Global configuration parameters for the Piece Goods WMS customization.
    /// These values serve as system-wide defaults; some can be overridden
    /// at the lot/serial class level or per-warehouse.
    /// </summary>
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        public static bool IsActive() => true;

        #region General Settings

        #region UsrPGMinRemnant
        /// <summary>
        /// Global minimum remnant threshold in yards. If cutting would leave
        /// a remnant below this value, the CutToOrderEngine suggests shipping
        /// the full roll. Can be overridden per lot/serial class.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "1.00")]
        [PXUIField(DisplayName = "Min Remnant Yardage",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrPGMinRemnant { get; set; }
        public abstract class usrPGMinRemnant : BqlDecimal.Field<usrPGMinRemnant> { }
        #endregion

        #region UsrPGAutoQtyMode
        /// <summary>
        /// Enable auto-quantity mode for PIECEGOODS serial class items.
        /// When true, scanning a serial barcode auto-confirms qty = 1
        /// without requiring a separate quantity entry step.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Quantity Mode",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGAutoQtyMode { get; set; }
        public abstract class usrPGAutoQtyMode : BqlBool.Field<usrPGAutoQtyMode> { }
        #endregion

        #region UsrPGAutoPrint
        /// <summary>
        /// Auto-print roll barcode label on receiving.
        /// Sends GS1-128 label to the configured Keyence-compatible printer.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Print Label on Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGAutoPrint { get; set; }
        public abstract class usrPGAutoPrint : BqlBool.Field<usrPGAutoPrint> { }
        #endregion

        #region UsrPGCutSuffix
        /// <summary>
        /// Serial number suffix format for cut pieces.
        /// {0} is replaced with the sequential cut number.
        /// Example: parent serial FAB-1024-260301-001 becomes FAB-1024-260301-001-C1
        /// </summary>
        [PXDBString(20, IsUnicode = true)]
        [PXDefault("-C{0}")]
        [PXUIField(DisplayName = "Cut Serial Suffix Format",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public string UsrPGCutSuffix { get; set; }
        public abstract class usrPGCutSuffix : BqlString.Field<usrPGCutSuffix> { }
        #endregion

        #endregion

        #region Pre-Receiving & Cross-Dock

        #region UsrPGPreRecv
        /// <summary>
        /// Enable the pre-receiving workflow globally. When true, serial numbers
        /// and bin assignments can be created from PO/ASN data before goods arrive.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Enable Pre-Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGPreRecv { get; set; }
        public abstract class usrPGPreRecv : BqlBool.Field<usrPGPreRecv> { }
        #endregion

        #region UsrPGCrossDock
        /// <summary>
        /// Enable cross-dock fulfillment globally. When true, rolls in
        /// RECV-DOCK location can be picked before formal put-away.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Enable Cross-Dock Fulfillment",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGCrossDock { get; set; }
        public abstract class usrPGCrossDock : BqlBool.Field<usrPGCrossDock> { }
        #endregion

        #region UsrPGXDockAge
        /// <summary>
        /// Days a roll can remain in RECV-DOCK before its put-away priority
        /// is escalated. Prevents staging area overflow. Default: 5 days.
        /// </summary>
        [PXDBInt]
        [PXDefault(5)]
        [PXUIField(DisplayName = "Cross-Dock Age Limit (Days)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGXDockAge { get; set; }
        public abstract class usrPGXDockAge : BqlInt.Field<usrPGXDockAge> { }
        #endregion

        #region UsrPGInTransitWt
        /// <summary>
        /// Weight penalty for In-Transit stock in the pick optimizer.
        /// Negative value means on-hand stock is preferred. Default: -20.
        /// Set to 0 to treat in-transit equally with on-hand.
        /// </summary>
        [PXDBInt]
        [PXDefault(-20)]
        [PXUIField(DisplayName = "In-Transit Allocation Weight",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGInTransitWt { get; set; }
        public abstract class usrPGInTransitWt : BqlInt.Field<usrPGInTransitWt> { }
        #endregion

        #region UsrPGYardageVar
        /// <summary>
        /// Yardage variance threshold for receiving validation.
        /// If actual yardage differs from expected by more than this percentage,
        /// the system flags a variance warning. Default: 0.02 (2%).
        /// </summary>
        [PXDBDecimal(4)]
        [PXDefault(TypeCode.Decimal, "0.0200")]
        [PXUIField(DisplayName = "Yardage Variance Threshold (%)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrPGYardageVar { get; set; }
        public abstract class usrPGYardageVar : BqlDecimal.Field<usrPGYardageVar> { }
        #endregion

        #endregion

        #region Pick Optimizer Weights

        #region UsrPGWtExact
        /// <summary>Scoring weight for exact yardage match (no cut needed). Default: 50.</summary>
        [PXDBInt]
        [PXDefault(50)]
        [PXUIField(DisplayName = "Weight: Exact Match",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGWtExact { get; set; }
        public abstract class usrPGWtExact : BqlInt.Field<usrPGWtExact> { }
        #endregion

        #region UsrPGWtRemnant
        /// <summary>Scoring weight for minimizing remnant yardage. Default: 30.</summary>
        [PXDBInt]
        [PXDefault(30)]
        [PXUIField(DisplayName = "Weight: Minimize Remnant",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGWtRemnant { get; set; }
        public abstract class usrPGWtRemnant : BqlInt.Field<usrPGWtRemnant> { }
        #endregion

        #region UsrPGWtDyeLot
        /// <summary>Scoring weight for dye lot matching on multi-roll orders. Default: 15.</summary>
        [PXDBInt]
        [PXDefault(15)]
        [PXUIField(DisplayName = "Weight: Dye Lot Match",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGWtDyeLot { get; set; }
        public abstract class usrPGWtDyeLot : BqlInt.Field<usrPGWtDyeLot> { }
        #endregion

        #region UsrPGWtLocation
        /// <summary>Scoring weight for location preference (bin vs RECV-DOCK). Default: 10.</summary>
        [PXDBInt]
        [PXDefault(10)]
        [PXUIField(DisplayName = "Weight: Location Preference",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGWtLocation { get; set; }
        public abstract class usrPGWtLocation : BqlInt.Field<usrPGWtLocation> { }
        #endregion

        #region UsrPGWtFIFO
        /// <summary>Scoring weight for FIFO aging (tiebreaker). Default: 5.</summary>
        [PXDBInt]
        [PXDefault(5)]
        [PXUIField(DisplayName = "Weight: FIFO Age",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public int? UsrPGWtFIFO { get; set; }
        public abstract class usrPGWtFIFO : BqlInt.Field<usrPGWtFIFO> { }
        #endregion

        #endregion
    }
}
