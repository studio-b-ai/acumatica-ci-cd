using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace HeritageFabrics.IN
{
    public sealed class InventoryAllocDetEnqResultExt : PXCacheExtension<InventoryAllocDetEnqResult>
    {
        public static bool IsActive() => true;

        #region UsrExpArrivalDate
        public abstract class usrExpArrivalDate : BqlDateTime.Field<usrExpArrivalDate> { }
        [PXDate]
        [PXUIField(DisplayName = "Exp. Arrival Date")]
        public DateTime? UsrExpArrivalDate { get; set; }
        #endregion
    }
}
