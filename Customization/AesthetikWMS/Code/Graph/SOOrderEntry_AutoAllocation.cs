using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.IN;
using PX.Objects.SO;

namespace Aesthetik.WMS
{
    public class SOOrderEntry_AutoAllocation : PXGraphExtension<SOOrderEntry>
    {
        public static bool IsActive() => true;

        private const string PieceGoodsClassID = "PIECENBR";

        private readonly HashSet<string> _assignedSerials = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        // Use FieldUpdated on OrderQty — fires when qty is changed on a detail line
        protected void _(Events.FieldUpdated<SOLine, SOLine.orderQty> e)
        {
            SOLine row = e.Row;
            if (row == null) return;

            PXTrace.WriteInformation($"[AUTO-ALLOC] FieldUpdated<orderQty> fired. Qty={row.OrderQty}, InvID={row.InventoryID}, Lot={row.LotSerialNbr}");

            SOOrder order = Base.Document.Current;
            if (order == null) return;
            string orderType = order.OrderType;

            // TEST: temporarily include SO for testing (remove after debug)
            if (orderType != "PC" && orderType != "FO" && orderType != "SO") return;

            // Guard: skip if lot already assigned
            if (!string.IsNullOrEmpty(row.LotSerialNbr))
            {
                PXTrace.WriteInformation("[AUTO-ALLOC] Skipped: lot already assigned");
                return;
            }

            if (row.InventoryID == null || (row.OrderQty ?? 0) <= 0)
            {
                PXTrace.WriteInformation($"[AUTO-ALLOC] Skipped: no item or qty <= 0");
                return;
            }

            if (!IsPieceGoodsItem(row.InventoryID)) return;

            decimal minQty = row.OrderQty ?? 0;
            int inventoryID = row.InventoryID.Value;
            int? siteID = row.SiteID ?? order.DefaultSiteID;

            if (siteID == null)
            {
                PXTrace.WriteInformation("[AUTO-ALLOC] Skipped: siteID is null");
                return;
            }

            RebuildAssignedSerials(row.LineNbr);

            var allSerials = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                    .And<INLotSerialStatus.siteID.IsEqual<@P.AsInt>>>
                .View.ReadOnly.Select(Base, inventoryID, siteID.Value);

            PXTrace.WriteInformation($"[AUTO-ALLOC] Found {allSerials.Count} serial records");

            var candidates = new List<BoltCandidate>();

            foreach (PXResult<INLotSerialStatus> result in allSerials)
            {
                var status = (INLotSerialStatus)result;
                if (status.LotSerialNbr == null) continue;
                if (_assignedSerials.Contains(status.LotSerialNbr)) continue;

                decimal qtyOnHand = status.QtyOnHand ?? 0;
                decimal qtyAvail = status.QtyAvail ?? 0;

                if (qtyOnHand < minQty) continue;
                if (qtyAvail != qtyOnHand) continue;

                candidates.Add(new BoltCandidate
                {
                    LotSerialNbr = status.LotSerialNbr,
                    QtyOnHand = qtyOnHand,
                    ReceiptDate = status.ReceiptDate ?? status.LastModifiedDateTime?.Date,
                });
            }

            PXTrace.WriteInformation($"[AUTO-ALLOC] {candidates.Count} candidates (minQty={minQty})");

            if (candidates.Count == 0) return;

            var best = candidates
                .OrderBy(c => c.ReceiptDate ?? DateTime.MaxValue)
                .ThenBy(c => c.QtyOnHand)
                .First();

            PXTrace.WriteInformation($"[AUTO-ALLOC] Assigning bolt {best.LotSerialNbr} (Qty={best.QtyOnHand})");

            // TEST 1: Assign lot ONLY — no qty change
            Base.Transactions.Cache.SetValueExt<SOLine.lotSerialNbr>(row, best.LotSerialNbr);
        }

        protected void _(Events.RowDeleted<SOLine> e)
        {
            if (e.Row?.LotSerialNbr != null)
                _assignedSerials.Remove(e.Row.LotSerialNbr);
        }

        private void RebuildAssignedSerials(int? excludeLineNbr)
        {
            _assignedSerials.Clear();
            foreach (SOLine line in Base.Transactions.Select())
            {
                if (line.LineNbr == excludeLineNbr) continue;
                if (!string.IsNullOrEmpty(line.LotSerialNbr))
                    _assignedSerials.Add(line.LotSerialNbr);
            }
        }

        private bool IsPieceGoodsItem(int? inventoryID)
        {
            if (inventoryID == null) return false;

            var item = SelectFrom<InventoryItem>
                .Where<InventoryItem.inventoryID.IsEqual<@P.AsInt>>
                .View.ReadOnly.Select(Base, inventoryID);

            if (item == null) return false;

            string lotClass = ((InventoryItem)item).LotSerClassID;
            PXTrace.WriteInformation($"[AUTO-ALLOC] LotSerClassID='{lotClass}'");

            return string.Equals(lotClass, PieceGoodsClassID, StringComparison.OrdinalIgnoreCase);
        }

        private class BoltCandidate
        {
            public string LotSerialNbr { get; set; }
            public decimal QtyOnHand { get; set; }
            public DateTime? ReceiptDate { get; set; }
        }
    }
}
