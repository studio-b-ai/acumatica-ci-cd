using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class POOrderEntry_Extension : PXGraphExtension<POOrderEntry>
    {
        public static bool IsActive() => true;

        #region Container Navigation Action
        public PXAction<POOrder> ViewContainer;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Container Tracking", MapEnableRights = PXCacheRights.Select)]
        protected void viewContainer()
        {
            POOrder order = Base.Document.Current;
            if (order == null) return;
            POOrderExt ext = order.GetExtension<POOrderExt>();
            string containerRef = ext?.UsrContainerRef;

            ContainerMaint graph = PXGraph.CreateInstance<ContainerMaint>();
            if (!string.IsNullOrEmpty(containerRef))
            {
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

        protected void _(Events.FieldDefaulting<POLine, POLineExt.usrExpArrivalDate> e)
        {
            if (e.Row == null) return;

            // First: try header-level expected arrival
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
                lineExt.UsrExpArrivalDate = newPromised;
                Base.Transactions.Update(e.Row);
            }
        }

        protected void _(Events.FieldUpdated<POOrder, POOrderExt.usrExpArrivalDate> e)
        {
            if (e.Row == null) return;
            DateTime? oldValue = (DateTime?)e.OldValue;
            DateTime? newValue = e.Row.GetExtension<POOrderExt>()?.UsrExpArrivalDate;
            if (newValue == null) return;
            if (oldValue == newValue) return;
            foreach (POLine line in Base.Transactions.Select())
            {
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

        /// <summary>
        /// Populates UsrQtyOnContainers (virtual) for each PO line.
        /// Replaces IIG's IGCMQtyOnContainers field.
        /// Queries UsrContainerPOLink to find matching container allocations.
        /// </summary>
        protected void _(Events.RowSelected<POLine> e)
        {
            if (e.Row == null) return;
            POOrder header = Base.Document.Current;
            if (header == null) return;

            try
            {
                // Build cache on first line of each PO
                string poKey = header.OrderType + ":" + header.OrderNbr;
                if (_containerQtyCache == null || !_containerQtyCache.ContainsKey(poKey + ":loaded"))
                {
                    _containerQtyCache = new Dictionary<string, decimal>(StringComparer.OrdinalIgnoreCase);
                    _containerQtyCache[poKey + ":loaded"] = 1;

                    // Query all container links for this PO
                    foreach (PXDataRecord rec in PXDatabase.SelectMulti<UsrContainerPOLink>(
                        new PXDataField("LineNbr"),
                        new PXDataField("OrderQty"),
                        new PXDataFieldValue("OrderType", header.OrderType),
                        new PXDataFieldValue("OrderNbr", header.OrderNbr)))
                    {
                        int? lineNbr = rec.GetInt32(0);
                        if (lineNbr != null)
                        {
                            string lineKey = poKey + ":" + lineNbr;
                            // Count container allocations per line
                            if (_containerQtyCache.ContainsKey(lineKey))
                                _containerQtyCache[lineKey] += 1;
                            else
                                _containerQtyCache[lineKey] = 1;
                        }
                    }
                }

                // Set virtual field
                string key = poKey + ":" + e.Row.LineNbr;
                decimal qty = 0;
                _containerQtyCache.TryGetValue(key, out qty);
                e.Cache.SetValue<POLineExt.usrQtyOnContainers>(e.Row, qty > 0 ? qty : (decimal?)null);
            }
            catch (Exception ex)
            {
                PXTrace.WriteError($"UsrQtyOnContainers error: {ex.Message}");
            }
        }
    }
}
