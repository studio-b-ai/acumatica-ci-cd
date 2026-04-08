using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container PO Link")]
    public class UsrContainerPOLink : PXBqlTable, IBqlTable
    {
        #region LinkID
        public abstract class linkID : BqlInt.Field<linkID> { }
        [PXDBIdentity(IsKey = true)]
        public int? LinkID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerPOLink.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region OrderType
        public abstract class orderType : BqlString.Field<orderType> { }
        [PXDBString(2, IsUnicode = true)]
        [PXDefault(POOrderType.RegularOrder)]
        [PXUIField(DisplayName = "PO Type")]
        public string OrderType { get; set; }
        #endregion

        #region OrderNbr
        public abstract class orderNbr : BqlString.Field<orderNbr> { }
        [PXDBString(15, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "PO Nbr")]
        [PXSelector(typeof(Search<POOrder.orderNbr, Where<POOrder.orderType, Equal<Current<UsrContainerPOLink.orderType>>>>),
            typeof(POOrder.orderNbr),
            typeof(POOrder.vendorID),
            typeof(POOrder.status),
            typeof(POOrder.orderDate))]
        public string OrderNbr { get; set; }
        #endregion

        #region LineNbr
        public abstract class lineNbr : BqlInt.Field<lineNbr> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Line Nbr")]
        public int? LineNbr { get; set; }
        #endregion
    }
}
