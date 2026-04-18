using PX.Data;
using PX.Data.BQL;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Customer (BAccount) DAC extension — customer-level pay-link opt-out.
    ///
    /// The DB column BAccount.UsrDisablePayLink is created by the
    /// AesthetikWMS SQL migration (AesthetikWMS_SOOrder_BAccount_Columns_v1).
    /// Without this extension the column has no DAC mapping, which causes
    /// Acumatica's CommandPreparing to throw on AR303000 (Customer Maintenance)
    /// save — "Cannot save Customer" reported in ticket #44514576665.
    ///
    /// ARInvoiceEntry_PayLink_Extension and CustomerMaint_PayLink_Extension
    /// both call GetExtension&lt;CustomerExt&gt;() — they compile only if this
    /// DAC extension exists in the assembly.
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
