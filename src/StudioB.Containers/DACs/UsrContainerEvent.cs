using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Event")]
    public class UsrContainerEvent : PXBqlTable, IBqlTable
    {
        #region EventID
        public abstract class eventID : BqlInt.Field<eventID> { }
        [PXDBIdentity(IsKey = true)]
        public int? EventID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerEvent.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region CarrierEventCode
        public abstract class carrierEventCode : BqlString.Field<carrierEventCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Carrier Event Code")]
        public string CarrierEventCode { get; set; }
        #endregion

        #region NormalizedEventCode
        public abstract class normalizedEventCode : BqlString.Field<normalizedEventCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Event")]
        [PXStringList(new string[] { "BOOKED", "LOADED", "DEPARTED", "IN_TRANSIT", "ARRIVED", "DISCHARGED", "CUSTOMS_HOLD", "CUSTOMS_CLEARED", "GATED_OUT", "DELIVERED" },
                       new string[] { "Booked", "Loaded", "Departed", "In Transit", "Arrived", "Discharged", "Customs Hold", "Customs Cleared", "Gated Out", "Delivered" })]
        public string NormalizedEventCode { get; set; }
        #endregion

        #region EventDateTime
        public abstract class eventDateTime : BqlDateTime.Field<eventDateTime> { }
        [PXDBDate(PreserveTime = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Event Date/Time")]
        public DateTime? EventDateTime { get; set; }
        #endregion

        #region EventClassifier
        public abstract class eventClassifier : BqlString.Field<eventClassifier> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Type")]
        [PXStringList(new string[] { "ACT", "EST", "PLN" },
                       new string[] { "Actual", "Estimated", "Planned" })]
        public string EventClassifier { get; set; }
        #endregion

        #region LocationName
        public abstract class locationName : BqlString.Field<locationName> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Location")]
        public string LocationName { get; set; }
        #endregion

        #region LocationCode
        public abstract class locationCode : BqlString.Field<locationCode> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "UN Loc Code")]
        public string LocationCode { get; set; }
        #endregion

        #region VesselName
        public abstract class vesselName : BqlString.Field<vesselName> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Vessel")]
        public string VesselName { get; set; }
        #endregion

        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Description")]
        public string Description { get; set; }
        #endregion

        #region RawPayload
        public abstract class rawPayload : BqlString.Field<rawPayload> { }
        [PXDBText(IsUnicode = true)]
        [PXUIField(DisplayName = "Raw Payload", Visible = false)]
        public string RawPayload { get; set; }
        #endregion

        #region CreatedDateTime
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime]
        [PXUIField(DisplayName = "Recorded")]
        public DateTime? CreatedDateTime { get; set; }
        #endregion
    }
}
