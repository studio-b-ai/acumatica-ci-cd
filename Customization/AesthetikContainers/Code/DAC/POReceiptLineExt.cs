using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    /// <summary>
    /// Landed cost tracking fields on PO Receipt lines.
    /// Records actual duty, freight, and brokerage costs allocated per receipt line.
    /// Works alongside Acumatica's native Landed Cost module (handles GL posting).
    /// </summary>
    public sealed class POReceiptLineExt : PXCacheExtension<POReceiptLine>
    {
        #region UsrActualDutyAmt
        public abstract class usrActualDutyAmt : PX.Data.BQL.BqlDecimal.Field<usrActualDutyAmt> { }

        /// <summary>
        /// Actual duty paid on this receipt line.
        /// Auto-populated from StockItem.UsrDutyRate * line value on receipt creation.
        /// User can override before release.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Actual Duty", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrActualDutyAmt { get; set; }
        #endregion

        #region UsrActualFreightAmt
        public abstract class usrActualFreightAmt : PX.Data.BQL.BqlDecimal.Field<usrActualFreightAmt> { }

        /// <summary>
        /// Freight cost allocated to this receipt line.
        /// Allocated from container-level freight by weight or value.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Freight Allocated", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrActualFreightAmt { get; set; }
        #endregion

        #region UsrBrokerageAmt
        public abstract class usrBrokerageAmt : PX.Data.BQL.BqlDecimal.Field<usrBrokerageAmt> { }

        /// <summary>
        /// Customs brokerage fee allocated to this receipt line.
        /// </summary>
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Brokerage", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrBrokerageAmt { get; set; }
        #endregion

        #region UsrLandedCostPerUnit
        public abstract class usrLandedCostPerUnit : PX.Data.BQL.BqlDecimal.Field<usrLandedCostPerUnit> { }

        /// <summary>
        /// Computed: (unit cost + duty + freight + brokerage) / qty.
        /// Represents the true cost per unit including all import costs.
        /// Virtual field — calculated, not stored.
        /// </summary>
        [PXDecimal(4)]
        [PXUIField(DisplayName = "Landed Cost/Unit", Enabled = false)]
        [PXFormula(null)] // Computed in RowSelected
        public decimal? UsrLandedCostPerUnit { get; set; }
        #endregion

        #region UsrHTSCode
        public abstract class usrHTSCode : PX.Data.BQL.BqlString.Field<usrHTSCode> { }

        /// <summary>
        /// HTS code copied from StockItem at receipt time.
        /// Preserved for historical compliance — item HTS may change over time.
        /// </summary>
        [PXDBString(12, IsUnicode = true)]
        [PXUIField(DisplayName = "HTS Code", Enabled = false)]
        public string UsrHTSCode { get; set; }
        #endregion

        #region UsrCountryOfOrigin
        public abstract class usrCountryOfOrigin : PX.Data.BQL.BqlString.Field<usrCountryOfOrigin> { }

        /// <summary>
        /// Country of origin copied from StockItem at receipt time.
        /// </summary>
        [PXDBString(2, IsFixed = true, IsUnicode = true)]
        [PXUIField(DisplayName = "Origin", Enabled = false)]
        public string UsrCountryOfOrigin { get; set; }
        #endregion
    }
}
