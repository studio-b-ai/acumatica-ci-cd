using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    /// <summary>
    /// Extends POReceiptEntry to auto-create a Landed Cost document
    /// when a PO Receipt linked to a container is released.
    /// </summary>
    public class POReceiptEntryContainerExt : PXGraphExtension<POReceiptEntry>
    {
        public static bool IsActive() => true;

        protected void _(Events.RowUpdated<POReceipt> e)
        {
            if (e.Row == null || e.OldRow == null) return;

            // Detect release: Released flips from false to true
            bool wasReleased = e.OldRow.Released == true;
            bool isReleased = e.Row.Released == true;
            if (wasReleased || !isReleased) return;

            // Check if any receipt lines are linked to a container
            string receiptNbr = e.Row.ReceiptNbr;
            if (string.IsNullOrEmpty(receiptNbr)) return;

            // Find containers linked to this receipt's PO lines
            var containerIDs = new HashSet<int>();
            foreach (POReceiptLine rl in PXSelect<POReceiptLine,
                Where<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>>>
                .Select(Base, receiptNbr))
            {
                if (string.IsNullOrEmpty(rl.PONbr)) continue;

                foreach (UsrContainerPOLink link in PXSelect<UsrContainerPOLink,
                    Where<UsrContainerPOLink.orderType, Equal<Required<UsrContainerPOLink.orderType>>,
                    And<UsrContainerPOLink.orderNbr, Equal<Required<UsrContainerPOLink.orderNbr>>,
                    And<UsrContainerPOLink.lineNbr, Equal<Required<UsrContainerPOLink.lineNbr>>>>>>
                    .Select(Base, rl.POType, rl.PONbr, rl.POLineNbr))
                {
                    if (link.ContainerID != null)
                        containerIDs.Add(link.ContainerID.Value);
                }
            }

            if (containerIDs.Count == 0) return;

            // For each container, create LC doc if it has costs and no existing LC
            foreach (int containerID in containerIDs)
            {
                try
                {
                    CreateLandedCostForContainer(containerID, receiptNbr);
                }
                catch (Exception ex)
                {
                    PXTrace.WriteWarning(
                        "Auto LC creation failed for container {0}: {1}",
                        containerID, ex.Message);
                }
            }
        }

        private void CreateLandedCostForContainer(int containerID, string receiptNbr)
        {
            UsrContainer container = PXSelect<UsrContainer,
                Where<UsrContainer.containerID, Equal<Required<UsrContainer.containerID>>>>
                .Select(Base, containerID);

            if (container == null) return;

            // Skip if LC already exists
            if (!string.IsNullOrEmpty(container.LandedCostRefNbr)) return;

            // Get container costs
            var costs = new List<UsrContainerCost>();
            foreach (UsrContainerCost cost in PXSelect<UsrContainerCost,
                Where<UsrContainerCost.containerID, Equal<Required<UsrContainerCost.containerID>>>>
                .Select(Base, containerID))
            {
                if ((cost.Amount ?? 0m) > 0m) costs.Add(cost);
            }

            if (costs.Count == 0) return; // No costs to allocate

            // Get LC code preferences
            var prefs = PXSelect<UsrContainerPrefs>.Select(Base).TopFirst;
            if (prefs == null) return; // No LC codes configured — skip silently

            // Create LC document
            var lcGraph = PXGraph.CreateInstance<POLandedCostDocEntry>();
            var lcDoc = lcGraph.Document.Insert(new POLandedCostDoc());
            lcDoc.DocDate = Base.Accessinfo.BusinessDate;

            // Set vendor from first cost with a vendor
            foreach (var cost in costs)
            {
                if (cost.VendorID != null)
                {
                    lcDoc.VendorID = cost.VendorID;
                    break;
                }
            }
            lcGraph.Document.Update(lcDoc);

            // Add cost detail lines
            foreach (var cost in costs)
            {
                string lcCode = GetLCCode(prefs, cost.CostType);
                if (string.IsNullOrEmpty(lcCode)) continue; // Skip unmapped cost types

                var detail = new POLandedCostDetail();
                detail.LandedCostCodeID = lcCode;
                detail.CuryLineAmt = cost.Amount;
                detail.Descr = cost.Description ?? cost.CostType;
                lcGraph.Details.Insert(detail);
            }

            // Add receipt lines
            foreach (POReceiptLine rl in PXSelect<POReceiptLine,
                Where<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>>>
                .Select(Base, receiptNbr))
            {
                // Verify this receipt line's PO is linked to this container
                UsrContainerPOLink link = PXSelect<UsrContainerPOLink,
                    Where<UsrContainerPOLink.containerID, Equal<Required<UsrContainerPOLink.containerID>>,
                    And<UsrContainerPOLink.orderType, Equal<Required<UsrContainerPOLink.orderType>>,
                    And<UsrContainerPOLink.orderNbr, Equal<Required<UsrContainerPOLink.orderNbr>>>>>>
                    .Select(Base, containerID, rl.POType, rl.PONbr);

                if (link == null) continue;

                // Add receipt line to LC doc via the ReceiptLines view
                var rcptDetail = new POLandedCostReceiptLine();
                rcptDetail.POReceiptType = rl.ReceiptType;
                rcptDetail.POReceiptNbr = rl.ReceiptNbr;
                rcptDetail.POReceiptLineNbr = rl.LineNbr;
                lcGraph.ReceiptLines.Insert(rcptDetail);
            }

            lcGraph.Actions.PressSave();

            // Update container with LC reference
            var containerCache = Base.Caches[typeof(UsrContainer)];
            container.LandedCostRefNbr = lcGraph.Document.Current.RefNbr;
            container.LandedCostStatus = lcGraph.Document.Current.Status;
            containerCache.Update(container);
            containerCache.Persist(PXDBOperation.Update);
        }

        private static string GetLCCode(UsrContainerPrefs prefs, string costType)
        {
            switch (costType?.ToUpperInvariant())
            {
                case "DUTY":
                case "TARIFF":
                    return prefs.DutyLCCode;
                case "SHIPPING":
                case "FREIGHT":
                    return prefs.FreightLCCode;
                case "BROKERAGE":
                    return prefs.BrokerageLCCode;
                case "INSURANCE":
                    return prefs.InsuranceLCCode;
                default:
                    return prefs.OtherLCCode;
            }
        }
    }
}
