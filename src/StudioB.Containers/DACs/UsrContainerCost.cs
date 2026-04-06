using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.AP;
using PX.Objects.CR;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Cost")]
    public class UsrContainerCost : PXBqlTable, IBqlTable
    {
        #region CostID
        public abstract class costID : BqlInt.Field<costID> { }
        [PXDBIdentity(IsKey = true)]
        public int? CostID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerCost.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region CostType
        public abstract class costType : BqlString.Field<costType> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Cost Type")]
        [PXStringList(new string[] { "SHIPPING", "DUTY", "TARIFF", "BROKERAGE", "OTHER" },
                       new string[] { "Shipping", "Duty", "Tariff", "Brokerage", "Other" })]
        public string CostType { get; set; }
        #endregion

        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Description")]
        public string Description { get; set; }
        #endregion

        #region Amount
        public abstract class amount : BqlDecimal.Field<amount> { }
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Amount")]
        public decimal? Amount { get; set; }
        #endregion

        #region VendorID
        public abstract class vendorID : BqlInt.Field<vendorID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Vendor")]
        [PXSelector(typeof(Search<BAccount.bAccountID,
            Where<BAccount.type, Equal<BAccountType.vendorType>,
                Or<BAccount.type, Equal<BAccountType.combinedType>>>>),
            typeof(BAccount.acctCD),
            typeof(BAccount.acctName),
            SubstituteKey = typeof(BAccount.acctCD))]
        public int? VendorID { get; set; }
        #endregion

        #region ReferenceNbr
        public abstract class referenceNbr : BqlString.Field<referenceNbr> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Reference Nbr")]
        public string ReferenceNbr { get; set; }
        #endregion

        #region APDocType
        public abstract class apDocType : BqlString.Field<apDocType> { }
        [PXDBString(3, IsFixed = true, IsUnicode = true)]
        [PXUIField(DisplayName = "AP Doc Type")]
        [APDocType.List]
        public string APDocType { get; set; }
        #endregion

        #region APRefNbr
        public abstract class apRefNbr : BqlString.Field<apRefNbr> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "AP Ref Nbr")]
        [PXSelector(typeof(Search<APInvoice.refNbr,
            Where<APInvoice.docType, Equal<Current<UsrContainerCost.apDocType>>>>),
            typeof(APInvoice.refNbr),
            typeof(APInvoice.vendorID),
            typeof(APInvoice.docDate),
            typeof(APInvoice.status))]
        public string APRefNbr { get; set; }
        #endregion
    }
}
