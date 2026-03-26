using System;
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

        #region UsrPGMinRemnant
        /// <summary>
        /// Minimum remnant yardage threshold. If cutting would leave a remnant
        /// below this value, the system suggests shipping the full roll instead.
        /// Default: 1.0 yard. Overrides the global INSetup value per-class.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(System.TypeCode.Decimal, "1.00")]
        [PXUIField(DisplayName = "Min Remnant (Yards)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrPGMinRemnant { get; set; }
        public abstract class usrPGMinRemnant : BqlDecimal.Field<usrPGMinRemnant> { }
        #endregion

        #region UsrPGAutoPrint
        /// <summary>
        /// When true, the system automatically sends a barcode label to the
        /// Keyence-compatible printer upon receiving a roll into this class.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Print Label on Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGAutoPrint { get; set; }
        public abstract class usrPGAutoPrint : BqlBool.Field<usrPGAutoPrint> { }
        #endregion

        #region UsrPGDefaultWidth
        /// <summary>
        /// Default fabric width in inches for items in this class.
        /// Pre-populates the Width attribute on new serials; can be overridden per roll.
        /// </summary>
        [PXDBDecimal(1)]
        [PXDefault(System.TypeCode.Decimal, "54.0")]
        [PXUIField(DisplayName = "Default Width (inches)",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public decimal? UsrPGDefaultWidth { get; set; }
        public abstract class usrPGDefaultWidth : BqlDecimal.Field<usrPGDefaultWidth> { }
        #endregion

        #region UsrPGPreRecvEnabled
        /// <summary>
        /// Enables the pre-receiving workflow for this lot/serial class.
        /// When true, serial numbers and bin assignments can be created from PO/ASN
        /// data before goods physically arrive at the warehouse.
        /// </summary>
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Enable Pre-Receiving",
            FieldClass = PieceGoodsConstants.LotSerialClassID)]
        public bool? UsrPGPreRecvEnabled { get; set; }
        public abstract class usrPGPreRecvEnabled : BqlBool.Field<usrPGPreRecvEnabled> { }
        #endregion
    }
}
