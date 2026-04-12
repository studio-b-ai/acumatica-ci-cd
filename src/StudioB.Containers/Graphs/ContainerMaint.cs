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

        // Delegate: return only the grid-selected container so frmDetail/frmTimeline
        // don't re-execute the full containers() delegate and reset Current.
        // On initial load, Containers.Current may be null if the grid hasn't
        // populated yet — fall back to querying the first container directly.
        protected virtual IEnumerable container()
        {
            UsrContainer current = Containers.Current;
            if (current == null)
            {
                current = SelectFrom<UsrContainer>
                    .OrderBy<UsrContainer.eta.Asc>
                    .View.SelectSingleBound(this, null);
            }
            if (current != null)
                yield return current;
        }

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

        // --- 2026-04-11: PCC redesign — Lead Time tab ---
        public SelectFrom<UsrContainerLeadTime>.View LeadTimes;

        protected virtual IEnumerable leadTimes()
        {
            var container = Container.Current;
            if (container?.ContainerID == null) yield break;

            foreach (PXResult<UsrContainerPOLink, POLine, POOrder, BAccount, InventoryItem> pr in
                SelectFrom<UsrContainerPOLink>
                    .LeftJoin<POLine>.On<POLine.orderType.IsEqual<UsrContainerPOLink.orderType>
                        .And<POLine.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>
                        .And<POLine.lineNbr.IsEqual<UsrContainerPOLink.lineNbr>>>
                    .LeftJoin<POOrder>.On<POOrder.orderType.IsEqual<UsrContainerPOLink.orderType>
                        .And<POOrder.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>>
                    .LeftJoin<BAccount>.On<BAccount.bAccountID.IsEqual<POOrder.vendorID>>
                    .LeftJoin<InventoryItem>.On<InventoryItem.inventoryID.IsEqual<POLine.inventoryID>>
                    .Where<UsrContainerPOLink.containerID.IsEqual<@P.AsInt>>
                    .View.Select(this, container.ContainerID))
            {
                var link = (UsrContainerPOLink)pr;
                var po = (POOrder)pr;
                var vendor = (BAccount)pr;
                var item = (InventoryItem)pr;

                var poExt = po != null ? PXCache<POOrder>.GetExtension<POOrderExt>(po) : null;

                DateTime? orderDate = po?.OrderDate;
                DateTime? ackedDate = poExt?.UsrAcknowledgedDate;
                DateTime? factoryDate = poExt?.UsrFactoryReadyDate;
                DateTime? shippedDate = container.DepartedDate;
                DateTime? deliveredDate = container.DeliveredDate;

                int? placedToAcked = DaysBetween(orderDate, ackedDate);
                int? ackedToFactory = DaysBetween(ackedDate, factoryDate);
                int? factoryToShip = DaysBetween(factoryDate, shippedDate);
                int? shipToDeliver = DaysBetween(shippedDate, deliveredDate);
                int? total = (placedToAcked ?? 0) + (ackedToFactory ?? 0) + (factoryToShip ?? 0) + (shipToDeliver ?? 0);

                yield return new UsrContainerLeadTime
                {
                    LineKey = string.Format("{0}-{1}-{2}", link.OrderType, link.OrderNbr, link.LineNbr),
                    OrderNbr = link.OrderNbr,
                    VendorName = vendor?.AcctName,
                    InventoryCD = item?.InventoryCD,
                    PlacedToAcked = placedToAcked,
                    AckedToFactory = ackedToFactory,
                    FactoryToShip = factoryToShip,
                    ShipToDeliver = shipToDeliver,
                    TotalDays = total > 0 ? total : (int?)null,
                };
            }
        }

        private static int? DaysBetween(DateTime? from, DateTime? to)
        {
            if (!from.HasValue || !to.HasValue) return null;
            return (int)(to.Value.Date - from.Value.Date).TotalDays;
        }
        // --- end 2026-04-11 additions ---

        protected virtual IEnumerable containers()
        {
            ContainerFilter filter = Filter.Current;

            // --- 2026-04-07: ViewMode-driven filtering for Command Center tiles ---
            // The ViewMode default lives on ContainerFilter.viewMode's PXDefault
            // attribute, NOT here. PR #295 tried to change it here and had no
            // effect because PXDefault populates filter.ViewMode before this
            // delegate runs. The ?? fallback is purely defensive against the
            // edge case where Filter.Current is null during early init.
            string viewMode = filter?.ViewMode ?? "ALL";
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
                customsHoldDays: customsHoldDays,
                factoryPromisedDate: row.FactoryPromisedDate,
                factoryActualDate: row.FactoryActualDate);
        }
        #endregion

        #region Status Constants
        public static class ContainerStatus
        {
            public const string Booked = "BOOKED";
            public const string Departed = "DEPARTED";
            public const string InTransit = "IN_TRANSIT";
            public const string Arrived = "ARRIVED";
            public const string Discharged = "DISCHARGED";
            public const string CustomsHold = "CUSTOMS_HOLD";
            public const string GatedOut = "GATED_OUT";
            public const string Delivered = "DELIVERED";
            public const string Cancelled = "CANCELLED";

            public class booked : BqlString.Constant<booked> { public booked() : base(Booked) { } }
            public class departed : BqlString.Constant<departed> { public departed() : base(Departed) { } }
            public class inTransit : BqlString.Constant<inTransit> { public inTransit() : base(InTransit) { } }
            public class customsHold : BqlString.Constant<customsHold> { public customsHold() : base(CustomsHold) { } }
            public class delivered : BqlString.Constant<delivered> { public delivered() : base(Delivered) { } }
            public class cancelled : BqlString.Constant<cancelled> { public cancelled() : base(Cancelled) { } }
        }

        private const decimal DefaultCustomsHoldCostPerDay = 150m;
        #endregion

        #region Actions
        public PXAction<ContainerFilter> OpenContainerDetail;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Open Detail", MapEnableRights = PXCacheRights.Select)]
        protected void openContainerDetail()
        {
            if (Container.Current == null) return;
            Container.AskExt();
        }

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

        // --- 2026-04-08: Phase E — Operational actions for the command center ---

        public PXAction<ContainerFilter> MarkCustomsCleared;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Mark Customs Cleared", MapEnableRights = PXCacheRights.Update)]
        protected void markCustomsCleared()
        {
            var c = Container.Current;
            if (c == null) return;
            if (c.CustomsReleasedDate.HasValue)
            {
                if (Container.Ask("Customs Already Cleared",
                    string.Format("Customs was already marked released on {0:MMM d}. Overwrite?",
                        c.CustomsReleasedDate.Value),
                    MessageButtons.YesNo) != WebDialogResult.Yes)
                    return;
            }
            DateTime now = Accessinfo.BusinessDate ?? DateTime.Today;
            c.CustomsReleasedDate = now;
            c.Status = ContainerStatus.GatedOut;
            Container.Update(c);

            var ev = (UsrContainerEvent)Events.Cache.CreateInstance();
            ev.ContainerID = c.ContainerID;
            ev.NormalizedEventCode = "CUSTOMS_CLEARED";
            ev.CarrierEventCode = "CUSTOMS_CLEARED";
            ev.EventDateTime = now;
            ev.EventClassifier = "ACT";
            ev.Description = "Customs released — marked manually via SB501000";
            Events.Insert(ev);

            Actions.PressSave();
        }

        public PXAction<ContainerFilter> MarkDelivered;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Mark Delivered", MapEnableRights = PXCacheRights.Update)]
        protected void markDelivered()
        {
            var c = Container.Current;
            if (c == null) return;
            DateTime now = Accessinfo.BusinessDate ?? DateTime.Today;
            c.DeliveredDate = now;
            c.Status = ContainerStatus.Delivered;
            Container.Update(c);

            var ev = (UsrContainerEvent)Events.Cache.CreateInstance();
            ev.ContainerID = c.ContainerID;
            ev.NormalizedEventCode = "DELIVERED";
            ev.CarrierEventCode = "DELIVERED";
            ev.EventDateTime = now;
            ev.EventClassifier = "ACT";
            ev.Description = "Delivered to warehouse — marked manually via SB501000";
            Events.Insert(ev);

            Actions.PressSave();
        }

        public PXAction<ContainerFilter> RecordETAUpdate;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Record ETA Update", MapEnableRights = PXCacheRights.Update)]
        protected void recordETAUpdate()
        {
            var c = Container.Current;
            if (c == null) return;
            // When the imports manager manually updates ETA on the form,
            // we append a history row automatically via FieldUpdated. This
            // action is for the "snapshot current ETA to history" convenience
            // button — useful when the ETA didn't change but they want a
            // tracked note.
            var h = (UsrContainerETAHistory)ETAHistory.Cache.CreateInstance();
            h.ContainerID = c.ContainerID;
            h.PreviousETA = c.ETA;
            h.NewETA = c.ETA;
            h.RecordedDate = Accessinfo.BusinessDate ?? DateTime.Today;
            h.Source = "MANUAL";
            h.Note = "Manual snapshot";
            ETAHistory.Insert(h);
            Actions.PressSave();
        }

        public PXAction<ContainerFilter> AttachDocument;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Attach Document", MapEnableRights = PXCacheRights.Update)]
        protected void attachDocument()
        {
            var c = Container.Current;
            if (c == null) return;
            // Inserts a stub UsrContainerDocument row the user then fills in.
            // Actual file upload happens via the NoteID file attachment UI
            // that Acumatica exposes on any row with a PXNote field.
            var d = (UsrContainerDocument)Documents.Cache.CreateInstance();
            d.ContainerID = c.ContainerID;
            d.DocumentType = "OTHER";
            d.Required = true;
            d.Status = "MISSING";
            Documents.Insert(d);
            Actions.PressSave();
        }

        public PXAction<ContainerFilter> PrintReceivingDoc;
        [PXButton]
        [PXUIField(DisplayName = "Print Receiving Doc", MapEnableRights = PXCacheRights.Select)]
        protected void printReceivingDoc()
        {
            var c = Container.Current;
            if (c == null) return;
            // v1: stub — writes an event row so there's an audit trail and
            // raises an info message. Actual PDF report rendering is Phase G
            // polish work (will wire a PXReportTool.Launch here).
            var ev = (UsrContainerEvent)Events.Cache.CreateInstance();
            ev.ContainerID = c.ContainerID;
            ev.NormalizedEventCode = "DOC_PRINTED";
            ev.CarrierEventCode = "DOC_PRINTED";
            ev.EventDateTime = Accessinfo.BusinessDate ?? DateTime.Today;
            ev.EventClassifier = "ACT";
            ev.Description = "Receiving document printed";
            Events.Insert(ev);
            Actions.PressSave();
        }

        // --- 2026-04-11: PCC redesign — Plan Next Order deep-link ---
        public PXAction<ContainerFilter> PlanNextOrder;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Plan Next Order", MapEnableRights = PXCacheRights.Select)]
        protected void planNextOrder()
        {
            var container = Container.Current;
            if (container == null) return;

            // Get primary vendor from first linked PO
            foreach (PXResult<UsrContainerPOLink, POOrder, BAccount, POLine, InventoryItem> row in POLinks.Select())
            {
                var po = (POOrder)row;
                if (po?.VendorID != null)
                {
                    throw new PXRedirectToUrlException(
                        string.Format("https://wms.asthetik.com/vendors/{0}", po.VendorID),
                        PXBaseRedirectException.WindowMode.NewWindow, "Plan Next Order");
                }
            }
        }
        // --- end 2026-04-11 Plan Next Order ---

        public PXAction<ContainerFilter> AddPOLink;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Add PO Line", MapEnableRights = PXCacheRights.Update)]
        protected void addPOLink()
        {
            var c = Container.Current;
            if (c == null) return;
            // v1: opens the AddPOLineFilter smart panel where the user picks
            // an open PO line to attach. The panel is declared on the ASPX.
            if (AddPOLineFilter.AskExt() == WebDialogResult.OK)
            {
                var f = AddPOLineFilter.Current;
                if (f?.OrderType == null || string.IsNullOrEmpty(f.OrderNbr)) return;
                var link = (UsrContainerPOLink)POLinks.Cache.CreateInstance();
                link.ContainerID = c.ContainerID;
                link.OrderType = f.OrderType;
                link.OrderNbr = f.OrderNbr;
                link.LineNbr = f.LineNbr;
                POLinks.Insert(link);
                Actions.PressSave();
            }
        }

        public PXAction<ContainerFilter> RemovePOLink;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Remove PO Line", MapEnableRights = PXCacheRights.Delete)]
        protected void removePOLink()
        {
            var current = POLinks.Current;
            if (current == null) return;
            if (Container.Ask("Remove PO Link",
                "Remove this PO line from the container?",
                MessageButtons.YesNo) != WebDialogResult.Yes) return;
            POLinks.Delete(current);
            Actions.PressSave();
        }

        // --- Phase F: Forwarder CSV import ---
        // Reads the most recent file attachment on the graph's Filter view,
        // parses it as CSV (forwarder-exported format: ContainerNumber, NewETA,
        // NewStatus, EventDate, EventDescription), and updates containers +
        // writes ETA history + event rows.
        public PXAction<ContainerFilter> ImportForwarderCSV;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Import Forwarder CSV", MapEnableRights = PXCacheRights.Update)]
        protected void importForwarderCSV()
        {
            // Find the most recently uploaded file attached to the Filter view
            Guid[] fileIds = PXNoteAttribute.GetFileNotes(Filter.Cache, Filter.Current);
            if (fileIds == null || fileIds.Length == 0)
            {
                throw new PXException(
                    "Attach the forwarder CSV file to this screen first using the paperclip icon, then click Import Forwarder CSV.");
            }

            // Load the most recently attached file
            var upload = PXGraph.CreateInstance<PX.SM.UploadFileMaintenance>();
            var file = upload.GetFile(fileIds[fileIds.Length - 1]);
            if (file == null || file.BinData == null || file.BinData.Length == 0)
            {
                throw new PXException("The attached file is empty or could not be read.");
            }

            string csvText = System.Text.Encoding.UTF8.GetString(file.BinData);
            // Strip BOM if present
            if (csvText.Length > 0 && csvText[0] == '\uFEFF')
                csvText = csvText.Substring(1);

            var result = ForwarderImportParser.Parse(csvText);
            if (result.Errors != null && result.Errors.Count > 0)
            {
                throw new PXException("CSV parse failed: " + string.Join(" | ", result.Errors));
            }

            int updated = 0, eventsAdded = 0, notFound = 0, rowErrors = 0;
            var notFoundNumbers = new List<string>();
            DateTime today = Accessinfo.BusinessDate ?? DateTime.Today;

            foreach (var row in result.Rows)
            {
                if (!string.IsNullOrEmpty(row.ParseError))
                {
                    rowErrors++;
                    continue;
                }

                UsrContainer container = SelectFrom<UsrContainer>
                    .Where<UsrContainer.containerCD.IsEqual<@P.AsString>>
                    .View.SelectSingleBound(this, null, row.ContainerNumber);

                if (container == null)
                {
                    notFound++;
                    if (notFoundNumbers.Count < 5) notFoundNumbers.Add(row.ContainerNumber);
                    continue;
                }

                bool changed = false;

                if (row.NewETA.HasValue && row.NewETA.Value != container.ETA)
                {
                    var hist = (UsrContainerETAHistory)ETAHistory.Cache.CreateInstance();
                    hist.ContainerID = container.ContainerID;
                    hist.PreviousETA = container.ETA;
                    hist.NewETA = row.NewETA.Value;
                    hist.RecordedDate = today;
                    hist.Source = "XLSX";
                    hist.Note = "Forwarder CSV import";
                    ETAHistory.Cache.Insert(hist);

                    container.ETA = row.NewETA.Value;
                    changed = true;
                }

                if (!string.IsNullOrEmpty(row.NewStatus) && row.NewStatus != container.Status)
                {
                    container.Status = row.NewStatus;
                    changed = true;
                }

                if (changed)
                {
                    Containers.Cache.Update(container);
                    updated++;
                }

                if (row.EventDate.HasValue || !string.IsNullOrEmpty(row.EventDescription))
                {
                    var ev = (UsrContainerEvent)Events.Cache.CreateInstance();
                    ev.ContainerID = container.ContainerID;
                    ev.NormalizedEventCode = !string.IsNullOrEmpty(row.NewStatus) ? row.NewStatus : "UPDATE";
                    ev.CarrierEventCode = "CSV_IMPORT";
                    ev.EventDateTime = row.EventDate ?? today;
                    ev.EventClassifier = "ACT";
                    ev.Description = row.EventDescription ?? "Forwarder CSV update";
                    Events.Cache.Insert(ev);
                    eventsAdded++;
                }
            }

            Actions.PressSave();

            var summary = new System.Text.StringBuilder();
            summary.AppendFormat("Import complete. Updated {0} containers, added {1} events.",
                updated, eventsAdded);
            if (notFound > 0)
            {
                summary.Append(" ");
                summary.AppendFormat("{0} container(s) not found: {1}{2}",
                    notFound,
                    string.Join(", ", notFoundNumbers),
                    notFound > notFoundNumbers.Count ? " …" : "");
            }
            if (rowErrors > 0)
            {
                summary.AppendFormat(" {0} row(s) had parse errors.", rowErrors);
            }
            Filter.View.Ask("Forwarder CSV Import", summary.ToString(), MessageButtons.OK);
        }

        // --- Add PO Line filter + selector view for the smart panel ---
        public PXFilter<AddPOLineFilter> AddPOLineFilter;

        public SelectFrom<POLine>
            .LeftJoin<POOrder>.On<POOrder.orderType.IsEqual<POLine.orderType>
                .And<POOrder.orderNbr.IsEqual<POLine.orderNbr>>>
            .LeftJoin<InventoryItem>.On<InventoryItem.inventoryID.IsEqual<POLine.inventoryID>>
            .Where<POLine.lineType.IsEqual<POLineType.goodsForInventory>
                .And<POLine.completed.IsEqual<False>>>
            .OrderBy<POLine.orderType.Asc, POLine.orderNbr.Asc, POLine.lineNbr.Asc>
            .View OpenPOLines;

        // --- end 2026-04-08 actions ---
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
            var metrics = new ContainerKPITileBuilder.MetricsData();
            decimal totalPOValue = 0m;

            foreach (UsrContainer c in SelectFrom<UsrContainer>.View.Select(this))
            {
                string status = c.Status ?? "";

                // --- Legacy counters ---
                if (status == ContainerStatus.Booked || status == ContainerStatus.Departed) open++;
                if (status == ContainerStatus.InTransit) inTransit++;
                if (status == ContainerStatus.CustomsHold) customsHold++;
                if (c.ETA != null && c.ETA >= weekStart && c.ETA < weekEnd) arrivingThisWeek++;

                // --- Pipeline stage counts (before skipping terminal) ---
                switch (status)
                {
                    case ContainerStatus.Booked: tile.PipelineBooked++; break;
                    case ContainerStatus.Departed:
                    case ContainerStatus.InTransit: tile.PipelineInTransit++; break;
                    case ContainerStatus.Arrived:
                    case ContainerStatus.Discharged: tile.PipelineAtPort++; break;
                    case ContainerStatus.CustomsHold: tile.PipelineCustoms++; break;
                }

                // Skip terminal states from risk aggregation
                if (status == ContainerStatus.Delivered || status == ContainerStatus.Cancelled)
                    continue;

                // --- Portfolio metrics (active containers only) ---
                metrics.ActiveContainerCount++;

                int holdDays = ContainerRiskCalculator.CustomsHoldDays(today, status, c.LastSyncDate);

                // --- Tile 1: LATE ---
                bool isLate = false;

                if (c.FactoryPromisedDate.HasValue && c.FactoryPromisedDate.Value.Date < today.Date
                    && !c.FactoryActualDate.HasValue)
                {
                    tile.LateFactoryOverdue++;
                    isLate = true;
                }
                if (c.ETA.HasValue && c.ETA.Value.Date < today.Date && !c.ATA.HasValue
                    && status != ContainerStatus.Delivered && status != ContainerStatus.Cancelled)
                {
                    tile.LatePastETA++;
                    isLate = true;
                }
                if (c.LastFreeDay.HasValue && c.LastFreeDay.Value.Date < today.Date)
                {
                    tile.LatePastLFD++;
                    isLate = true;
                }
                if (status == ContainerStatus.CustomsHold && holdDays > 3)
                {
                    tile.LateCustomsHold++;
                    isLate = true;
                }
                if (isLate)
                    tile.LateCount++;

                // --- Tile 2: AT RISK $ ---
                decimal demurrageExposure = ContainerRiskCalculator.ComputeDemurrageExposure(
                    today, c.LastFreeDay, c.DemurrageDailyRate,
                    customsHoldDays: holdDays,
                    customsHoldEstimatedCostPerDay: null);
                tile.AtRiskDemurrage += demurrageExposure;

                // Customs hold estimated cost: $150/day as a default
                if (holdDays > 0)
                    tile.AtRiskCustomsHoldCost += holdDays * DefaultCustomsHoldCostPerDay;

                // --- Yard-based cross-dock metrics ---
                if (c.ContainerID.HasValue)
                {
                    decimal containerPOValue = 0m;
                    foreach (PXResult<UsrContainerPOLink, POLine> plr in SelectFrom<UsrContainerPOLink>
                        .LeftJoin<POLine>.On<POLine.orderType.IsEqual<UsrContainerPOLink.orderType>
                            .And<POLine.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>
                            .And<POLine.lineNbr.IsEqual<UsrContainerPOLink.lineNbr>>>
                        .Where<UsrContainerPOLink.containerID.IsEqual<@P.AsInt>>
                        .View.Select(this, c.ContainerID))
                    {
                        var poLine = (POLine)plr;

                        // For each PO line, compute yard-based cross-dock
                        if (poLine?.OrderQty != null && poLine.OrderQty.Value > 0m)
                        {
                            metrics.TotalYards += poLine.OrderQty.Value;
                            containerPOValue += poLine.ExtCost ?? 0m;

                            // Find matching open SO lines for this InventoryID
                            if (poLine.InventoryID != null)
                            {
                                decimal soQtySum = 0m;
                                foreach (PX.Objects.SO.SOLine soLine in SelectFrom<PX.Objects.SO.SOLine>
                                    .Where<PX.Objects.SO.SOLine.inventoryID.IsEqual<@P.AsInt>
                                        .And<PX.Objects.SO.SOLine.completed.IsEqual<False>>>
                                    .View.Select(this, poLine.InventoryID))
                                {
                                    soQtySum += soLine.OrderQty ?? 0m;
                                }
                                decimal crossDockedQty = Math.Min(poLine.OrderQty.Value, soQtySum);
                                metrics.CrossDockedYards += crossDockedQty;

                                // Uncovered proportion of this PO line's value
                                decimal uncoveredQty = poLine.OrderQty.Value - crossDockedQty;
                                if (uncoveredQty > 0m && poLine.OrderQty.Value > 0m)
                                {
                                    metrics.UncoveredValue += (poLine.ExtCost ?? 0m) * (uncoveredQty / poLine.OrderQty.Value);
                                }
                            }
                        }
                    }
                    totalPOValue += containerPOValue;
                }
            }

            tile.AtRiskTotal = tile.AtRiskDemurrage + tile.AtRiskCustomsHoldCost;

            // Compute yard-based cross-dock rate
            metrics.OpenPOValue = totalPOValue;
            metrics.CrossDockRate = metrics.TotalYards > 0m
                ? metrics.CrossDockedYards / metrics.TotalYards * 100m
                : 0m;

            // Assign legacy fields for backwards compat
            e.Row.KPIOpen = open;
            e.Row.KPIInTransit = inTransit;
            e.Row.KPIArrivingThisWeek = arrivingThisWeek;
            e.Row.KPICustomsHold = customsHold;

            // Assign new tile fields
            e.Row.KPILateCount = tile.LateCount;
            e.Row.KPIAtRiskTotal = tile.AtRiskTotal;
            e.Row.KPITilesHtml = ContainerKPITileBuilder.Build(tile, metrics);
        }

        protected void _(Events.RowSelected<UsrContainer> e)
        {
            if (e.Row == null) return;
            var row = e.Row;

            // Sync Container.Current to match grid selection (frmTimeline/frmDetail
            // now bind to "Containers" DataMember, but keep this for backend callers)
            if (Container.Current?.ContainerID != row.ContainerID)
                Container.Current = row;

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
            row.DocsSummary = docsRequired > 0
                ? string.Format("{0}/{1}", docsReceived, docsRequired)
                : "—";

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
                docsRequired, docsReceived, etaChanges, holdDays,
                factoryPromisedDate: row.FactoryPromisedDate,
                factoryActualDate: row.FactoryActualDate);

            if (row.LastFreeDay.HasValue)
                row.DaysToLFD = (int)(row.LastFreeDay.Value.Date - today.Date).TotalDays;
            else
                row.DaysToLFD = null;

            row.DemurrageExposure = ContainerRiskCalculator.ComputeDemurrageExposure(
                today, row.LastFreeDay, row.DemurrageDailyRate,
                holdDays, customsHoldEstimatedCostPerDay: null);

            // --- Phase D: Timeline strip + tab count aggregation ---
            // PO date aggregates for hybrid timeline (hoisted for timeline build below)
            DateTime? earliestOrderDate = null;
            DateTime? latestAckedDate = null;
            DateTime? latestFactoryReadyDate = null;

            if (row.ContainerID.HasValue)
            {
                // Events count — simple row count from the child view
                int eventsCount = 0;
                foreach (UsrContainerEvent ev in SelectFrom<UsrContainerEvent>
                    .Where<UsrContainerEvent.containerID.IsEqual<@P.AsInt>>
                    .View.Select(this, row.ContainerID))
                {
                    eventsCount++;
                }
                row.EventsCount = eventsCount;

                // PO links count + total extended cost + PO dates for timeline
                int poLinksCount = 0;
                decimal poLinksTotal = 0m;
                foreach (PXResult<UsrContainerPOLink, POLine, POOrder> pr in SelectFrom<UsrContainerPOLink>
                    .LeftJoin<POLine>.On<POLine.orderType.IsEqual<UsrContainerPOLink.orderType>
                        .And<POLine.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>
                        .And<POLine.lineNbr.IsEqual<UsrContainerPOLink.lineNbr>>>
                    .LeftJoin<POOrder>.On<POOrder.orderType.IsEqual<UsrContainerPOLink.orderType>
                        .And<POOrder.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>>
                    .Where<UsrContainerPOLink.containerID.IsEqual<@P.AsInt>>
                    .View.Select(this, row.ContainerID))
                {
                    poLinksCount++;
                    var line = (POLine)pr;
                    if (line?.ExtCost != null) poLinksTotal += line.ExtCost.Value;

                    var po = (POOrder)pr;
                    if (po != null)
                    {
                        if (po.OrderDate.HasValue && (!earliestOrderDate.HasValue || po.OrderDate.Value < earliestOrderDate.Value))
                            earliestOrderDate = po.OrderDate;
                        var poExt = PXCache<POOrder>.GetExtension<POOrderExt>(po);
                        if (poExt?.UsrAcknowledgedDate != null && (!latestAckedDate.HasValue || poExt.UsrAcknowledgedDate.Value > latestAckedDate.Value))
                            latestAckedDate = poExt.UsrAcknowledgedDate;
                        if (poExt?.UsrFactoryReadyDate != null && (!latestFactoryReadyDate.HasValue || poExt.UsrFactoryReadyDate.Value > latestFactoryReadyDate.Value))
                            latestFactoryReadyDate = poExt.UsrFactoryReadyDate;
                    }
                }
                row.POLinksCount = poLinksCount;
                row.POLinksTotal = poLinksTotal;

                // Costs count + total
                int costsCount = 0;
                decimal costsTotal = 0m;
                foreach (UsrContainerCost c in SelectFrom<UsrContainerCost>
                    .Where<UsrContainerCost.containerID.IsEqual<@P.AsInt>>
                    .View.Select(this, row.ContainerID))
                {
                    costsCount++;
                    if (c.Amount != null) costsTotal += c.Amount.Value;
                }
                row.CostsCount = costsCount;
                row.CostsTotal = costsTotal;
            }
            else
            {
                row.EventsCount = 0;
                row.POLinksCount = 0;
                row.POLinksTotal = 0m;
                row.CostsCount = 0;
                row.CostsTotal = 0m;
            }

            // Build the timeline HTML for the selected row
            row.TimelineHtml = ContainerTimelineBuilder.Build(new ContainerTimelineBuilder.TimelineData
            {
                Status = row.Status,
                // PO-sourced dates (hybrid timeline)
                OrderDate = earliestOrderDate,
                AcknowledgedDate = latestAckedDate,
                FactoryReadyDate = latestFactoryReadyDate,
                // Container-level mill/factory dates
                FactoryPromisedDate = row.FactoryPromisedDate,
                FactoryActualDate = row.FactoryActualDate,
                MillAckDate = row.MillAckDate,
                // Container-sourced dates
                BookedDate = row.BookedDate,
                DepartedDate = row.DepartedDate,
                ArrivedPortDate = row.ArrivedPortDate,
                CustomsReleasedDate = row.CustomsReleasedDate,
                DeliveredDate = row.DeliveredDate,
                ETD = row.ETD,
                ETA = row.ETA,
                ATA = row.ATA,
                CustomsHoldDays = holdDays,
            });

            // Build the JSON payload that the client-side tab label updater consumes.
            // Key-value pairs: tab index → label text. Tabs in SB501000:
            //   0 = Events, 1 = PO Links, 2 = Costs
            // (Phase E will add Docs and ETA History tabs.)
            string docsBadge = "";
            if (docsRequired > 0)
            {
                bool complete = docsReceived >= docsRequired;
                docsBadge = string.Format(" ({0}/{1})", docsReceived, docsRequired);
                if (!complete) docsBadge += " \u25CF"; // red dot suffix rendered by JS
            }
            row.TabLabelsJson = string.Format(
                "{{\"0\":\"Events ({0})\",\"1\":\"POs ({1}) \u2022 ${2:N0}\",\"2\":\"Costs ({3}) \u2022 ${4:N0}\"}}",
                eventsCount(row),
                row.POLinksCount, row.POLinksTotal,
                row.CostsCount, row.CostsTotal);
        }

        // Helper for format-string nullable int — keeps the composite string clean
        private static int eventsCount(UsrContainer row) => row.EventsCount ?? 0;
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
