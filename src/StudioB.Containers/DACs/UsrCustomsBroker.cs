using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Customs Broker")]
    public class UsrCustomsBroker : PXBqlTable, IBqlTable
    {
        #region BrokerID
        public abstract class brokerID : BqlInt.Field<brokerID> { }
        [PXDBIdentity]
        public int? BrokerID { get; set; }
        #endregion

        #region BrokerCD
        public abstract class brokerCD : BqlString.Field<brokerCD> { }
        [PXDBString(15, IsUnicode = true, IsKey = true, InputMask = ">CCCCCCCCCCCCCCC")]
        [PXDefault]
        [PXUIField(DisplayName = "Broker ID", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrCustomsBroker.brokerCD>),
            typeof(UsrCustomsBroker.brokerCD),
            typeof(UsrCustomsBroker.description),
            typeof(UsrCustomsBroker.contactName),
            typeof(UsrCustomsBroker.email),
            typeof(UsrCustomsBroker.active))]
        public string BrokerCD { get; set; }
        #endregion

        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(100, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Name")]
        public string Description { get; set; }
        #endregion

        #region ContactName
        public abstract class contactName : BqlString.Field<contactName> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Contact Name")]
        public string ContactName { get; set; }
        #endregion

        #region Email
        public abstract class email : BqlString.Field<email> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Email")]
        public string Email { get; set; }
        #endregion

        #region Phone
        public abstract class phone : BqlString.Field<phone> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Phone")]
        public string Phone { get; set; }
        #endregion

        #region FilerCode
        public abstract class filerCode : BqlString.Field<filerCode> { }
        [PXDBString(3, IsUnicode = true)]
        [PXUIField(DisplayName = "CBP Filer Code")]
        public string FilerCode { get; set; }
        #endregion

        #region Active
        public abstract class active : BqlBool.Field<active> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Active")]
        public bool? Active { get; set; }
        #endregion

        #region Notes
        public abstract class notes : BqlString.Field<notes> { }
        [PXDBString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Notes")]
        public string Notes { get; set; }
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
