using System;
using PX.Data;
using PX.Objects.AR;
using PX.Objects.CS;

namespace HeritageFabrics.AR
{
    public class ARInvoiceEntry_PayLink_Extension : PXGraphExtension<ARInvoiceEntry>
    {
        public static bool IsActive() => true;

        protected void _(Events.RowSelected<ARInvoice> e)
        {
            if (e.Row == null) return;

            bool disablePayLink = IsPayLinkDisabledForCustomer(e.Row.CustomerID);

            if (Base.Actions.Contains("SendPaymentLink"))
            {
                Base.Actions["SendPaymentLink"].SetEnabled(!disablePayLink);
            }

            if (Base.Actions.Contains("sendPayLink"))
            {
                Base.Actions["sendPayLink"].SetEnabled(!disablePayLink);
            }
        }

        private bool IsPayLinkDisabledForCustomer(int? customerID)
        {
            if (customerID == null) return false;

            Customer customer = PXSelect<Customer,
                Where<Customer.bAccountID, Equal<Required<Customer.bAccountID>>>>
                .Select(Base, customerID);

            if (customer == null) return false;

            // Check 1: Explicit per-customer flag
            CustomerExt ext = customer.GetExtension<CustomerExt>();
            if (ext?.UsrDisablePayLink == true) return true;

            // Check 2: Terms description contains "factor"
            if (!string.IsNullOrEmpty(customer.TermsID))
            {
                Terms terms = PXSelect<Terms,
                    Where<Terms.termsID, Equal<Required<Terms.termsID>>>>
                    .Select(Base, customer.TermsID);
                if (terms?.Descr != null &&
                    terms.Descr.IndexOf("factor", StringComparison.OrdinalIgnoreCase) >= 0)
                    return true;
            }

            return false;
        }
    }
}
