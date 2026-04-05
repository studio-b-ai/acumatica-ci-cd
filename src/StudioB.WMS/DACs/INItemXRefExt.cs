using System;
using PX.Data;
using PX.Objects.IN;

namespace HeritageFabrics.IN
{
    /// <summary>
    /// Absorbed from WMSynergy.ExpirationDateAtStockItems.
    /// Adds an expiration date field to the Item Cross-Reference grid on Stock Items (IN202500).
    /// Used to track vendor-assigned expiry dates per cross-reference entry
    /// for compliance and receiving validation.
    /// </summary>
    public class INItemXRefExt : PXCacheExtension<PX.Objects.IN.INItemXRef>
    {
        public static bool IsActive() => true;

        #region UsrHFExpiryDate
        [PXDBDate]
        [PXUIField(DisplayName = "Expiry Date")]
        public virtual DateTime? UsrHFExpiryDate { get; set; }
        public abstract class usrHFExpiryDate : PX.Data.BQL.BqlDateTime.Field<usrHFExpiryDate> { }
        #endregion
    }
}
