using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.DAC
{
    /// <summary>
    /// Custom DAC that maps directly to the AuditHistory SQL table.
    /// Used instead of PX.SM.AuditHistory for GI OData exposure because
    /// system DACs crash the OData catalog when exposed via GI.
    /// This custom DAC is a simple read-only mirror of the same table.
    /// </summary>
    [Serializable]
    [PXCacheName("Audit History View")]
    public class AuditHistory : PXBqlTable, IBqlTable
    {
        #region BatchID
        public abstract class batchID : BqlLong.Field<batchID> { }
        [PXDBLong(IsKey = true)]
        [PXUIField(DisplayName = "Batch ID")]
        public virtual long? BatchID { get; set; }
        #endregion

        #region ChangeID
        public abstract class changeID : BqlLong.Field<changeID> { }
        [PXDBLong(IsKey = true)]
        [PXUIField(DisplayName = "Change ID")]
        public virtual long? ChangeID { get; set; }
        #endregion

        #region ScreenID
        public abstract class screenID : BqlString.Field<screenID> { }
        [PXDBString(8, IsFixed = true)]
        [PXUIField(DisplayName = "Screen ID")]
        public virtual string ScreenID { get; set; }
        #endregion

        #region UserID
        public abstract class userID : BqlGuid.Field<userID> { }
        [PXDBGuid]
        [PXUIField(DisplayName = "User ID")]
        public virtual Guid? UserID { get; set; }
        #endregion

        #region ChangeDate
        public abstract class changeDate : BqlDateTime.Field<changeDate> { }
        [PXDBDate(PreserveTime = true)]
        [PXUIField(DisplayName = "Change Date")]
        public virtual DateTime? ChangeDate { get; set; }
        #endregion

        #region Operation
        public abstract class operation : BqlString.Field<operation> { }
        [PXDBString(1, IsFixed = true)]
        [PXUIField(DisplayName = "Operation")]
        public virtual string Operation { get; set; }
        #endregion

        #region TableName
        public abstract class tableName : BqlString.Field<tableName> { }
        [PXDBString(100)]
        [PXUIField(DisplayName = "Table Name")]
        public virtual string TableName { get; set; }
        #endregion

        #region CombinedKey
        public abstract class combinedKey : BqlString.Field<combinedKey> { }
        [PXDBString(796)]
        [PXUIField(DisplayName = "Combined Key")]
        public virtual string CombinedKey { get; set; }
        #endregion

        #region ModifiedFields
        public abstract class modifiedFields : BqlString.Field<modifiedFields> { }
        [PXDBString(IsUnicode = true)]
        [PXUIField(DisplayName = "Modified Fields")]
        public virtual string ModifiedFields { get; set; }
        #endregion
    }
}
