using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Port")]
    public class UsrPort : PXBqlTable, IBqlTable
    {
        #region PortID
        public abstract class portID : BqlInt.Field<portID> { }
        [PXDBIdentity]
        public int? PortID { get; set; }
        #endregion
        #region PortCode
        public abstract class portCode : BqlString.Field<portCode> { }
        [PXDBString(10, IsUnicode = true, IsKey = true, InputMask = ">aaaaaaaaaa")]
        [PXDefault]
        [PXUIField(DisplayName = "Port Code", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrPort.portCode>),
            typeof(UsrPort.portCode),
            typeof(UsrPort.portName),
            typeof(UsrPort.country))]
        public string PortCode { get; set; }
        #endregion
        #region PortName
        public abstract class portName : BqlString.Field<portName> { }
        [PXDBString(100, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Port Name", Visibility = PXUIVisibility.SelectorVisible)]
        public string PortName { get; set; }
        #endregion
        #region Country
        public abstract class country : BqlString.Field<country> { }
        [PXDBString(2, IsUnicode = true)]
        [PXUIField(DisplayName = "Country")]
        public string Country { get; set; }
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
