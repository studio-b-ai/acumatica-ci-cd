using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class POOrderEntry_Extension : PXGraphExtension<POOrderEntry>
    {
        public static bool IsActive() => true;

        // ── Re-entrancy guards ───────────────────────────────────────────────────
        // Prevents cascading event-handler loops that caused the PO-entry failure.
        //
        //  _isProcessingLine    — guards FieldDefaulting<POLine> and
        //                         FieldUpdated<POLine, promisedDate>, which can
        //                         mutually trigger each other via Transactions.Update().
        //
        //  _isProcessingHeader  — guards FieldUpdated<POOrder, usrExpArrivalDate>,
        //                         which calls Transactions.Update() in a loop and
        //                         would otherwise cascade back into itself through
        //                         the line-level RowSelected handler.
        //
        //  _isProcessingRowSelected — guards RowSelected<POLine>, which performs a
        //                         PXDatabase query and cache write; without this guard
        //                         the Transactions.Update() calls inside the header
        //                         propagation loop would re-enter RowSelected for
        //                         every line on every update.
        //
        //  _isProcessingFactoryPromisedLine / Header — dedicated guards for the
        //                         2026-04-18 PR-5 UsrFactoryPromisedDate cascade.
        //                         Kept separate from the UsrExpArrivalDate guards
        //                         so propagating one date doesn't suppress the
        //                         other mid-flight (possible if a header edit
        //                         sets both dates in one transaction).
        // ────────────────────────────────────────────────────────────────────────
        private bool _isProcessingLine                  = false;
        private bool _isProcessingHeader                = false;
        private bool _isProcessingRowSelected           = false;
        private bool _isProcessingFactoryPromisedLine   = false;
        private bool _isProcessingFactoryPromisedHeader = false;

        #region Container Navigation Action
        public PXAction<POOrder> ViewContainer;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Container Tracking", MapEnableRights = PXCacheRights.Select)]
        protected void viewContainer()
        {
            // Fix C: null-check Current before any access to the document
            POOrder order = Base.Document.Current;
            if (order == null) return;

            // REVIEWED: extension-safe — Base.Document.Current, cache-init
            POOrderExt ext = order.GetExtension<POOrderExt>();
            string containerRef = ext?.UsrContainerRef;

            ContainerMaint graph = PXGraph.CreateInstance<ContainerMaint>();
            if (!string.IsNullOrEmpty(containerRef))
            {
                // Fix C: BQL has a Where<> clause with a Required<> parameter — correctly
                // scoped; no unfiltered select.
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

        // Cache for container-qty lookups — keyed by "OrderType:OrderNbr:LineNbr".
        // Invalidated whenever lines are inserted, deleted, or the document changes.
        private Dictionary<string, decimal> _containerQtyCache;

        /// <summary>
        /// Defaults UsrExpArrivalDate for a new PO line.
        /// Priority: header UsrExpArrivalDate → line PromisedDate → leave blank.
        /// </summary>
        protected void _(Events.FieldDefaulting<POLine, POLineExt.usrExpArrivalDate> e)
        {
            // Fix A: re-entrancy guard — FieldUpdated<POLine> sets _isProcessingLine=true
            // before calling Transactions.Update(), which would re-fire FieldDefaulting
            // for the same line.  Block that second invocation here.
            if (_isProcessingLine) return;

            if (e.Row == null) return;

            // Fix C: null-check Current before accessing document header
            POOrder header = Base.Document.Current;
            if (header != null)
            {
                // REVIEWED: extension-safe — Base.Document.Current, cache-init
                POOrderExt headerExt = header.GetExtension<POOrderExt>();
                if (headerExt?.UsrExpArrivalDate != null)
                {
                    e.NewValue = headerExt.UsrExpArrivalDate;
                    e.Cancel = true;
                    return;
                }
            }

            // Fallback: seed from the line's PromisedDate so the field is never blank
            if (e.Row.PromisedDate != null)
            {
                e.NewValue = e.Row.PromisedDate;
                e.Cancel = true;
            }
        }

        /// <summary>
        /// When PromisedDate changes on a PO line and UsrExpArrivalDate hasn't been
        /// manually overridden (still null or still matches the old PromisedDate),
        /// update UsrExpArrivalDate to match.
        /// </summary>
        protected void _(Events.FieldUpdated<POLine, POLine.promisedDate> e)
        {
            // Fix A: re-entrancy guard — this handler calls Transactions.Update(),
            // which fires FieldDefaulting and can re-enter here.
            if (_isProcessingLine) return;

            if (e.Row == null) return;
            POLineExt lineExt = e.Row.GetExtension<POLineExt>();
            if (lineExt == null) return;

            DateTime? oldPromised = (DateTime?)e.OldValue;
            DateTime? newPromised = e.Row.PromisedDate;
            if (newPromised == null) return;

            // Only propagate when the expected-arrival date is still inherited
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
        /// When the header-level UsrExpArrivalDate changes, propagate it down to all
        /// lines whose expected-arrival date is still "inherited" (null, or equal to
        /// the old header value).
        /// </summary>
        protected void _(Events.FieldUpdated<POOrder, POOrderExt.usrExpArrivalDate> e)
        {
            // Fix A: re-entrancy guard — each Transactions.Update() below fires
            // RowSelected<POLine>, which is on a separate flag, but also fires
            // FieldUpdated<POOrder> again if any line update bubbles header-side
            // recalculation.  Block that second entry here.
            if (_isProcessingHeader) return;

            if (e.Row == null) return;

            DateTime? oldValue = (DateTime?)e.OldValue;
            DateTime? newValue = e.Row.GetExtension<POOrderExt>()?.UsrExpArrivalDate;
            if (newValue == null) return;
            if (oldValue == newValue) return;

            _isProcessingHeader = true;
            try
            {
                // Fix C: Base.Transactions is a PXSelect scoped to the current document
                // by the Acumatica cache infrastructure — no additional Where<> is needed.
                // Null-check each element to guard against empty result sets.
                foreach (POLine line in Base.Transactions.Select())
                {
                    if (line == null) continue;
                    // REVIEWED: extension-safe — row from Base.Transactions.Select(), cache-init
                    POLineExt lineExt = line.GetExtension<POLineExt>();
                    if (lineExt == null) continue;

                    bool isInherited = lineExt.UsrExpArrivalDate == null
                                    || lineExt.UsrExpArrivalDate == oldValue;
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

        // ── UsrFactoryPromisedDate cascade (PR-5, 2026-04-18) ──────────────────
        // Mirrors UsrExpArrivalDate pattern: header default cascades to line
        // default; inherited lines stay inherited until manually overridden.
        // Re-entrancy guarded with dedicated flags so one cascade doesn't
        // suppress the other when both dates change in one transaction.

        /// <summary>
        /// Defaults UsrFactoryPromisedDate for a new PO line.
        /// Priority: header UsrFactoryPromisedDate → leave blank.
        /// </summary>
        protected void _(Events.FieldDefaulting<POLine, POLineExt.usrFactoryPromisedDate> e)
        {
            if (_isProcessingFactoryPromisedLine) return;
            if (e.Row == null) return;

            POOrder header = Base.Document.Current;
            if (header == null) return;

            POOrderExt headerExt = header.GetExtension<POOrderExt>();
            if (headerExt?.UsrFactoryPromisedDate != null)
            {
                e.NewValue = headerExt.UsrFactoryPromisedDate;
                e.Cancel = true;
            }
            // No fallback to PromisedDate — FactoryPromisedDate is the vendor's
            // production commitment, not the PO-level delivery promise. Leave
            // blank when header is unset; email parser populates from vendor
            // acknowledgment message.
        }

        /// <summary>
        /// When the header-level UsrFactoryPromisedDate changes, propagate it down
        /// to all lines whose factory-promised date is still "inherited" (null,
        /// or equal to the old header value).
        /// </summary>
        protected void _(Events.FieldUpdated<POOrder, POOrderExt.usrFactoryPromisedDate> e)
        {
            if (_isProcessingFactoryPromisedHeader) return;
            if (e.Row == null) return;

            DateTime? oldValue = (DateTime?)e.OldValue;
            DateTime? newValue = e.Row.GetExtension<POOrderExt>()?.UsrFactoryPromisedDate;
            if (newValue == null) return;
            if (oldValue == newValue) return;

            _isProcessingFactoryPromisedHeader = true;
            try
            {
                foreach (POLine line in Base.Transactions.Select())
                {
                    if (line == null) continue;
                    POLineExt lineExt = line.GetExtension<POLineExt>();
                    if (lineExt == null) continue;

                    bool isInherited = lineExt.UsrFactoryPromisedDate == null
                                    || lineExt.UsrFactoryPromisedDate == oldValue;
                    if (isInherited)
                    {
                        lineExt.UsrFactoryPromisedDate = newValue;
                        Base.Transactions.Update(line);
                    }
                }
            }
            finally
            {
                _isProcessingFactoryPromisedHeader = false;
            }
        }

        /// <summary>
        /// Populates the virtual UsrQtyOnContainers field for each PO line.
        /// Uses a per-PO cache to avoid one DB round-trip per line on every render.
        /// </summary>
        protected void _(Events.RowSelected<POLine> e)
        {
            // Fix A: re-entrancy guard — the header FieldUpdated handler calls
            // Transactions.Update() inside a loop, which fires RowSelected for
            // every updated line.  Without this guard that causes O(n²) re-entry.
            if (_isProcessingRowSelected) return;

            if (e.Row == null) return;

            // Fix C: null-check Current before accessing document header
            POOrder header = Base.Document.Current;
            if (header == null) return;

            _isProcessingRowSelected = true;
            try
            {
                string poKey = header.OrderType + ":" + header.OrderNbr;

                // Build (or rebuild) the cache on the first RowSelected call for this PO
                if (_containerQtyCache == null || !_containerQtyCache.ContainsKey(poKey + ":loaded"))
                {
                    _containerQtyCache = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
                    _containerQtyCache[poKey + ":loaded"] = 1;

                    // Fix C: PXDatabase.SelectMulti is explicitly scoped by
                    // PXDataFieldValue filters on OrderType + OrderNbr — correctly bounded.
                    // Null-check each record to guard against unexpected nulls in the set.
                    foreach (PXDataRecord rec in PXDatabase.SelectMulti<UsrContainerPOLink>(
                        new PXDataField("LineNbr"),
                        new PXDataField("OrderQty"),
                        new PXDataFieldValue("OrderType", header.OrderType),
                        new PXDataFieldValue("OrderNbr",  header.OrderNbr)))
                    {
                        if (rec == null) continue;
                        int? lineNbr = rec.GetInt32(0);
                        if (lineNbr == null) continue;

                        string lineKey = poKey + ":" + lineNbr;
                        if (_containerQtyCache.ContainsKey(lineKey))
                            _containerQtyCache[lineKey] += 1;
                        else
                            _containerQtyCache[lineKey] = 1;
                    }
                }

                // Populate the virtual field; use null (not 0) when there are no allocations
                string key = poKey + ":" + e.Row.LineNbr;
                decimal qty = 0;
                _containerQtyCache.TryGetValue(key, out qty);
                e.Cache.SetValue<POLineExt.usrQtyOnContainers>(e.Row, qty > 0 ? qty : (decimal?)null);
            }
            catch (Exception ex)
            {
                PXTrace.WriteError($"[POOrderEntry_Extension] UsrQtyOnContainers error: {ex.Message}");
            }
            finally
            {
                _isProcessingRowSelected = false;
            }
        }

        /// <summary>
        /// Invalidate the container-qty cache whenever a new PO line is inserted so that
        /// the next RowSelected call re-queries and the new line gets a fresh allocation count.
        /// </summary>
        protected void _(Events.RowInserted<POLine> e)
        {
            // Flush the cache so RowSelected rebuilds it for the updated line set
            _containerQtyCache = null;
        }

        /// <summary>
        /// Invalidate the container-qty cache whenever a PO line is deleted so that
        /// removed lines no longer contribute stale counts to the cache.
        /// </summary>
        protected void _(Events.RowDeleted<POLine> e)
        {
            // Flush the cache so RowSelected rebuilds it for the updated line set
            _containerQtyCache = null;
        }
    }
}
