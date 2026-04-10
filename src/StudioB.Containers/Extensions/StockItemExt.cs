using PX.Data;
using PX.Objects.IN;

namespace StudioB.Containers
{
    public sealed class StockItemExt : PXCacheExtension<InventoryItem>
    {
        public static bool IsActive() => true;
        #region UsrFiberContent
        public abstract class usrFiberContent : PX.Data.BQL.BqlString.Field<usrFiberContent> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Fiber Content", Visibility = PXUIVisibility.SelectorVisible)]
        public string UsrFiberContent { get; set; }
        #endregion
        #region UsrDutyRate
        public abstract class usrDutyRate : PX.Data.BQL.BqlDecimal.Field<usrDutyRate> { }
        [PXDBDecimal(4)]
        [PXUIField(DisplayName = "Duty Rate")]
        public decimal? UsrDutyRate { get; set; }
        #endregion
        #region UsrPreferentialTariff
        public abstract class usrPreferentialTariff : PX.Data.BQL.BqlBool.Field<usrPreferentialTariff> { }
        [PXDBBool]
        [PXUIField(DisplayName = "Preferential Tariff")]
        public bool? UsrPreferentialTariff { get; set; }
        #endregion
        #region UsrFreightClass
        public abstract class usrFreightClass : PX.Data.BQL.BqlString.Field<usrFreightClass> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "Freight Class")]
        public string UsrFreightClass { get; set; }
        #endregion
        #region UsrCbmPerUnit
        public abstract class usrCbmPerUnit : PX.Data.BQL.BqlDecimal.Field<usrCbmPerUnit> { }
        [PXDBDecimal(6)]
        [PXUIField(DisplayName = "CBM Per Unit")]
        public decimal? UsrCbmPerUnit { get; set; }
        #endregion
    }
}
