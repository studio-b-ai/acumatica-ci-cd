using System;
using PX.Data;
using PX.Data.BQL;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Unbound single-row DAC used as the data source for the PXFormView header inside
    /// the Break Pricing panel on SO301000.
    ///
    /// Why a separate DAC instead of putting the label on SOPricingBreakTier?
    ///   • PXFormView (the header) and PXGrid (the tiers) must bind to *different*
    ///     data members.  Acumatica does not allow a single DAC/view to serve both.
    ///   • A PXFilter<SOPricingBreakHeader> view is always current (single row),
    ///     which is exactly what a header label needs.
    ///
    /// The graph extension (SOOrderEntry_BreakPricing) keeps this current by calling
    ///   BreakPricingHeader.Current.ItemDescription = ...
    /// whenever the selected SOLine changes.
    /// </summary>
    [Serializable]
    [PXCacheName("Break Pricing Header")]
    public class SOPricingBreakHeader : IBqlTable
    {
        #region ItemDescription
        /// <summary>
        /// Formatted string displayed in the panel title bar.
        /// Built by the graph extension as:  "{InventoryCD} – {Descr}"
        /// Falls back to "(no item selected)" when no line is active.
        /// </summary>
        public abstract class itemDescription : BqlString.Field<itemDescription> { }

        [PXString(512, IsUnicode = true)]
        [PXUIField(DisplayName = "Item", Enabled = false)]
        public virtual string ItemDescription { get; set; }
        #endregion

        #region InventoryID (backing field — not displayed)
        /// <summary>
        /// Tracks which InventoryID is currently reflected in the header and grid.
        /// Used by the graph extension to short-circuit re-loading when the user
        /// clicks a different split of the same item.
        /// </summary>
        public abstract class inventoryID : BqlInt.Field<inventoryID> { }

        [PXInt]
        [PXUIField(DisplayName = "Inventory ID", Visible = false, Enabled = false)]
        public virtual int? InventoryID { get; set; }
        #endregion
    }
}
