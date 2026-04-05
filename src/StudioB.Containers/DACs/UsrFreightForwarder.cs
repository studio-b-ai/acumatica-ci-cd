using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Freight Forwarder")]
    public class UsrFreightForwarder : PXBqlTable, IBqlTable
    {
        #region ForwarderID
        public abstract class forwarderID : BqlInt.Field<forwarderID> { }
        [PXDBIdentity]
        public int? ForwarderID { get; set; }
        #endregion

        #region ForwarderCD
        public abstract class forwarderCD : BqlString.Field<forwarderCD> { }
        [PXDBString(15, IsUnicode = true, IsKey = true, InputMask = ">CCCCCCCCCCCCCCC")]
        [PXDefault]
        [PXUIField(DisplayName = "Forwarder ID", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrFreightForwarder.forwarderCD>),
            typeof(UsrFreightForwarder.forwarderCD),
            typeof(UsrFreightForwarder.name),
            typeof(UsrFreightForwarder.carrierAPIType),
            typeof(UsrFreightForwarder.active))]
        public string ForwarderCD { get; set; }
        #endregion

        #region Name
        public abstract class name : BqlString.Field<name> { }
        [PXDBString(100, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Company Name")]
        public string Name { get; set; }
        #endregion

        #region ContactName
        public abstract class contactName : BqlString.Field<contactName> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Contact Name")]
        public string ContactName { get; set; }
        #endregion

        #region Phone
        public abstract class phone : BqlString.Field<phone> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Phone")]
        public string Phone { get; set; }
        #endregion

        #region Email
        public abstract class email : BqlString.Field<email> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Email")]
        public string Email { get; set; }
        #endregion

        #region Website
        public abstract class website : BqlString.Field<website> { }
        [PXDBString(200, IsUnicode = true)]
        [PXUIField(DisplayName = "Website")]
        public string Website { get; set; }
        #endregion

        #region CarrierAPIType
        public abstract class carrierAPIType : BqlString.Field<carrierAPIType> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "API Type")]
        [PXStringList(
            new[] { "SEATRATES", "MAERSK", "FEDEX", "UPS", "OTHER" },
            new[] { "Seatrates", "Maersk", "FedEx", "UPS", "Other" })]
        public string CarrierAPIType { get; set; }
        #endregion

        #region CarrierAPIKey
        public abstract class carrierAPIKey : BqlString.Field<carrierAPIKey> { }
        [PXRSACryptString(200, IsUnicode = true)]
        [PXUIField(DisplayName = "API Key")]
        public string CarrierAPIKey { get; set; }
        #endregion

        #region Active
        public abstract class active : BqlBool.Field<active> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Active")]
        public bool? Active { get; set; }
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

        #region CreatedByScreenID
        public abstract class createdByScreenID : BqlString.Field<createdByScreenID> { }
        [PXDBCreatedByScreenID]
        public string CreatedByScreenID { get; set; }
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

        #region LastModifiedByScreenID
        public abstract class lastModifiedByScreenID : BqlString.Field<lastModifiedByScreenID> { }
        [PXDBLastModifiedByScreenID]
        public string LastModifiedByScreenID { get; set; }
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
