using System;
using PX.Data;
using PX.Data.BQL;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Virtual (unbound) DAC that represents one price-break tier for a specific
    /// inventory item on SO301000.
    ///
    /// This DAC has NO database backing — every field uses a non-persisting
    /// [PXxxx] attribute (never [PXDBxxx]).  The data is populated at runtime
    /// by SOOrderEntry_PricingBreak_Extension and lives only in the PXCache for
    /// the duration of the screen session.
    ///
    /// Keys
    /// ----
    ///   InventoryID + BreakLevel  — composite key that uniquely identifies a
    ///   single tier row within the in-memory grid.
    ///
    /// Tier semantics
    /// --------------
    ///   Tier 1 : MinQty=1,  MaxQty=24   → UnitPrice applies for qty 1-24
    ///   Tier 2 : MinQty=25, MaxQty=99   → UnitPrice applies for qty 25-99
    ///   Tier 3 : MinQty=100,MaxQty=null → UnitPrice applies for qty 100+
    ///
    /// A null MaxQty means "no upper bound" (unlimited).
    /// </summary>
    [PXCacheName("SO Pricing Break Tier")]
    [Serializable]
    public class SOPricingBreakTier : IBqlTable
    {
        #region InventoryID
        /// <summary>
        /// Key field — links this tier row to its parent inventory item.
        /// Matches InventoryItem.inventoryID / SOLine.inventoryID.
        /// </summary>
        public abstract class inventoryID : BqlInt.Field<inventoryID> { }

        [PXInt(IsKey = true)]
        [PXUIField(DisplayName = "Inventory ID", Visible = false)]
        public virtual int? InventoryID { get; set; }
        #endregion

        #region BreakLevel
        /// <summary>
        /// Key field — tier ordinal (1-based).
        /// Tier 1 is the base price; higher levels represent volume discounts.
        /// The extension assigns these sequentially and they are stable for
        /// the life of the cache entry.
        /// </summary>
        public abstract class breakLevel : BqlInt.Field<breakLevel> { }

        [PXInt(IsKey = true)]
        [PXUIField(DisplayName = "Tier #", Enabled = false)]
        public virtual int? BreakLevel { get; set; }
        #endregion

        #region MinQty
        /// <summary>
        /// Minimum order quantity (inclusive) at which this tier price applies.
        /// Must be &gt; 0.  Tier 1 is always MinQty = 1 (or the lowest configured
        /// break point from the price schedule).
        /// </summary>
        public abstract class minQty : BqlDecimal.Field<minQty> { }

        [PXDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Min Qty", Enabled = false)]
        public virtual decimal? MinQty { get; set; }
        #endregion

        #region MaxQty
        /// <summary>
        /// Maximum order quantity (inclusive) for this tier.
        /// A null value means there is no upper limit ("unlimited").
        /// The UI renders null as "—" via a custom formatter on the ASPX grid.
        /// </summary>
        public abstract class maxQty : BqlDecimal.Field<maxQty> { }

        [PXDecimal(2)]
        [PXUIField(DisplayName = "Max Qty", Enabled = false)]
        public virtual decimal? MaxQty { get; set; }
        #endregion

        #region UnitPrice
        /// <summary>
        /// Per-unit price for this tier, expressed in the order currency (CuryID).
        /// Sourced from ARSalesPrice / INItemCustSalesPrice for the item + customer
        /// class combination.  Read-only in the grid; editing is done on the
        /// price-maintenance screens.
        /// </summary>
        public abstract class unitPrice : BqlDecimal.Field<unitPrice> { }

        [PXDecimal(4)]
        [PXDefault(TypeCode.Decimal, "0.0000")]
        [PXUIField(DisplayName = "Unit Price", Enabled = false)]
        public virtual decimal? UnitPrice { get; set; }
        #endregion

        #region CuryID
        /// <summary>
        /// Currency in which UnitPrice is expressed.
        /// Inherited from the parent SOOrder.CuryID at population time.
        /// Shown for reference so reps can immediately see whether the price is
        /// in USD, CAD, EUR, etc. without navigating away.
        /// </summary>
        public abstract class curyID : BqlString.Field<curyID> { }

        [PXString(5, IsUnicode = true)]
        [PXUIField(DisplayName = "Currency", Enabled = false)]
        public virtual string CuryID { get; set; }
        #endregion

        #region UOM
        /// <summary>
        /// Unit of measure that governs both MinQty/MaxQty and UnitPrice.
        /// Typically "YD" (yards) for fabric items or "EA" for cut yardage.
        /// Matches the UOM stored on the active price schedule record.
        /// </summary>
        public abstract class uOM : BqlString.Field<uOM> { }

        [PXString(6, IsUnicode = true)]
        [PXUIField(DisplayName = "UOM", Enabled = false)]
        public virtual string UOM { get; set; }
        #endregion

        #region Description
        /// <summary>
        /// Human-readable label for the tier, e.g. "Tier 1", "Tier 2", "Tier 3".
        /// Constructed by the extension as "Tier {BreakLevel}" so sales reps
        /// can orient themselves in the grid at a glance without decoding qty ranges.
        /// </summary>
        public abstract class description : BqlString.Field<description> { }

        [PXString(50, IsUnicode = true)]
        [PXUIField(DisplayName = "Description", Enabled = false)]
        public virtual string Description { get; set; }
        #endregion
    }
}
