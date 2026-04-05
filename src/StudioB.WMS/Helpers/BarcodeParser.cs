using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace Aesthetik.WMS
{
    /// <summary>
    /// Parser for GS1-128 compound barcodes used on piece goods roll labels.
    ///
    /// Decodes Application Identifiers (AIs) from the barcode data:
    ///   AI 01 (GTIN/SKU): Item inventory ID
    ///   AI 21 (Serial):   Unique roll serial number
    ///   AI 10 (Lot):      Dye lot identifier
    ///
    /// Supports two input formats:
    ///   1. FNC1-delimited (scanner output): data fields separated by GS character (0x1D)
    ///   2. Human-readable (parenthesized): (01)FAB-1024(21)260301-001(10)DL-2026-0412
    ///
    /// Keyence scanners are pre-configured to parse GS1-128 AIs natively and output
    /// decoded fields. This parser handles both raw and Keyence-decoded formats.
    /// </summary>
    public static class BarcodeParser
    {
        /// <summary>
        /// Attempts to parse a GS1-128 compound barcode string.
        /// Returns true if at least one AI was successfully decoded.
        /// </summary>
        /// <param name="barcodeData">Raw barcode data from scanner.</param>
        /// <param name="result">Parsed barcode fields.</param>
        /// <returns>True if parsing succeeded.</returns>
        public static bool TryParseGS1128(string barcodeData, out GS1128Result result)
        {
            result = new GS1128Result();

            if (string.IsNullOrWhiteSpace(barcodeData))
                return false;

            // Determine format and parse
            Dictionary<string, string> ais;

            if (barcodeData.Contains(PieceGoodsConstants.GS1_AI_Start.ToString()))
            {
                // Human-readable format: (01)FAB-1024(21)260301-001(10)DL-2026-0412
                ais = ParseHumanReadable(barcodeData);
            }
            else if (barcodeData.Contains(PieceGoodsConstants.GS1_FNC1.ToString()))
            {
                // FNC1-delimited format from scanner
                ais = ParseFNC1Delimited(barcodeData);
            }
            else
            {
                // Attempt to match as a simple serial number (no AI encoding)
                // This handles cases where the Keyence scanner pre-strips AIs
                result.RawSerial = barcodeData.Trim();
                return true;
            }

            if (ais == null || ais.Count == 0)
            {
                // Fallback: treat entire string as a serial
                result.RawSerial = barcodeData.Trim();
                return true;
            }

            // Map AIs to result fields
            if (ais.TryGetValue(PieceGoodsConstants.AI_GTIN, out var gtin))
                result.SKU = gtin;

            if (ais.TryGetValue(PieceGoodsConstants.AI_Serial, out var serial))
                result.SerialNumber = serial;

            if (ais.TryGetValue(PieceGoodsConstants.AI_Lot, out var lot))
                result.DyeLot = lot;

            result.HasSKU    = !string.IsNullOrEmpty(result.SKU);
            result.HasSerial = !string.IsNullOrEmpty(result.SerialNumber);
            result.HasDyeLot = !string.IsNullOrEmpty(result.DyeLot);

            return result.HasSKU || result.HasSerial;
        }

        /// <summary>
        /// Parses human-readable GS1-128 format: (AI)value(AI)value...
        /// </summary>
        private static Dictionary<string, string> ParseHumanReadable(string data)
        {
            var result = new Dictionary<string, string>(StringComparer.Ordinal);

            // Regex: capture (nn) followed by value until next ( or end
            var matches = Regex.Matches(data, @"\((\d{2,4})\)([^(]*)");

            foreach (Match match in matches)
            {
                if (match.Groups.Count >= 3)
                {
                    string ai = match.Groups[1].Value;
                    string value = match.Groups[2].Value.TrimEnd();
                    result[ai] = value;
                }
            }

            return result;
        }

        /// <summary>
        /// Parses FNC1-delimited GS1-128 format from scanner output.
        /// Fields are separated by GS (Group Separator, 0x1D) character.
        /// Each field starts with a 2-4 digit AI prefix.
        /// </summary>
        private static Dictionary<string, string> ParseFNC1Delimited(string data)
        {
            var result = new Dictionary<string, string>(StringComparer.Ordinal);

            // Split on FNC1 separator
            string[] segments = data.Split(PieceGoodsConstants.GS1_FNC1);

            foreach (string segment in segments)
            {
                if (string.IsNullOrWhiteSpace(segment)) continue;

                // Known fixed-length AIs
                // AI 01 (GTIN): 14 digits fixed (but we use variable-length SKUs)
                // AI 10 (Lot): variable length
                // AI 21 (Serial): variable length

                // Try 2-digit AI prefix first
                if (segment.Length >= 3)
                {
                    string ai2 = segment.Substring(0, 2);
                    if (IsKnownAI(ai2))
                    {
                        result[ai2] = segment.Substring(2);
                        continue;
                    }
                }

                // Try 4-digit AI prefix (less common for our use case)
                if (segment.Length >= 5)
                {
                    string ai4 = segment.Substring(0, 4);
                    if (IsKnownAI(ai4))
                    {
                        result[ai4] = segment.Substring(4);
                        continue;
                    }
                }
            }

            return result;
        }

        /// <summary>
        /// Checks if the given string is a known GS1 Application Identifier.
        /// </summary>
        private static bool IsKnownAI(string ai)
        {
            return ai == PieceGoodsConstants.AI_GTIN   // 01
                || ai == PieceGoodsConstants.AI_Serial  // 21
                || ai == PieceGoodsConstants.AI_Lot;    // 10
        }

        /// <summary>
        /// Generates a GS1-128 human-readable barcode string for label printing.
        /// </summary>
        /// <param name="sku">Item inventory ID.</param>
        /// <param name="serialNumber">Roll serial number.</param>
        /// <param name="dyeLot">Dye lot identifier (optional).</param>
        /// <returns>Formatted barcode string: (01)SKU(21)Serial(10)Lot</returns>
        public static string GenerateGS1128Label(string sku, string serialNumber, string dyeLot = null)
        {
            var label = $"(01){sku}(21){serialNumber}";

            if (!string.IsNullOrEmpty(dyeLot))
                label += $"(10){dyeLot}";

            return label;
        }

        /// <summary>
        /// Generates FNC1-delimited barcode data for Keyence printer input.
        /// </summary>
        public static string GenerateGS1128Raw(string sku, string serialNumber, string dyeLot = null)
        {
            var fnc1 = PieceGoodsConstants.GS1_FNC1;
            var data = $"01{sku}{fnc1}21{serialNumber}";

            if (!string.IsNullOrEmpty(dyeLot))
                data += $"{fnc1}10{dyeLot}";

            return data;
        }
    }

    /// <summary>
    /// Result of parsing a GS1-128 compound barcode.
    /// </summary>
    public class GS1128Result
    {
        /// <summary>Item inventory ID (from AI 01).</summary>
        public string SKU { get; set; }

        /// <summary>Roll serial number (from AI 21).</summary>
        public string SerialNumber { get; set; }

        /// <summary>Dye lot identifier (from AI 10).</summary>
        public string DyeLot { get; set; }

        /// <summary>Raw serial string if no AI encoding was detected.</summary>
        public string RawSerial { get; set; }

        public bool HasSKU { get; set; }
        public bool HasSerial { get; set; }
        public bool HasDyeLot { get; set; }

        /// <summary>
        /// Returns the most useful serial identifier:
        /// AI-decoded serial if available, otherwise the raw string.
        /// </summary>
        public string EffectiveSerial => SerialNumber ?? RawSerial;
    }
}
