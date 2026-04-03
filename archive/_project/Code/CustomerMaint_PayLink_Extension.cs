using PX.Data;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    /// <summary>
    /// Graph extension for CustomerMaint (AR303000).
    /// Defaults UsrDisablePayLink from the customer class when the class changes,
    /// and ensures the field is visible on the screen.
    /// </summary>
    public class CustomerMaint_PayLink_Extension : PXGraphExtension<CustomerMaint>
    {
        public static bool IsActive() => true;

        /// <summary>
        /// When the Customer Class changes, default UsrDisablePayLink from the class-level DisablePayLink.
        /// </summary>
        protected void _(Events.FieldUpdated<Customer, Customer.customerClassID> e)
        {
            if (e.Row == null) return;

            string classID = e.Row.CustomerClassID;
            if (string.IsNullOrEmpty(classID)) return;

            ARCustomerClass custClass = PXSelect<ARCustomerClass,
                Where<ARCustomerClass.customerClassID, Equal<Required<ARCustomerClass.customerClassID>>>>
                .Select(Base, classID);

            if (custClass != null)
            {
                CustomerExt ext = e.Row.GetExtension<CustomerExt>();
                if (ext != null)
                {
                    ext.UsrDisablePayLink = custClass.DisablePayLink ?? false;
                }
            }
        }
    }
}
