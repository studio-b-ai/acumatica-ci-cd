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

        // --- 2026-04-07: Command Center redesign (RFC 1 Phase A) ---

        #region ViewMode
        public abstract class viewMode : BqlString.Field<viewMode> { }
        [PXString(15)]
        // 2026-04-08: default changed from "EXCEPTIONS" to "ALL". The original
        // intent was an exception-first screen that drilled in when the user
        // clicked a tile, but HF users opened the screen and saw "No records
        // found" (0 exceptions) with no obvious path to the full container
        // pipeline. Default is now ALL; tiles still drill down to EXCEPTIONS
        // / WATCH / ARRIVING. PR #295 tried to fix this at the ContainerMaint
        // containers() delegate via `filter?.ViewMode ?? "ALL"` but that was
        // dead code because PXDefault populates the field before the delegate
        // runs — the source of truth is this attribute.
        [PXDefault("ALL")]
        [PXUIField(DisplayName = "View")]
        [PXStringList(
            new string[] { "EXCEPTIONS", "WATCH", "ARRIVING", "ALL" },
            new string[] { "Exceptions", "Watch", "Arriving 7 Days", "All Containers" })]
        public string ViewMode { get; set; }
        #endregion

        // Tile 1 — ACTION REQUIRED
        #region KPIActionCount
        public abstract class kpiActionCount : BqlInt.Field<kpiActionCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Action Required", Enabled = false)]
        public int? KPIActionCount { get; set; }
        #endregion

        #region KPIActionBreakdown
        public abstract class kpiActionBreakdown : BqlString.Field<kpiActionBreakdown> { }
        [PXString(500)]
        [PXUIField(DisplayName = "Action Breakdown", Enabled = false)]
        public string KPIActionBreakdown { get; set; }
        #endregion

        // Tile 2 — WATCH
        #region KPIWatchCount
        public abstract class kpiWatchCount : BqlInt.Field<kpiWatchCount> { }
        [PXInt]
        [PXUIField(DisplayName = "Watch", Enabled = false)]
        public int? KPIWatchCount { get; set; }
        #endregion

        #region KPIWatchBreakdown
        public abstract class kpiWatchBreakdown : BqlString.Field<kpiWatchBreakdown> { }
        [PXString(500)]
        [PXUIField(DisplayName = "Watch Breakdown", Enabled = false)]
        public string KPIWatchBreakdown { get; set; }
        #endregion

        // Tile 3 — $ EXPOSURE
        #region KPIExposureTotal
        public abstract class kpiExposureTotal : BqlDecimal.Field<kpiExposureTotal> { }
        [PXDecimal(2)]
        [PXUIField(DisplayName = "Exposure", Enabled = false)]
        public decimal? KPIExposureTotal { get; set; }
        #endregion

        #region KPIExposureBreakdown
        public abstract class kpiExposureBreakdown : BqlString.Field<kpiExposureBreakdown> { }
        [PXString(500)]
        [PXUIField(DisplayName = "Exposure Breakdown", Enabled = false)]
        public string KPIExposureBreakdown { get; set; }
        #endregion

        // Rendered HTML for PXHtmlView tile row
        #region KPITilesHtml
        public abstract class kpiTilesHtml : BqlString.Field<kpiTilesHtml> { }
        [PXString(8000)]
        [PXUIField(DisplayName = "KPI Tiles", Enabled = false)]
        public string KPITilesHtml { get; set; }
        #endregion

        // (TimelineHtml moved to UsrContainer in Phase D — per-row field,
        //  not filter-scoped. Leaving this comment as a breadcrumb.)

        // --- Legacy KPI fields (kept for backwards compat; replaced by tile fields above) ---
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
