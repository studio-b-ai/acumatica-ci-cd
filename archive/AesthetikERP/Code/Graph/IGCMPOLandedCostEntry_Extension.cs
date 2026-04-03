using System;
using System.Collections.Generic;
using PX.Data;
using IGCM;
using IGCM.DAC;
using PX.Objects.PO;
using HeritageFabrics.PO;

namespace HeritageFabrics.IGCM
{
    public class IGCMPOLandedCostEntry_Extension : PXGraphExtension<IGCMPOLandedCostEntry>
    {
        public static bool IsActive() => true;

        [PXOverride]
        public void Persist(Action del)
        {
            // Capture container header and line PO references BEFORE base save
            IGCMPOLandedCost header = (IGCMPOLandedCost)Base.Caches[typeof(IGCMPOLandedCost)].Current;
            DateTime? containerDate = header?.ExpectedArrivalDate;

            var poRefs = new List<Tuple<string, string, int?>>();

            if (containerDate != null)
            {
                PXCache lineCache = Base.Caches[typeof(IGCMPOLandedCostLine)];
                foreach (IGCMPOLandedCostLine line in lineCache.Cached)
                {
                    PXEntryStatus status = lineCache.GetStatus(line);
                    if (status == PXEntryStatus.Deleted || status == PXEntryStatus.InsertedDeleted)
                        continue;
                    if (string.IsNullOrEmpty(line.POOrderType) || string.IsNullOrEmpty(line.PONbr))
                        continue;
                    poRefs.Add(Tuple.Create(line.POOrderType, line.PONbr, line.POLineNbr));
                }
            }

            // Execute base save
            del();

            // After successful save, propagate container date to linked PO records
            if (containerDate == null || poRefs.Count == 0) return;

            HashSet<string> updatedHeaders = new HashSet<string>();

            foreach (Tuple<string, string, int?> po in poRefs)
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
