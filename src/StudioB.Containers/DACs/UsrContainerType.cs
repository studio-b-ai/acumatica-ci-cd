using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Type")]
    public class UsrContainerType : PXBqlTable, IBqlTable
    {
        #region ContainerTypeID
        public abstract class containerTypeID : BqlInt.Field<containerTypeID> { }
        [PXDBIdentity]
        public int? ContainerTypeID { get; set; }
        #endregion
        #region TypeCD
        public abstract class typeCD : BqlString.Field<typeCD> { }
        [PXDBString(10, IsUnicode = true, IsKey = true, InputMask = ">aaaaaaaaaa")]
        [PXDefault]
        [PXUIField(DisplayName = "Type ID", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrContainerType.typeCD>),
            typeof(UsrContainerType.typeCD),
            typeof(UsrContainerType.description))]
        public string TypeCD { get; set; }
        #endregion
        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(60, IsUnicode = true)]
        [PXUIField(DisplayName = "Description", Visibility = PXUIVisibility.SelectorVisible)]
        public string Description { get; set; }
        #endregion
        #region LengthFt
        public abstract class lengthFt : BqlDecimal.Field<lengthFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Length (ft)")]
        public decimal? LengthFt { get; set; }
        #endregion
        #region WidthFt
        public abstract class widthFt : BqlDecimal.Field<widthFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Width (ft)")]
        public decimal? WidthFt { get; set; }
        #endregion
        #region HeightFt
        public abstract class heightFt : BqlDecimal.Field<heightFt> { }
        [PXDBDecimal(1)]
        [PXUIField(DisplayName = "Height (ft)")]
        public decimal? HeightFt { get; set; }
        #endregion
        #region MaxWeightKg
        public abstract class maxWeightKg : BqlDecimal.Field<maxWeightKg> { }
        [PXDBDecimal(0)]
        [PXUIField(DisplayName = "Max Weight (kg)")]
        public decimal? MaxWeightKg { get; set; }
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
