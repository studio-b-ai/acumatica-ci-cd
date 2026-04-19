using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public sealed class POLineExt : PXCacheExtension<POLine>
    {
        public static bool IsActive() => true;
        #region UsrExpArrivalDate
        public abstract class usrExpArrivalDate : BqlDateTime.Field<usrExpArrivalDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Exp. Arrival Date")]
        public DateTime? UsrExpArrivalDate { get; set; }
        #endregion
        #region UsrActArrivalDate
        public abstract class usrActArrivalDate : BqlDateTime.Field<usrActArrivalDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Arrival Date")]
        public DateTime? UsrActArrivalDate { get; set; }
        #endregion
        #region UsrFactoryPromisedDate
        public abstract class usrFactoryPromisedDate : BqlDateTime.Field<usrFactoryPromisedDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Factory Promised Ready Date")]
        public DateTime? UsrFactoryPromisedDate { get; set; }
        #endregion
        #region UsrQtyOnContainers
        public abstract class usrQtyOnContainers : PX.Data.BQL.BqlDecimal.Field<usrQtyOnContainers> { }
        /// <summary>
        /// Virtual (non-persisted) field showing total quantity allocated to containers
        /// for this PO line. Replaces IIG's IGCMQtyOnContainers.
        /// Populated via RowSelected on POOrderEntry_Extension.
        /// </summary>
        [PXDecimal(4)]
        [PXUIField(DisplayName = "Qty on Containers", Enabled = false)]
        public decimal? UsrQtyOnContainers { get; set; }
        #endregion
    }
}
