using System;
using PX.Data;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Graph extension for ARInvoiceEntry (AR301000 / AR.30.10.00).
    /// Intercepts payment link processing to check the customer-level
    /// UsrDisablePayLink flag before generating/sending payment links.
    ///
    /// The base product checks ARCustomerClass.DisablePayLink at the class level.
    /// This extension adds a customer-level override so individual customers
    /// (e.g., factor customers) can be excluded without changing the entire class.
    ///
    /// How it works:
    /// - On RowSelected, if the customer has UsrDisablePayLink=true,
    ///   the "Send Payment Link" action is disabled.
    /// - On RowPersisted (after release), if the customer has the flag set,
    ///   any pending payment link processing is skipped.
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
