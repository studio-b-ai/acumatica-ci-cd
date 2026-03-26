using PX.Data;
using PX.Objects.IN;

namespace StudioB.Containers
{
    /// <summary>
    /// Tariff and trade compliance fields on StockItem.
    /// Used for landed cost auto-population and customs declarations.
    /// </summary>
    public sealed class StockItemExt : PXCacheExtension<InventoryItem>
    {
        #region UsrHTSCode
        public abstract class usrHTSCode : PX.Data.BQL.BqlString.Field<usrHTSCode> { }

        /// <summary>
        /// Harmonized Tariff Schedule code (e.g., 5407.61.0000).
        /// Used to determine duty rate for imported fabric.
        /// </summary>
        [PXDBString(12, IsUnicode = true)]
        [PXUIField(DisplayName = "HTS Code", Visibility = PXUIVisibility.SelectorVisible)]
        public string UsrHTSCode { get; set; }
        #endregion

        #region UsrDutyRate
        public abstract class usrDutyRate : PX.Data.BQL.BqlDecimal.Field<usrDutyRate> { }

        /// <summary>
        /// Default duty percentage for this item (e.g., 8.5 = 8.5%).
        /// Auto-populates POReceiptLine.UsrActualDutyAmt on receipt creation.
        /// </summary>
        [PXDBDecimal(4)]
        [PXDefault(TypeCode.Decimal, "0.0000")]
        [PXUIField(DisplayName = "Duty Rate %", Visibility = PXUIVisibility.SelectorVisible)]
        public decimal? UsrDutyRate { get; set; }
        #endregion

        #region UsrCountryOfOrigin
        public abstract class usrCountryOfOrigin : PX.Data.BQL.BqlString.Field<usrCountryOfOrigin> { }

        /// <summary>
        /// ISO 3166-1 alpha-2 country code (e.g., CN, IN, PK, TR, BE).
        /// Printed on blind-ship labels and used for customs declarations.
        /// </summary>
        [PXDBString(2, IsFixed = true, IsUnicode = true)]
        [PXUIField(DisplayName = "Country of Origin", Visibility = PXUIVisibility.SelectorVisible)]
        public string UsrCountryOfOrigin { get; set; }
        #endregion

        #region UsrFiberContent
        public abstract class usrFiberContent : PX.Data.BQL.BqlString.Field<usrFiberContent> { }

        /// <summary>
        /// Fiber content description (e.g., "100% Linen", "55% Cotton 45% Polyester").
        /// Printed on blind-ship labels for textile labeling compliance.
        /// </summary>
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Fiber Content", Visibility = PXUIVisibility.SelectorVisible)]
        public string UsrFiberContent { get; set; }
        #endregion

        #region UsrPreferentialTariff
        public abstract class usrPreferentialTariff : PX.Data.BQL.BqlBool.Field<usrPreferentialTariff> { }

        /// <summary>
        /// Whether this item qualifies for FTA/GSP reduced duty rate.
        /// </summary>
        [PXDBBool]
        [PXDefault(false)]
        [PXUIField(DisplayName = "Preferential Tariff")]
        public bool? UsrPreferentialTariff { get; set; }
        #endregion

        #region UsrFreightClass
        public abstract class usrFreightClass : PX.Data.BQL.BqlString.Field<usrFreightClass> { }

        /// <summary>
        /// NMFC freight class for LTL shipping (e.g., "70" for textiles).
        /// Used by ShipEngine LTL rate requests.
        /// </summary>
        [PXDBString(10, IsUnicode = true)]
        [PXDefault("70")]
        [PXUIField(DisplayName = "Freight Class")]
        public string UsrFreightClass { get; set; }
        #endregion
    }
}
