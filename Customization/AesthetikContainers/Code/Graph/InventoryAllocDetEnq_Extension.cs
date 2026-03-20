using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.IN;

namespace StudioB.Containers
{
    public class InventoryAllocDetEnq_Extension : PXGraphExtension<InventoryAllocDetEnq>
    {
        public static bool IsActive() => true;

        private readonly Dictionary<string, DateTime?> _dateCache
            = new Dictionary<string, DateTime?>(StringComparer.OrdinalIgnoreCase);

        /// <summary>
        /// RowSelected fires for each visible row in the inquiry grid.
        /// Populates the virtual UsrExpArrivalDate from the linked PO header.
        /// Uses generic event syntax (guaranteed to wire up for extension fields).
        /// </summary>
        protected void _(Events.RowSelected<InventoryAllocDetEnqResult> e)
        {
            if (e.Row == null || string.IsNullOrEmpty(e.Row.RefNbr)) return;

            string refNbr = e.Row.RefNbr.Trim();

            // Skip if already populated
            DateTime? current = (DateTime?)e.Cache.GetValue(e.Row, "UsrExpArrivalDate");
            if (current != null) return;

            DateTime? arrivalDate = LookupPOArrivalDate(refNbr);

            if (arrivalDate != null)
            {
                e.Cache.SetValue(e.Row, "UsrExpArrivalDate", arrivalDate);
            }
        }

        private DateTime? LookupPOArrivalDate(string refNbr)
        {
            if (_dateCache.TryGetValue(refNbr, out DateTime? cached))
                return cached;

            DateTime? arrivalDate = null;
            try
            {
                // Explicit column names — avoids BQL extension field resolution
                // issues that occur in foreign inquiry graphs
                using (PXDataRecord rec = PXDatabase.SelectSingle<PX.Objects.PO.POOrder>(
                    new PXDataField("UsrExpArrivalDate"),
                    new PXDataFieldValue("OrderNbr", refNbr)))
                {
                    arrivalDate = rec?.GetDateTime(0);
                }
            }
            catch (Exception ex)
            {
                PXTrace.WriteError(
                    $"IN402000 UsrExpArrivalDate lookup error for RefNbr={refNbr}: {ex.Message}");
            }

            _dateCache[refNbr] = arrivalDate;
            return arrivalDate;
        }
    }
}
