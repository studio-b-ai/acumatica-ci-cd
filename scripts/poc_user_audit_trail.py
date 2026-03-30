"""POC: Generate UserAuditTrail GI SQL using the GI Builder Engine.

This script generates the transactional SQL that creates the UserAuditTrail
Generic Inquiry. The SQL is designed to run inside a CustomizationPlugin's
UpdateDatabase() method.

Usage:
    python scripts/poc_user_audit_trail.py [--schema-file data/gi-schema.json] [--output data/user-audit-trail.sql]

If no schema file is provided, uses a mock schema based on known GI table structures.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gi_builder import GIDefinition, GIBuilder
from gi_schema import GISchemaMap


# Mock schema based on known GI table structures from the 2026-03-29 investigation.
# This will be replaced with real INFORMATION_SCHEMA data once schema discovery runs.
MOCK_SCHEMA = {
    "GIDesign": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "ScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "FilterColCount": {"data_type": "int", "nullable": "YES", "max_length": None, "default": "((3))"},
        "PageSize": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "ExportTop": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "ExposeViaOData": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "NoteID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "CreatedDateTime": {"data_type": "datetime", "nullable": "YES", "max_length": None, "default": None},
        "LastModifiedByID": {"data_type": "uniqueidentifier", "nullable": "YES", "max_length": None, "default": None},
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
        "SortOrder": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "Width": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "IsVisible": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "DefaultNav": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "Caption": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "RowID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIFilter": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "DisplayName": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "DataType": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIWhere": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "Condition": {"data_type": "nvarchar", "nullable": "YES", "max_length": 2, "default": None},
        "Value1": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "Operation": {"data_type": "nvarchar", "nullable": "YES", "max_length": 1, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GISort": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "SortOrder": {"data_type": "nvarchar", "nullable": "YES", "max_length": 1, "default": None},
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
}

# Template audit column values — these would come from a real existing GI
# in production. For the POC, use placeholder values.
TEMPLATE_ROW = {
    "CreatedByID": "B5344897-037E-4D58-B5C3-1BDFD0F47BF4",  # admin user GUID
    "CreatedByScreenID": "SM208000",
    # NoteID intentionally omitted — auto-generated as UUID per row by GIBuilder
}


def build_user_audit_trail_spec() -> GIDefinition:
    return GIDefinition(
        name="UserAuditTrail",
        screen_id="GI000099",
        tables=[
            {"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"},
        ],
        results=[
            {"field": "ScreenID", "caption": "Screen ID", "width": 120},
            {"field": "Operation", "caption": "Operation", "width": 100},
            {"field": "ChangeDate", "caption": "Change Date", "width": 150},
            {"field": "TableName", "caption": "Table", "width": 150},
            {"field": "BatchID", "caption": "Batch ID", "width": 80},
            {"field": "ChangeID", "caption": "Change ID", "width": 80},
            {"field": "CombinedKey", "caption": "Combined Key", "width": 200},
            {"field": "ModifiedFields", "caption": "Modified Fields", "width": 300},
            {"field": "UserID", "caption": "User", "width": 120},
        ],
        filters=[
            {"name": "ScreenFilter", "display_name": "Screen ID", "data_type": 6},
            {"name": "FromDate", "display_name": "From Date", "data_type": 5},
            {"name": "ToDate", "display_name": "To Date", "data_type": 5},
        ],
        where=[
            {"field": "AuditHistory.ScreenID", "condition": "E ", "value": "@ScreenFilter", "operation": "A"},
            {"field": "AuditHistory.ChangeDate", "condition": "GE", "value": "@FromDate", "operation": "A"},
            {"field": "AuditHistory.ChangeDate", "condition": "LE", "value": "@ToDate", "operation": "A"},
        ],
        sort=[
            {"field": "AuditHistory.ChangeDate", "order": "D"},
        ],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate UserAuditTrail GI SQL")
    parser.add_argument("--schema-file", help="Path to cached schema JSON (from Phase 1)")
    parser.add_argument("--output", default="data/user-audit-trail.sql", help="Output SQL file")
    parser.add_argument("--company-id", type=int, default=2, help="Acumatica CompanyID")
    args = parser.parse_args()

    if args.schema_file:
        schema = GISchemaMap.load(Path(args.schema_file))
    else:
        schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")

    spec = build_user_audit_trail_spec()
    builder = GIBuilder(schema, template_row=TEMPLATE_ROW, company_id=args.company_id)
    sql = builder.build_sql(spec)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql)
    print(f"Generated {len(sql)} bytes of SQL to {output_path}")
    print(f"GI: {spec.name} ({len(spec.tables)} tables, {len(spec.results)} results, "
          f"{len(spec.filters)} filters, {len(spec.where)} conditions, {len(spec.sort)} sorts)")
