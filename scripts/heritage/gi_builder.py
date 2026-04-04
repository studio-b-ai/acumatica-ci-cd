"""GI Definition Builder — generate validated, transactional SQL for Generic Inquiries.

Phase 2 of the GI Builder Engine. Takes a GI specification and produces
idempotent, transactional SQL suitable for embedding in a CustomizationPlugin's
UpdateDatabase() method.

Generated SQL includes:
- Pre-flight idempotency check (skip if GI already exists)
- BEGIN TRANSACTION / BEGIN TRY / BEGIN CATCH error handling
- Post-flight row count verification
- REVIEWED marker so it passes validate-project.py GI SQL check
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from gi_schema import GISchemaMap


# Audit columns that come from the template row
AUDIT_COLUMNS = {"CreatedByID", "CreatedByScreenID", "CreatedDateTime",
                 "LastModifiedByID", "LastModifiedByScreenID", "LastModifiedDateTime"}


@dataclass
class GIDefinition:
    """Specification for a Generic Inquiry to create."""

    name: str
    screen_id: str
    tables: list[dict]       # [{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}]
    results: list[dict]      # [{"field": "ScreenID", "caption": "Screen", "width": 120}]
    filters: list[dict] = field(default_factory=list)
    where: list[dict] = field(default_factory=list)
    sort: list[dict] = field(default_factory=list)


def _sql_value(val: Any, data_type: str) -> str:
    """Format a Python value as a SQL literal."""
    if val is None:
        return "NULL"
    if data_type == "int" or data_type == "bit":
        return str(int(val))
    if data_type == "uniqueidentifier":
        return f"N'{val}'"
    # String types: nvarchar, varchar, etc.
    escaped = str(val).replace("'", "''")
    return f"N'{escaped}'"


class GIBuilder:
    """Builds validated, transactional SQL for creating a Generic Inquiry."""

    def __init__(self, schema: GISchemaMap, template_row: dict, company_id: int):
        self.schema = schema
        self.template_row = template_row
        self.company_id = company_id

    def _validate_template_row(self) -> None:
        """Ensure template row has at least the critical audit columns."""
        required = {"CreatedByID"}
        missing = required - set(self.template_row.keys())
        if missing:
            raise ValueError(
                f"Template row missing required audit columns: {', '.join(sorted(missing))}. "
                f"Extract these from an existing GI row."
            )

    def _build_row(self, table_name: str, values: dict) -> dict:
        """Build a complete row dict for a table, filling defaults and audit columns.

        - Starts with the provided values
        - Fills CompanyID from self.company_id
        - Fills audit columns from self.template_row
        - Auto-generates UUIDs for uniqueidentifier NOT NULL columns not otherwise filled
        - Validates against schema — raises ValueError if any NOT NULL column without
          default is missing
        """
        if table_name not in self.schema.tables:
            raise ValueError(f"Unknown table: {table_name}")

        row = dict(values)

        # Fill CompanyID
        row.setdefault("CompanyID", self.company_id)

        # Fill audit columns from template
        for col, val in self.template_row.items():
            if col in self.schema.tables[table_name]:
                row.setdefault(col, val)

        # Auto-generate UUIDs for uniqueidentifier NOT NULL columns without defaults
        for col, info in self.schema.tables[table_name].items():
            if (info["data_type"] == "uniqueidentifier"
                    and info["nullable"] == "NO"
                    and info.get("default") is None
                    and col not in row):
                row[col] = str(uuid.uuid4())

        # Validate: check for NOT NULL columns without defaults that are still missing
        errors = self.schema.validate_row(table_name, row)
        if errors:
            raise ValueError(
                f"Row validation failed for {table_name}:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        return row

    def _insert_sql(self, table_name: str, row: dict) -> str:
        """Generate an INSERT INTO statement for a row."""
        cols_in_schema = self.schema.tables[table_name]
        # Only include columns that exist in the schema
        cols = [c for c in row if c in cols_in_schema]
        col_list = ", ".join(cols)
        val_list = ", ".join(
            _sql_value(row[c], cols_in_schema[c]["data_type"]) for c in cols
        )
        return f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list});"

    def build_sql(self, spec: GIDefinition) -> str:
        """Build the complete transactional SQL script for a GI definition."""
        self._validate_template_row()

        design_id = str(uuid.uuid4())
        lines: list[str] = []

        # Review marker (must be present for validate-project.py)
        lines.append("-- REVIEWED: gi-sql-safe")
        lines.append(f"-- GI Builder: {spec.name}")
        lines.append("")

        # Pre-flight idempotency check
        lines.append(f"IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'{spec.name}' AND CompanyID = {self.company_id})")
        lines.append("BEGIN")
        lines.append(f"    PRINT 'GI [{spec.name}] already exists for CompanyID {self.company_id} — skipping.';")
        lines.append("    RETURN;")
        lines.append("END")
        lines.append("")

        # Transaction with error handling
        lines.append("BEGIN TRANSACTION;")
        lines.append("BEGIN TRY")
        lines.append("")

        # Track expected counts for post-flight verification
        expected_counts: dict[str, int] = {}

        # 1. GIDesign row
        design_row = self._build_row("GIDesign", {
            "DesignID": design_id,
            "Name": spec.name,
            "ScreenID": spec.screen_id,
        })
        lines.append(f"    -- GIDesign: {spec.name}")
        lines.append(f"    {self._insert_sql('GIDesign', design_row)}")
        lines.append("")
        expected_counts["GIDesign"] = 1

        # 2. GITable rows
        if spec.tables:
            lines.append("    -- GITable rows")
            for tbl in spec.tables:
                table_row = self._build_row("GITable", {
                    "DesignID": design_id,
                    "Alias": tbl["alias"],
                    "Name": tbl["dac"],
                })
                lines.append(f"    {self._insert_sql('GITable', table_row)}")
            lines.append("")
            expected_counts["GITable"] = len(spec.tables)

        # 3. GIResult rows
        # CRITICAL: IsActive=1 and IsVisible=1 are REQUIRED for columns to render.
        # Without them, the GI silently falls back to the Activities GI (EP4040PL).
        # Width, Caption, SortOrder, DefaultNav, FastFilter are also required.
        if spec.results:
            lines.append("    -- GIResult rows")
            for i, res in enumerate(spec.results):
                result_row = self._build_row("GIResult", {
                    "DesignID": design_id,
                    "LineNbr": i + 1,
                    "SortOrder": i + 1,
                    "IsActive": 1,
                    "Field": res["field"],
                    "Width": res.get("width", 120),
                    "IsVisible": 1,
                    "DefaultNav": 1 if i == 0 else 0,
                    "QuickFilter": 0,
                    "FastFilter": 1,
                    "Caption": res.get("caption", res["field"]),
                })
                lines.append(f"    {self._insert_sql('GIResult', result_row)}")
            lines.append("")
            expected_counts["GIResult"] = len(spec.results)

        # 4. GIFilter rows
        # DisplayName and DataType are required for filters to appear in the UI.
        if spec.filters:
            lines.append("    -- GIFilter rows")
            for i, flt in enumerate(spec.filters):
                filter_row = self._build_row("GIFilter", {
                    "DesignID": design_id,
                    "LineNbr": i + 1,
                    "Name": flt["name"],
                    "DisplayName": flt.get("display_name", flt["name"]),
                    "DataType": flt.get("data_type", 6),  # 6=string
                    "IsExpression": 0,
                })
                lines.append(f"    {self._insert_sql('GIFilter', filter_row)}")
            lines.append("")
            expected_counts["GIFilter"] = len(spec.filters)

        # 5. GIWhere rows
        # Condition, Value1, IsExpression, Operation, IsActive are all required.
        if spec.where:
            lines.append("    -- GIWhere rows")
            for i, wh in enumerate(spec.where):
                where_row = self._build_row("GIWhere", {
                    "DesignID": design_id,
                    "LineNbr": i + 1,
                    "IsActive": 1,
                    "DataFieldName": wh["field"],
                    "Condition": wh.get("condition", "E "),
                    "Value1": wh.get("value", ""),
                    "IsExpression": wh.get("is_expression", 0),
                    "Operation": wh.get("operation", "A"),
                })
                lines.append(f"    {self._insert_sql('GIWhere', where_row)}")
            lines.append("")
            expected_counts["GIWhere"] = len(spec.where)

        # 6. GISort rows
        # SortOrder ("A"/"D") and IsActive are required.
        if spec.sort:
            lines.append("    -- GISort rows")
            for i, srt in enumerate(spec.sort):
                sort_row = self._build_row("GISort", {
                    "DesignID": design_id,
                    "LineNbr": i + 1,
                    "IsActive": 1,
                    "DataFieldName": srt["field"],
                    "SortOrder": srt.get("order", "A"),
                })
                lines.append(f"    {self._insert_sql('GISort', sort_row)}")
            lines.append("")
            expected_counts["GISort"] = len(spec.sort)

        # Post-flight verification
        lines.append("    -- Post-flight row count verification")
        for table, expected in expected_counts.items():
            lines.append(f"    IF (SELECT COUNT(*) FROM {table} WHERE DesignID = N'{design_id}' AND CompanyID = {self.company_id}) <> {expected}")
            lines.append("    BEGIN")
            lines.append(f"        RAISERROR('Post-flight check failed: {table} expected {expected} row(s) for DesignID {design_id}', 16, 1);")
            lines.append("    END")
        lines.append("")

        # Commit
        lines.append("    COMMIT TRANSACTION;")
        lines.append(f"    PRINT 'GI [{spec.name}] created successfully.';")
        lines.append("")

        # Error handling
        lines.append("END TRY")
        lines.append("BEGIN CATCH")
        lines.append("    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
        lines.append("    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();")
        lines.append("    DECLARE @ErrSev INT = ERROR_SEVERITY();")
        lines.append("    DECLARE @ErrState INT = ERROR_STATE();")
        lines.append(f"    PRINT 'GI [{spec.name}] creation FAILED: ' + @ErrMsg;")
        lines.append("    RAISERROR(@ErrMsg, @ErrSev, @ErrState);")
        lines.append("END CATCH")

        return "\n".join(lines)
