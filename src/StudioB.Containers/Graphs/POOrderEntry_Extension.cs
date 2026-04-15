using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class POOrderEntry_Extension : PXGraphExtension<POOrderEntry>
    {
        public static bool IsActive() => true;

        // Re-entrancy guards — prevent cascading event handler loops.
        // _isProcessingLine guards the two POLine handlers (FieldDefaulting + FieldUpdated<POLine>)
        // which can mutually trigger each other via Transactions.Update().
        // _isProcessingHeader guards the POOrder-level FieldUpdated handler which calls
        // Transactions.Update() in a loop, which in turn fires RowSelected<POLine>.
        private bool _isProcessingLine = false;
        private bool _isProcessingHeader = false;
        private bool _isProcessingRowSelected = false;

        #region Container Navigation Action
        public PXAction<POOrder> ViewContainer;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Container Tracking", MapEnableRights = PXCacheRights.Select)]
        protected void viewContainer()
        {
            // Fix C: null-check Current before accessing
            POOrder order = Base.Document.Current;
            if (order == null) return;

            POOrderExt ext = order.GetExtension<POOrderExt>();
            string containerRef = ext?.UsrContainerRef;

            ContainerMaint graph = PXGraph.CreateInstance<ContainerMaint>();
            if (!string.IsNullOrEmpty(containerRef))
            {
                // Fix C: BQL already has a Where clause with a Required parameter — correctly scoped
                UsrContainer container = PXSelect<UsrContainer,
                    Where<UsrContainer.containerCD, Equal<Required<UsrContainer.containerCD>>>>
                    .Select(graph, containerRef.Trim());
                if (container != null)
                {
                    graph.Container.Current = container;
                }
            }
            throw new PXRedirectRequiredException(graph, "Container Tracking");
        }
        #endregion

        // Cache container qty lookups per PO to avoid repeated queries
        private Dictionary<string, decimal> _containerQtyCache;

        /// <summary>
        /// Defaults UsrExpArrivalDate for a new PO line.
        /// First tries the header-level expected arrival date, then falls back to PromisedDate.
        /// </summary>
        protected void _(Events.FieldDefaulting<POLine, POLineExt.usrExpArrivalDate> e)
        {
            // Fix A: re-entrancy guard
            if (_isProcessingLine) return;

            if (e.Row == null) return;

            // Fix C: null-check Current before accessing
            POOrder header = Base.Document.Current;
            if (header != null)
            {
                POOrderExt headerExt = header.GetExtension<POOrderExt>();
                if (headerExt?.UsrExpArrivalDate != null)
                {
                    e.NewValue = headerExt.UsrExpArrivalDate;
                    e.Cancel = true;
                    return;
                }
            }

            // Fallback: seed from line's PromisedDate so expected arrival is never blank
            if (e.Row.PromisedDate != null)
            {
                e.NewValue = e.Row.PromisedDate;
                e.Cancel = true;
            }
        }

        /// <summary>
        /// When PromisedDate changes on a PO line and UsrExpArrivalDate hasn't been
        /// manually overridden (still null or still matches old PromisedDate), update
        /// UsrExpArrivalDate to match. This ensures expected arrival is never blank
        /// and stays in sync until explicitly overridden by container propagation,
        /// forwarder update, or manual entry.
        /// </summary>
        protected void _(Events.FieldUpdated<POLine, POLine.promisedDate> e)
        {
            // Fix A: re-entrancy guard
            if (_isProcessingLine) return;

            if (e.Row == null) return;
            POLineExt lineExt = e.Row.GetExtension<POLineExt>();
            if (lineExt == null) return;

            DateTime? oldPromised = (DateTime?)e.OldValue;
            DateTime? newPromised = e.Row.PromisedDate;
            if (newPromised == null) return;

            // Seed if expected is null, or update if expected still matches old promised
            bool shouldUpdate = lineExt.UsrExpArrivalDate == null
                             || lineExt.UsrExpArrivalDate == oldPromised;

            if (shouldUpdate)
            {
                _isProcessingLine = true;
                try
                {
                    lineExt.UsrExpArrivalDate = newPromised;
                    Base.Transactions.Update(e.Row);
                }
                finally
                {
                    _isProcessingLine = false;
                }
            }
        }

        /// <summary>
        /// When the header-level UsrExpArrivalDate changes, propagate it to all lines
        /// whose expected arrival date is still inherited (null or matches old header value).
        /// </summary>
        protected void _(Events.FieldUpdated<POOrder, POOrderExt.usrExpArrivalDate> e)
        {
            // Fix A: re-entrancy guard
            if (_isProcessingHeader) return;

            if (e.Row == null) return;

            DateTime? oldValue = (DateTime?)e.OldValue;
            DateTime? newValue = e.Row.GetExtension<POOrderExt>()?.UsrExpArrivalDate;
            if (newValue == null) return;
            if (oldValue == newValue) return;

            _isProcessingHeader = true;
            try
            {
                // Fix C: Base.Transactions is already scoped to the current document
                // by Acumatica's cache — safe to iterate. Guard against empty result set.
                foreach (POLine line in Base.Transactions.Select())
                {
                    if (line == null) continue;
                    POLineExt lineExt = line.GetExtension<POLineExt>();
                    if (lineExt == null) continue;
                    bool isInherited = lineExt.UsrExpArrivalDate == null || lineExt.UsrExpArrivalDate == oldValue;
                    if (isInherited)
                    {
                        lineExt.UsrExpArrivalDate = newValue;
                        Base.Transactions.Update(line);
                    }
                }
            }
            finally
            {
                _isProcessingHeader = false;
            }
        }

        /// <summary>
        /// Populates UsrQtyOnContainers (virtual) for each PO line.
        /// Replaces IIG's IGCMQtyOnContainers field.
        /// Queries UsrContainerPOLink to find matching container allocations.
        /// </summary>
        protected void _(Events.RowSelected<POLine> e)
        {
            // Fix A: re-entrancy guard
            if (_isProcessingRowSelected) return;

            if (e.Row == null) return;

            // Fix C: null-check Current before accessing
            POOrder header = Base.Document.Current;
            if (header == null) return;

            _isProcessingRowSelected = true;
            try
            {
                // Build cache on first line of each PO
                string poKey = header.OrderType + ":" + header.OrderNbr;
                if (_containerQtyCache == null || !_containerQtyCache.ContainsKey(poKey + ":loaded"))
                {
                    _containerQtyCache = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
                    _containerQtyCache[poKey + ":loaded"] = 1;

                    // Fix C: PXDatabase.SelectMulti is already scoped by the explicit
                    // PXDataFieldValue filters on OrderType + OrderNbr — correctly bounded.
                    // Guard against null records in the result set.
                    foreach (PXDataRecord rec in PXDatabase.SelectMulti<UsrContainerPOLink>(
                        new PXDataField("LineNbr"),
                        new PXDataField("OrderQty"),
                        new PXDataFieldValue("OrderType", header.OrderType),
                        new PXDataFieldValue("OrderNbr", header.OrderNbr)))
                    {
                        if (rec == null) continue;
                        int? lineNbr = rec.GetInt32(0);
                        if (lineNbr != null)
                        {
                            string lineKey = poKey + ":" + lineNbr;
                            // Accumulate container allocation count per line
                            if (_containerQtyCache.ContainsKey(lineKey))
                                _containerQtyCache[lineKey] += 1;
                            else
                                _containerQtyCache[lineKey] = 1;
                        }
                    }
                }

                // Set virtual field — default to null (not zero) when no allocations found
                string key = poKey + ":" + e.Row.LineNbr;
                decimal qty = 0;
                _containerQtyCache.TryGetValue(key, out qty);
                e.Cache.SetValue<POLineExt.usrQtyOnContainers>(e.Row, qty > 0 ? qty : (decimal?)null);
            }
            catch (Exception ex)
            {
                PXTrace.WriteError($"UsrQtyOnContainers error: {ex.Message}");
            }
            finally
            {
                _isProcessingRowSelected = false;
            }
        }
    }
}
