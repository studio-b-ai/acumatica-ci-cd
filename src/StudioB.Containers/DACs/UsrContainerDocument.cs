using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Document")]
    public class UsrContainerDocument : PXBqlTable, IBqlTable
    {
        #region DocumentID
        public abstract class documentID : BqlInt.Field<documentID> { }
        [PXDBIdentity(IsKey = true)]
        public int? DocumentID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerDocument.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region DocumentType
        public abstract class documentType : BqlString.Field<documentType> { }
        [PXDBString(10, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Document Type")]
        [PXStringList(
            new string[] { "CI", "PL", "BOL", "ISF", "ENTRY", "CO", "FDA", "USDA", "FCC", "INS", "OTHER" },
            new string[] { "Commercial Invoice", "Packing List", "Bill of Lading", "ISF Filing", "CBP Entry / 7501",
                           "Certificate of Origin", "FDA Prior Notice", "USDA Permit", "FCC Declaration",
                           "Insurance Certificate", "Other" })]
        public string DocumentType { get; set; }
        #endregion

        #region Required
        public abstract class required : BqlBool.Field<required> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Required")]
        public bool? Required { get; set; }
        #endregion

        #region Status
        public abstract class status : BqlString.Field<status> { }
        [PXDBString(10, IsUnicode = true)]
        [PXDefault("MISSING")]
        [PXUIField(DisplayName = "Status")]
        [PXStringList(
            new string[] { "MISSING", "RECEIVED", "VERIFIED", "REJECTED" },
            new string[] { "Missing", "Received", "Verified", "Rejected" })]
        public string Status { get; set; }
        #endregion

        #region ReceivedDate
        public abstract class receivedDate : BqlDateTime.Field<receivedDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Received")]
        public DateTime? ReceivedDate { get; set; }
        #endregion

        #region VerifiedBy
        public abstract class verifiedBy : BqlGuid.Field<verifiedBy> { }
        [PXDBGuid]
        [PXUIField(DisplayName = "Verified By")]
        public Guid? VerifiedBy { get; set; }
        #endregion

        #region Note
        public abstract class note : BqlString.Field<note> { }
        [PXDBString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Note")]
        public string Note { get; set; }
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
