using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Unbound/projection DAC used exclusively as a view-model for the Break Pricing
    /// panel on SO301000.  Rows are populated in-memory by SOOrderEntry_BreakPricing
    /// by reading ARSalesPrice / INItemSalesPrice break-tier records for the inventory
    /// item that is currently selected in the Document Details grid.
    ///
    /// Why unbound?
    ///   • Break-price records already live in standard Acumatica tables (ARSalesPrice).
    ///   • We need a *filtered, display-only* projection – no additional DB table.
    ///   • PXVirtualDAC keeps the cache ephemeral and never triggers a persist.
    ///
    /// Column layout matches the panel grid:
    ///   Tier | MinQty | MaxQty | UnitPrice | UOM
    /// </summary>
    [Serializable]
    [PXCacheName("Break Pricing Tier")]
    [PXVirtual]
    public class SOPricingBreakTier : IBqlTable
    {
        #region TierOrder
        /// <summary>
        /// Display sequence (1-based). Drives grid sort order.
        /// This is the key field – the cache uses it as the identity for each row.
        /// </summary>
        public abstract class tierOrder : BqlInt.Field<tierOrder> { }

        [PXInt(IsKey = true)]
        [PXUIField(DisplayName = "Tier", Enabled = false)]
        public virtual int? TierOrder { get; set; }
        #endregion

        #region MinQty
        /// <summary>
        /// Minimum quantity (break-price lower bound), inclusive.
        /// Sourced from ARSalesPrice.BreakQty.
        /// </summary>
        public abstract class minQty : BqlDecimal.Field<minQty> { }

        [PXDecimal(4)]
        [PXUIField(DisplayName = "Min Qty", Enabled = false)]
        public virtual decimal? MinQty { get; set; }
        #endregion

        #region MaxQty
        /// <summary>
        /// Maximum quantity (break-price upper bound), exclusive.
        /// Derived as the MinQty of the next tier minus one unit, or null for the last tier.
        /// Displayed as "No Limit" when null via a custom formatting hook.
        /// </summary>
        public abstract class maxQty : BqlDecimal.Field<maxQty> { }

        [PXDecimal(4)]
        [PXUIField(DisplayName = "Max Qty", Enabled = false)]
        public virtual decimal? MaxQty { get; set; }
        #endregion

        #region UnitPrice
        /// <summary>
        /// Price per unit of measure at this tier, in the order's currency.
        /// Sourced from ARSalesPrice.SalesPrice.
        /// </summary>
        public abstract class unitPrice : BqlDecimal.Field<unitPrice> { }

        [PXDecimal(4)]
        [PXUIField(DisplayName = "Unit Price", Enabled = false)]
        public virtual decimal? UnitPrice { get; set; }
        #endregion

        #region UOM
        /// <summary>
        /// Unit of measure for MinQty / MaxQty quantities and UnitPrice.
        /// Sourced from ARSalesPrice.UOM.
        /// </summary>
        public abstract class uOM : BqlString.Field<uOM> { }

        [PXString(6, IsUnicode = true)]
        [PXUIField(DisplayName = "UOM", Enabled = false)]
        public virtual string UOM { get; set; }
        #endregion

        #region InventoryID (hidden, used for cache filtering only)
        /// <summary>
        /// InventoryID of the currently-selected SO line item.
        /// Not displayed in the grid; used by the graph extension to correlate
        /// which item these tiers belong to so the cache is invalidated correctly
        /// when the user selects a different line.
        /// </summary>
        public abstract class inventoryID : BqlInt.Field<inventoryID> { }

        [PXInt]
        [PXUIField(DisplayName = "Inventory ID", Visible = false, Enabled = false)]
        public virtual int? InventoryID { get; set; }
        #endregion

        #region InventoryDescription (header display field — unbound)
        /// <summary>
        /// Human-readable item description used in the panel header label.
        /// Populated alongside TierOrder rows by the graph extension.
        /// The ASPX label references this via a separate PXFormView bound to a
        /// PXFilter&lt;SOPricingBreakHeader&gt; view – see SOPricingBreakHeader.
        /// </summary>
        public abstract class inventoryDescription : BqlString.Field<inventoryDescription> { }

        [PXString(256, IsUnicode = true)]
        [PXUIField(DisplayName = "Item Description", Visible = false, Enabled = false)]
        public virtual string InventoryDescription { get; set; }
        #endregion
    }
}
