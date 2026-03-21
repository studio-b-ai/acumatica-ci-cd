using PX.Data;
using PX.Data.BQL;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Adds a customer-level "Exclude from Payment Link Processing" flag.
    /// The base product only has this on ARCustomerClass (DisablePayLink).
    /// This extension allows per-customer override so factor customers
    /// can be excluded without affecting the entire customer class.
    /// </summary>
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
