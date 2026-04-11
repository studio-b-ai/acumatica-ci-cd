using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    /// <summary>
    /// Unbound DAC for the Lead Time tab on SB501000.
    /// Shows per-PO-line lead time breakdown across 4 stages.
    /// All fields computed at runtime — no database table.
    /// </summary>
    [Serializable]
    [PXVirtual]
    public class UsrContainerLeadTime : PXBqlTable, IBqlTable
    {
        #region LineKey
        public abstract class lineKey : BqlString.Field<lineKey> { }
        [PXString(50, IsKey = true, IsUnicode = true)]
        [PXUIField(DisplayName = "Key", Visible = false)]
        public virtual string LineKey { get; set; }
        #endregion

        #region OrderNbr
        public abstract class orderNbr : BqlString.Field<orderNbr> { }
        [PXString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "PO Nbr")]
        public virtual string OrderNbr { get; set; }
        #endregion

        #region VendorName
        public abstract class vendorName : BqlString.Field<vendorName> { }
        [PXString(255, IsUnicode = true)]
        [PXUIField(DisplayName = "Vendor")]
        public virtual string VendorName { get; set; }
        #endregion

        #region InventoryCD
        public abstract class inventoryCD : BqlString.Field<inventoryCD> { }
        [PXString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Inventory ID")]
        public virtual string InventoryCD { get; set; }
        #endregion

        #region PlacedToAcked
        public abstract class placedToAcked : BqlInt.Field<placedToAcked> { }
        [PXInt]
        [PXUIField(DisplayName = "Placed \u2192 Acked")]
        public virtual int? PlacedToAcked { get; set; }
        #endregion

        #region AckedToFactory
        public abstract class ackedToFactory : BqlInt.Field<ackedToFactory> { }
        [PXInt]
        [PXUIField(DisplayName = "Acked \u2192 Factory")]
        public virtual int? AckedToFactory { get; set; }
        #endregion

        #region FactoryToShip
        public abstract class factoryToShip : BqlInt.Field<factoryToShip> { }
        [PXInt]
        [PXUIField(DisplayName = "Factory \u2192 Ship")]
        public virtual int? FactoryToShip { get; set; }
        #endregion

        #region ShipToDeliver
        public abstract class shipToDeliver : BqlInt.Field<shipToDeliver> { }
        [PXInt]
        [PXUIField(DisplayName = "Ship \u2192 Deliver")]
        public virtual int? ShipToDeliver { get; set; }
        #endregion

        #region TotalDays
        public abstract class totalDays : BqlInt.Field<totalDays> { }
        [PXInt]
        [PXUIField(DisplayName = "Total Days")]
        public virtual int? TotalDays { get; set; }
        #endregion
    }
}
