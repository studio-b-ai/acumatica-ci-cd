using PX.Data;
using PX.Data.BQL;
using PX.Objects.SO;

namespace StudioB.Containers
{
    /// <summary>
    /// Replaces IIG UsrIGCMIncludeInContainer on SOShipment.
    /// Flags whether a shipment should be included in container consolidation.
    /// </summary>
    public sealed class ShipmentExt : PXCacheExtension<SOShipment>
    {
        public static bool IsActive() => true;

        #region UsrIncludeInContainer
        public abstract class usrIncludeInContainer : BqlBool.Field<usrIncludeInContainer> { }
        [PXDBBool]
        [PXDefault(false, PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Include in Container")]
        public bool? UsrIncludeInContainer { get; set; }
        #endregion

        #region UsrContainerID
        public abstract class usrContainerID : BqlInt.Field<usrContainerID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Container")]
        [PXSelector(typeof(Search<UsrContainer.containerID>),
            SubstituteKey = typeof(UsrContainer.containerCD),
            DescriptionField = typeof(UsrContainer.vesselName))]
        public int? UsrContainerID { get; set; }
        #endregion
    }
}
