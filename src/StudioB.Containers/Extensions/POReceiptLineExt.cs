using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public sealed class POReceiptLineExt : PXCacheExtension<POReceiptLine>
    {
        public static bool IsActive() => true;
        #region UsrActualDutyAmt
        public abstract class usrActualDutyAmt : PX.Data.BQL.BqlDecimal.Field<usrActualDutyAmt> { }
        [PXDBDecimal(4)]
        [PXDefault(System.TypeCode.Decimal, "0.00", PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Actual Duty", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrActualDutyAmt { get; set; }
        #endregion
        #region UsrActualFreightAmt
        public abstract class usrActualFreightAmt : PX.Data.BQL.BqlDecimal.Field<usrActualFreightAmt> { }
        [PXDBDecimal(4)]
        [PXDefault(System.TypeCode.Decimal, "0.00", PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Freight Allocated", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrActualFreightAmt { get; set; }
        #endregion
        #region UsrBrokerageAmt
        public abstract class usrBrokerageAmt : PX.Data.BQL.BqlDecimal.Field<usrBrokerageAmt> { }
        [PXDBDecimal(4)]
        [PXDefault(System.TypeCode.Decimal, "0.00", PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Brokerage", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrBrokerageAmt { get; set; }
        #endregion
        #region UsrLandedCostPerUnit
        public abstract class usrLandedCostPerUnit : PX.Data.BQL.BqlDecimal.Field<usrLandedCostPerUnit> { }
        [PXDecimal(4)]
        [PXUIField(DisplayName = "Landed Cost/Unit", Enabled = false)]
        public decimal? UsrLandedCostPerUnit { get; set; }
        #endregion
    }
}
