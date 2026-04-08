using System;
using System.Linq;
using StudioB.Containers;
using Xunit;

namespace StudioB.Containers.Tests
{
    public class ForwarderImportParserTests
    {
        // ---------------------------------------------------------------
        // SplitCsvLine — quoted field handling
        // ---------------------------------------------------------------

        [Fact]
        public void SplitCsvLine_Simple_Comma_Separated()
        {
            var f = ForwarderImportParser.SplitCsvLine("a,b,c");
            Assert.Equal(new[] { "a", "b", "c" }, f);
        }

        [Fact]
        public void SplitCsvLine_Handles_Quoted_Field_With_Comma()
        {
            var f = ForwarderImportParser.SplitCsvLine("MSCU1234567,2026-04-15,IN_TRANSIT,2026-04-10,\"In transit, Hamburg → LA\"");
            Assert.Equal(5, f.Length);
            Assert.Equal("In transit, Hamburg → LA", f[4]);
        }

        [Fact]
        public void SplitCsvLine_Handles_Escaped_Quote()
        {
            var f = ForwarderImportParser.SplitCsvLine("\"a\"\"b\",c");
            Assert.Equal(new[] { "a\"b", "c" }, f);
        }

        [Fact]
        public void SplitCsvLine_Empty_String_Returns_Empty_Array()
        {
            var f = ForwarderImportParser.SplitCsvLine("");
            Assert.Empty(f);
        }

        [Fact]
        public void SplitCsvLine_Handles_Trailing_Empty_Field()
        {
            var f = ForwarderImportParser.SplitCsvLine("a,b,");
            Assert.Equal(new[] { "a", "b", "" }, f);
        }

        // ---------------------------------------------------------------
        // Parse — file-level errors
        // ---------------------------------------------------------------

        [Fact]
        public void Parse_Empty_File_Returns_Error()
        {
            var r = ForwarderImportParser.Parse("");
            Assert.Empty(r.Rows);
            Assert.Single(r.Errors);
            Assert.Contains("empty", r.Errors[0], StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void Parse_Whitespace_Only_Returns_Error()
        {
            var r = ForwarderImportParser.Parse("   \n\t  ");
            Assert.Empty(r.Rows);
            Assert.Single(r.Errors);
        }

        [Fact]
        public void Parse_Header_Only_Returns_No_Data_Error()
        {
            var r = ForwarderImportParser.Parse("ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n");
            Assert.Single(r.Errors);
            Assert.Contains("no data", r.Errors[0], StringComparison.OrdinalIgnoreCase);
        }

        [Fact]
        public void Parse_Header_Too_Few_Columns_Returns_Error()
        {
            var r = ForwarderImportParser.Parse("ContainerNumber,NewETA\nABC,2026-04-15");
            Assert.NotEmpty(r.Errors);
        }

        // ---------------------------------------------------------------
        // Parse — happy path
        // ---------------------------------------------------------------

        [Fact]
        public void Parse_One_Row_Full_Fields()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "MSCU1234567,2026-04-15,IN_TRANSIT,2026-04-10,Vessel departed";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Empty(r.Errors);
            Assert.Single(r.Rows);
            var row = r.Rows[0];
            Assert.Equal("MSCU1234567", row.ContainerNumber);
            Assert.Equal(new DateTime(2026, 4, 15), row.NewETA);
            Assert.Equal("IN_TRANSIT", row.NewStatus);
            Assert.Equal(new DateTime(2026, 4, 10), row.EventDate);
            Assert.Equal("Vessel departed", row.EventDescription);
            Assert.Null(row.ParseError);
        }

        [Fact]
        public void Parse_Multiple_Rows()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,2026-04-15,IN_TRANSIT,,\n" +
                      "B,2026-04-20,ARRIVED,,\n" +
                      "C,,,,";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Empty(r.Errors);
            Assert.Equal(3, r.Rows.Count);
            Assert.Equal("A", r.Rows[0].ContainerNumber);
            Assert.Equal("B", r.Rows[1].ContainerNumber);
            Assert.Equal("C", r.Rows[2].ContainerNumber);
        }

        [Fact]
        public void Parse_Status_Is_Uppercased()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,,in_transit,,";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Equal("IN_TRANSIT", r.Rows[0].NewStatus);
        }

        [Fact]
        public void Parse_Various_Date_Formats()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,2026-04-15,,,\n" +
                      "B,4/15/2026,,,\n" +
                      "C,15-Apr-2026,,,\n" +
                      "D,04/15/2026,,,";
            var r = ForwarderImportParser.Parse(csv);
            foreach (var row in r.Rows)
            {
                Assert.Null(row.ParseError);
                Assert.Equal(new DateTime(2026, 4, 15), row.NewETA);
            }
        }

        [Fact]
        public void Parse_Row_With_Bad_Date_Has_ParseError_But_Is_Not_Dropped()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,not-a-date,IN_TRANSIT,,";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Single(r.Rows);
            Assert.Contains("Unrecognized ETA date", r.Rows[0].ParseError);
            Assert.Equal("A", r.Rows[0].ContainerNumber);  // Still parsed the container number
            Assert.Equal("IN_TRANSIT", r.Rows[0].NewStatus); // Still parsed other valid fields
        }

        [Fact]
        public void Parse_Row_With_Missing_Container_Has_ParseError()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      ",2026-04-15,IN_TRANSIT,,";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Single(r.Rows);
            Assert.Contains("Missing container number", r.Rows[0].ParseError);
        }

        [Fact]
        public void Parse_Skips_Blank_Lines()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,2026-04-15,,,\n" +
                      "\n" +
                      "   \n" +
                      "B,2026-04-20,,,";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Equal(2, r.Rows.Count);
            Assert.Equal("A", r.Rows[0].ContainerNumber);
            Assert.Equal("B", r.Rows[1].ContainerNumber);
        }

        [Fact]
        public void Parse_Handles_Windows_Line_Endings()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\r\n" +
                      "A,2026-04-15,,,\r\n" +
                      "B,2026-04-20,,,\r\n";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Equal(2, r.Rows.Count);
        }

        [Fact]
        public void Parse_Handles_Quoted_Description_With_Comma()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,2026-04-15,IN_TRANSIT,2026-04-10,\"In transit, Hamburg\"";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Single(r.Rows);
            Assert.Equal("In transit, Hamburg", r.Rows[0].EventDescription);
        }

        [Fact]
        public void Parse_Preserves_Line_Numbers_For_Error_Reporting()
        {
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription\n" +
                      "A,2026-04-15,,,\n" +
                      ",2026-04-20,,,\n" +  // line 3 — missing container
                      "C,2026-04-25,,,";
            var r = ForwarderImportParser.Parse(csv);
            var badRow = r.Rows.First(x => x.ParseError != null);
            Assert.Equal(3, badRow.LineNumber);
        }

        [Fact]
        public void Parse_Allows_Rows_With_More_Columns_Than_Expected()
        {
            // Extra columns beyond EventDescription should not cause parse failure
            var csv = "ContainerNumber,NewETA,NewStatus,EventDate,EventDescription,Extra\n" +
                      "A,2026-04-15,IN_TRANSIT,2026-04-10,Arrived,Something extra";
            var r = ForwarderImportParser.Parse(csv);
            Assert.Empty(r.Errors);
            Assert.Single(r.Rows);
            Assert.Null(r.Rows[0].ParseError);
        }
    }
}
