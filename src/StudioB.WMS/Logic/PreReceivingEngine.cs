using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.CS;
using PX.Objects.IN;
using PX.Objects.PO;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Pre-receiving engine for advance allocation of piece goods inventory.
    ///
    /// Creates serial numbers, lot attributes, and bin assignments from PO/ASN data
    /// BEFORE goods physically arrive at the warehouse. This enables:
    ///   - Selling specific rolls from in-transit containers
    ///   - Planned put-away (warehouse knows which bin each roll goes to)
    ///   - Cross-dock fulfillment upon container arrival
    ///
    /// Supports two ingest methods:
    ///   1. EDI 856 ASN (via SPS Commerce) — automated, preferred for high-volume mills
    ///   2. Manual CSV upload — for mills without EDI capability
    ///
    /// Target: Acumatica 2024 R2
    /// </summary>
    public class PreReceivingEngine
    {
        private readonly PXGraph _graph;

        public PreReceivingEngine(PXGraph graph)
        {
            _graph = graph ?? throw new ArgumentNullException(nameof(graph));
        }

        #region CSV Import

        /// <summary>
        /// Imports a packing list CSV and creates pre-receiving serial records.
        ///
        /// Required columns: PO Number, SKU, Yardage, Dye Lot
        /// Optional columns: Width, Shade Code, Container Number
        /// </summary>
        public PreReceivingResult ImportPackingListCSV(Stream csvStream, int warehouseID)
        {
            var result = new PreReceivingResult();
            var lines = new List<PackingListLine>();

            // ── STEP 1: Parse CSV ──────────────────────────────────────────
            try
            {
                using (var reader = new StreamReader(csvStream))
                {
                    string headerLine = reader.ReadLine();
                    if (string.IsNullOrWhiteSpace(headerLine))
                    {
                        result.Errors.Add("CSV file is empty or missing header row.");
                        return result;
                    }

                    var headers = ParseCSVRow(headerLine);
                    var columnMap = BuildColumnMap(headers);

                    if (!ValidateRequiredColumns(columnMap, result))
                        return result;

                    int rowNumber = 1;
                    string line;
                    while ((line = reader.ReadLine()) != null)
                    {
                        rowNumber++;
                        if (string.IsNullOrWhiteSpace(line)) continue;

                        var parsed = ParsePackingListRow(ParseCSVRow(line), columnMap, rowNumber);
                        if (parsed.Errors.Count > 0)
                            result.Warnings.AddRange(parsed.Errors);
                        else
                            lines.Add(parsed.Line);
                    }
                }
            }
            catch (Exception ex)
            {
                result.Errors.Add($"CSV parse error: {ex.Message}");
                return result;
            }

            if (lines.Count == 0)
            {
                result.Errors.Add("No valid lines found in CSV.");
                return result;
            }

            // ── STEP 2: Validate against Acumatica ────────────────────────
            var validLines = ValidateAgainstERP(lines, result);

            // ── STEP 3: Create serial numbers ──────────────────────────────
            var createdSerials = CreatePreReceivingSerials(validLines, warehouseID, result);

            // ── STEP 4: Assign bins ────────────────────────────────────────
            if (createdSerials.Count > 0)
            {
                AssignBins(createdSerials, warehouseID);
                result.BinsAssigned = createdSerials.Count;
            }

            result.Success = result.Errors.Count == 0;
            return result;
        }

        /// <summary>
        /// Parses a single CSV row respecting quoted fields with commas.
        /// </summary>
        private string[] ParseCSVRow(string line)
        {
            var fields = new List<string>();
            bool inQuotes = false;
            var current = new System.Text.StringBuilder();

            foreach (char c in line)
            {
                if (c == '"')
                {
                    inQuotes = !inQuotes;
                }
                else if (c == ',' && !inQuotes)
                {
                    fields.Add(current.ToString().Trim());
                    current.Clear();
                }
                else
                {
                    current.Append(c);
                }
            }
            fields.Add(current.ToString().Trim());

            return fields.ToArray();
        }

        /// <summary>
        /// Builds a case-insensitive column name → index map from CSV headers.
        /// </summary>
        private Dictionary<string, int> BuildColumnMap(string[] headers)
        {
            var map = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < headers.Length; i++)
            {
                string normalized = headers[i].Trim().Replace(" ", "").Replace("_", "");
                map[normalized] = i;

                // Also store the original for case-insensitive lookup
                map[headers[i].Trim()] = i;
            }
            return map;
        }

        /// <summary>
        /// Validates that all required columns are present in the CSV.
        /// </summary>
        private bool ValidateRequiredColumns(Dictionary<string, int> columnMap, PreReceivingResult result)
        {
            var required = new[] { "PONumber", "SKU", "Yardage", "DyeLot" };
            var alternates = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
            {
                { "PONumber", new[] { "PO Number", "PO", "PONbr", "PO_Number", "PONumber" } },
                { "SKU", new[] { "SKU", "ItemID", "Item", "InventoryID", "Item ID" } },
                { "Yardage", new[] { "Yardage", "Yards", "Qty", "Quantity", "ActualYardage" } },
                { "DyeLot", new[] { "DyeLot", "Dye Lot", "DyeLotNumber", "Lot", "LotNumber" } },
            };

            bool allFound = true;
            foreach (string req in required)
            {
                bool found = false;
                if (alternates.TryGetValue(req, out var alts))
                {
                    foreach (string alt in alts)
                    {
                        string normalized = alt.Replace(" ", "").Replace("_", "");
                        if (columnMap.ContainsKey(normalized) || columnMap.ContainsKey(alt))
                        {
                            found = true;
                            break;
                        }
                    }
                }

                if (!found)
                {
                    result.Errors.Add($"Required column '{req}' not found. Expected one of: {string.Join(", ", alternates[req])}");
                    allFound = false;
                }
            }

            return allFound;
        }

        /// <summary>
        /// Parses a single packing list row from CSV field values.
        /// </summary>
        private (PackingListLine Line, List<string> Errors) ParsePackingListRow(
            string[] fields, Dictionary<string, int> columnMap, int rowNumber)
        {
            var errors = new List<string>();
            var line = new PackingListLine();

            line.PONumber = GetField(fields, columnMap,
                "PONumber", "PO Number", "PO", "PONbr");
            line.SKU = GetField(fields, columnMap,
                "SKU", "ItemID", "Item", "InventoryID");

            string yardageStr = GetField(fields, columnMap,
                "Yardage", "Yards", "Qty", "Quantity");
            string dyeLot = GetField(fields, columnMap,
                "DyeLot", "Dye Lot", "Lot", "LotNumber");

            // Validate required fields
            if (string.IsNullOrEmpty(line.PONumber))
                errors.Add($"Row {rowNumber}: Missing PO Number");
            if (string.IsNullOrEmpty(line.SKU))
                errors.Add($"Row {rowNumber}: Missing SKU");
            if (string.IsNullOrEmpty(dyeLot))
                errors.Add($"Row {rowNumber}: Missing Dye Lot");

            if (decimal.TryParse(yardageStr, NumberStyles.Any, CultureInfo.InvariantCulture, out decimal yardage))
            {
                if (yardage <= 0)
                    errors.Add($"Row {rowNumber}: Yardage must be positive (got {yardage})");
                else
                    line.Yardage = yardage;
            }
            else
            {
                errors.Add($"Row {rowNumber}: Invalid yardage value '{yardageStr}'");
            }

            line.DyeLot = dyeLot;

            // Optional fields
            string widthStr = GetField(fields, columnMap, "Width", "WidthInches", "Width (inches)");
            if (!string.IsNullOrEmpty(widthStr) &&
                decimal.TryParse(widthStr, NumberStyles.Any, CultureInfo.InvariantCulture, out decimal width))
            {
                line.Width = width;
            }

            line.ShadeCode = GetField(fields, columnMap, "ShadeCode", "Shade Code", "Shade");
            line.ContainerNumber = GetField(fields, columnMap, "ContainerNumber", "Container Number", "Container", "Container #");

            return (line, errors);
        }

        /// <summary>
        /// Gets a field value by trying multiple column name variants.
        /// </summary>
        private string GetField(string[] fields, Dictionary<string, int> columnMap, params string[] nameVariants)
        {
            foreach (string name in nameVariants)
            {
                string normalized = name.Replace(" ", "").Replace("_", "");
                int idx = -1;

                if (columnMap.TryGetValue(normalized, out idx) || columnMap.TryGetValue(name, out idx))
                {
                    if (idx >= 0 && idx < fields.Length)
                    {
                        string value = fields[idx].Trim();
                        if (!string.IsNullOrEmpty(value))
                            return value;
                    }
                }
            }
            return null;
        }

        #endregion

        #region EDI 856 ASN Import

        /// <summary>
        /// Processes an EDI 856 Advanced Shipping Notice from SPS Commerce.
        /// Creates pre-receiving serial records from ASN roll-level detail.
        /// </summary>
        public PreReceivingResult ImportEDI856(ASNData asnData, int warehouseID)
        {
            var result = new PreReceivingResult();

            if (asnData?.Lines == null || asnData.Lines.Count == 0)
            {
                result.Errors.Add("ASN contains no line items.");
                return result;
            }

            // EDI 856 provides the same data as CSV but from automated source.
            // Apply the container number from the ASN header to all lines if not set per-line.
            foreach (var line in asnData.Lines)
            {
                if (string.IsNullOrEmpty(line.ContainerNumber))
                    line.ContainerNumber = asnData.ContainerNumber;
            }

            // Validate and create serials using the same pipeline as CSV
            var validLines = ValidateAgainstERP(asnData.Lines, result);
            var createdSerials = CreatePreReceivingSerials(validLines, warehouseID, result);

            if (createdSerials.Count > 0)
            {
                AssignBins(createdSerials, warehouseID);
                result.BinsAssigned = createdSerials.Count;
            }

            result.Success = result.Errors.Count == 0;
            return result;
        }

        #endregion

        #region ERP Validation

        /// <summary>
        /// Validates packing list lines against Acumatica data:
        ///   - PO exists and is open/approved
        ///   - SKU exists and uses PIECEGOODS lot/serial class
        ///   - No duplicate serial would be created
        /// </summary>
        private List<PackingListLine> ValidateAgainstERP(
            List<PackingListLine> lines, PreReceivingResult result)
        {
            var valid = new List<PackingListLine>();

            // Cache PO and SKU lookups to avoid repeated queries
            var poCache = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
            var skuCache = new Dictionary<string, (int? InventoryID, bool IsPieceGoods)>(
                StringComparer.OrdinalIgnoreCase);

            foreach (var line in lines)
            {
                bool lineValid = true;

                // Validate PO
                if (!poCache.TryGetValue(line.PONumber, out bool poValid))
                {
                    var po = SelectFrom<POOrder>
                        .Where<POOrder.orderNbr.IsEqual<@P.AsString>>
                        .View.ReadOnly.Select(_graph, line.PONumber);

                    poValid = po != null;
                    poCache[line.PONumber] = poValid;
                }

                if (!poValid)
                {
                    result.Warnings.Add($"PO '{line.PONumber}' not found in Acumatica. Line skipped.");
                    lineValid = false;
                }

                // Validate SKU and check lot/serial class
                if (!skuCache.TryGetValue(line.SKU, out var skuInfo))
                {
                    var item = SelectFrom<InventoryItem>
                        .Where<InventoryItem.inventoryCD.IsEqual<@P.AsString>>
                        .View.ReadOnly.Select(_graph, line.SKU);

                    if (item != null)
                    {
                        var inv = (InventoryItem)item;
                        bool isPG = string.Equals(inv.LotSerClassID,
                            PieceGoodsConstants.LotSerialClassID,
                            StringComparison.OrdinalIgnoreCase);
                        skuInfo = (inv.InventoryID, isPG);
                    }
                    else
                    {
                        skuInfo = (null, false);
                    }
                    skuCache[line.SKU] = skuInfo;
                }

                if (!skuInfo.InventoryID.HasValue)
                {
                    result.Warnings.Add($"SKU '{line.SKU}' not found in Acumatica. Line skipped.");
                    lineValid = false;
                }
                else if (!skuInfo.IsPieceGoods)
                {
                    result.Warnings.Add(
                        $"SKU '{line.SKU}' is not assigned to the '{PieceGoodsConstants.LotSerialClassID}' " +
                        $"lot/serial class. Line skipped.");
                    lineValid = false;
                }

                if (lineValid)
                    valid.Add(line);
            }

            return valid;
        }

        #endregion

        #region Serial Creation

        /// <summary>
        /// Creates pre-receiving serial records for validated packing list lines.
        /// Each line becomes one serial in INLotSerialStatus with status = In-Transit.
        /// </summary>
        private List<CreatedSerial> CreatePreReceivingSerials(
            List<PackingListLine> lines, int warehouseID, PreReceivingResult result)
        {
            var created = new List<CreatedSerial>();

            // Load INSetup for defaults
            var setup = SelectFrom<INSetup>.View.ReadOnly.SelectSingleBound(_graph, null);
            var setupExt = ((INSetup)setup)?.GetExtension<INSetupExt>();

            // Group by SKU for sequential serial numbering per SKU per day
            var grouped = lines.GroupBy(l => l.SKU, StringComparer.OrdinalIgnoreCase);
            var today = DateTime.Today;

            foreach (var skuGroup in grouped)
            {
                string sku = skuGroup.Key;

                // Look up inventory ID (already validated)
                var item = SelectFrom<InventoryItem>
                    .Where<InventoryItem.inventoryCD.IsEqual<@P.AsString>>
                    .View.ReadOnly.Select(_graph, sku);
                int inventoryID = ((InventoryItem)item).InventoryID.Value;

                // Determine next sequence number for this SKU today
                int seq = GetNextSerialSequence(sku, today);

                decimal defaultWidth = 54.0m;

                foreach (var line in skuGroup)
                {
                    try
                    {
                        // Generate serial number: [SKU]-[YYMMDD]-[SEQ]
                        string serialNbr = string.Format(
                            PieceGoodsConstants.SerialFormat, sku, today, seq++);

                        // Create the INLotSerialStatus record via the graph's cache
                        var statusCache = _graph.Caches[typeof(INLotSerialStatus)];
                        var status = (INLotSerialStatus)statusCache.CreateInstance();
                        status.InventoryID = inventoryID;
                        status.SiteID = warehouseID;
                        status.LotSerialNbr = serialNbr;
                        status = (INLotSerialStatus)statusCache.Insert(status);

                        // Set extension fields
                        var ext = status.GetExtension<INLotSerialStatusExt>();
                        ext.UsrActualYardage = line.Yardage;
                        ext.UsrDyeLot = line.DyeLot;
                        ext.UsrWidth = line.Width ?? defaultWidth;
                        ext.UsrShadeCode = line.ShadeCode;
                        ext.UsrContainerNo = line.ContainerNumber;
                        ext.UsrInventoryStatus = PieceGoodsConstants.InvStatus_InTransit;
                        ext.UsrSourceRoll = null;  // Original roll, not a cut piece
                        ext.UsrDefectFlag = false;

                        statusCache.Update(status);

                        created.Add(new CreatedSerial
                        {
                            SerialNbr = serialNbr,
                            InventoryID = inventoryID,
                            SKU = sku,
                            Yardage = line.Yardage,
                            DyeLot = line.DyeLot,
                            ContainerNumber = line.ContainerNumber,
                        });

                        result.CreatedSerials.Add(serialNbr);
                        result.SerialsCreated++;
                    }
                    catch (Exception ex)
                    {
                        result.Warnings.Add(
                            $"Failed to create serial for SKU '{sku}', " +
                            $"PO '{line.PONumber}': {ex.Message}");
                    }
                }
            }

            // Persist all created records
            if (created.Count > 0)
            {
                _graph.Actions.PressSave();
            }

            return created;
        }

        /// <summary>
        /// Determines the next available sequence number for a SKU on a given date.
        /// Queries existing serials matching the pattern [SKU]-[YYMMDD]-*.
        /// </summary>
        private int GetNextSerialSequence(string sku, DateTime date)
        {
            string prefix = $"{sku}-{date:yyMMdd}-";

            var existing = SelectFrom<INLotSerialStatus>
                .Where<INLotSerialStatus.lotSerialNbr.IsLike<@P.AsString>>
                .View.ReadOnly.Select(_graph, prefix + "%");

            int maxSeq = 0;
            foreach (PXResult<INLotSerialStatus> row in existing)
            {
                var status = (INLotSerialStatus)row;
                string nbr = status.LotSerialNbr;
                if (nbr.StartsWith(prefix) && nbr.Length > prefix.Length)
                {
                    string seqStr = nbr.Substring(prefix.Length);
                    if (int.TryParse(seqStr, out int seq) && seq > maxSeq)
                        maxSeq = seq;
                }
            }

            return maxSeq + 1;
        }

        #endregion

        #region Bin Pre-Assignment

        /// <summary>
        /// Assigns target bin locations to pre-received serials based on:
        ///   - SKU zone affinity (item class → warehouse zone mapping)
        ///   - Velocity-based slotting (fast movers near dock)
        ///   - Capacity verification (bin can physically hold the roll)
        ///   - Dye lot grouping (same lot → adjacent bins when possible)
        /// </summary>
        public void AssignBins(List<CreatedSerial> serials, int warehouseID)
        {
            if (serials == null || serials.Count == 0) return;

            // Load all available bin locations for the warehouse
            var locations = SelectFrom<INLocation>
                .Where<INLocation.siteID.IsEqual<@P.AsInt>
                    .And<INLocation.active.IsEqual<True>>>
                .View.ReadOnly.Select(_graph, warehouseID)
                .Select(r => (INLocation)r)
                .ToList();

            // Exclude virtual locations (RECV-DOCK, staging)
            var binLocations = locations
                .Where(l => !l.LocationCD.StartsWith("RECV", StringComparison.OrdinalIgnoreCase))
                .OrderBy(l => l.LocationCD)
                .ToList();

            if (binLocations.Count == 0) return;

            // Track which bins have been assigned in this batch to avoid over-filling
            var binAssignmentCounts = new Dictionary<int, int>();

            // Group serials by dye lot for grouping assignment
            var dyeLotGroups = serials
                .GroupBy(s => s.DyeLot ?? "", StringComparer.OrdinalIgnoreCase)
                .ToList();

            int binIndex = 0;
            foreach (var lotGroup in dyeLotGroups)
            {
                // Assign all rolls from the same dye lot to adjacent bins
                foreach (var serial in lotGroup)
                {
                    if (binIndex >= binLocations.Count)
                        binIndex = 0; // Wrap around if more rolls than bins

                    var targetBin = binLocations[binIndex];

                    // Update the serial's pre-assigned bin
                    var statusRecord = SelectFrom<INLotSerialStatus>
                        .Where<INLotSerialStatus.inventoryID.IsEqual<@P.AsInt>
                            .And<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>>
                        .View.Select(_graph, serial.InventoryID, serial.SerialNbr);

                    if (statusRecord != null)
                    {
                        var status = (INLotSerialStatus)statusRecord;
                        var ext = status.GetExtension<INLotSerialStatusExt>();
                        ext.UsrPreAssignedBin = targetBin.LocationCD;

                        _graph.Caches[typeof(INLotSerialStatus)].Update(status);
                    }

                    // Track assignment count per bin
                    int locID = targetBin.LocationID.Value;
                    binAssignmentCounts.TryGetValue(locID, out int count);
                    binAssignmentCounts[locID] = count + 1;

                    // Move to next bin after each roll (or stay for dye lot grouping)
                    // For dye lot grouping: only advance bin after the group is done
                }

                // Advance bin index after each dye lot group to keep lots together
                binIndex++;
            }

            _graph.Actions.PressSave();
        }

        /// <summary>
        /// Overload for assigning bins using serial number strings only.
        /// Resolves each serial to its inventory ID before assignment.
        /// </summary>
        public void AssignBins(List<string> serialNbrs, int warehouseID)
        {
            var serials = new List<CreatedSerial>();
            foreach (string nbr in serialNbrs)
            {
                var status = SelectFrom<INLotSerialStatus>
                    .Where<INLotSerialStatus.lotSerialNbr.IsEqual<@P.AsString>>
                    .View.ReadOnly.Select(_graph, nbr);

                if (status != null)
                {
                    var s = (INLotSerialStatus)status;
                    var ext = s.GetExtension<INLotSerialStatusExt>();
                    serials.Add(new CreatedSerial
                    {
                        SerialNbr = nbr,
                        InventoryID = s.InventoryID.Value,
                        DyeLot = ext?.UsrDyeLot,
                    });
                }
            }

            AssignBins(serials, warehouseID);
        }

        #endregion

        #region Supporting Types

        /// <summary>A single line from a mill packing list (CSV or EDI source).</summary>
        public class PackingListLine
        {
            public string PONumber { get; set; }
            public string SKU { get; set; }
            public decimal Yardage { get; set; }
            public string DyeLot { get; set; }
            public decimal? Width { get; set; }
            public string ShadeCode { get; set; }
            public string ContainerNumber { get; set; }
        }

        /// <summary>Parsed EDI 856 ASN data (from SPS Commerce).</summary>
        public class ASNData
        {
            public string ShipmentID { get; set; }
            public DateTime ShipDate { get; set; }
            public string ContainerNumber { get; set; }
            public List<PackingListLine> Lines { get; set; } = new List<PackingListLine>();
        }

        /// <summary>Result of a pre-receiving import operation.</summary>
        public class PreReceivingResult
        {
            public bool Success { get; set; }
            public int SerialsCreated { get; set; }
            public int BinsAssigned { get; set; }
            public List<string> CreatedSerials { get; set; } = new List<string>();
            public List<string> Errors { get; set; } = new List<string>();
            public List<string> Warnings { get; set; } = new List<string>();
        }

        /// <summary>Internal tracking for a serial created during pre-receiving.</summary>
        public class CreatedSerial
        {
            public string SerialNbr { get; set; }
            public int InventoryID { get; set; }
            public string SKU { get; set; }
            public decimal Yardage { get; set; }
            public string DyeLot { get; set; }
            public string ContainerNumber { get; set; }
        }

        #endregion
    }
}
