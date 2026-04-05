using PX.Data;
using PX.Data.BQL;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// DAC extension for SOLine — stores original requested quantity
    /// before auto-allocation overrides OrderQty with bolt totals.
    /// </summary>
    public sealed class SOLineExt : PXCacheExtension<SOLine>
    {
        public static bool IsActive() => true;

        #region UsrRequestedQty
        [PXDecimal(4)]
        [PXDefault(PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Requested Qty", Enabled = false)]
        public decimal? UsrRequestedQty { get; set; }
        public abstract class usrRequestedQty : BqlDecimal.Field<usrRequestedQty> { }
        #endregion
    }
}
