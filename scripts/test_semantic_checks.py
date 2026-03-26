#!/usr/bin/env python3
"""Tests for semantic_checks.py — DAC field and SQL column parsers."""

import pytest
from semantic_checks import parse_dac_fields, parse_sql_columns, _strip_comments


# ── Fixtures: realistic C# code ──────────────────────────────────────────

INSETUP_EXT = """\
using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.IN;

namespace Aesthetik.WMS
{
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        public static bool IsActive() => true;

        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "1.00")]
        [PXUIField(DisplayName = "Min Remnant Yardage")]
        public decimal? UsrPGMinRemnant { get; set; }
        public abstract class usrPGMinRemnant : BqlDecimal.Field<usrPGMinRemnant> { }

        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Auto-Quantity Mode")]
        public bool? UsrPGAutoQtyMode { get; set; }
        public abstract class usrPGAutoQtyMode : BqlBool.Field<usrPGAutoQtyMode> { }

        [PXDBString(20, IsUnicode = true)]
        [PXDefault("-C{0}")]
        [PXUIField(DisplayName = "Cut Serial Suffix Format")]
        public string UsrPGCutSuffix { get; set; }
        public abstract class usrPGCutSuffix : BqlString.Field<usrPGCutSuffix> { }

        [PXDBInt]
        [PXDefault(5)]
        [PXUIField(DisplayName = "Cross-Dock Age Limit (Days)")]
        public int? UsrPGXDockAge { get; set; }
        public abstract class usrPGXDockAge : BqlInt.Field<usrPGXDockAge> { }

        [PXDBDecimal(4)]
        [PXDefault(TypeCode.Decimal, "0.0200")]
        [PXUIField(DisplayName = "Yardage Variance Threshold (%)")]
        public decimal? UsrPGYardageVar { get; set; }
        public abstract class usrPGYardageVar : BqlDecimal.Field<usrPGYardageVar> { }
    }
}
"""

CUSTOMER_EXT = """\
using PX.Data;
using PX.Data.BQL;
using PX.Objects.AR;

namespace HeritageFabrics.AR
{
    public sealed class CustomerExt : PXCacheExtension<Customer>
    {
        public static bool IsActive() => true;

        public abstract class usrDisablePayLink : BqlBool.Field<usrDisablePayLink> { }

        [PXDBBool]
        [PXDefault(false, PersistingCheck = PXPersistingCheck.Nothing)]
        [PXUIField(DisplayName = "Exclude from Payment Link Processing")]
        public bool? UsrDisablePayLink { get; set; }
    }
}
"""

MULTI_EXT = """\
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace HeritageFabrics.PO
{
    public sealed class POOrderExt : PXCacheExtension<POOrder>
    {
        public static bool IsActive() => true;

        [PXDBDate]
        [PXUIField(DisplayName = "Exp. Arrival Date")]
        public DateTime? UsrExpArrivalDate { get; set; }
    }

    public sealed class POLineExt : PXCacheExtension<POLine>
    {
        public static bool IsActive() => true;

        [PXDBDate]
        [PXUIField(DisplayName = "Exp. Arrival Date")]
        public DateTime? UsrExpArrivalDate { get; set; }

        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Landed Cost Amount")]
        public decimal? UsrLandedCostAmt { get; set; }
    }
}
"""

SQL_IFNOTEXISTS = """\
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGMinRemnant') ALTER TABLE INSetup ADD UsrPGMinRemnant decimal(18,2) NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGAutoQtyMode') ALTER TABLE INSetup ADD UsrPGAutoQtyMode bit NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INLotSerialStatus') AND name = 'UsrDyeLot') ALTER TABLE INLotSerialStatus ADD UsrDyeLot nvarchar(30) NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INLotSerialStatus') AND name = 'UsrWidth') ALTER TABLE INLotSerialStatus ADD UsrWidth decimal(18,1) NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGXDockAge') ALTER TABLE INSetup ADD UsrPGXDockAge int NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('SOOrder') AND name = 'UsrComplianceHold') ALTER TABLE SOOrder ADD UsrComplianceHold bit NULL",
"IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('SOOrder') AND name = 'UsrComplianceHoldReason') ALTER TABLE SOOrder ADD UsrComplianceHoldReason nvarchar(500) NULL",
"""

SQL_BARE = """\
ALTER TABLE POOrder ADD UsrExpArrivalDate datetime NULL;
ALTER TABLE POOrder ADD UsrContainerRef nvarchar(50) NULL;
ALTER TABLE InventoryItem ADD UsrDutyRate decimal(19,4) NULL DEFAULT 0.0000;
ALTER TABLE InventoryItem ADD UsrPreferentialTariff bit NULL DEFAULT 0;
"""


# ── Tests: _strip_comments ───────────────────────────────────────────────

class TestStripComments:
    def test_single_line(self):
        code = "int x = 1; // comment\nint y = 2;"
        assert "// comment" not in _strip_comments(code)
        assert "int x = 1;" in _strip_comments(code)

    def test_multi_line(self):
        code = "int x = 1; /* block\ncomment */ int y = 2;"
        result = _strip_comments(code)
        assert "block" not in result
        assert "int y = 2;" in result

    def test_xml_doc_comments(self):
        code = "/// <summary>This is doc</summary>\npublic int Foo;"
        result = _strip_comments(code)
        assert "summary" not in result
        assert "public int Foo;" in result


# ── Tests: parse_dac_fields ──────────────────────────────────────────────

class TestParseDacFields:
    def test_decimal_field(self):
        fields = parse_dac_fields(INSETUP_EXT)
        remnant = next(f for f in fields if f["name"] == "UsrPGMinRemnant")
        assert remnant["db_type"] == "PXDBDecimal"
        assert remnant["precision"] == 2
        assert remnant["dac"] == "INSetup"
        assert remnant["default_value"] == "1.00"

    def test_bool_field(self):
        fields = parse_dac_fields(INSETUP_EXT)
        auto_qty = next(f for f in fields if f["name"] == "UsrPGAutoQtyMode")
        assert auto_qty["db_type"] == "PXDBBool"
        assert auto_qty["precision"] is None
        assert auto_qty["default_value"] == "true"

    def test_string_field(self):
        fields = parse_dac_fields(INSETUP_EXT)
        suffix = next(f for f in fields if f["name"] == "UsrPGCutSuffix")
        assert suffix["db_type"] == "PXDBString"
        assert suffix["precision"] == 20
        assert suffix["default_value"] == "-C{0}"

    def test_int_field(self):
        fields = parse_dac_fields(INSETUP_EXT)
        age = next(f for f in fields if f["name"] == "UsrPGXDockAge")
        assert age["db_type"] == "PXDBInt"
        assert age["precision"] is None
        assert age["default_value"] == "5"

    def test_decimal_precision_4(self):
        fields = parse_dac_fields(INSETUP_EXT)
        var = next(f for f in fields if f["name"] == "UsrPGYardageVar")
        assert var["db_type"] == "PXDBDecimal"
        assert var["precision"] == 4
        assert var["default_value"] == "0.0200"

    def test_total_field_count(self):
        """INSetupExt has 5 fields in the fixture."""
        fields = parse_dac_fields(INSETUP_EXT)
        assert len(fields) == 5

    def test_bool_false_default(self):
        fields = parse_dac_fields(CUSTOMER_EXT)
        disable = next(f for f in fields if f["name"] == "UsrDisablePayLink")
        assert disable["db_type"] == "PXDBBool"
        assert disable["precision"] is None
        assert disable["dac"] == "Customer"
        assert disable["default_value"] == "false"

    def test_multiple_extensions_correct_dac(self):
        """Each field should be tagged with its own extension's DAC."""
        fields = parse_dac_fields(MULTI_EXT)
        po_fields = [f for f in fields if f["dac"] == "POOrder"]
        pl_fields = [f for f in fields if f["dac"] == "POLine"]
        assert len(po_fields) == 1
        assert po_fields[0]["name"] == "UsrExpArrivalDate"
        assert len(pl_fields) == 2
        assert {f["name"] for f in pl_fields} == {"UsrExpArrivalDate", "UsrLandedCostAmt"}

    def test_date_field_no_precision(self):
        fields = parse_dac_fields(MULTI_EXT)
        date_field = next(
            f for f in fields if f["dac"] == "POOrder" and f["name"] == "UsrExpArrivalDate"
        )
        assert date_field["db_type"] == "PXDBDate"
        assert date_field["precision"] is None
        assert date_field["default_value"] is None

    def test_no_extensions_returns_empty(self):
        code = "public class Foo { public int Bar { get; set; } }"
        assert parse_dac_fields(code) == []

    def test_namespace_stripped_from_dac(self):
        """Fully qualified DAC like PX.Objects.SO.SOShipment → SOShipment."""
        code = """\
public sealed class SOShipmentExt : PXCacheExtension<PX.Objects.SO.SOShipment>
{
    [PXDBBool]
    [PXDefault(false)]
    public bool? UsrCustomFlag { get; set; }
}
"""
        fields = parse_dac_fields(code)
        assert len(fields) == 1
        assert fields[0]["dac"] == "SOShipment"


# ── Tests: parse_sql_columns ────────────────────────────────────────────

class TestParseSqlColumns:
    def test_decimal_with_scale(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        remnant = next(c for c in cols if c["column"] == "UsrPGMinRemnant")
        assert remnant["table"] == "INSetup"
        assert remnant["sql_type"] == "decimal"
        assert remnant["precision"] == 2  # scale, not total digits

    def test_bit_no_precision(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        auto_qty = next(c for c in cols if c["column"] == "UsrPGAutoQtyMode")
        assert auto_qty["sql_type"] == "bit"
        assert auto_qty["precision"] is None

    def test_nvarchar_precision(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        dye = next(c for c in cols if c["column"] == "UsrDyeLot")
        assert dye["table"] == "INLotSerialStatus"
        assert dye["sql_type"] == "nvarchar"
        assert dye["precision"] == 30

    def test_int_no_precision(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        age = next(c for c in cols if c["column"] == "UsrPGXDockAge")
        assert age["sql_type"] == "int"
        assert age["precision"] is None

    def test_decimal_scale_1(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        width = next(c for c in cols if c["column"] == "UsrWidth")
        assert width["sql_type"] == "decimal"
        assert width["precision"] == 1

    def test_nvarchar_500(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        reason = next(c for c in cols if c["column"] == "UsrComplianceHoldReason")
        assert reason["sql_type"] == "nvarchar"
        assert reason["precision"] == 500

    def test_total_count_ifnotexists(self):
        cols = parse_sql_columns(SQL_IFNOTEXISTS)
        assert len(cols) == 7

    def test_bare_alter_table(self):
        cols = parse_sql_columns(SQL_BARE)
        assert len(cols) == 4

    def test_bare_datetime(self):
        cols = parse_sql_columns(SQL_BARE)
        dt = next(c for c in cols if c["column"] == "UsrExpArrivalDate")
        assert dt["table"] == "POOrder"
        assert dt["sql_type"] == "datetime"
        assert dt["precision"] is None

    def test_bare_decimal_scale_4(self):
        cols = parse_sql_columns(SQL_BARE)
        duty = next(c for c in cols if c["column"] == "UsrDutyRate")
        assert duty["table"] == "InventoryItem"
        assert duty["sql_type"] == "decimal"
        assert duty["precision"] == 4  # scale from decimal(19,4)

    def test_bare_nvarchar(self):
        cols = parse_sql_columns(SQL_BARE)
        ref = next(c for c in cols if c["column"] == "UsrContainerRef")
        assert ref["sql_type"] == "nvarchar"
        assert ref["precision"] == 50

    def test_bare_bit(self):
        cols = parse_sql_columns(SQL_BARE)
        tariff = next(c for c in cols if c["column"] == "UsrPreferentialTariff")
        assert tariff["sql_type"] == "bit"
        assert tariff["precision"] is None
