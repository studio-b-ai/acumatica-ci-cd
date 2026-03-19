using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.PO
{
    [Serializable]
    [PXCacheName("PO Relation")]
    public class UsrPORelation : IBqlTable
    {
        public static bool IsActive() => true;

        #region UsrPORelationID
        public abstract class usrPORelationID : BqlInt.Field<usrPORelationID> { }
        [PXDBIdentity(IsKey = true)]
        public int? UsrPORelationID { get; set; }
        #endregion

        #region RefNoteID
        public abstract class refNoteID : BqlGuid.Field<refNoteID> { }
        [PXDBGuid]
        [PXParent(typeof(Select<POOrder, Where<POOrder.noteID, Equal<Current<refNoteID>>>>))]
        [PXUIField(DisplayName = "Ref Note ID", Visible = false)]
        public Guid? RefNoteID { get; set; }
        #endregion

        #region Role
        public abstract class role : BqlString.Field<role> { }
        [PXDBString(30, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Role")]
        [PXStringList(
            new[] { "BUYER", "AP", "SHIPPING", "FREIGHT", "INSPECTOR", "SALESREP", "OTHER" },
            new[] { "Buyer", "AP Contact", "Shipping", "Freight Broker", "Inspector", "Sales Rep", "Other" })]
        public string Role { get; set; }
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

        #region Company
        public abstract class company : BqlString.Field<company> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Company")]
        public string Company { get; set; }
        #endregion

        #region AddToCC
        public abstract class addToCC : BqlBool.Field<addToCC> { }
        [PXDBBool]
        [PXDefault(false)]
        [PXUIField(DisplayName = "Add to CC")]
        public bool? AddToCC { get; set; }
        #endregion

        #region IsActive
        public abstract class isActive : BqlBool.Field<isActive> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Active")]
        public bool? IsActive { get; set; }
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
