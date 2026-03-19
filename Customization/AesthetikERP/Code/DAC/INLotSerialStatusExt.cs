using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// DAC extension for INLotSerialStatus.
    /// Surfaces the physical attributes of each roll/piece throughout the inventory lifecycle.
    /// These fields are populated at pre-receiving or physical receiving, and updated
    /// by the CutToOrderEngine when rolls are split.
    /// </summary>
    public sealed class INLotSerialStatusExt : PXCacheExtension<INLotSerialStatus>
    {
        public static bool IsActive() => true;

        #region UsrActualYardage
        /// <summary>
        /// Remaining yardage on this roll. Decremented when a cut is performed.
        /// For cut pieces, this equals the cut amount. For original rolls, this
        /// starts at the mill-reported yardage and decreases with each cut.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Actual Yardage", Enabled = true)]
        public decimal? UsrActualYardage { get; set; }
        public abstract class usrActualYardage : BqlDecimal.Field<usrActualYardage> { }
        #endregion

        #region UsrDyeLot
        /// <summary>
        /// Mill dye lot identifier. Critical for color consistency across multi-roll orders.
        /// Inherited by cut pieces from the source roll.
        /// </summary>
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Dye Lot")]
        public string UsrDyeLot { get; set; }
        public abstract class usrDyeLot : BqlString.Field<usrDyeLot> { }
        #endregion

        #region UsrWidth
        /// <summary>
        /// Fabric width in inches. May vary by roll even within the same SKU.
        /// Defaults from the lot/serial class but can be overridden per roll.
        /// </summary>
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Width (in)")]
        public decimal? UsrWidth { get; set; }
        public abstract class usrWidth : BqlDecimal.Field<usrWidth> { }
        #endregion

        #region UsrShadeCode
        /// <summary>
        /// Color shade variation (A/B/C). Used for lot matching on multi-roll orders.
        /// Not all rolls have shade codes — depends on the fabric type.
        /// </summary>
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Shade Code")]
        public string UsrShadeCode { get; set; }
        public abstract class usrShadeCode : BqlString.Field<usrShadeCode> { }
        #endregion

        #region UsrSourceRoll
        /// <summary>
        /// Parent serial number if this is a cut piece. Null for original rolls.
        /// Creates a permanent traceability link for quality tracking.
        /// Set automatically by CutToOrderEngine; read-only in the UI.
        /// </summary>
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Source Roll", Enabled = false)]
        public string UsrSourceRoll { get; set; }
        public abstract class usrSourceRoll : BqlString.Field<usrSourceRoll> { }
        #endregion

        #region UsrDefectFlag
        /// <summary>
        /// Marks this roll as having known defects. Rolls with DefectFlag = true
        /// are excluded from the TextilePickOptimizer's auto-pick candidates
        /// and from CutToOrderEngine cut candidates unless manually overridden.
        /// </summary>
        [PXDBBool]
        [PXDefault(false)]
        [PXUIField(DisplayName = "Defect Flag")]
        public bool? UsrDefectFlag { get; set; }
        public abstract class usrDefectFlag : BqlBool.Field<usrDefectFlag> { }
        #endregion

        #region UsrInventoryStatus
        /// <summary>
        /// Piece goods lifecycle status. Controls which workflows can act on this serial.
        /// Values: IN-TRANSIT, RECEIVING, PUT-AWAY, AVAILABLE, XDOCK-HOLD
        /// </summary>
        [PXDBString(15, IsUnicode = true)]
        [PXDefault(PieceGoodsConstants.InvStatus_Available)]
        [PXUIField(DisplayName = "Piece Status")]
        [PXStringList(
            new[] {
                PieceGoodsConstants.InvStatus_InTransit,
                PieceGoodsConstants.InvStatus_Receiving,
                PieceGoodsConstants.InvStatus_PutAway,
                PieceGoodsConstants.InvStatus_Available,
                PieceGoodsConstants.InvStatus_CrossDockHold
            },
            new[] {
                "In-Transit",
                "Receiving",
                "Put-Away",
                "Available",
                "Cross-Dock Hold"
            })]
        public string UsrInventoryStatus { get; set; }
        public abstract class usrInventoryStatus : BqlString.Field<usrInventoryStatus> { }
        #endregion

        #region UsrPreAssignedBin
        /// <summary>
        /// Target bin assigned before physical arrival. Used by the PreReceivingEngine
        /// for planned put-away and by the CrossDockManager to show the intended
        /// destination on the pick/pack display. Updated if the roll is physically
        /// placed in a different bin.
        /// </summary>
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Pre-Assigned Bin")]
        public string UsrPreAssignedBin { get; set; }
        public abstract class usrPreAssignedBin : BqlString.Field<usrPreAssignedBin> { }
        #endregion

        #region UsrContainerNo
        /// <summary>
        /// Shipping container ID linking rolls to the same inbound shipment.
        /// Used for container-level put-away tracking and the cross-dock dashboard.
        /// </summary>
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Container #")]
        public string UsrContainerNo { get; set; }
        public abstract class usrContainerNo : BqlString.Field<usrContainerNo> { }
        #endregion
    }
}
