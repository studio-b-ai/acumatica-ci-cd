"""Tests for GI Schema Discovery module."""
import json
import textwrap
from pathlib import Path

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from gi_schema import (
    GI_TABLES,
    GISchemaMap,
    generate_discovery_sql,
    parse_information_schema_output,
)

SAMPLE_LOG = textwrap.dedent("""\
    [SCHEMA] Table: GIDesign
      DesignID: uniqueidentifier(n/a) nullable=NO default=NULL
      Name: nvarchar(256) nullable=NO default=NULL
      CompanyID: int(n/a) nullable=NO default=((0))
      NoteID: uniqueidentifier(n/a) nullable=YES default=NULL
      CreatedByID: uniqueidentifier(n/a) nullable=NO default=NULL
    [SCHEMA] Table: GIResult
      DesignID: uniqueidentifier(n/a) nullable=NO default=NULL
      LineNbr: int(n/a) nullable=NO default=NULL
      ObjectName: nvarchar(512) nullable=YES default=NULL
      Field: nvarchar(512) nullable=YES default=NULL
      IsActive: bit(n/a) nullable=NO default=((1))
""")


def test_parse_schema_output():
    tables = parse_information_schema_output(SAMPLE_LOG)
    assert "GIDesign" in tables
    assert "GIResult" in tables
    assert len(tables) == 2

    design = tables["GIDesign"]
    assert "DesignID" in design
    assert design["DesignID"]["data_type"] == "uniqueidentifier"
    assert design["DesignID"]["max_length"] is None
    assert design["DesignID"]["nullable"] == "NO"
    assert design["DesignID"]["default"] is None

    assert design["Name"]["data_type"] == "nvarchar"
    assert design["Name"]["max_length"] == 256

    assert design["CompanyID"]["default"] == "((0))"

    result = tables["GIResult"]
    assert result["ObjectName"]["nullable"] == "YES"
    assert result["IsActive"]["default"] == "((1))"


def test_not_null_columns():
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    not_null = schema.not_null_columns("GIDesign")
    assert "DesignID" in not_null
    assert "Name" in not_null
    assert "CompanyID" in not_null
    assert "CreatedByID" in not_null
    assert "NoteID" not in not_null


def test_columns_with_defaults():
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    with_defaults = schema.columns_with_defaults("GIDesign")
    assert "CompanyID" in with_defaults
    assert "DesignID" not in with_defaults  # NOT NULL but no default
    assert "NoteID" not in with_defaults  # nullable, not NOT NULL


def test_validate_row_valid():
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    row = {
        "DesignID": "abc-123",
        "Name": "MyGI",
        "CompanyID": 2,
        "CreatedByID": "user-1",
    }
    errors = schema.validate_row("GIDesign", row)
    assert errors == []


def test_validate_row_missing_required():
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    row = {"DesignID": "abc-123"}  # missing Name, CreatedByID
    errors = schema.validate_row("GIDesign", row)
    assert len(errors) == 2
    assert any("Name" in e for e in errors)
    assert any("CreatedByID" in e for e in errors)


def test_validate_row_missing_with_default_ok():
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    # CompanyID is NOT NULL but has default ((0)), so omitting it is fine
    row = {
        "DesignID": "abc-123",
        "Name": "MyGI",
        "CreatedByID": "user-1",
    }
    errors = schema.validate_row("GIDesign", row)
    assert errors == []


def test_save_and_load(tmp_path):
    tables = parse_information_schema_output(SAMPLE_LOG)
    schema = GISchemaMap(tables, "24.200.0001")

    filepath = tmp_path / "gi_schema.json"
    schema.save(filepath)

    loaded = GISchemaMap.load(filepath)
    assert loaded.acumatica_version == "24.200.0001"
    assert loaded.tables == schema.tables
    assert loaded.not_null_columns("GIDesign") == schema.not_null_columns("GIDesign")


def test_generate_discovery_sql():
    sql = generate_discovery_sql()
    for table in GI_TABLES:
        assert f'[SCHEMA] Table: {table}' in sql
        assert f"TABLE_NAME = '{table}'" in sql
    assert "INFORMATION_SCHEMA.COLUMNS" in sql
    assert "WriteLog" in sql
