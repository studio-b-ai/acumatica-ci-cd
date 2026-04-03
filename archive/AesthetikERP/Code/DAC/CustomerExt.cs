using PX.Data;
using PX.Data.BQL;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    public sealed class CustomerExt : PXCacheExtension<Customer>
    {
        public static bool IsActive() => true;

        #region UsrDisablePayLink
        public abstract class usrDisablePayLink : BqlBool.Field<usrDisablePayLink> { }

        [PXDBBool]
        [PXDefault(false, PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Exclude from Payment Link Processing")]
        public bool? UsrDisablePayLink { get; set; }
        #endregion
    }
}
