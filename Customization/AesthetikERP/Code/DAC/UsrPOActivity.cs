using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.PO
{
    [Serializable]
    [PXCacheName("PO Activity")]
    public class UsrPOActivity : IBqlTable
    {
        #region UsrPOActivityID
        public abstract class usrPOActivityID : BqlInt.Field<usrPOActivityID> { }
        [PXDBIdentity(IsKey = true)]
        public int? UsrPOActivityID { get; set; }
        #endregion

        #region RefNoteID
        public abstract class refNoteID : BqlGuid.Field<refNoteID> { }
        [PXDBGuid]
        [PXParent(typeof(Select<POOrder, Where<POOrder.noteID, Equal<Current<refNoteID>>>>))]
        [PXUIField(DisplayName = "Ref Note ID", Visible = false)]
        public Guid? RefNoteID { get; set; }
        #endregion

        #region Type
        public abstract class type : BqlString.Field<type> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault("NOTE")]
        [PXUIField(DisplayName = "Type")]
        [PXStringList(
            new[] { "NOTE", "TASK", "CALL", "EMAIL", "MEETING" },
            new[] { "Note", "Task", "Call", "Email", "Meeting" })]
        public string Type { get; set; }
        #endregion

        #region Subject
        public abstract class subject : BqlString.Field<subject> { }
        [PXDBString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Subject")]
        public string Subject { get; set; }
        #endregion

        #region Body
        public abstract class body : BqlString.Field<body> { }
        [PXDBText(IsUnicode = true)]
        [PXUIField(DisplayName = "Body")]
        public string Body { get; set; }
        #endregion

        #region Status
        public abstract class status : BqlString.Field<status> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault("OPEN")]
        [PXUIField(DisplayName = "Status")]
        [PXStringList(
            new[] { "OPEN", "COMPLETED", "CANCELLED" },
            new[] { "Open", "Completed", "Cancelled" })]
        public string Status { get; set; }
        #endregion

        #region Priority
        public abstract class priority : BqlString.Field<priority> { }
        [PXDBString(10, IsUnicode = true)]
        [PXDefault("NORMAL")]
        [PXUIField(DisplayName = "Priority")]
        [PXStringList(
            new[] { "HIGH", "NORMAL", "LOW" },
            new[] { "High", "Normal", "Low" })]
        public string Priority { get; set; }
        #endregion

        #region StartDate
        public abstract class startDate : BqlDateTime.Field<startDate> { }
        [PXDBDate]
        [PXUIField(DisplayName = "Start Date")]
        public DateTime? StartDate { get; set; }
        #endregion

        #region OwnerID
        public abstract class ownerID : BqlGuid.Field<ownerID> { }
        [PXDBGuid]
        [PXUIField(DisplayName = "Owner")]
        public Guid? OwnerID { get; set; }
        #endregion

        #region Audit
        public abstract class createdByID : BqlGuid.Field<createdByID> { }
        [PXDBCreatedByID] public Guid? CreatedByID { get; set; }
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime] public DateTime? CreatedDateTime { get; set; }
        public abstract class lastModifiedByID : BqlGuid.Field<lastModifiedByID> { }
        [PXDBLastModifiedByID] public Guid? LastModifiedByID { get; set; }
        public abstract class lastModifiedDateTime : BqlDateTime.Field<lastModifiedDateTime> { }
        [PXDBLastModifiedDateTime] public DateTime? LastModifiedDateTime { get; set; }
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp] public byte[] Tstamp { get; set; }
        #endregion
    }
}
