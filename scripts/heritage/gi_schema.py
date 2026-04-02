"""GI Schema Discovery — parse INFORMATION_SCHEMA output and validate rows.

The schema discovery SQL runs inside a CustomizationPlugin (UpdateDatabase).
This module parses the WriteLog output and provides validation.
"""
import json
import re
from pathlib import Path


# All GI tables that need schema discovery
GI_TABLES = [
    "GIDesign", "GITable", "GIResult", "GIWhere", "GISort",
    "GIFilter", "GIRelation", "GIOn", "GIGroupBy",
]


class GISchemaMap:
    """Cached schema map for GI tables, keyed by Acumatica version."""

    def __init__(self, tables: dict, acumatica_version: str):
        self.tables = tables
        self.acumatica_version = acumatica_version

    def not_null_columns(self, table_name: str) -> list[str]:
        """Return list of NOT NULL column names for a table."""
        if table_name not in self.tables:
            raise ValueError(f"Unknown table: {table_name}")
        return [
            col for col, info in self.tables[table_name].items()
            if info["nullable"] == "NO"
        ]

    def columns_with_defaults(self, table_name: str) -> list[str]:
        """Return NOT NULL columns that have database defaults (safe to omit)."""
        if table_name not in self.tables:
            raise ValueError(f"Unknown table: {table_name}")
        return [
            col for col, info in self.tables[table_name].items()
            if info["nullable"] == "NO" and info.get("default") is not None
        ]

    def validate_row(self, table_name: str, row: dict) -> list[str]:
        """Validate a row dict against schema. Returns list of error strings."""
        errors = []
        for col in self.not_null_columns(table_name):
            if col not in row or row[col] is None:
                col_info = self.tables[table_name][col]
                if col_info.get("default") is not None:
                    continue  # DB will fill it
                errors.append(
                    f"Missing required column {table_name}.{col} "
                    f"({col_info['data_type']}, NOT NULL, no default)"
                )
        return errors

    def save(self, path: Path):
        """Save schema map to JSON file."""
        data = {
            "acumatica_version": self.acumatica_version,
            "tables": self.tables,
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "GISchemaMap":
        """Load schema map from JSON file."""
        data = json.loads(path.read_text())
        return cls(data["tables"], data["acumatica_version"])


def parse_information_schema_output(log_text: str) -> dict:
    """Parse WriteLog output from the schema discovery plugin.

    Expected format per line:
    [SCHEMA] Table: GIDesign
      ColumnName: datatype(maxlen) nullable=YES/NO default=VALUE
    """
    tables = {}
    current_table = None
    col_pattern = re.compile(
        r"^\s+(\w+): (\w+)\(([^)]*)\) nullable=(YES|NO) default=(.+)$"
    )

    for line in log_text.splitlines():
        if line.startswith("[SCHEMA] Table: "):
            current_table = line.split(": ", 1)[1].strip()
            tables[current_table] = {}
        elif current_table:
            m = col_pattern.match(line)
            if m:
                col_name, dtype, max_len, nullable, default = m.groups()
                tables[current_table][col_name] = {
                    "data_type": dtype,
                    "max_length": None if max_len == "n/a" else int(max_len),
                    "nullable": nullable,
                    "default": None if default == "NULL" else default,
                }

    return tables


def generate_discovery_sql() -> str:
    """Generate the SQL that runs inside UpdateDatabase() to discover GI schemas.

    This SQL queries INFORMATION_SCHEMA.COLUMNS for each GI table and
    outputs in the format that parse_information_schema_output() expects.
    The output goes through WriteLog() in the CustomizationPlugin.
    """
    lines = []
    for table in GI_TABLES:
        lines.append(f'WriteLog("[SCHEMA] Table: {table}");')
        lines.append('using (var cmd = new SqlCommand(')
        lines.append('    @"SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH, COLUMN_DEFAULT')
        lines.append('      FROM INFORMATION_SCHEMA.COLUMNS')
        lines.append(f"      WHERE TABLE_NAME = '{table}'")
        lines.append('      ORDER BY ORDINAL_POSITION", conn))')
        lines.append('{')
        lines.append('    using (var reader = cmd.ExecuteReader())')
        lines.append('    {')
        lines.append('        while (reader.Read())')
        lines.append('        {')
        lines.append('            string col = reader.GetString(0);')
        lines.append('            string dtype = reader.GetString(1);')
        lines.append('            string nullable = reader.GetString(2);')
        lines.append('            string maxLen = reader.IsDBNull(3) ? "n/a" : reader.GetInt32(3).ToString();')
        lines.append('            string def = reader.IsDBNull(4) ? "NULL" : reader.GetString(4);')
        lines.append('            WriteLog(string.Format("  {0}: {1}({2}) nullable={3} default={4}",')
        lines.append('                col, dtype, maxLen, nullable, def));')
        lines.append('        }')
        lines.append('    }')
        lines.append('}')
    return "\n".join(lines)
