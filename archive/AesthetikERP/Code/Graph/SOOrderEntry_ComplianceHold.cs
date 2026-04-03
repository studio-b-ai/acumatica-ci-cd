using PX.Data;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    public class SOOrderEntry_ComplianceHold : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        protected void _(Events.RowSelected<SOOrder> e)
        {
            if (e.Row == null) return;
            SOOrderExt ext = e.Row.GetExtension<SOOrderExt>();
            bool held = ext?.UsrComplianceHold == true;

            Base.Actions["CreateShipmentIssue"]?.SetEnabled(!held);
            AcknowledgeComplianceHold.SetVisible(held);
            AcknowledgeComplianceHold.SetEnabled(held);

            if (held)
            {
                e.Cache.RaiseExceptionHandling<SOOrderExt.usrComplianceHold>(
                    e.Row, true,
                    new PXSetPropertyException(
                        "This order is on compliance hold. Review and acknowledge requirements before shipping.",
                        PXErrorLevel.Warning));
            }
        }

        public PXAction<SOOrder> AcknowledgeComplianceHold;

        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Acknowledge Compliance", MapEnableRights = PXCacheRights.Update)]
        protected void acknowledgeComplianceHold()
        {
            SOOrder order = Base.Document.Current;
            if (order == null) return;

            SOOrderExt ext = order.GetExtension<SOOrderExt>();
            if (ext?.UsrComplianceHold != true) return;

            Base.Document.Cache.SetValueExt<SOOrderExt.usrComplianceHold>(order, false);
            Base.Document.Cache.SetValueExt<SOOrderExt.usrComplianceHoldReason>(order, null);
            Base.Document.Update(order);
            Base.Actions.PressSave();
        }
    }
}
