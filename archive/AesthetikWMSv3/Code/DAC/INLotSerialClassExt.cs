using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    /// <summary>
    /// DAC extension for INLotSerialClass.
    /// Adds PIECEGOODS-specific configuration fields to the lot/serial class definition.
    /// These fields control per-class behavior for the piece goods workflow:
    /// minimum remnant threshold, auto-print on receiving, default width, and pre-receiving toggle.
    /// </summary>
    public sealed class INLotSerialClassExt : PXCacheExtension<INLotSerialClass>
    {
        public static bool IsActive() => true;

        #region UsrMinRemnant
        /// <summary>
        /// Minimum remnant yardage threshold. If cutting would leave a remnant
        /// below this value, the system suggests shipping the full roll instead.
        /// Default: 1.0 yard. Overrides the global INSetup value per-class.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "1.00")]
        [PXUIField(DisplayName = "Min Remnant (Yards)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrMinRemnant { get; set; }
        public abstract class usrMinRemnant : BqlDecimal.Field<usrMinRemnant> { }
        #endregion

        #region UsrAutoPrint
        /// <summary>
        /// When true, the system automatically sends a barcode label to the
        /// Keyence-compatible printer upon receiving a roll into this class.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Print Label on Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrAutoPrint { get; set; }
        public abstract class usrAutoPrint : BqlBool.Field<usrAutoPrint> { }
        #endregion

        #region UsrDefaultWidth
        /// <summary>
        /// Default fabric width in inches for items in this class.
        /// Pre-populates the Width attribute on new serials; can be overridden per roll.
        /// </summary>
        [PXDBDecimal(1)]
        [PXDefault(TypeCode.Decimal, "54.0")]
        [PXUIField(DisplayName = "Default Width (inches)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrDefaultWidth { get; set; }
        public abstract class usrDefaultWidth : BqlDecimal.Field<usrDefaultWidth> { }
        #endregion

        #region UsrPreRecvEnabled
        /// <summary>
        /// Enables the pre-receiving workflow for this lot/serial class.
        /// When true, serial numbers and bin assignments can be created from PO/ASN
        /// data before goods physically arrive at the warehouse.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Enable Pre-Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPreRecvEnabled { get; set; }
        public abstract class usrPreRecvEnabled : BqlBool.Field<usrPreRecvEnabled> { }
        #endregion
    }
}
