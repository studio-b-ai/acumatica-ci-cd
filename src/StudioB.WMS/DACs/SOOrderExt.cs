using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.SO;

namespace Aesthetik.WMS
{
    /// <summary>
    /// SOOrder DAC extension — HubSpot deal ID, WMS status, compliance hold.
    /// Migrated from HeritageFabricsPOv5 during ISV consolidation.
    ///
    /// NoteID is required here (ticket #44514576665): without [PXNote] on the
    /// extension, Acumatica's cache routing for the Notes/Activities panel on
    /// SO301000 cannot persist notes — the framework maps note CRUD through the
    /// active extension cache, and a missing NoteID field causes a silent drop
    /// or a "Field 'NoteID' not found" exception on Save.
    /// </summary>
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
        [PXUIField(DisplayName = "Compliance Hold", Enabled = true)]
        public bool? UsrComplianceHold { get; set; }
        #endregion

        #region UsrComplianceHoldReason
        public abstract class usrComplianceHoldReason : BqlString.Field<usrComplianceHoldReason> { }

        [PXDBString(500, IsUnicode = true)]
        [PXUIField(DisplayName = "Compliance Hold Reason", Enabled = true)]
        public string UsrComplianceHoldReason { get; set; }
        #endregion

        #region NoteID
        // Required for the Notes/Activities panel on SO301000 to persist notes.
        // When a PXCacheExtension is active on SOOrder, Acumatica routes note
        // CRUD through the extension cache. Without this field the framework
        // cannot locate NoteID at persist time, causing notes to be silently
        // dropped or an exception thrown. The [PXNote] attribute on the
        // extension delegates to the base SOOrder.NoteID column — no new DB
        // column is created; this is a routing/mapping declaration only.
        public abstract class noteID : BqlGuid.Field<noteID> { }
        [PXNote]
        public Guid? NoteID { get; set; }
        #endregion
    }
}
