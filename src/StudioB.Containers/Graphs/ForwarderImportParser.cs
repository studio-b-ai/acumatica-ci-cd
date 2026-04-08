using System;
using System.Collections.Generic;
using System.IO;

namespace StudioB.Containers
{
    /// <summary>
    /// Pure-logic CSV parser for forwarder status updates. Accepts the standard
    /// 5-column layout forwarders export (Flexport, Expeditors, CHR, etc. —
    /// exported via "Download as Excel" then saved as CSV).
    ///
    /// Column layout (header row required):
    /// ContainerNumber, NewETA, NewStatus, EventDate, EventDescription
    ///
    /// - ContainerNumber: matches UsrContainer.ContainerCD exactly
    /// - NewETA: date (yyyy-MM-dd, M/d/yyyy, or ISO)
    /// - NewStatus: optional — one of BOOKED/DEPARTED/IN_TRANSIT/ARRIVED/
    ///              DISCHARGED/CUSTOMS_HOLD/GATED_OUT/DELIVERED
    /// - EventDate: optional — date/time of the new event
    /// - EventDescription: optional — free text
    /// </summary>
    public static class ForwarderImportParser
    {
        public struct ParsedRow
        {
            public int LineNumber;          // 1-based source row number
            public string ContainerNumber;
            public DateTime? NewETA;
            public string NewStatus;
            public DateTime? EventDate;
            public string EventDescription;
            public string RawLine;
            public string ParseError;       // non-null if the row failed to parse
        }

        public struct ParseResult
        {
            public List<ParsedRow> Rows;
            public List<string> Errors;     // file-level errors (bad header, empty file)
        }

        private static readonly string[] ExpectedHeaders = new[]
        {
            "ContainerNumber", "NewETA", "NewStatus", "EventDate", "EventDescription"
        };

        public static ParseResult Parse(string csvText)
        {
            var result = new ParseResult
            {
                Rows = new List<ParsedRow>(),
                Errors = new List<string>()
            };

            if (string.IsNullOrWhiteSpace(csvText))
            {
                result.Errors.Add("File is empty.");
                return result;
            }

            // Normalize line endings and split
            string normalized = csvText.Replace("\r\n", "\n").Replace("\r", "\n");
            string[] lines = normalized.Split('\n');

            if (lines.Length < 2)
            {
                result.Errors.Add("File has no data rows (expecting at least a header + one row).");
                return result;
            }

            // Parse + validate header
            string[] header = SplitCsvLine(lines[0]);
            if (header.Length < ExpectedHeaders.Length)
            {
                result.Errors.Add(string.Format(
                    "Header has {0} columns, expected at least {1}: {2}",
                    header.Length, ExpectedHeaders.Length, string.Join(", ", ExpectedHeaders)));
                return result;
            }

            // Parse data rows
            for (int i = 1; i < lines.Length; i++)
            {
                string line = lines[i];
                if (string.IsNullOrWhiteSpace(line)) continue;

                var row = new ParsedRow { LineNumber = i + 1, RawLine = line };
                string[] fields = SplitCsvLine(line);

                if (fields.Length < 1 || string.IsNullOrWhiteSpace(fields[0]))
                {
                    row.ParseError = "Missing container number";
                    result.Rows.Add(row);
                    continue;
                }

                row.ContainerNumber = fields[0].Trim();

                if (fields.Length > 1 && !string.IsNullOrWhiteSpace(fields[1]))
                {
                    if (TryParseDate(fields[1], out DateTime eta))
                        row.NewETA = eta;
                    else
                        row.ParseError = AppendErr(row.ParseError, "Unrecognized ETA date '" + fields[1] + "'");
                }

                if (fields.Length > 2 && !string.IsNullOrWhiteSpace(fields[2]))
                    row.NewStatus = fields[2].Trim().ToUpperInvariant();

                if (fields.Length > 3 && !string.IsNullOrWhiteSpace(fields[3]))
                {
                    if (TryParseDate(fields[3], out DateTime evt))
                        row.EventDate = evt;
                    else
                        row.ParseError = AppendErr(row.ParseError, "Unrecognized event date '" + fields[3] + "'");
                }

                if (fields.Length > 4)
                    row.EventDescription = fields[4].Trim();

                result.Rows.Add(row);
            }

            // If we parsed a valid header but no data rows, surface that as a
            // file-level error rather than returning silently-empty rows.
            if (result.Rows.Count == 0 && result.Errors.Count == 0)
            {
                result.Errors.Add("File has no data rows after the header.");
            }

            return result;
        }

        /// <summary>
        /// Parses a CSV line handling simple quoting. Does NOT handle embedded
        /// newlines inside quoted fields — sufficient for forwarder exports.
        /// </summary>
        public static string[] SplitCsvLine(string line)
        {
            if (string.IsNullOrEmpty(line)) return new string[0];

            var result = new List<string>();
            var current = new System.Text.StringBuilder();
            bool inQuotes = false;

            for (int i = 0; i < line.Length; i++)
            {
                char ch = line[i];
                if (inQuotes)
                {
                    if (ch == '"')
                    {
                        // Escaped quote ("")
                        if (i + 1 < line.Length && line[i + 1] == '"')
                        {
                            current.Append('"');
                            i++;
                        }
                        else
                        {
                            inQuotes = false;
                        }
                    }
                    else
                    {
                        current.Append(ch);
                    }
                }
                else
                {
                    if (ch == ',')
                    {
                        result.Add(current.ToString());
                        current.Clear();
                    }
                    else if (ch == '"' && current.Length == 0)
                    {
                        inQuotes = true;
                    }
                    else
                    {
                        current.Append(ch);
                    }
                }
            }
            result.Add(current.ToString());
            return result.ToArray();
        }

        private static bool TryParseDate(string s, out DateTime dt)
        {
            s = s.Trim();
            // Try the common formats seen in forwarder exports
            string[] formats = new[]
            {
                "yyyy-MM-dd",
                "yyyy-MM-ddTHH:mm:ss",
                "yyyy-MM-dd HH:mm:ss",
                "M/d/yyyy",
                "M/d/yyyy h:mm tt",
                "M/d/yyyy H:mm",
                "MM/dd/yyyy",
                "d-MMM-yyyy",
                "d-MMM-yy",
            };
            if (DateTime.TryParseExact(s, formats, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeLocal, out dt))
                return true;
            if (DateTime.TryParse(s, System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeLocal, out dt))
                return true;
            return false;
        }

        private static string AppendErr(string existing, string next)
        {
            return string.IsNullOrEmpty(existing) ? next : existing + "; " + next;
        }
    }
}
