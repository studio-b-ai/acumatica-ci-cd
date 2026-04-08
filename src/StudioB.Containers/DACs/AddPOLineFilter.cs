using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;
using PX.Objects.AP;
using PX.Objects.CR;

namespace StudioB.Containers
{
    /// <summary>
    /// Smart-panel filter for the Add PO Line action on SB501000.
    /// Lets the imports manager pick an open PO line to attach to the current
    /// container. Not persisted — lives only in the panel's PXFilter.
    /// </summary>
    [Serializable]
    [PXCacheName("Add PO Line Filter")]
    public class AddPOLineFilter : PXBqlTable, IBqlTable
    {
        #region VendorID
        public abstract class vendorID : BqlInt.Field<vendorID> { }
        [PXInt]
        [PXUIField(DisplayName = "Vendor")]
        [PXSelector(typeof(Search<Vendor.bAccountID,
            Where<Vendor.type, Equal<BAccountType.vendorType>>>),
            SubstituteKey = typeof(Vendor.acctCD),
            DescriptionField = typeof(Vendor.acctName))]
        public int? VendorID { get; set; }
        #endregion

        #region OrderType
        public abstract class orderType : BqlString.Field<orderType> { }
        [PXString(2, IsFixed = true)]
        [PXUIField(DisplayName = "Order Type")]
        [PXDefault("RO", PersistingCheck = PXPersistingCheck.Nothing)]
        public string OrderType { get; set; }
        #endregion

        #region OrderNbr
        public abstract class orderNbr : BqlString.Field<orderNbr> { }
        [PXString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "Order Nbr")]
        [PXSelector(typeof(Search<POOrder.orderNbr,
            Where<POOrder.vendorID, Equal<Current<AddPOLineFilter.vendorID>>,
                And<POOrder.status, NotEqual<POOrderStatus.closed>,
                And<POOrder.status, NotEqual<POOrderStatus.cancelled>>>>>),
            typeof(POOrder.orderNbr),
            typeof(POOrder.orderDate),
            typeof(POOrder.status),
            typeof(POOrder.vendorRefNbr),
            typeof(POOrder.curyOrderTotal))]
        public string OrderNbr { get; set; }
        #endregion

        #region LineNbr
        public abstract class lineNbr : BqlInt.Field<lineNbr> { }
        [PXInt]
        [PXUIField(DisplayName = "Line Nbr")]
        [PXSelector(typeof(Search<POLine.lineNbr,
            Where<POLine.orderType, Equal<Current<AddPOLineFilter.orderType>>,
                And<POLine.orderNbr, Equal<Current<AddPOLineFilter.orderNbr>>>>>),
            typeof(POLine.lineNbr),
            typeof(POLine.inventoryID),
            typeof(POLine.orderQty),
            typeof(POLine.extCost))]
        public int? LineNbr { get; set; }
        #endregion
    }
}
