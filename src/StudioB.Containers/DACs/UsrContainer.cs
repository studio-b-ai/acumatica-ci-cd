using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container")]
    public class UsrContainer : PXBqlTable, IBqlTable
    {
        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBIdentity]
        public int? ContainerID { get; set; }
        #endregion

        #region ContainerCD
        public abstract class containerCD : BqlString.Field<containerCD> { }
        [PXDBString(20, IsUnicode = true, IsKey = true, InputMask = "")]
        [PXDefault]
        [PXUIField(DisplayName = "Container Nbr", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrContainer.containerCD>),
            typeof(UsrContainer.containerCD),
            typeof(UsrContainer.carrierCode),
            typeof(UsrContainer.status),
            typeof(UsrContainer.vesselName),
            typeof(UsrContainer.eta))]
        public string ContainerCD { get; set; }
        #endregion

        #region CarrierCode
        public abstract class carrierCode : BqlString.Field<carrierCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Carrier")]
        [PXStringList(new string[] { "MAERSK", "CHR", "OTS", "OTHER" },
                       new string[] { "Maersk", "CH Robinson", "OTS", "Other" })]
        public string CarrierCode { get; set; }
        #endregion

        #region BookingRef
        public abstract class bookingRef : BqlString.Field<bookingRef> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Booking Ref")]
        public string BookingRef { get; set; }
        #endregion

        #region BillOfLading
        public abstract class billOfLading : BqlString.Field<billOfLading> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Bill of Lading")]
        public string BillOfLading { get; set; }
        #endregion

        #region VesselName
        public abstract class vesselName : BqlString.Field<vesselName> { }
        [PXDBString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Vessel")]
        public string VesselName { get; set; }
        #endregion

        #region VesselIMO
        public abstract class vesselIMO : BqlString.Field<vesselIMO> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "IMO #")]
        public string VesselIMO { get; set; }
        #endregion

        #region VoyageNbr
        public abstract class voyageNbr : BqlString.Field<voyageNbr> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Voyage #")]
        public string VoyageNbr { get; set; }
        #endregion

        #region PortOfLoading
        public abstract class portOfLoading : BqlString.Field<portOfLoading> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Port of Loading")]
        [PXSelector(typeof(Search<UsrPort.portCode,
            Where<UsrPort.active, Equal<True>>>),
            typeof(UsrPort.portCode),
            typeof(UsrPort.portName),
            typeof(UsrPort.country))]
        public string PortOfLoading { get; set; }
        #endregion

        #region PortOfDischarge
        public abstract class portOfDischarge : BqlString.Field<portOfDischarge> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Port of Discharge")]
        [PXSelector(typeof(Search<UsrPort.portCode,
            Where<UsrPort.active, Equal<True>>>),
            typeof(UsrPort.portCode),
            typeof(UsrPort.portName),
            typeof(UsrPort.country))]
        public string PortOfDischarge { get; set; }
        #endregion

        #region ETD
        public abstract class etd : BqlDateTime.Field<etd> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Est. Departure")]
        public DateTime? ETD { get; set; }
        #endregion

        #region ATD
        public abstract class atd : BqlDateTime.Field<atd> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Departure")]
        public DateTime? ATD { get; set; }
        #endregion

        #region ETA
        public abstract class eta : BqlDateTime.Field<eta> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Est. Arrival")]
        public DateTime? ETA { get; set; }
        #endregion

        #region ATA
        public abstract class ata : BqlDateTime.Field<ata> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Act. Arrival")]
        public DateTime? ATA { get; set; }
        #endregion

        #region Status
        public abstract class status : BqlString.Field<status> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault("BOOKED")]
        [PXUIField(DisplayName = "Status")]
        [PXStringList(new string[] { "BOOKED", "DEPARTED", "IN_TRANSIT", "ARRIVED", "DISCHARGED", "CUSTOMS_HOLD", "GATED_OUT", "DELIVERED", "CANCELLED" },
                       new string[] { "Booked", "Departed", "In Transit", "Arrived", "Discharged", "Customs Hold", "Gated Out", "Delivered", "Cancelled" })]
        public string Status { get; set; }
        #endregion

        #region ContainerType
        public abstract class containerType : BqlString.Field<containerType> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Type")]
        [PXSelector(typeof(Search<UsrContainerType.typeCD,
            Where<UsrContainerType.active, Equal<True>>>),
            typeof(UsrContainerType.typeCD),
            typeof(UsrContainerType.description))]
        public string ContainerType { get; set; }
        #endregion

        #region SealNbr
        public abstract class sealNbr : BqlString.Field<sealNbr> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Seal #")]
        public string SealNbr { get; set; }
        #endregion

        #region LastEventCode
        public abstract class lastEventCode : BqlString.Field<lastEventCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Last Event", Enabled = false)]
        public string LastEventCode { get; set; }
        #endregion

        #region LastEventDate
        public abstract class lastEventDate : BqlDateTime.Field<lastEventDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Last Event Date", Enabled = false)]
        public DateTime? LastEventDate { get; set; }
        #endregion

        #region LastSyncDate
        public abstract class lastSyncDate : BqlDateTime.Field<lastSyncDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Last Sync", Enabled = false)]
        public DateTime? LastSyncDate { get; set; }
        #endregion

        #region NoteID
        public abstract class noteID : BqlGuid.Field<noteID> { }
        [PXNote]
        public Guid? NoteID { get; set; }
        #endregion

        #region CreatedByID
        public abstract class createdByID : BqlGuid.Field<createdByID> { }
        [PXDBCreatedByID]
        public Guid? CreatedByID { get; set; }
        #endregion

        #region CreatedDateTime
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime]
        public DateTime? CreatedDateTime { get; set; }
        #endregion

        #region LastModifiedByID
        public abstract class lastModifiedByID : BqlGuid.Field<lastModifiedByID> { }
        [PXDBLastModifiedByID]
        public Guid? LastModifiedByID { get; set; }
        #endregion

        #region LastModifiedDateTime
        public abstract class lastModifiedDateTime : BqlDateTime.Field<lastModifiedDateTime> { }
        [PXDBLastModifiedDateTime]
        public DateTime? LastModifiedDateTime { get; set; }
        #endregion

        #region Tstamp
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp]
        public byte[] Tstamp { get; set; }
        #endregion
    }
}
