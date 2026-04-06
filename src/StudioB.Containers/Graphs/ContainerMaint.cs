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

        protected virtual IEnumerable containers()
        {
            ContainerFilter filter = Filter.Current;

            if (filter != null && !string.IsNullOrEmpty(filter.StatusFilter))
            {
                string sf = filter.StatusFilter;

                if (sf == "OPEN")
                {
                    foreach (UsrContainer row in SelectFrom<UsrContainer>
                        .Where<UsrContainer.status.IsEqual<ContainerStatus.booked>
                            .Or<UsrContainer.status.IsEqual<ContainerStatus.departed>>>
                        .OrderBy<UsrContainer.eta.Asc>
                        .View.Select(this))
                    {
                        yield return row;
                    }
                    yield break;
                }
                else if (sf == "ARRIVING_THIS_WEEK")
                {
                    DateTime weekStart = DateTime.Today.AddDays(-(int)DateTime.Today.DayOfWeek + (int)DayOfWeek.Monday);
                    if (weekStart > DateTime.Today) weekStart = weekStart.AddDays(-7);
                    DateTime weekEnd = weekStart.AddDays(7);

                    foreach (UsrContainer row in SelectFrom<UsrContainer>
                        .OrderBy<UsrContainer.eta.Asc>
                        .View.Select(this))
                    {
                        if (row.ETA != null && row.ETA >= weekStart && row.ETA < weekEnd)
                            yield return row;
                    }
                    yield break;
                }
                else
                {
                    foreach (UsrContainer row in SelectFrom<UsrContainer>
                        .OrderBy<UsrContainer.eta.Asc>
                        .View.Select(this))
                    {
                        if (row.Status == sf)
                            yield return row;
                    }
                    yield break;
                }
            }

            foreach (UsrContainer row in SelectFrom<UsrContainer>
                .OrderBy<UsrContainer.eta.Asc>
                .View.Select(this))
            {
                yield return row;
            }
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

            int open = 0, inTransit = 0, arrivingThisWeek = 0, customsHold = 0;

            DateTime weekStart = DateTime.Today.AddDays(-(int)DateTime.Today.DayOfWeek + (int)DayOfWeek.Monday);
            if (weekStart > DateTime.Today) weekStart = weekStart.AddDays(-7);
            DateTime weekEnd = weekStart.AddDays(7);

            foreach (UsrContainer c in SelectFrom<UsrContainer>.View.Select(this))
            {
                string status = c.Status ?? "";
                if (status == ContainerStatus.Booked || status == ContainerStatus.Departed) open++;
                if (status == ContainerStatus.InTransit) inTransit++;
                if (status == ContainerStatus.CustomsHold) customsHold++;
                if (c.ETA != null && c.ETA >= weekStart && c.ETA < weekEnd) arrivingThisWeek++;
            }

            e.Row.KPIOpen = open;
            e.Row.KPIInTransit = inTransit;
            e.Row.KPIArrivingThisWeek = arrivingThisWeek;
            e.Row.KPICustomsHold = customsHold;
        }

        protected void _(Events.RowSelected<UsrContainer> e)
        {
            if (e.Row == null) return;
            bool isActive = e.Row.Status != ContainerStatus.Delivered && e.Row.Status != ContainerStatus.Cancelled;
            PXUIFieldAttribute.SetEnabled<UsrContainer.containerCD>(e.Cache, e.Row, string.IsNullOrEmpty(e.Row.ContainerCD));
            RefreshTracking.SetEnabled(isActive);
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
