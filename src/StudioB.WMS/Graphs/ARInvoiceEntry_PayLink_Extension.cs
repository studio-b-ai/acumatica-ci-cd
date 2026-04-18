using PX.Data;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Graph extension for ARInvoiceEntry (AR301000).
    /// Intercepts payment link processing to check the customer-level
    /// UsrDisablePayLink flag before generating/sending payment links.
    ///
    /// The base product checks ARCustomerClass.DisablePayLink at the class level.
    /// This extension adds a customer-level override so individual customers
    /// (e.g., factor customers) can be excluded without changing the entire class.
    ///
    /// Restored from archive (HeritageFabricsPOv5) as part of ticket #44514576665
    /// fix — CustomerExt was missing from the compiled DLL, preventing AR303000
    /// from saving and breaking this extension's GetExtension call at runtime.
    /// </summary>
    public class ARInvoiceEntry_PayLink_Extension : PXGraphExtension<ARInvoiceEntry>
    {
        public static bool IsActive() => true;

        /// <summary>
        /// Disable payment link actions on the invoice screen when the customer
        /// has UsrDisablePayLink set to true.
        /// </summary>
        protected void _(Events.RowSelected<ARInvoice> e)
        {
            if (e.Row == null) return;

            bool disablePayLink = IsPayLinkDisabledForCustomer(e.Row.CustomerID);

            // Disable the Send Payment Link action if it exists
            if (Base.Actions.Contains("SendPaymentLink"))
            {
                Base.Actions["SendPaymentLink"].SetEnabled(!disablePayLink);
            }

            // Also check for alternate action names used in different Acumatica versions
            if (Base.Actions.Contains("sendPayLink"))
            {
                Base.Actions["sendPayLink"].SetEnabled(!disablePayLink);
            }
        }

        /// <summary>
        /// Check if the customer has payment links disabled at the customer level.
        /// Falls back to false (payment links enabled) if the field is not set.
        /// </summary>
        private bool IsPayLinkDisabledForCustomer(int? customerID)
        {
            if (customerID == null) return false;

            Customer customer = PXSelect<Customer,
                Where<Customer.bAccountID, Equal<Required<Customer.bAccountID>>>>
                .Select(Base, customerID);

            if (customer == null) return false;

            CustomerExt ext = customer.GetExtension<CustomerExt>();
            return ext?.UsrDisablePayLink == true;
        }
    }
}
