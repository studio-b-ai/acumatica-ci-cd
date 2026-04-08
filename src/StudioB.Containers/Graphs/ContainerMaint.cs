using System;
using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.PO;
using PX.Objects.CR;
using PX.Objects.IN;

namespace StudioB.Containers
{
    public class ContainerMaint : PXGraph<ContainerMaint>
    {
        public static bool IsActive() => true;

        #region Views
        public PXFilter<ContainerFilter> Filter;

        public SelectFrom<UsrContainer>
            .OrderBy<UsrContainer.eta.Asc>
            .View Containers;

        public SelectFrom<UsrContainer>.View Container;

        public SelectFrom<UsrContainerEvent>
            .Where<UsrContainerEvent.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .OrderBy<UsrContainerEvent.eventDateTime.Desc>
            .View Events;

        public SelectFrom<UsrContainerPOLink>
            .LeftJoin<POOrder>.On<POOrder.orderType.IsEqual<UsrContainerPOLink.orderType>
                .And<POOrder.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>>
            .LeftJoin<BAccount>.On<BAccount.bAccountID.IsEqual<POOrder.vendorID>>
            .LeftJoin<POLine>.On<POLine.orderType.IsEqual<UsrContainerPOLink.orderType>
                .And<POLine.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>
                .And<POLine.lineNbr.IsEqual<UsrContainerPOLink.lineNbr>>>
            .LeftJoin<InventoryItem>.On<InventoryItem.inventoryID.IsEqual<POLine.inventoryID>>
            .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View POLinks;

        public SelectFrom<UsrContainerCost>
            .Where<UsrContainerCost.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View Costs;

        // --- 2026-04-07: Command Center redesign (RFC 1 Phase A) ---
        public SelectFrom<UsrContainerETAHistory>
            .Where<UsrContainerETAHistory.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .OrderBy<UsrContainerETAHistory.recordedDate.Desc>
            .View ETAHistory;

        public SelectFrom<UsrContainerDocument>
            .Where<UsrContainerDocument.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .OrderBy<UsrContainerDocument.documentType.Asc>
            .View Documents;
        // --- end 2026-04-07 additions ---

        protected virtual IEnumerable containers()
        {
            ContainerFilter filter = Filter.Current;

            // --- 2026-04-07: ViewMode-driven filtering for Command Center tiles ---
            string viewMode = filter?.ViewMode ?? "EXCEPTIONS";
            DateTime today = Accessinfo.BusinessDate ?? DateTime.Today;

            // Load all rows once, then apply post-filter. Container count is small enough
            // (<1000 containers in HF's history) that in-memory filtering is acceptable,
            // and it lets us apply risk-level logic that's hard to express in BQL.
            var all = new List<UsrContainer>();
            foreach (UsrContainer row in SelectFrom<UsrContainer>
                .OrderBy<UsrContainer.eta.Asc>
                .View.Select(this))
            {
                all.Add(row);
            }

            // Legacy StatusFilter still honored for KPI card compatibility
            if (filter != null && !string.IsNullOrEmpty(filter.StatusFilter))
            {
                string sf = filter.StatusFilter;
                if (sf == "OPEN")
                {
                    foreach (var row in all)
                        if (row.Status == ContainerStatus.Booked || row.Status == ContainerStatus.Departed)
                            yield return row;
                    yield break;
                }
                if (sf == "ARRIVING_THIS_WEEK")
                {
                    DateTime weekStart = today.AddDays(-(int)today.DayOfWeek + (int)DayOfWeek.Monday);
                    if (weekStart > today) weekStart = weekStart.AddDays(-7);
                    DateTime weekEnd = weekStart.AddDays(7);
                    foreach (var row in all)
                        if (row.ETA != null && row.ETA >= weekStart && row.ETA < weekEnd)
                            yield return row;
                    yield break;
                }
                foreach (var row in all)
                    if (row.Status == sf) yield return row;
                yield break;
            }

            // New ViewMode filtering
            if (viewMode == "ALL")
            {
                foreach (var row in all) yield return row;
                yield break;
            }
            if (viewMode == "ARRIVING")
            {
                DateTime horizon = today.AddDays(7);
                foreach (var row in all)
                    if (row.ETA.HasValue && row.ETA.Value.Date >= today.Date && row.ETA.Value.Date <= horizon.Date)
                        yield return row;
                yield break;
            }

            // EXCEPTIONS (default) and WATCH both require the risk level which is computed
            // per-row at RowSelected time. To filter here we recompute cheaply inline.
            foreach (var row in all)
            {
                string rl = ComputeRiskLevelInline(row, today);
                if (viewMode == "EXCEPTIONS" && rl == ContainerRiskCalculator.RiskCritical)
                    yield return row;
                else if (viewMode == "WATCH" && rl == ContainerRiskCalculator.RiskWarning)
                    yield return row;
            }
        }

        /// <summary>
        /// Lightweight inline risk level computation for the data delegate filter.
        /// Counts of docs and ETA history are skipped here (set to 0) — they'd cost a query
        /// per container which is too expensive at list time. Full risk level lands during
        /// RowSelected for the currently displayed rows.
        /// </summary>
        private string ComputeRiskLevelInline(UsrContainer row, DateTime today)
        {
            int customsHoldDays = ContainerRiskCalculator.CustomsHoldDays(today, row.Status, row.LastSyncDate);
            return ContainerRiskCalculator.ComputeRiskLevel(
                today,
                row.Status,
                row.LastFreeDay,
                row.ETA,
                row.ISFFiledDate,
                row.DepartedDate,
                docsRequired: 0,
                docsReceived: 0,
                etaChangesLast7Days: 0,
                customsHoldDays: customsHoldDays);
        }
        #endregion

        #region Status Constants
        public static class ContainerStatus
        {
            public const string Booked = "BOOKED";
            public const string Departed = "DEPARTED";
            public const string InTransit = "IN_TRANSIT";
            public const string CustomsHold = "CUSTOMS_HOLD";
            public const string Delivered = "DELIVERED";
            public const string Cancelled = "CANCELLED";

            public class booked : BqlString.Constant<booked> { public booked() : base(Booked) { } }
            public class departed : BqlString.Constant<departed> { public departed() : base(Departed) { } }
            public class inTransit : BqlString.Constant<inTransit> { public inTransit() : base(InTransit) { } }
            public class customsHold : BqlString.Constant<customsHold> { public customsHold() : base(CustomsHold) { } }
            public class delivered : BqlString.Constant<delivered> { public delivered() : base(Delivered) { } }
            public class cancelled : BqlString.Constant<cancelled> { public cancelled() : base(Cancelled) { } }
        }
        #endregion

        #region Actions
        public PXAction<ContainerFilter> RefreshTracking;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Refresh Tracking", MapEnableRights = PXCacheRights.Update)]
        protected void refreshTracking()
        {
            UsrContainer container = Container.Current;
            if (container == null) return;
            container.LastSyncDate = DateTime.UtcNow;
            Container.Update(container);
            Actions.PressSave();
        }

        public PXAction<ContainerFilter> CreateLandedCost;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Create Landed Cost", MapEnableRights = PXCacheRights.Update)]
        protected void createLandedCost()
        {
            UsrContainer container = Container.Current;
            if (container == null) return;

            // Validate: container has costs
            var costs = new List<UsrContainerCost>();
            foreach (UsrContainerCost c in Costs.Select())
            {
                if ((c.Amount ?? 0m) > 0m) costs.Add(c);
            }
            if (costs.Count == 0)
                throw new PXException("Add costs to this container before creating a Landed Cost document.");

            // Validate: container has PO links
            var poLinks = new List<UsrContainerPOLink>();
            foreach (PXResult<UsrContainerPOLink, POOrder, BAccount, POLine, InventoryItem> row in POLinks.Select())
            {
                poLinks.Add((UsrContainerPOLink)row);
            }
            if (poLinks.Count == 0)
                throw new PXException("Link at least one PO to this container before creating a Landed Cost document.");

            // Validate: LC codes configured
            var prefs = PXSelect<UsrContainerPrefs>.Select(this).TopFirst;
            if (prefs == null)
                throw new PXException("Configure Landed Cost Codes in Container Preferences (SB302030).");

            // Warn if LC already created
            if (!string.IsNullOrEmpty(container.LandedCostRefNbr))
            {
                if (Container.Ask("Landed Cost",
                    string.Format("Landed Cost {0} already exists for this container. Create another?", container.LandedCostRefNbr),
                    MessageButtons.YesNo) != WebDialogResult.Yes)
                {
                    return;
                }
            }

            // Find released PO receipts linked to this container's POs
            var receiptNbrs = new HashSet<string>();
            foreach (var link in poLinks)
            {
                foreach (PXResult<POReceiptLine, POReceipt> rl in PXSelectJoin<POReceiptLine,
                    InnerJoin<POReceipt, On<POReceipt.receiptType, Equal<POReceiptLine.receiptType>,
                        And<POReceipt.receiptNbr, Equal<POReceiptLine.receiptNbr>>>>,
                    Where<POReceiptLine.pOType, Equal<Required<POReceiptLine.pOType>>,
                        And<POReceiptLine.pONbr, Equal<Required<POReceiptLine.pONbr>>,
                        And<POReceipt.released, Equal<True>>>>>
                    .Select(this, link.OrderType, link.OrderNbr))
                {
                    var receipt = (POReceipt)rl;
                    receiptNbrs.Add(receipt.ReceiptNbr);
                }
            }

            if (receiptNbrs.Count == 0)
                throw new PXException("No released PO receipts found for the linked POs. Release receipts before creating a Landed Cost document.");

            // Create the Landed Cost document via separate graph
            var lcGraph = PXGraph.CreateInstance<POLandedCostDocEntry>();
            var lcDoc = lcGraph.Document.Insert(new POLandedCostDoc());
            lcDoc.DocDate = Accessinfo.BusinessDate;

            // Set vendor from first cost row that has one
            foreach (var cost in costs)
            {
                if (cost.VendorID != null)
                {
                    lcDoc.VendorID = cost.VendorID;
                    break;
                }
            }
            lcGraph.Document.Update(lcDoc);

            // Add cost detail lines
            foreach (var cost in costs)
            {
                string lcCode = GetLCCode(prefs, cost.CostType);
                if (string.IsNullOrEmpty(lcCode))
                {
                    throw new PXException(
                        string.Format("No Landed Cost Code configured for cost type '{0}'. Set it in Container Preferences (SB302030).", cost.CostType));
                }

                var detail = new POLandedCostDetail();
                detail.LandedCostCodeID = lcCode;
                detail.CuryLineAmt = cost.Amount;
                detail.Descr = cost.Description ?? cost.CostType;
                lcGraph.Details.Insert(detail);
            }

            lcGraph.Actions.PressSave();

            // Store reference on container
            container.LandedCostRefNbr = lcGraph.Document.Current.RefNbr;
            container.LandedCostStatus = lcGraph.Document.Current.Status;
            Container.Update(container);

            // Backfill custom receipt line fields so per-unit calculator stays accurate.
            // Aggregate container costs by type, then distribute proportionally across
            // receipt lines by quantity.
            decimal totalDuty = 0m, totalFreight = 0m, totalBrokerage = 0m;
            foreach (var cost in costs)
            {
                switch (cost.CostType)
                {
                    case "DUTY": totalDuty += cost.Amount ?? 0m; break;
                    case "TARIFF": totalDuty += cost.Amount ?? 0m; break;  // tariff rolls into duty
                    case "SHIPPING": totalFreight += cost.Amount ?? 0m; break;
                    case "BROKERAGE": totalBrokerage += cost.Amount ?? 0m; break;
                }
            }

            if (totalDuty > 0m || totalFreight > 0m || totalBrokerage > 0m)
            {
                // Sum total receipt qty for proportional allocation
                decimal totalQty = 0m;
                var receiptLineKeys = new List<Tuple<string, string, int?>>();
                foreach (var rl in receiptNbrs)
                {
                    foreach (POReceiptLine line in PXSelect<POReceiptLine,
                        Where<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>>>
                        .Select(this, rl))
                    {
                        totalQty += line.ReceiptQty ?? 0m;
                        receiptLineKeys.Add(Tuple.Create(line.ReceiptType, line.ReceiptNbr, (int?)line.LineNbr));
                    }
                }

                if (totalQty > 0m)
                {
                    var receiptGraph = PXGraph.CreateInstance<PX.Objects.PO.POReceiptEntry>();
                    foreach (var key in receiptLineKeys)
                    {
                        POReceiptLine rl = PXSelect<POReceiptLine,
                            Where<POReceiptLine.receiptType, Equal<Required<POReceiptLine.receiptType>>,
                                And<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>,
                                And<POReceiptLine.lineNbr, Equal<Required<POReceiptLine.lineNbr>>>>>>
                            .Select(this, key.Item1, key.Item2, key.Item3);
                        if (rl == null) continue;

                        decimal share = (rl.ReceiptQty ?? 0m) / totalQty;
                        var ext = PXCache<POReceiptLine>.GetExtension<POReceiptLineExt>(rl);
                        if (ext != null)
                        {
                            ext.UsrActualDutyAmt = Math.Round(totalDuty * share, 2);
                            ext.UsrActualFreightAmt = Math.Round(totalFreight * share, 2);
                            ext.UsrBrokerageAmt = Math.Round(totalBrokerage * share, 2);
                            this.Caches[typeof(POReceiptLine)].Update(rl);
                        }
                    }
                }
            }

            Actions.PressSave();
        }

        private string GetLCCode(UsrContainerPrefs prefs, string costType)
        {
            switch (costType)
            {
                case "SHIPPING": return prefs.LCCodeShipping;
                case "DUTY": return prefs.LCCodeDuty;
                case "TARIFF": return prefs.LCCodeTariff;
                case "BROKERAGE": return prefs.LCCodeBrokerage;
                case "OTHER": return prefs.LCCodeOther;
                default: return prefs.LCCodeOther;
            }
        }
        #endregion

        #region Event Handlers
        protected void _(Events.RowSelected<ContainerFilter> e)
        {
            if (e.Row == null) return;

            DateTime today = Accessinfo.BusinessDate ?? DateTime.Today;
            DateTime weekStart = today.AddDays(-(int)today.DayOfWeek + (int)DayOfWeek.Monday);
            if (weekStart > today) weekStart = weekStart.AddDays(-7);
            DateTime weekEnd = weekStart.AddDays(7);
            DateTime horizon7 = today.AddDays(7);

            // Legacy KPI counters
            int open = 0, inTransit = 0, arrivingThisWeek = 0, customsHold = 0;

            // Command Center tile data
            var tile = new ContainerKPITileBuilder.KPIData();

            foreach (UsrContainer c in SelectFrom<UsrContainer>.View.Select(this))
            {
                string status = c.Status ?? "";

                // --- Legacy counters ---
                if (status == ContainerStatus.Booked || status == ContainerStatus.Departed) open++;
                if (status == ContainerStatus.InTransit) inTransit++;
                if (status == ContainerStatus.CustomsHold) customsHold++;
                if (c.ETA != null && c.ETA >= weekStart && c.ETA < weekEnd) arrivingThisWeek++;

                // Skip terminal states from risk aggregation
                if (status == ContainerStatus.Delivered || status == ContainerStatus.Cancelled)
                    continue;

                // --- Risk level (inline, without doc/history joins for perf) ---
                int holdDays = ContainerRiskCalculator.CustomsHoldDays(today, status, c.LastSyncDate);
                string rl = ContainerRiskCalculator.ComputeRiskLevel(
                    today, status, c.LastFreeDay, c.ETA, c.ISFFiledDate, c.DepartedDate,
                    docsRequired: 0, docsReceived: 0, etaChangesLast7Days: 0,
                    customsHoldDays: holdDays);

                // --- Tile 1 breakdown ---
                if (rl == ContainerRiskCalculator.RiskCritical)
                {
                    tile.ActionCount++;

                    if (c.LastFreeDay.HasValue && c.LastFreeDay.Value.Date < today.Date)
                    {
                        tile.ActionPastLFD++;
                        if (c.DemurrageDailyRate.HasValue)
                            tile.ActionPastLFDDailyRate += c.DemurrageDailyRate.Value;
                    }
                    if (status == ContainerStatus.CustomsHold && holdDays > 2)
                        tile.ActionCustomsHold++;
                    if (!c.ISFFiledDate.HasValue && !c.DepartedDate.HasValue &&
                        status == ContainerStatus.Booked &&
                        c.ETA.HasValue && (c.ETA.Value.Date - today.Date).TotalDays < 14)
                        tile.ActionISFCutoff++;
                }
                // --- Tile 2 breakdown ---
                else if (rl == ContainerRiskCalculator.RiskWarning)
                {
                    tile.WatchCount++;

                    if (c.LastFreeDay.HasValue &&
                        (c.LastFreeDay.Value.Date - today.Date).TotalDays <= 3)
                    {
                        // LFD-soon counted in ETA slipped bucket only if it's not already action-level
                    }
                    if (c.ETA.HasValue &&
                        c.ETA.Value.Date <= horizon7.Date &&
                        c.ETA.Value.Date >= today.Date)
                        tile.WatchArrivingSoon++;
                }

                // --- Tile 3 exposure ---
                decimal exposure = ContainerRiskCalculator.ComputeDemurrageExposure(
                    today, c.LastFreeDay, c.DemurrageDailyRate,
                    customsHoldDays: holdDays,
                    customsHoldEstimatedCostPerDay: null);
                if (exposure > 0m)
                {
                    tile.ExposureDemurrage += exposure;
                }
            }

            tile.ExposureTotal = tile.ExposureDemurrage + tile.ExposureDutyVariance + tile.ExposureOther;

            // Assign legacy fields for backwards compat
            e.Row.KPIOpen = open;
            e.Row.KPIInTransit = inTransit;
            e.Row.KPIArrivingThisWeek = arrivingThisWeek;
            e.Row.KPICustomsHold = customsHold;

            // Assign Command Center tile fields
            e.Row.KPIActionCount = tile.ActionCount;
            e.Row.KPIWatchCount = tile.WatchCount;
            e.Row.KPIExposureTotal = tile.ExposureTotal;
            e.Row.KPITilesHtml = ContainerKPITileBuilder.Build(tile);
        }

        protected void _(Events.RowSelected<UsrContainer> e)
        {
            if (e.Row == null) return;
            var row = e.Row;

            bool isActive = row.Status != ContainerStatus.Delivered && row.Status != ContainerStatus.Cancelled;
            PXUIFieldAttribute.SetEnabled<UsrContainer.containerCD>(e.Cache, row, string.IsNullOrEmpty(row.ContainerCD));
            RefreshTracking.SetEnabled(isActive);

            // --- Compute per-row risk, LFD countdown, exposure, doc counts ---
            DateTime today = Accessinfo.BusinessDate ?? DateTime.Today;
            int holdDays = ContainerRiskCalculator.CustomsHoldDays(today, row.Status, row.LastSyncDate);

            // Document counts — only for the currently displayed row, to keep list-time perf OK
            int docsRequired = 0, docsReceived = 0;
            if (row.ContainerID.HasValue)
            {
                foreach (UsrContainerDocument d in SelectFrom<UsrContainerDocument>
                    .Where<UsrContainerDocument.containerID.IsEqual<@P.AsInt>>
                    .View.Select(this, row.ContainerID))
                {
                    if (d.Required == true) docsRequired++;
                    if (d.Status == "RECEIVED" || d.Status == "VERIFIED") docsReceived++;
                }
            }

            row.DocsRequiredCount = docsRequired;
            row.DocsReceivedCount = docsReceived;

            // ETA change count (last 7 days) — only for the displayed row
            int etaChanges = 0;
            if (row.ContainerID.HasValue)
            {
                DateTime sevenDaysAgo = today.AddDays(-7);
                foreach (UsrContainerETAHistory h in SelectFrom<UsrContainerETAHistory>
                    .Where<UsrContainerETAHistory.containerID.IsEqual<@P.AsInt>
                        .And<UsrContainerETAHistory.recordedDate.IsGreaterEqual<@P.AsDateTime>>>
                    .View.Select(this, row.ContainerID, sevenDaysAgo))
                {
                    etaChanges++;
                }
            }

            row.RiskLevel = ContainerRiskCalculator.ComputeRiskLevel(
                today, row.Status, row.LastFreeDay, row.ETA, row.ISFFiledDate, row.DepartedDate,
                docsRequired, docsReceived, etaChanges, holdDays);

            if (row.LastFreeDay.HasValue)
                row.DaysToLFD = (int)(row.LastFreeDay.Value.Date - today.Date).TotalDays;
            else
                row.DaysToLFD = null;

            row.DemurrageExposure = ContainerRiskCalculator.ComputeDemurrageExposure(
                today, row.LastFreeDay, row.DemurrageDailyRate,
                holdDays, customsHoldEstimatedCostPerDay: null);
        }
        #endregion

        #region Persist Override
        public override void Persist()
        {
            UsrContainer container = Container.Current;
            base.Persist();

            if (container?.ETA != null)
            {
                var poRefs = new List<Tuple<string, string, int?>>();
                foreach (UsrContainerPOLink link in POLinks.Select())
                {
                    poRefs.Add(Tuple.Create(link.OrderType, link.OrderNbr, link.LineNbr));
                }
                if (poRefs.Count > 0)
                {
                    ContainerDatePropagation.PropagateArrivalDate(container.ETA, poRefs);
                }
            }

            if (container != null)
            {
                try
                {
                    var webhookUrl = System.Configuration.ConfigurationManager.AppSettings["ContainerWebhookUrl"];
                    if (!string.IsNullOrEmpty(webhookUrl))
                    {
                        var json = Newtonsoft.Json.JsonConvert.SerializeObject(new
                        {
                            ContainerCD = container.ContainerCD,
                            CarrierCode = container.CarrierCode,
                            ContainerID = container.ContainerID,
                            Status = container.Status,
                        });
                        using (var wc = new System.Net.WebClient())
                        {
                            wc.Headers[System.Net.HttpRequestHeader.ContentType] = "application/json";
                            wc.UploadStringAsync(new System.Uri(webhookUrl), "POST", json);
                        }
                    }
                }
                catch { /* Fire-and-forget */ }
            }
        }
        #endregion
    }
}
