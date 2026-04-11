using System;
using System.Text;

namespace StudioB.Containers
{
    /// <summary>
    /// Builds the HTML for the SB501000 status timeline strip — 8 cells showing
    /// the PO-to-delivery lifecycle. Rendered via <c>PXHtmlView</c> bound to
    /// <c>UsrContainer.TimelineHtml</c>.
    ///
    /// Hybrid PO + container stages:
    ///   PLACED → ACKED → FACTORY READY → SHIPPED → IN TRANSIT →
    ///   ARRIVED PORT → CUSTOMS → DELIVERED
    ///
    /// First 3 sourced from linked PO dates, last 5 from container events.
    /// Each cell shows one of three states:
    ///   complete — milestone has a real timestamp (green check)
    ///   active   — current state (colored marker)
    ///   pending  — not yet reached (gray)
    /// </summary>
    public static class ContainerTimelineBuilder
    {
        public struct TimelineData
        {
            public string Status;
            // PO-sourced dates (first 3 stages)
            public DateTime? OrderDate;          // PLACED — earliest linked PO OrderDate
            public DateTime? AcknowledgedDate;   // ACKED — latest linked PO UsrAcknowledgedDate
            public DateTime? FactoryReadyDate;   // FACTORY READY — latest linked PO UsrFactoryReadyDate
            // Container-sourced dates (last 5 stages)
            public DateTime? DepartedDate;       // SHIPPED
            public DateTime? ArrivedPortDate;    // ARRIVED PORT
            public DateTime? CustomsReleasedDate; // CUSTOMS
            public DateTime? DeliveredDate;      // DELIVERED
            public DateTime? ETD;
            public DateTime? ETA;
            public DateTime? ATA;
            public int? CustomsHoldDays;
            // Legacy — kept for backwards compat but no longer drives a stop
            public DateTime? BookedDate;
        }

        private struct Stop
        {
            public string Key;
            public string Label;
            public DateTime? ActualDate;
            public DateTime? EstimatedDate;
            public bool IsCurrent;
            public bool IsAlert;  // customs hold, etc.
        }

        public static string Build(TimelineData data)
        {
            var stops = BuildStops(data);

            var sb = new StringBuilder(2048);
            sb.Append("<style>");
            sb.Append(TimelineStyles);
            sb.Append("</style>");

            sb.Append("<div class='cmd-timeline'>");
            for (int i = 0; i < stops.Length; i++)
            {
                var s = stops[i];
                bool isComplete = s.ActualDate.HasValue;
                string cls = "cmd-timeline-cell";
                if (isComplete) cls += " tl-complete";
                if (s.IsCurrent) cls += " tl-current";
                if (s.IsAlert) cls += " tl-alert";

                sb.AppendFormat("<div class='{0}'>", cls);
                sb.Append("<div class='tl-marker'>");
                if (isComplete) sb.Append("&#10003;");          // ✓
                else if (s.IsAlert) sb.Append("&#9888;");       // ⚠
                else if (s.IsCurrent) sb.Append("&#9679;");     // ●
                else sb.Append("&#9675;");                       // ○
                sb.Append("</div>");
                sb.AppendFormat("<div class='tl-label'>{0}</div>", s.Label);

                string dateStr = FormatCellDate(s);
                sb.AppendFormat("<div class='tl-date'>{0}</div>", dateStr);
                sb.Append("</div>");

                // Connector line between cells (except after last)
                if (i < stops.Length - 1)
                {
                    bool connectorComplete = stops[i + 1].ActualDate.HasValue || stops[i + 1].IsCurrent;
                    sb.AppendFormat("<div class='tl-connector{0}'></div>",
                        connectorComplete ? " tl-connector-complete" : "");
                }
            }
            sb.Append("</div>");

            return sb.ToString();
        }

        private static Stop[] BuildStops(TimelineData d)
        {
            var stops = new Stop[8];
            // PO-sourced stages
            stops[0] = new Stop { Key = "PLACED",    Label = "PLACED",        ActualDate = d.OrderDate };
            stops[1] = new Stop { Key = "ACKED",     Label = "ACKED",         ActualDate = d.AcknowledgedDate };
            stops[2] = new Stop { Key = "FACTORY",   Label = "FACTORY READY", ActualDate = d.FactoryReadyDate };
            // Container-sourced stages
            stops[3] = new Stop { Key = "SHIPPED",   Label = "SHIPPED",       ActualDate = d.DepartedDate, EstimatedDate = d.ETD };
            stops[4] = new Stop { Key = "TRANSIT",   Label = "IN TRANSIT",    ActualDate = null };
            stops[5] = new Stop { Key = "ARRIVED",   Label = "ARRIVED PORT",  ActualDate = d.ArrivedPortDate ?? d.ATA, EstimatedDate = d.ETA };
            stops[6] = new Stop { Key = "CUSTOMS",   Label = "CUSTOMS",       ActualDate = d.CustomsReleasedDate };
            stops[7] = new Stop { Key = "DELIVERED", Label = "DELIVERED",     ActualDate = d.DeliveredDate };

            // For IN TRANSIT, mark complete if departed and not yet arrived
            if (d.DepartedDate.HasValue && !d.ArrivedPortDate.HasValue && !d.ATA.HasValue)
            {
                string status = d.Status ?? "";
                if (status == "IN_TRANSIT" || status == "DEPARTED")
                    stops[4].ActualDate = d.DepartedDate; // show as reached
            }

            // Mark the current stop based on the container status
            string currentKey = MapStatusToStopKey(d.Status);
            for (int i = 0; i < stops.Length; i++)
            {
                if (stops[i].Key == currentKey)
                {
                    stops[i].IsCurrent = true;
                    if (currentKey == "CUSTOMS" && d.CustomsHoldDays.HasValue && d.CustomsHoldDays.Value > 2)
                        stops[i].IsAlert = true;
                }
            }

            return stops;
        }

        private static string MapStatusToStopKey(string status)
        {
            if (string.IsNullOrEmpty(status)) return "PLACED";
            switch (status)
            {
                case "BOOKED":         return "PLACED";
                case "DEPARTED":       return "SHIPPED";
                case "IN_TRANSIT":     return "TRANSIT";
                case "ARRIVED":
                case "DISCHARGED":     return "ARRIVED";
                case "CUSTOMS_HOLD":   return "CUSTOMS";
                case "GATED_OUT":      return "DELIVERED"; // gated out → near delivery
                case "DELIVERED":      return "DELIVERED";
                case "CANCELLED":      return "PLACED";
                default:               return "PLACED";
            }
        }

        private static string FormatCellDate(Stop s)
        {
            if (s.ActualDate.HasValue)
                return s.ActualDate.Value.ToString("MMM d");
            if (s.EstimatedDate.HasValue)
                return "~" + s.EstimatedDate.Value.ToString("MMM d");
            return "&nbsp;";
        }

        private const string TimelineStyles = @"
.cmd-timeline {
  display: flex;
  align-items: center;
  padding: 14px 18px 10px 18px;
  background: #fafbfc;
  border-left: 4px solid #1d3557;
  font-family: 'Segoe UI', system-ui, sans-serif;
}
.cmd-timeline-cell {
  flex: 0 0 auto;
  text-align: center;
  min-width: 80px;
  padding: 0 6px;
}
.tl-marker {
  width: 26px;
  height: 26px;
  line-height: 24px;
  border-radius: 50%;
  font-size: 13px;
  margin: 0 auto 6px auto;
  color: #9aa5b1;
  background: #fff;
  border: 2px solid #cbd2d9;
}
.cmd-timeline-cell.tl-complete .tl-marker {
  color: #fff;
  background: #2d8a5f;
  border-color: #2d8a5f;
}
.cmd-timeline-cell.tl-current .tl-marker {
  color: #fff;
  background: #1d3557;
  border-color: #1d3557;
  box-shadow: 0 0 0 3px #dde6f1;
}
.cmd-timeline-cell.tl-alert .tl-marker {
  color: #fff;
  background: #d64045;
  border-color: #d64045;
  box-shadow: 0 0 0 3px #fadcd9;
}
.tl-label {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #4a5568;
  line-height: 1.2;
  margin-bottom: 2px;
  white-space: nowrap;
}
.tl-date {
  font-size: 10px;
  color: #4a5568;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
}
.cmd-timeline-cell.tl-complete .tl-label { color: #2d8a5f; }
.cmd-timeline-cell.tl-current .tl-label { color: #1d3557; font-weight: 700; }
.cmd-timeline-cell.tl-alert .tl-label { color: #d64045; font-weight: 700; }
.tl-connector {
  flex: 1 1 auto;
  height: 2px;
  background: #cbd2d9;
  margin: 0 2px 18px 2px;
  min-width: 8px;
}
.tl-connector-complete { background: #2d8a5f; }
";
    }
}
