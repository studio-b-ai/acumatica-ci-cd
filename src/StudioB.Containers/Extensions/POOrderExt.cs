using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.Containers
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
        #region UsrContainerRef
        public abstract class usrContainerRef : BqlString.Field<usrContainerRef> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Container / BOL Ref")]
        public string UsrContainerRef { get; set; }
        #endregion
        #region UsrAcknowledgedDate
        public abstract class usrAcknowledgedDate : BqlDateTime.Field<usrAcknowledgedDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Vendor Acknowledged Date")]
        public DateTime? UsrAcknowledgedDate { get; set; }
        #endregion
        #region UsrFactoryReadyDate
        public abstract class usrFactoryReadyDate : BqlDateTime.Field<usrFactoryReadyDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Factory Ready Date")]
        public DateTime? UsrFactoryReadyDate { get; set; }
        #endregion
    }
}
