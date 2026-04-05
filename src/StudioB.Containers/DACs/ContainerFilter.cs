using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Filter")]
    public class ContainerFilter : PXBqlTable, IBqlTable
    {
        #region StatusFilter
        public abstract class statusFilter : BqlString.Field<statusFilter> { }
        [PXString(20)]
        [PXUIField(DisplayName = "Status Filter")]
        public string StatusFilter { get; set; }
        #endregion

        #region KPIOpen
        public abstract class kpiOpen : BqlInt.Field<kpiOpen> { }
        [PXInt]
        [PXUIField(DisplayName = "Open", Enabled = false)]
        public int? KPIOpen { get; set; }
        #endregion

        #region KPIInTransit
        public abstract class kpiInTransit : BqlInt.Field<kpiInTransit> { }
        [PXInt]
        [PXUIField(DisplayName = "In Transit", Enabled = false)]
        public int? KPIInTransit { get; set; }
        #endregion

        #region KPIArrivingThisWeek
        public abstract class kpiArrivingThisWeek : BqlInt.Field<kpiArrivingThisWeek> { }
        [PXInt]
        [PXUIField(DisplayName = "Arriving This Week", Enabled = false)]
        public int? KPIArrivingThisWeek { get; set; }
        #endregion

        #region KPICustomsHold
        public abstract class kpiCustomsHold : BqlInt.Field<kpiCustomsHold> { }
        [PXInt]
        [PXUIField(DisplayName = "Customs Hold", Enabled = false)]
        public int? KPICustomsHold { get; set; }
        #endregion
    }
}
