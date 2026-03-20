using System;
using System.Collections.Generic;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    /// <summary>
    /// Propagates container Expected Arrival Date to linked PO headers and lines.
    /// Replaces IGCMPOLandedCostEntry_Extension (IIG dependency removed).
    /// Wire to ContainerEntry.Persist override when container DACs are built.
    /// </summary>
    public static class ContainerDatePropagation
    {
        /// <summary>
        /// Updates PO headers and lines with the container's expected arrival date.
        /// </summary>
        /// <param name="containerDate">The container's expected arrival date.</param>
        /// <param name="poRefs">List of (OrderType, OrderNbr, LineNbr) tuples from container lines.</param>
        public static void PropagateArrivalDate(
            DateTime? containerDate,
            List<Tuple<string, string, int?>> poRefs)
        {
            if (containerDate == null || poRefs == null || poRefs.Count == 0) return;

            HashSet<string> updatedHeaders = new HashSet<string>();

            foreach (var po in poRefs)
            {
                // Update PO Line
                if (po.Item3 != null)
                {
                    PXDatabase.Update<POLine>(
                        new PXDataFieldAssign<POLineExt.usrExpArrivalDate>(containerDate),
                        new PXDataFieldRestrict<POLine.orderType>(po.Item1),
                        new PXDataFieldRestrict<POLine.orderNbr>(po.Item2),
                        new PXDataFieldRestrict<POLine.lineNbr>(po.Item3)
                    );
                }

                // Update PO Header (once per unique PO)
                string headerKey = po.Item1 + ":" + po.Item2;
                if (!updatedHeaders.Contains(headerKey))
                {
                    PXDatabase.Update<POOrder>(
                        new PXDataFieldAssign<POOrderExt.usrExpArrivalDate>(containerDate),
                        new PXDataFieldRestrict<POOrder.orderType>(po.Item1),
                        new PXDataFieldRestrict<POOrder.orderNbr>(po.Item2)
                    );
                    updatedHeaders.Add(headerKey);
                }
            }
        }
    }
}
