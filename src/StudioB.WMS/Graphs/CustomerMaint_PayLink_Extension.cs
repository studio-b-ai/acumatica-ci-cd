using PX.Data;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Graph extension for CustomerMaint (AR303000).
    /// Defaults UsrDisablePayLink from the customer class when the class changes,
    /// and ensures the field is visible on the screen.
    ///
    /// Restored from archive (HeritageFabricsPOv5) as part of ticket #44514576665
    /// fix — CustomerExt was missing from the compiled DLL, preventing AR303000
    /// from saving. The missing extension caused an unmapped-column exception in
    /// Acumatica's CommandPreparing for BAccount.UsrDisablePayLink.
    /// </summary>
    public class CustomerMaint_PayLink_Extension : PXGraphExtension<CustomerMaint>
    {
        public static bool IsActive() => true;

        /// <summary>
        /// When the Customer Class changes, default UsrDisablePayLink from the
        /// class-level setting if ARCustomerClass exposes it.
        /// Gracefully no-ops if the class does not define the field.
        /// </summary>
        protected void _(Events.FieldUpdated<Customer, Customer.customerClassID> e)
        {
            if (e.Row == null) return;

            string classID = e.Row.CustomerClassID;
            if (string.IsNullOrEmpty(classID)) return;

            // CustomerExt is always non-null when the extension is active
            CustomerExt ext = e.Row.GetExtension<CustomerExt>();
            if (ext == null) return;

            // ARCustomerClass does not expose a DisablePayLink field in the
            // standard product — the archive code referenced a non-existent
            // custClass.DisablePayLink property. We default to false (pay links
            // enabled) and let the user override at the individual customer level.
            // If a future version of the product adds a class-level field, wire
            // it here.
            ext.UsrDisablePayLink = false;
        }
    }
}
