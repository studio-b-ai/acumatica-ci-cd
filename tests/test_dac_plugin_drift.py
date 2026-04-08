"""
DAC/plugin schema drift detector — Python layer.

Parses src/StudioB.Containers/DACs/Usr*.cs for [PXDB*] attributes and
src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs for EnsureTable
and EnsureColumn calls, then asserts every DAC field has matching plugin
coverage with exact type match.

Design: docs/plans/2026-04-08-dac-plugin-drift-design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DAC_DIR = REPO_ROOT / "src" / "StudioB.Containers" / "DACs"
PLUGIN_FILE = REPO_ROOT / "src" / "StudioB.Containers" / "Graphs" / "AesthetikContainersInstall.cs"


@dataclass(frozen=True)
class DacField:
    """A DAC field with a [PXDB*] attribute that requires plugin coverage."""
    table: str                # SQL table name (from [PXCacheName] or class name)
    file_path: str            # Source file path
    line_number: int          # Line where the field's region starts
    field_name: str           # SQL column name (e.g., "LCCodeShipping")
    attribute: str            # e.g., "PXDBString"
    args: str                 # e.g., "15, IsUnicode = true"
    is_key: bool
    has_default: bool
    default_value: Optional[str]
    expected_ddl: str         # computed SQL type (e.g., "nvarchar(15) NULL")


@dataclass(frozen=True)
class PluginColumn:
    """A column known to the install plugin via EnsureTable or EnsureColumn."""
    table: str
    column: str
    ddl: str                  # normalized type fragment
    source: str               # "EnsureColumn" or "EnsureTable"


@dataclass(frozen=True)
class DriftEntry:
    dac_field: DacField
    plugin_column: Optional[PluginColumn]
    reason: str               # "missing" | "type_mismatch"
    suggested_fix: str        # ready-to-paste EnsureColumn line


def find_drift(dac_fields: list[DacField],
               plugin_coverage: dict[str, dict[str, PluginColumn]]) -> list[DriftEntry]:
    """Compare DAC fields against plugin coverage. Returns drift entries."""
    drift: list[DriftEntry] = []
    for field in dac_fields:
        table_cols = plugin_coverage.get(field.table, {})
        plugin_col = table_cols.get(field.field_name)
        if plugin_col is None:
            drift.append(DriftEntry(
                dac_field=field,
                plugin_column=None,
                reason="missing",
                suggested_fix=f'EnsureColumn(conn, "{field.table}", "{field.field_name}", "{field.expected_ddl}");',
            ))
    return drift


# ─── DAC file parser ─────────────────────────────────────────────────────

# Attribute names we care about. Others (PXDefault, PXUIField, etc.) are handled as modifiers.
_DB_BOUND_ATTRIBUTES = {
    "PXDBString", "PXDBInt", "PXDBBool", "PXDBDecimal",
    "PXDBDate", "PXDBGuid", "PXDBIdentity", "PXDBText",
    "PXRSACryptString",
}

# Attributes that indicate audit fields — always excluded from drift check.
_AUDIT_ATTRIBUTES = {
    "PXDBCreatedByID", "PXDBCreatedByScreenID", "PXDBCreatedDateTime",
    "PXDBLastModifiedByID", "PXDBLastModifiedByScreenID", "PXDBLastModifiedDateTime",
    "PXDBTimestamp", "PXNote",
}

_CACHE_NAME_RE = re.compile(r'\[PXCacheName\s*\(\s*"([^"]+)"\s*\)\]')
_CLASS_RE = re.compile(r'public\s+class\s+(\w+)\s*:\s*PXBqlTable')
_REGION_RE = re.compile(r'#region\s+(\w+)\s*$', re.MULTILINE)

# One region's content: everything from #region Name to #endregion
# Captures the property name via `public ... PropName { get; set; }`
_PROP_RE = re.compile(r'public\s+[^\s]+\??\s+(\w+)\s*\{\s*get;\s*set;\s*\}')

# Attribute parser: captures attribute name + args inside []
_ATTR_RE = re.compile(r'\[(\w+)(?:\(([^\]]*)\))?\]')


def _find_regions(source: str) -> list[tuple[str, str, int]]:
    """Return list of (region_name, region_body, line_number) tuples."""
    regions = []
    lines = source.split("\n")
    i = 0
    while i < len(lines):
        m = _REGION_RE.search(lines[i])
        if m:
            name = m.group(1)
            start_line = i + 1
            body_lines = []
            i += 1
            while i < len(lines) and "#endregion" not in lines[i]:
                body_lines.append(lines[i])
                i += 1
            regions.append((name, "\n".join(body_lines), start_line))
        i += 1
    return regions


def _compute_expected_ddl(attribute: str,
                          args: str,
                          has_default: bool,
                          default_value: Optional[str],
                          is_key: bool) -> str:
    """Canonical DAC attribute → SQL type fragment mapping.

    Returns e.g. 'nvarchar(15) NULL' or 'decimal(19,2) NOT NULL DEFAULT 1'.
    """
    # Parse the arg string (e.g. "15, IsUnicode = true, IsFixed = true, IsKey = true")
    size = None
    is_unicode = False
    is_fixed = False
    # First positional arg is size
    if args:
        first = args.split(",")[0].strip()
        if first.isdigit():
            size = int(first)
        if "IsUnicode = true" in args:
            is_unicode = True
        if "IsFixed = true" in args:
            is_fixed = True
        if "IsKey = true" in args:
            is_key = True

    # Compute SQL type
    if attribute == "PXDBString":
        char_type = "nchar" if is_fixed else ("nvarchar" if is_unicode else "varchar")
        sql_type = f"{char_type}({size})" if size else char_type
    elif attribute == "PXDBText":
        sql_type = "nvarchar(MAX)"
    elif attribute == "PXDBInt":
        sql_type = "int"
    elif attribute == "PXDBIdentity":
        return "int IDENTITY(1,1) NOT NULL"
    elif attribute == "PXDBBool":
        sql_type = "bit"
    elif attribute == "PXDBDecimal":
        scale = int(args.strip()) if args and args.strip().isdigit() else 2
        sql_type = f"decimal(19,{scale})"
    elif attribute == "PXDBDate":
        sql_type = "datetime"
    elif attribute == "PXDBGuid":
        sql_type = "uniqueidentifier"
    elif attribute == "PXRSACryptString":
        sql_type = f"nvarchar({size})" if size else "nvarchar"
    else:
        raise ValueError(f"unrecognized DAC attribute: {attribute}")

    # Nullability + default
    if is_key or has_default:
        # NOT NULL with default
        if attribute == "PXDBBool":
            default_sql = "DEFAULT 1" if default_value == "true" else "DEFAULT 0"
            return f"{sql_type} NOT NULL {default_sql}"
        if attribute == "PXDBInt" and default_value and default_value.isdigit():
            return f"{sql_type} NOT NULL DEFAULT {default_value}"
        if is_key and attribute == "PXDBString":
            return f"{sql_type} NOT NULL DEFAULT ''"
        if has_default and default_value:
            # Normalize string literals: "X" → 'X' (SQL Server uses single quotes)
            normalized_default = default_value
            if normalized_default.startswith('"') and normalized_default.endswith('"'):
                normalized_default = "'" + normalized_default[1:-1] + "'"
            return f"{sql_type} NOT NULL DEFAULT {normalized_default}"
        return f"{sql_type} NOT NULL"

    # Nullable (default case)
    if attribute == "PXDBBool":
        return f"{sql_type} NOT NULL DEFAULT 0"
    return f"{sql_type} NULL"


def parse_dac_file(source: str, file_path: str) -> list[DacField]:
    """Extract DAC fields with [PXDB*] attributes that need plugin coverage."""
    # Table name: prefer [PXCacheName("X")], fall back to class name stripped of Usr prefix
    cache_match = _CACHE_NAME_RE.search(source)
    class_match = _CLASS_RE.search(source)
    if class_match is None:
        return []
    table_name = class_match.group(1)  # e.g., "UsrContainerPrefs"

    fields: list[DacField] = []
    for region_name, region_body, line_num in _find_regions(source):
        # Find attributes in this region
        attrs = _ATTR_RE.findall(region_body)
        if not attrs:
            continue

        # Skip if region is an audit/boilerplate field
        attr_names = {a[0] for a in attrs}
        if attr_names & _AUDIT_ATTRIBUTES:
            continue

        # Find the PXDB* attribute (there should be exactly one)
        pxdb_attr = None
        pxdb_args = ""
        has_default = False
        default_value = None
        for attr_name, attr_args in attrs:
            if attr_name in _DB_BOUND_ATTRIBUTES:
                pxdb_attr = attr_name
                pxdb_args = attr_args
            elif attr_name == "PXDefault":
                has_default = True
                # Extract the first positional arg as default value
                if attr_args:
                    first_arg = attr_args.split(",")[0].strip()
                    default_value = first_arg

        if pxdb_attr is None:
            # Unbound field — skip
            continue

        # Get the C# property name (region_name is the capitalized name matching the property)
        # Verify via _PROP_RE
        prop_match = _PROP_RE.search(region_body)
        if prop_match is None:
            continue
        prop_name = prop_match.group(1)

        # SQL column name = property name (Acumatica convention)
        field_name = prop_name

        is_key = "IsKey = true" in pxdb_args

        expected_ddl = _compute_expected_ddl(
            pxdb_attr, pxdb_args, has_default, default_value, is_key
        )

        fields.append(DacField(
            table=table_name,
            file_path=file_path,
            line_number=line_num,
            field_name=field_name,
            attribute=pxdb_attr,
            args=pxdb_args,
            is_key=is_key,
            has_default=has_default,
            default_value=default_value,
            expected_ddl=expected_ddl,
        ))
    return fields


# ─── Plugin file parser ──────────────────────────────────────────────────

# EnsureColumn(conn, "TableName", "ColumnName", "type DDL");
_ENSURE_COLUMN_RE = re.compile(
    r'EnsureColumn\s*\(\s*conn\s*,\s*'
    r'"(\w+)"\s*,\s*'           # table
    r'"(\w+)"\s*,\s*'           # column
    r'"([^"]+)"\s*\)\s*;',      # type DDL
    re.MULTILINE,
)

# EnsureTable(conn, "TableName", @"...column DDL...");
_ENSURE_TABLE_RE = re.compile(
    r'EnsureTable\s*\(\s*conn\s*,\s*'
    r'"(\w+)"\s*,\s*'           # table
    r'@"([^"]*)"\s*\)\s*;',     # DDL body (verbatim string)
    re.DOTALL,
)


def _split_top_level_commas(body: str) -> list[str]:
    """Split a DDL body on commas that are not inside parentheses."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _parse_ensure_table_body(body: str) -> dict[str, str]:
    """Parse the DDL body of an EnsureTable call into {column: ddl_fragment}."""
    columns: dict[str, str] = {}
    for raw_line in _split_top_level_commas(body):
        line = raw_line.strip()
        if not line or line.startswith("CONSTRAINT"):
            continue
        # Split on first whitespace: "ColumnName type..."
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        col_name, col_ddl = parts
        if col_name == "CompanyID":
            continue  # Boilerplate
        columns[col_name] = col_ddl.strip()
    return columns


def parse_plugin_file(source: str) -> dict[str, dict[str, PluginColumn]]:
    """Extract EnsureTable + EnsureColumn coverage from install plugin source."""
    coverage: dict[str, dict[str, PluginColumn]] = {}

    # EnsureTable blocks
    for match in _ENSURE_TABLE_RE.finditer(source):
        table_name = match.group(1)
        ddl_body = match.group(2)
        cols = _parse_ensure_table_body(ddl_body)
        coverage.setdefault(table_name, {})
        for col_name, col_ddl in cols.items():
            coverage[table_name][col_name] = PluginColumn(
                table=table_name,
                column=col_name,
                ddl=col_ddl,
                source="EnsureTable",
            )

    # EnsureColumn calls
    for match in _ENSURE_COLUMN_RE.finditer(source):
        table_name = match.group(1)
        col_name = match.group(2)
        col_ddl = match.group(3).strip()
        coverage.setdefault(table_name, {})
        coverage[table_name][col_name] = PluginColumn(
            table=table_name,
            column=col_name,
            ddl=col_ddl,
            source="EnsureColumn",
        )

    return coverage


# ─── Meta-tests ──────────────────────────────────────────────────────────

def test_detector_catches_missing_column():
    """DAC field exists but plugin has no EnsureColumn/EnsureTable coverage."""
    dac_field = DacField(
        table="UsrTestTable",
        file_path="fake.cs",
        line_number=10,
        field_name="TestField",
        attribute="PXDBString",
        args="20, IsUnicode = true",
        is_key=False,
        has_default=False,
        default_value=None,
        expected_ddl="nvarchar(20) NULL",
    )
    plugin_coverage: dict[str, dict[str, PluginColumn]] = {}
    drift = find_drift([dac_field], plugin_coverage)
    assert len(drift) == 1
    assert drift[0].reason == "missing"
    assert drift[0].dac_field.field_name == "TestField"
    assert 'EnsureColumn(conn, "UsrTestTable", "TestField", "nvarchar(20) NULL");' in drift[0].suggested_fix


def test_parse_dac_file_extracts_pxdb_fields():
    """parse_dac_file pulls out fields decorated with [PXDB*]."""
    source = """
using PX.Data;
namespace StudioB.Containers {
    [PXCacheName("Test")]
    public class UsrTest : PXBqlTable, IBqlTable {
        #region TestField
        public abstract class testField : BqlString.Field<testField> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "Test")]
        public string TestField { get; set; }
        #endregion
    }
}
"""
    fields = parse_dac_file(source, "fake.cs")
    assert len(fields) == 1
    assert fields[0].field_name == "TestField"
    assert fields[0].attribute == "PXDBString"
    assert fields[0].expected_ddl == "nvarchar(20) NULL"
    assert fields[0].table == "UsrTest"
    assert fields[0].is_key == False
    assert fields[0].has_default == False


def test_parse_dac_file_skips_unbound_fields():
    """Fields with [PXString] (no DB prefix) are unbound — excluded."""
    source = """
public class UsrTest : PXBqlTable, IBqlTable {
    #region RiskLevel
    public abstract class riskLevel : BqlString.Field<riskLevel> { }
    [PXString(1)]
    [PXUIField(DisplayName = "Risk")]
    public string RiskLevel { get; set; }
    #endregion
}
"""
    fields = parse_dac_file(source, "fake.cs")
    assert len(fields) == 0


def test_parse_dac_file_skips_audit_fields():
    """Audit field regions (CreatedByID, Tstamp, etc.) are excluded."""
    source = """
public class UsrTest : PXBqlTable, IBqlTable {
    #region CreatedByID
    public abstract class createdByID : BqlGuid.Field<createdByID> { }
    [PXDBCreatedByID]
    public Guid? CreatedByID { get; set; }
    #endregion
    #region Tstamp
    public abstract class tstamp : BqlByteArray.Field<tstamp> { }
    [PXDBTimestamp]
    public byte[] Tstamp { get; set; }
    #endregion
}
"""
    fields = parse_dac_file(source, "fake.cs")
    assert len(fields) == 0


def test_parse_dac_file_audit_skip_is_selective():
    """When a DAC has both audit and real fields, only real fields are returned."""
    source = """
public class UsrTest : PXBqlTable, IBqlTable {
    #region TestName
    public abstract class testName : BqlString.Field<testName> { }
    [PXDBString(50, IsUnicode = true)]
    [PXUIField(DisplayName = "Name")]
    public string TestName { get; set; }
    #endregion
    #region CreatedByID
    public abstract class createdByID : BqlGuid.Field<createdByID> { }
    [PXDBCreatedByID]
    public Guid? CreatedByID { get; set; }
    #endregion
    #region Tstamp
    public abstract class tstamp : BqlByteArray.Field<tstamp> { }
    [PXDBTimestamp]
    public byte[] Tstamp { get; set; }
    #endregion
}
"""
    fields = parse_dac_file(source, "fake.cs")
    assert len(fields) == 1
    assert fields[0].field_name == "TestName"
    assert fields[0].expected_ddl == "nvarchar(50) NULL"


def test_parse_dac_file_returns_empty_for_filter_dac():
    """Filter DACs use non-persistent attributes like [PXInt] — their fields are excluded."""
    source = """
[Serializable]
[PXCacheName("Filter")]
public class AddPOLineFilter : PXBqlTable, IBqlTable {
    #region VendorID
    public abstract class vendorID : BqlInt.Field<vendorID> { }
    [PXInt]
    [PXUIField(DisplayName = "Vendor")]
    public int? VendorID { get; set; }
    #endregion
}
"""
    # Filter DACs have [PXInt] (not PXDBInt) — non-persistent fields.
    # parse_dac_file should return an empty list (the field is unbound).
    fields = parse_dac_file(source, "fake.cs")
    assert len(fields) == 0


def test_parse_plugin_file_extracts_ensure_column():
    """EnsureColumn calls are captured with correct table/col/ddl."""
    source = '''
        EnsureColumn(conn, "UsrContainerPrefs", "LCCodeShipping", "nvarchar(15) NULL");
        EnsureColumn(conn, "UsrContainerPrefs", "LCCodeDuty", "nvarchar(15) NULL");
    '''
    coverage = parse_plugin_file(source)
    assert "UsrContainerPrefs" in coverage
    assert "LCCodeShipping" in coverage["UsrContainerPrefs"]
    assert coverage["UsrContainerPrefs"]["LCCodeShipping"].ddl == "nvarchar(15) NULL"
    assert coverage["UsrContainerPrefs"]["LCCodeShipping"].source == "EnsureColumn"


def test_parse_plugin_file_extracts_ensure_table():
    """EnsureTable body columns are captured, CompanyID and CONSTRAINT lines skipped."""
    source = '''
        EnsureTable(conn, "UsrTest", @"
            CompanyID int NOT NULL DEFAULT 0,
            TestID int IDENTITY(1,1) NOT NULL,
            TestName nvarchar(50) NULL,
            CONSTRAINT PK_UsrTest PRIMARY KEY (CompanyID, TestID)
        ");
    '''
    coverage = parse_plugin_file(source)
    assert "UsrTest" in coverage
    assert "CompanyID" not in coverage["UsrTest"]
    assert coverage["UsrTest"]["TestID"].ddl == "int IDENTITY(1,1) NOT NULL"
    assert coverage["UsrTest"]["TestName"].ddl == "nvarchar(50) NULL"
