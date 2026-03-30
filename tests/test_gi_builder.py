"""Tests for GI Definition Builder (Phase 2)."""
import sys
import os
import re
import uuid

import pytest

# Add scripts/ to path so we can import gi_builder and gi_schema
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from gi_schema import GISchemaMap
from gi_builder import GIBuilder, GIDefinition


# ---------------------------------------------------------------------------
# Mock schema — mirrors real Acumatica GI tables with enough columns to test
# ---------------------------------------------------------------------------
MOCK_SCHEMA = {
    "GIDesign": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "ScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "NoteID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
    },
    "GITable": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Alias": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 512, "default": None},
        "Type": {"data_type": "int", "nullable": "NO", "max_length": None, "default": "((0))"},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIResult": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Field": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "RowID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIFilter": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIWhere": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GISort": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
}


TEMPLATE_ROW = {
    "CreatedByID": "b5344897-037e-4574-a7e4-c6e42653e643",
}

COMPANY_ID = 2


@pytest.fixture
def schema():
    return GISchemaMap(MOCK_SCHEMA, "24.200.0001")


@pytest.fixture
def builder(schema):
    return GIBuilder(schema, TEMPLATE_ROW, COMPANY_ID)


@pytest.fixture
def simple_spec():
    return GIDefinition(
        name="TestInquiry",
        screen_id="GI000001",
        tables=[{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}],
        results=[{"field": "ScreenID", "caption": "Screen", "width": 120}],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildSimpleGI:
    """test_build_simple_gi — single table, single result."""

    def test_contains_transaction_structure(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "BEGIN TRANSACTION" in sql
        assert "COMMIT TRANSACTION" in sql

    def test_contains_gi_design_insert(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "INSERT INTO GIDesign" in sql

    def test_contains_gi_table_insert(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "INSERT INTO GITable" in sql
        assert "AuditHistory" in sql
        assert "PX.SM.AuditHistory" in sql

    def test_contains_gi_result_insert(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "INSERT INTO GIResult" in sql
        assert "ScreenID" in sql

    def test_company_id_present(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert str(COMPANY_ID) in sql


class TestBuildWithFiltersAndWhere:
    """test_build_with_filters_and_where — GI with filters and where clauses."""

    @pytest.fixture
    def full_spec(self):
        return GIDefinition(
            name="FullInquiry",
            screen_id="GI000002",
            tables=[{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}],
            results=[{"field": "ScreenID", "caption": "Screen", "width": 120}],
            filters=[
                {"name": "ScreenFilter"},
                {"name": "DateFilter"},
            ],
            where=[
                {"field": "AuditHistory.ScreenID"},
            ],
            sort=[
                {"field": "AuditHistory.CreatedDateTime"},
            ],
        )

    def test_filter_inserts(self, builder, full_spec):
        sql = builder.build_sql(full_spec)
        assert "INSERT INTO GIFilter" in sql
        assert "ScreenFilter" in sql
        assert "DateFilter" in sql

    def test_where_inserts(self, builder, full_spec):
        sql = builder.build_sql(full_spec)
        assert "INSERT INTO GIWhere" in sql
        assert "AuditHistory.ScreenID" in sql

    def test_sort_inserts(self, builder, full_spec):
        sql = builder.build_sql(full_spec)
        assert "INSERT INTO GISort" in sql
        assert "AuditHistory.CreatedDateTime" in sql

    def test_sequential_line_numbers(self, builder, full_spec):
        sql = builder.build_sql(full_spec)
        # Two filters should have LineNbr 1 and 2
        filter_inserts = [line for line in sql.splitlines() if "INSERT INTO GIFilter" in line]
        assert len(filter_inserts) == 2
        assert ", 1," in filter_inserts[0]
        assert ", 2," in filter_inserts[1]


class TestIdempotentCheck:
    """test_idempotent_check — SQL contains IF EXISTS check for the GI name."""

    def test_if_exists_present(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "IF EXISTS" in sql
        assert "TestInquiry" in sql

    def test_skip_logic(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "RETURN" in sql
        assert "already exists" in sql


class TestValidationFailsOnMissingAuditColumns:
    """test_validation_fails_on_missing_audit_columns — empty template row raises ValueError."""

    def test_empty_template_raises(self, schema):
        builder = GIBuilder(schema, {}, COMPANY_ID)
        spec = GIDefinition(
            name="BadInquiry",
            screen_id="GI000099",
            tables=[{"dac": "PX.SM.Test", "alias": "Test"}],
            results=[{"field": "ID"}],
        )
        with pytest.raises(ValueError, match="Template row missing required audit columns"):
            builder.build_sql(spec)


class TestReviewMarkerPresent:
    """test_review_marker_present — SQL contains the review marker."""

    def test_marker_at_top(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "-- REVIEWED: gi-sql-safe" in sql
        # Should be within the first few lines
        first_line = sql.splitlines()[0]
        assert "REVIEWED" in first_line


class TestPostFlightVerification:
    """test_post_flight_verification — SQL contains SELECT COUNT verification."""

    def test_count_checks_present(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "SELECT COUNT(*)" in sql
        assert "Post-flight check failed" in sql

    def test_checks_cover_all_tables(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        # Simple spec uses GIDesign, GITable, GIResult
        for table in ["GIDesign", "GITable", "GIResult"]:
            assert f"SELECT COUNT(*) FROM {table}" in sql

    def test_rollback_in_catch(self, builder, simple_spec):
        sql = builder.build_sql(simple_spec)
        assert "ROLLBACK TRANSACTION" in sql
        assert "BEGIN CATCH" in sql


class TestSQLEscaping:
    """Verify SQL value escaping handles edge cases."""

    def test_single_quote_in_name(self, builder):
        spec = GIDefinition(
            name="Kevin's Inquiry",
            screen_id="GI000001",
            tables=[{"dac": "PX.SM.Test", "alias": "Test"}],
            results=[{"field": "ID"}],
        )
        sql = builder.build_sql(spec)
        # Single quote should be doubled in the INSERT
        assert "Kevin''s Inquiry" in sql
