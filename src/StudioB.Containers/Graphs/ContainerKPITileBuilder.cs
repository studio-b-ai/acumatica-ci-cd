using System;
using System.Globalization;
using System.Text;

namespace StudioB.Containers
{
    /// <summary>
    /// Builds the HTML string for the SB501000 KPI tile row.
    /// Follows the approved tile spec from docs/plans/2026-04-07-sb501000-kpi-tile-approved.md.
    /// Three tiles: ACTION REQUIRED (red), WATCH (amber), $ EXPOSURE (accent).
    /// </summary>
    public static class ContainerKPITileBuilder
    {
        public struct KPIData
        {
            public int ActionCount;
            public int WatchCount;
            public decimal ExposureTotal;
            public int ActionPastLFD;
            public decimal ActionPastLFDDailyRate;
            public int ActionCustomsHold;
            public int ActionISFCutoff;
            public int WatchEtaSlipped;
            public int WatchDocsIncomplete;
            public int WatchArrivingSoon;
            public decimal ExposureDemurrage;
            public decimal ExposureDutyVariance;
            public decimal ExposureOther;
        }

        public static string Build(KPIData data)
        {
            var sb = new StringBuilder(2048);

            // Outer container — ensures stylesheet is embedded even if external CSS fails
            // to load, keeping the screen functional in Acumatica SaaS where custom CSS
            // injection is uncertain.
            sb.Append("<style>");
            sb.Append(EmbeddedStyles);
            sb.Append("</style>");

            sb.Append("<div class='cmd-tile-row'>");

            // ----- Tile 1: ACTION REQUIRED -----
            bool actionEmpty = data.ActionCount == 0;
            sb.AppendFormat(
                "<div class='cmd-tile cmd-tile-critical{0}' onclick=\"sb501000SetViewMode('EXCEPTIONS')\">",
                actionEmpty ? " cmd-tile-empty" : "");
            sb.Append("<div class='cmd-tile-header'>");
            sb.Append("<span class='cmd-tile-marker'>&#9679;</span>"); // ●
            sb.Append("<span class='cmd-tile-label'>ACTION</span>");
            sb.Append("</div>");
            sb.AppendFormat("<div class='cmd-tile-number'>{0}</div>", data.ActionCount);
            sb.AppendFormat("<div class='cmd-tile-sublabel'>{0}</div>",
                actionEmpty ? "NO CRITICAL ITEMS" : "CONTAINERS NEED ACTION");

            if (!actionEmpty)
            {
                sb.Append("<div class='cmd-tile-subtext'>");
                if (data.ActionPastLFD > 0)
                    sb.AppendFormat("<div>&bull; {0} PAST LFD &middot; {1}/DAY</div>",
                        data.ActionPastLFD, FormatMoney(data.ActionPastLFDDailyRate));
                if (data.ActionCustomsHold > 0)
                    sb.AppendFormat("<div>&bull; {0} CUSTOMS HOLD &gt; 2D</div>", data.ActionCustomsHold);
                if (data.ActionISFCutoff > 0)
                    sb.AppendFormat("<div>&bull; {0} ISF CUTOFF &lt; 14D</div>", data.ActionISFCutoff);
                sb.Append("</div>");
            }
            sb.Append("</div>");

            // ----- Tile 2: WATCH -----
            bool watchEmpty = data.WatchCount == 0;
            sb.AppendFormat(
                "<div class='cmd-tile cmd-tile-warning{0}' onclick=\"sb501000SetViewMode('WATCH')\">",
                watchEmpty ? " cmd-tile-empty" : "");
            sb.Append("<div class='cmd-tile-header'>");
            sb.Append("<span class='cmd-tile-marker cmd-tile-marker-warning'>&#9670;</span>"); // ◆
            sb.Append("<span class='cmd-tile-label cmd-tile-label-warning'>WATCH</span>");
            sb.Append("</div>");
            sb.AppendFormat("<div class='cmd-tile-number cmd-tile-number-warning'>{0}</div>", data.WatchCount);
            sb.AppendFormat("<div class='cmd-tile-sublabel'>{0}</div>",
                watchEmpty ? "NOTHING ON WATCH" : "CONTAINERS ON WATCHLIST");

            if (!watchEmpty)
            {
                sb.Append("<div class='cmd-tile-subtext'>");
                if (data.WatchEtaSlipped > 0)
                    sb.AppendFormat("<div>&bull; {0} ETA SLIPPED 7D</div>", data.WatchEtaSlipped);
                if (data.WatchDocsIncomplete > 0)
                    sb.AppendFormat("<div>&bull; {0} DOCS INCOMPLETE</div>", data.WatchDocsIncomplete);
                if (data.WatchArrivingSoon > 0)
                    sb.AppendFormat("<div>&bull; {0} ARRIVE IN 7D</div>", data.WatchArrivingSoon);
                sb.Append("</div>");
            }
            sb.Append("</div>");

            // ----- Tile 3: $ EXPOSURE -----
            bool exposureEmpty = data.ExposureTotal == 0m;
            sb.AppendFormat(
                "<div class='cmd-tile cmd-tile-exposure{0}' onclick=\"sb501000ShowExposurePanel()\">",
                exposureEmpty ? " cmd-tile-empty" : "");
            sb.Append("<div class='cmd-tile-header'>");
            sb.Append("<span class='cmd-tile-marker cmd-tile-marker-accent'>$</span>");
            sb.Append("<span class='cmd-tile-label cmd-tile-label-accent'>EXPOSURE</span>");
            sb.Append("</div>");
            sb.AppendFormat("<div class='cmd-tile-number cmd-tile-number-exposure'>{0}</div>",
                FormatMoney(data.ExposureTotal));
            sb.AppendFormat("<div class='cmd-tile-sublabel'>{0}</div>",
                exposureEmpty ? "NO EXPOSURE" : "AT RISK THIS WEEK");

            if (!exposureEmpty)
            {
                sb.Append("<div class='cmd-tile-subtext'>");
                if (data.ExposureDemurrage > 0m)
                    sb.AppendFormat("<div>&bull; {0} DEMURRAGE</div>", FormatMoney(data.ExposureDemurrage));
                if (data.ExposureDutyVariance > 0m)
                    sb.AppendFormat("<div>&bull; {0} DUTY VAR</div>", FormatMoney(data.ExposureDutyVariance));
                if (data.ExposureOther > 0m)
                    sb.AppendFormat("<div>&bull; {0} OTHER</div>", FormatMoney(data.ExposureOther));
                sb.Append("</div>");
            }
            sb.Append("</div>");

            sb.Append("</div>"); // cmd-tile-row

            // Inline script for click handlers — uses Acumatica's px_alls dispatcher.
            // On click, sets the Filter.ViewMode field and triggers a refresh.
            sb.Append(ClickHandlerScript);

            return sb.ToString();
        }

        private static string FormatMoney(decimal amount)
        {
            if (amount == 0m) return "$0";
            return amount.ToString("C0", CultureInfo.GetCultureInfo("en-US"));
        }

        private const string EmbeddedStyles = @"
.cmd-tile-row { display: flex; gap: 20px; padding: 10px 4px 14px 4px; font-family: 'Segoe UI', system-ui, sans-serif; }
.cmd-tile {
  flex: 1 1 0;
  min-width: 0;
  height: 140px;
  padding: 16px 18px;
  border-left: 4px solid #4a5568;
  background: #f8f9fa;
  cursor: pointer;
  transition: background-color 120ms ease-out;
  box-sizing: border-box;
  overflow: hidden;
}
.cmd-tile-critical { border-left-color: #d64045; background: #fdecea; }
.cmd-tile-critical:hover { background: #fadcd9; }
.cmd-tile-warning  { border-left-color: #e8a33d; background: #fef5e7; }
.cmd-tile-warning:hover { background: #fcebd3; }
.cmd-tile-exposure { border-left-color: #1d3557; background: #ebf0f7; }
.cmd-tile-exposure:hover { background: #dde6f1; }
.cmd-tile-empty { border-left-color: #2d8a5f; background: #f0f7f2; opacity: 0.8; }
.cmd-tile-empty:hover { background: #e3efe8; }
.cmd-tile-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.cmd-tile-marker { font-size: 14px; line-height: 1; color: #d64045; }
.cmd-tile-marker-warning { color: #e8a33d; }
.cmd-tile-marker-accent { color: #1d3557; font-weight: 700; }
.cmd-tile-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; color: #d64045; }
.cmd-tile-label-warning { color: #b37517; }
.cmd-tile-label-accent { color: #1d3557; }
.cmd-tile-number {
  font-size: 48px;
  font-weight: 300;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  margin-bottom: 2px;
  color: #d64045;
}
.cmd-tile-number-warning { color: #b37517; }
.cmd-tile-number-exposure { color: #1d3557; font-size: 40px; }
.cmd-tile-empty .cmd-tile-number { color: #2d8a5f; }
.cmd-tile-sublabel { font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: #4a5568; margin-bottom: 6px; }
.cmd-tile-subtext { font-size: 11px; color: #4a5568; line-height: 1.45; font-variant-numeric: tabular-nums; }
.cmd-tile-subtext div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
";

        private const string ClickHandlerScript = @"
<script>
window.sb501000SetViewMode = function(mode) {
  try {
    var ds = px_alls['ds'];
    if (ds && ds.executeAction) {
      var frm = px_alls['frmFilter'];
      if (frm) {
        frm.updateControlValue('edViewMode', mode);
        frm.postData(true);
      }
    }
  } catch(e) { console.error('sb501000SetViewMode failed', e); }
};
window.sb501000ShowExposurePanel = function() {
  try {
    var ds = px_alls['ds'];
    if (ds && ds.executeCallback) {
      ds.executeCallback('ShowExposurePanel');
    }
  } catch(e) { console.error('sb501000ShowExposurePanel failed', e); }
};
</script>
";
    }
}
