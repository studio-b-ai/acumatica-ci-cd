using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Preferences")]
    public class UsrContainerPrefs : PXBqlTable, IBqlTable
    {
        #region PrefsID
        public abstract class prefsID : BqlInt.Field<prefsID> { }
        [PXDBInt(IsKey = true)]
        [PXDefault(1)]
        [PXUIField(Visible = false)]
        public int? PrefsID { get; set; }
        #endregion
        #region DefaultCarrierCode
        public abstract class defaultCarrierCode : BqlString.Field<defaultCarrierCode> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Default Carrier Code")]
        public string DefaultCarrierCode { get; set; }
        #endregion
        #region DefaultContainerType
        public abstract class defaultContainerType : BqlString.Field<defaultContainerType> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Default Container Type")]
        [PXSelector(typeof(Search<UsrContainerType.typeCD,
            Where<UsrContainerType.active, Equal<True>>>),
            typeof(UsrContainerType.typeCD),
            typeof(UsrContainerType.description))]
        public string DefaultContainerType { get; set; }
        #endregion
        #region DefaultInTransitWarehouse
        public abstract class defaultInTransitWarehouse : BqlString.Field<defaultInTransitWarehouse> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Default In-Transit Warehouse")]
        public string DefaultInTransitWarehouse { get; set; }
        #endregion
        #region AutoLinkPOsByRef
        public abstract class autoLinkPOsByRef : BqlBool.Field<autoLinkPOsByRef> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Link POs by Container Ref")]
        public bool? AutoLinkPOsByRef { get; set; }
        #endregion
        #region TrackingPollIntervalHours
        public abstract class trackingPollIntervalHours : BqlInt.Field<trackingPollIntervalHours> { }
        [PXDBInt]
        [PXDefault(24)]
        [PXUIField(DisplayName = "Tracking Poll Interval (hours)")]
        public int? TrackingPollIntervalHours { get; set; }
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
