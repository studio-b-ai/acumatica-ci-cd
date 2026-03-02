using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace HeritageFabrics.PO
{
    public sealed class POOrderExt : PXCacheExtension<POOrder>
    {
        public static bool IsActive() => true;
        #region UsrExpArrivalDate
        public abstract class usrExpArrivalDate : BqlDateTime.Field<usrExpArrivalDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Exp. Arrival Date", Visibility = PXUIVisibility.SelectorVisible)]
        public DateTime? UsrExpArrivalDate { get; set; }
        #endregion
        #region UsrActArrivalDate
        public abstract class usrActArrivalDate : BqlDateTime.Field<usrActArrivalDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Arrival Date", Visibility = PXUIVisibility.SelectorVisible)]
        public DateTime? UsrActArrivalDate { get; set; }
        #endregion
    }
}
