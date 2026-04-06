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
