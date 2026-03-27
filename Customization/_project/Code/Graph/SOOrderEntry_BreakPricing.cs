using System;
using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.AR;
using PX.Objects.IN;
using PX.Objects.SO;

namespace HeritageFabrics.SO
{
    /// <summary>
    /// Graph extension for SOOrderEntry that drives the Break Pricing panel on SO301000.
    ///
    /// Responsibilities
    /// ────────────────
    /// 1. Expose a PXFilter&lt;SOPricingBreakHeader&gt; view (header label data).
    /// 2. Expose a PXSelectReadonly&lt;SOPricingBreakTier&gt; virtual delegate view (grid rows).
    /// 3. React to SOLine row selection changes (RowSelected) and refresh both views.
    /// 4. Query ARSalesPrice break tiers for the selected inventory item, sorted by qty.
    /// 5. Derive MaxQty as (next tier's MinQty - epsilon), null for the last tier.
    ///
    /// Data source: ARSalesPrice
    ///   • Filtered by: InventoryID, CustPriceClassID = "BASE" (or null = all-customer
    ///     base price list), SalesPrice.PricType = 'B' (base price).
    ///   • Ordered by BreakQty ASC.
    ///   • This gives us the publicly-visible break pricing ladder regardless of the
    ///     specific customer on the order, which is the correct behavior for a visual
    ///     reference panel (sales reps see the tier ladder, not a single calculated price).
    ///
    /// Acumatica version target: 2024 R2 (24.208)
    /// </summary>
    public class SOOrderEntry_BreakPricing : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        // ─────────────────────────────────────────────────────────────────────
        // Views
        // ─────────────────────────────────────────────────────────────────────

        /// <summary>
        /// Single-row filter driving the panel header label.
        /// Bind the PXFormView on SO301000 to DataMember="BreakPricingHeader".
        /// </summary>
        public PXFilter<SOPricingBreakHeader> BreakPricingHeader;

        /// <summary>
        /// Delegate-backed virtual view that returns break tier rows for the
        /// currently-selected SOLine's InventoryID.
        /// Bind the nested PXGrid on SO301000 to DataMember="BreakPricingTiers".
        /// </summary>
        public PXSelectReadonly<SOPricingBreakTier> BreakPricingTiers;

        /// <summary>
        /// Custom delegate for BreakPricingTiers.  Acumatica calls this when the
        /// grid needs to populate.  We build the list in-memory from ARSalesPrice.
        /// </summary>
        protected virtual IEnumerable breakPricingTiers()
        {
            SOPricingBreakHeader header = BreakPricingHeader.Current;
            if (header?.InventoryID == null)
                yield break;

            foreach (SOPricingBreakTier tier in LoadTiers(header.InventoryID.Value))
                yield return tier;
        }

        // ─────────────────────────────────────────────────────────────────────
        // Event Handlers
        // ─────────────────────────────────────────────────────────────────────

        /// <summary>
        /// Fires whenever a row in the Details grid is highlighted / selected.
        /// We refresh the break pricing panel to match the focused SOLine.
        /// </summary>
        protected void _(Events.RowSelected<SOLine> e)
        {
            SOLine line = e.Row;
            SOPricingBreakHeader header = BreakPricingHeader.Current
                ?? new SOPricingBreakHeader();

            // Short-circuit: same item as before → nothing to reload
            if (line?.InventoryID != null && line.InventoryID == header.InventoryID)
                return;

            if (line?.InventoryID == null)
            {
                // No line selected — clear the panel
                header.InventoryID = null;
                header.ItemDescription = Messages.NoItemSelected;
            }
            else
            {
                int inventoryID = line.InventoryID.Value;
                string description = ResolveItemDescription(inventoryID);

                header.InventoryID = inventoryID;
                header.ItemDescription = description;
            }

            BreakPricingHeader.Cache.Clear();
            BreakPricingHeader.Cache.Insert(header);

            // Force the tier grid to re-query
            BreakPricingTiers.Cache.Clear();
        }

        // ─────────────────────────────────────────────────────────────────────
        // Core data-loading helpers
        // ─────────────────────────────────────────────────────────────────────

        /// <summary>
        /// Queries ARSalesPrice for all base-price break tiers for the given
        /// InventoryID, ordered by BreakQty ascending, then builds the list of
        /// SOPricingBreakTier view-model objects with derived MaxQty values.
        /// </summary>
        private List<SOPricingBreakTier> LoadTiers(int inventoryID)
        {
            // Pull all base-price (PriceType = 'B') break records for this item.
            // We purposely do NOT filter by CustomerID or CustPriceClassID so the
            // panel shows the full ladder regardless of which customer is on the order.
            // SalesPrice records with BreakQty = 0 represent the "base" price (no break);
            // those with BreakQty > 0 are the actual break tiers — we include all.
            var rawRows = SelectFrom<ARSalesPrice>
                .Where<ARSalesPrice.inventoryID.IsEqual<@P.AsInt>
                    .And<ARSalesPrice.priceType.IsEqual<ARPriceType.basePrice>>
                    .And<ARSalesPrice.isPromotionalPrice.IsEqual<False>>>
                .OrderBy<ARSalesPrice.breakQty.Asc>
                .View.ReadOnly.Select(Base, inventoryID);

            var tiers = new List<SOPricingBreakTier>();
            int seq = 0;

            // We need the raw price records as a list to compute MaxQty from n+1
            var priceList = new List<ARSalesPrice>();
            foreach (PXResult<ARSalesPrice> row in rawRows)
                priceList.Add((ARSalesPrice)row);

            for (int i = 0; i < priceList.Count; i++)
            {
                ARSalesPrice price = priceList[i];
                seq++;

                // MaxQty = next tier's BreakQty (so tiers are [min, max) non-overlapping).
                // For the last tier MaxQty is null → displayed as "No Limit" by ASPX format.
                decimal? maxQty = null;
                if (i + 1 < priceList.Count)
                {
                    maxQty = priceList[i + 1].BreakQty;
                }

                tiers.Add(new SOPricingBreakTier
                {
                    TierOrder = seq,
                    MinQty = price.BreakQty,
                    MaxQty = maxQty,
                    UnitPrice = price.SalesPrice,
                    UOM = price.UOM,
                    InventoryID = inventoryID,
                });
            }

            return tiers;
        }

        /// <summary>
        /// Returns a display string "SKU – Description" for the panel header.
        /// Falls back gracefully if the item record is not found.
        /// </summary>
        private string ResolveItemDescription(int inventoryID)
        {
            InventoryItem item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.SelectSingleBound(Base, null, inventoryID);

            if (item == null)
                return Messages.NoItemSelected;

            string cd = item.InventoryCD?.Trim() ?? string.Empty;
            string descr = item.Descr?.Trim() ?? string.Empty;

            if (string.IsNullOrEmpty(descr))
                return cd;

            return string.IsNullOrEmpty(cd) ? descr : $"{cd} – {descr}";
        }

        // ─────────────────────────────────────────────────────────────────────
        // String constants (avoids a separate Messages.cs for a single string)
        // ─────────────────────────────────────────────────────────────────────
        private static class Messages
        {
            public const string NoItemSelected = "(no item selected)";
        }
    }
}
