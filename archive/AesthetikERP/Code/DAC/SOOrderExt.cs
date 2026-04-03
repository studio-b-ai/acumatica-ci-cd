using PX.Data;
using PX.Data.BQL;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    public sealed class SOOrderExt : PXCacheExtension<SOOrder>
    {
        public static bool IsActive() => true;

        #region UsrHubSpotDealId
        public abstract class usrHubSpotDealId : BqlString.Field<usrHubSpotDealId> { }

        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "HubSpot Order ID", Visibility = PXUIVisibility.SelectorVisible)]
        public string UsrHubSpotDealId { get; set; }
        #endregion

        #region UsrWMSStatus
        public abstract class usrWMSStatus : BqlString.Field<usrWMSStatus> { }

        [PXDBString(20, IsUnicode = true)]
        [PXDefault(PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "WMS Status")]
        [PXStringList(
            new[] { "N", "A", "P", "F", "K", "S" },
            new[] { "Not Started", "Allocated", "Picking", "Finishing", "Packed", "Shipped" }
        )]
        public string UsrWMSStatus { get; set; }
        #endregion

        #region UsrComplianceHold
        public abstract class usrComplianceHold : BqlBool.Field<usrComplianceHold> { }

        [PXDBBool]
        [PXDefault(false, PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Compliance Hold", Enabled = false)]
        public bool? UsrComplianceHold { get; set; }
        #endregion

        #region UsrComplianceHoldReason
        public abstract class usrComplianceHoldReason : BqlString.Field<usrComplianceHoldReason> { }

        [PXDBString(500, IsUnicode = true)]
        [PXUIField(DisplayName = "Compliance Hold Reason", Enabled = false)]
        public string UsrComplianceHoldReason { get; set; }
        #endregion
    }
}
