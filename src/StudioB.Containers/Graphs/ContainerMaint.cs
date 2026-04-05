using System;
using PX.Data;
using PX.Data.BQL.Fluent;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class ContainerMaint : PXGraph<ContainerMaint, UsrContainer>
    {
        public static bool IsActive() => true;

        #region Views
        public SelectFrom<UsrContainer>.View Container;

        public SelectFrom<UsrContainerEvent>
            .Where<UsrContainerEvent.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .OrderBy<UsrContainerEvent.eventDateTime.Desc>
            .View Events;

        public SelectFrom<UsrContainerPOLink>
            .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View POLinks;
        #endregion

        #region Actions
        public PXAction<UsrContainer> RefreshTracking;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Refresh Tracking", MapEnableRights = PXCacheRights.Update)]
        protected void refreshTracking()
        {
            // Placeholder — tracking refresh triggered via API from webhook-router.
            // This action can be wired to call the carrier API directly in a future phase,
            // or to push a message to the webhook-router BullMQ queue.
            UsrContainer container = Container.Current;
            if (container == null) return;

            container.LastSyncDate = DateTime.UtcNow;
            Container.Update(container);
            Actions.PressSave();
        }
        #endregion

        #region Event Handlers
        protected void _(Events.RowSelected<UsrContainer> e)
        {
            if (e.Row == null) return;
            bool isActive = e.Row.Status != "DELIVERED" && e.Row.Status != "CANCELLED";
            PXUIFieldAttribute.SetEnabled<UsrContainer.containerCD>(e.Cache, e.Row, string.IsNullOrEmpty(e.Row.ContainerCD));
            RefreshTracking.SetEnabled(isActive);
        }
        #endregion

        #region Persist Override
        public override void Persist()
        {
            UsrContainer container = Container.Current;
            base.Persist();

            // After save, propagate ETA to linked PO headers and lines
            if (container?.ETA != null)
            {
                var poRefs = new System.Collections.Generic.List<Tuple<string, string, int?>>();
                foreach (UsrContainerPOLink link in POLinks.Select())
                {
                    poRefs.Add(Tuple.Create(link.OrderType, link.OrderNbr, link.LineNbr));
                }
                if (poRefs.Count > 0)
                {
                    ContainerDatePropagation.PropagateArrivalDate(container.ETA, poRefs);
                }
            }

            // Push container update to webhook-router for carrier event refresh
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
                catch { /* Fire-and-forget — don't block save */ }
            }
        }
        #endregion
    }
}
