using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container ETA History")]
    public class UsrContainerETAHistory : PXBqlTable, IBqlTable
    {
        #region ETAHistoryID
        public abstract class eTAHistoryID : BqlInt.Field<eTAHistoryID> { }
        [PXDBIdentity(IsKey = true)]
        public int? ETAHistoryID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerETAHistory.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region RecordedDate
        public abstract class recordedDate : BqlDateTime.Field<recordedDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXDefault(typeof(AccessInfo.businessDate))]
        [PXUIField(DisplayName = "Recorded")]
        public DateTime? RecordedDate { get; set; }
        #endregion

        #region PreviousETA
        public abstract class previousETA : BqlDateTime.Field<previousETA> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Previous ETA")]
        public DateTime? PreviousETA { get; set; }
        #endregion

        #region NewETA
        public abstract class newETA : BqlDateTime.Field<newETA> { }
        [PXDBDate]
        [PXDefault]
        [PXUIField(DisplayName = "New ETA")]
        public DateTime? NewETA { get; set; }
        #endregion

        #region SlipDays
        public abstract class slipDays : BqlInt.Field<slipDays> { }
        [PXInt]
        [PXUIField(DisplayName = "Slip (days)", Enabled = false)]
        public int? SlipDays { get; set; }
        #endregion

        #region Source
        public abstract class source : BqlString.Field<source> { }
        [PXDBString(10, IsUnicode = true)]
        [PXDefault("MANUAL")]
        [PXUIField(DisplayName = "Source")]
        [PXStringList(new string[] { "MANUAL", "XLSX", "API", "CARRIER" },
                       new string[] { "Manual", "XLSX Import", "API", "Carrier Webhook" })]
        public string Source { get; set; }
        #endregion

        #region Note
        public abstract class note : BqlString.Field<note> { }
        [PXDBString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Note")]
        public string Note { get; set; }
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

        #region Tstamp
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp]
        public byte[] Tstamp { get; set; }
        #endregion
    }
}
