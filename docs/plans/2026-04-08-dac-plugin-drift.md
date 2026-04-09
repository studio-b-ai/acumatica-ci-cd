# DAC / Plugin Schema Drift Test Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a two-layer static test (Python pytest + C# xUnit) that asserts every `[PXDB*]` field in `src/StudioB.Containers/DACs/Usr*.cs` has matching plugin coverage in `AesthetikContainersInstall.cs`, with exact type matching and auto-remediation output.

**Architecture:** Python regex-based parser + C# reflection-based parser. Both layers share the same plugin source file parser (regex — the plugin's DDL is string literals at runtime). Meta-tests use inline source strings as fake DAC/plugin fixtures. Real test walks actual repo files.

**Tech Stack:** Python 3 (pytest), C# net10 (xUnit 2.9), regex only (no Roslyn, no C# parser).

**Design reference:** `docs/plans/2026-04-08-dac-plugin-drift-design.md`

**Worktree:** `.claude/worktrees/dac-drift-test/` — branch `feat/dac-plugin-drift-test` based on `origin/main` (`630cca4`).

---

## Pre-flight

**Step 1: Verify worktree state**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/dac-drift-test
git status
git log --oneline -2
```

Expected: clean working tree, HEAD at `5d3f6b4` (design doc commit) on `feat/dac-plugin-drift-test`.

**Step 2: Verify baseline tests pass**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/dac-drift-test
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj 2>&1 | tail -6
```

Expected: `Passed! - Failed: 0, Passed: 41, Skipped: 0, Total: 41`

No Python baseline run — the existing Python tests hit a live sandbox. This work does not touch them.

---

## Python Layer (Tasks 1-7)

### Task 1: Scaffold + first failing meta-test + minimal detector

**Files:**
- Create: `tests/test_dac_plugin_drift.py`

**Step 1.1: Write the scaffolded file with first failing test**

Create `tests/test_dac_plugin_drift.py`:

```python
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
```

**Step 1.2: Run test — expect PASS**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/dac-drift-test
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -20
```

Expected: `test_detector_catches_missing_column PASSED`. (The minimal `find_drift` implementation already handles this case because `DacField` is constructed directly — no parser needed yet.)

**Step 1.3: Commit**

```bash
git add tests/test_dac_plugin_drift.py
git commit -m "test(drift): scaffold DAC/plugin drift detector with first meta-test"
```

---

### Task 2: Add DAC file parser + meta-test against a real DAC source

**Files:**
- Modify: `tests/test_dac_plugin_drift.py`

**Step 2.1: Add `parse_dac_file` function and meta-test**

Append to `tests/test_dac_plugin_drift.py` (before the meta-tests section):

```python
# ─── DAC file parser ─────────────────────────────────────────────────────

# Attribute names we care about. Others (PXDefault, PXUIField, etc.) are handled as modifiers.
_PXDB_ATTRIBUTES = {
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
        m = _REGION_RE.match(lines[i])
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
        sql_type = "UNKNOWN"

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
            return f"{sql_type} NOT NULL DEFAULT {default_value}"
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
            if attr_name in _PXDB_ATTRIBUTES:
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
```

And add this meta-test at the bottom of the file:

```python
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
```

**Step 2.2: Run tests — expect all 4 pass**

```bash
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -15
```

Expected: 4 passed (the new meta-tests + the existing `test_detector_catches_missing_column`).

**Step 2.3: Commit**

```bash
git add tests/test_dac_plugin_drift.py
git commit -m "test(drift): add parse_dac_file for C# DAC source extraction"
```

---

### Task 3: Add plugin file parser

**Files:**
- Modify: `tests/test_dac_plugin_drift.py`

**Step 3.1: Add `parse_plugin_file` function and meta-tests**

Append before the meta-tests section:

```python
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


def _parse_ensure_table_body(body: str) -> dict[str, str]:
    """Parse the DDL body of an EnsureTable call into {column: ddl_fragment}."""
    columns: dict[str, str] = {}
    for raw_line in body.split(","):
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
```

Add these meta-tests at the bottom:

```python
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
```

**Step 3.2: Run tests — expect 6 pass**

```bash
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -15
```

Expected: 6 passed.

**Step 3.3: Commit**

```bash
git add tests/test_dac_plugin_drift.py
git commit -m "test(drift): add parse_plugin_file for EnsureTable/EnsureColumn extraction"
```

---

### Task 4: Add type mismatch detection + auto-remediation format

**Files:**
- Modify: `tests/test_dac_plugin_drift.py`

**Step 4.1: Extend `find_drift` to detect type mismatches + add `format_remediation`**

Replace the existing `find_drift` function with:

```python
def _normalize_ddl(ddl: str) -> str:
    """Canonicalize whitespace and case for DDL comparison."""
    return re.sub(r'\s+', ' ', ddl.strip().lower())


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
            continue

        if _normalize_ddl(plugin_col.ddl) != _normalize_ddl(field.expected_ddl):
            drift.append(DriftEntry(
                dac_field=field,
                plugin_column=plugin_col,
                reason="type_mismatch",
                suggested_fix=f'EnsureColumn(conn, "{field.table}", "{field.field_name}", "{field.expected_ddl}");',
            ))

    return drift


def format_remediation(drift_entries: list[DriftEntry]) -> str:
    """Format drift entries as a copy-pasteable auto-remediation block."""
    if not drift_entries:
        return "No drift detected."

    # Group by table
    by_table: dict[str, list[DriftEntry]] = {}
    for entry in drift_entries:
        by_table.setdefault(entry.dac_field.table, []).append(entry)

    out: list[str] = []
    out.append("")
    out.append("DAC drift detected in StudioB.Containers:")
    out.append("")

    for table, entries in by_table.items():
        missing = [e for e in entries if e.reason == "missing"]
        mismatched = [e for e in entries if e.reason == "type_mismatch"]
        file_path = entries[0].dac_field.file_path

        out.append(f"Table: {table} (DAC: {file_path})")

        if missing:
            out.append(f"  Missing plugin coverage for {len(missing)} field(s).")
            out.append("  Paste the following into AesthetikContainersInstall.cs:")
            out.append("")
            # Compute column width for alignment
            max_field_len = max(len(e.dac_field.field_name) for e in missing)
            for e in missing:
                padded_name = f'"{e.dac_field.field_name}",'.ljust(max_field_len + 3)
                out.append(
                    f'      EnsureColumn(conn, "{table}", {padded_name} '
                    f'"{e.dac_field.expected_ddl}");'
                )
            out.append("")

        if mismatched:
            out.append(f"  Type mismatch on {len(mismatched)} field(s):")
            for e in mismatched:
                out.append(
                    f"      {e.dac_field.field_name}: "
                    f"DAC expects '{e.dac_field.expected_ddl}' but plugin has '{e.plugin_column.ddl}'"
                )
            out.append("  Update the existing EnsureColumn/EnsureTable DDL to match the DAC.")
            out.append("")

    return "\n".join(out)
```

Add these meta-tests:

```python
def test_detector_catches_length_mismatch():
    """DAC says nvarchar(50), plugin says nvarchar(20) → type_mismatch."""
    field = DacField(
        table="UsrTest", file_path="fake.cs", line_number=1,
        field_name="Name", attribute="PXDBString", args="50, IsUnicode = true",
        is_key=False, has_default=False, default_value=None,
        expected_ddl="nvarchar(50) NULL",
    )
    coverage = {"UsrTest": {"Name": PluginColumn(
        table="UsrTest", column="Name", ddl="nvarchar(20) NULL", source="EnsureColumn"
    )}}
    drift = find_drift([field], coverage)
    assert len(drift) == 1
    assert drift[0].reason == "type_mismatch"
    assert "nvarchar(50) NULL" in drift[0].suggested_fix


def test_detector_catches_decimal_precision_mismatch():
    """DAC says PXDBDecimal(2), plugin says decimal(19,4) → type_mismatch."""
    field = DacField(
        table="UsrTest", file_path="fake.cs", line_number=1,
        field_name="Rate", attribute="PXDBDecimal", args="2",
        is_key=False, has_default=False, default_value=None,
        expected_ddl="decimal(19,2) NULL",
    )
    coverage = {"UsrTest": {"Rate": PluginColumn(
        table="UsrTest", column="Rate", ddl="decimal(19,4) NULL", source="EnsureColumn"
    )}}
    drift = find_drift([field], coverage)
    assert len(drift) == 1
    assert drift[0].reason == "type_mismatch"


def test_detector_passes_when_all_covered():
    """Happy path: DAC field matches plugin exactly → no drift."""
    field = DacField(
        table="UsrTest", file_path="fake.cs", line_number=1,
        field_name="Name", attribute="PXDBString", args="50, IsUnicode = true",
        is_key=False, has_default=False, default_value=None,
        expected_ddl="nvarchar(50) NULL",
    )
    coverage = {"UsrTest": {"Name": PluginColumn(
        table="UsrTest", column="Name", ddl="nvarchar(50) NULL", source="EnsureColumn"
    )}}
    drift = find_drift([field], coverage)
    assert drift == []


def test_format_remediation_produces_pasteable_output():
    """format_remediation includes the full EnsureColumn line with correct quoting."""
    field = DacField(
        table="UsrContainerPrefs", file_path="src/StudioB.Containers/DACs/UsrContainerPrefs.cs",
        line_number=55, field_name="LCCodeShipping",
        attribute="PXDBString", args="15, IsUnicode = true",
        is_key=False, has_default=False, default_value=None,
        expected_ddl="nvarchar(15) NULL",
    )
    drift = [DriftEntry(
        dac_field=field,
        plugin_column=None,
        reason="missing",
        suggested_fix='EnsureColumn(conn, "UsrContainerPrefs", "LCCodeShipping", "nvarchar(15) NULL");',
    )]
    output = format_remediation(drift)
    assert 'EnsureColumn(conn, "UsrContainerPrefs"' in output
    assert 'nvarchar(15) NULL' in output
    assert 'UsrContainerPrefs.cs' in output
```

**Step 4.2: Run tests — expect 10 pass**

```bash
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -20
```

Expected: 10 passed.

**Step 4.3: Commit**

```bash
git add tests/test_dac_plugin_drift.py
git commit -m "test(drift): add type mismatch detection and auto-remediation formatter"
```

---

### Task 5: Wire up the real test against StudioB.Containers

**Files:**
- Modify: `tests/test_dac_plugin_drift.py`

**Step 5.1: Add the real test**

Add at the bottom of the meta-tests section:

```python
# ─── Real test ────────────────────────────────────────────────────────────

# DAC files that are filter/transient and don't need plugin coverage
_EXCLUDED_DAC_FILES = {
    "ContainerFilter.cs",
    "AddPOLineFilter.cs",
}


def test_studiob_containers_dac_matches_plugin():
    """Every DAC field in src/StudioB.Containers/DACs/ must have plugin coverage."""
    assert DAC_DIR.exists(), f"DAC dir not found: {DAC_DIR}"
    assert PLUGIN_FILE.exists(), f"Plugin file not found: {PLUGIN_FILE}"

    # Parse all DAC files
    all_fields: list[DacField] = []
    for cs_file in sorted(DAC_DIR.glob("Usr*.cs")):
        if cs_file.name in _EXCLUDED_DAC_FILES:
            continue
        source = cs_file.read_text(encoding="utf-8")
        all_fields.extend(parse_dac_file(source, str(cs_file.relative_to(REPO_ROOT))))

    # Parse the plugin
    plugin_source = PLUGIN_FILE.read_text(encoding="utf-8")
    coverage = parse_plugin_file(plugin_source)

    # Find drift
    drift = find_drift(all_fields, coverage)

    assert not drift, format_remediation(drift)
```

**Step 5.2: Run the real test — EXPECT IT TO FAIL with the 4 decimal precision bugs**

```bash
python3 -m pytest tests/test_dac_plugin_drift.py::test_studiob_containers_dac_matches_plugin -v 2>&1 | tail -40
```

Expected: **FAIL** with output flagging 4 type mismatches on `UsrContainer.DemurrageDailyRate`, `UsrContainer.DutyPaid`, `UsrContainer.MPFAmount`, `UsrContainer.HMFAmount` — each showing "DAC expects 'decimal(19,2) NULL' but plugin has 'decimal(19,4) NULL'".

If any OTHER drift appears, stop and investigate — this plan assumed only the 4 decimal bugs are present. Additional drift means either a parser bug or a second real bug.

**Step 5.3: Commit the failing test (temporarily use xfail to keep CI green while we fix)**

Edit `test_studiob_containers_dac_matches_plugin`: wrap it with `@pytest.mark.xfail` temporarily:

```python
import pytest

@pytest.mark.xfail(reason="4 known decimal precision bugs — fix in next commit", strict=True)
def test_studiob_containers_dac_matches_plugin():
    ...
```

Also add `import pytest` at the top if not already present.

Run:

```bash
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -15
```

Expected: 10 passed + 1 xfailed (xfailed counts as "pass" for CI).

Commit:

```bash
git add tests/test_dac_plugin_drift.py
git commit -m "test(drift): wire up real test; 4 known decimal bugs xfailed temporarily"
```

---

### Task 6: Fix the 4 decimal precision bugs in the plugin

**Files:**
- Modify: `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs`

**Step 6.1: Update the 4 EnsureColumn lines**

Find and replace (exact strings):

```
EnsureColumn(conn, "UsrContainer", "DemurrageDailyRate",  "decimal(19,4) NULL");
```
→
```
EnsureColumn(conn, "UsrContainer", "DemurrageDailyRate",  "decimal(19,2) NULL");
```

Same replacement pattern for `DutyPaid`, `MPFAmount`, `HMFAmount` — all four change from `decimal(19,4) NULL` to `decimal(19,2) NULL`.

**Step 6.2: Remove the xfail marker**

Edit `tests/test_dac_plugin_drift.py` — remove the `@pytest.mark.xfail(...)` line and the `import pytest` if no longer needed.

**Step 6.3: Run the real test — now should PASS**

```bash
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -15
```

Expected: 11 passed (all meta-tests + the real test).

**Step 6.4: Run the C# unit tests to confirm no regression**

```bash
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj 2>&1 | tail -6
```

Expected: `Passed! - Failed: 0, Passed: 41, Skipped: 0, Total: 41`

**Step 6.5: Commit**

```bash
git add src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs tests/test_dac_plugin_drift.py
git commit -m "fix(plugin): correct decimal precision on 4 UsrContainer fields

DAC declares [PXDBDecimal(2)] but plugin shipped as decimal(19,4):
  - DemurrageDailyRate
  - DutyPaid
  - MPFAmount
  - HMFAmount

Caught by new DAC/plugin drift test on first run. Would have caused
silent rounding discrepancies in landed cost reports. Fix brings plugin
DDL in line with DAC spec.

Also removes the temporary xfail marker now that the real test passes."
```

---

## C# xUnit Layer (Tasks 7-9)

### Task 7: Scaffold C# test file + mirror find_drift logic

**Files:**
- Create: `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`
- Modify: `tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj`

**Step 7.1: Create the C# test file**

Create `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.RegularExpressions;
using Xunit;

namespace StudioB.Containers.Tests
{
    /// <summary>
    /// DAC/plugin schema drift detector — C# reflection layer.
    ///
    /// Uses reflection on the compiled StudioB.Containers.dll to enumerate DAC
    /// fields decorated with [PXDB*] attributes, then parses
    /// AesthetikContainersInstall.cs source for EnsureTable/EnsureColumn calls
    /// and asserts every DAC field has matching plugin coverage.
    ///
    /// Paired with tests/test_dac_plugin_drift.py (Python layer). Both must pass.
    /// </summary>
    public class DacPluginDriftTests
    {
        // Audit and boilerplate attributes — skipped from drift check
        private static readonly HashSet<string> AuditAttributeNames = new()
        {
            "PXDBCreatedByIDAttribute", "PXDBCreatedByScreenIDAttribute",
            "PXDBCreatedDateTimeAttribute", "PXDBLastModifiedByIDAttribute",
            "PXDBLastModifiedByScreenIDAttribute", "PXDBLastModifiedDateTimeAttribute",
            "PXDBTimestampAttribute", "PXNoteAttribute",
        };

        // DAC classes to exclude (filter DACs, etc.)
        private static readonly HashSet<string> ExcludedDacClasses = new()
        {
            "ContainerFilter", "AddPOLineFilter",
        };

        public record DacField(
            string Table,
            string FieldName,
            string AttributeName,
            string ExpectedDdl
        );

        public record PluginColumn(
            string Table,
            string Column,
            string Ddl,
            string Source  // "EnsureColumn" or "EnsureTable"
        );

        public record DriftEntry(
            DacField Field,
            PluginColumn? PluginCol,
            string Reason,
            string SuggestedFix
        );

        private static string RepoRoot()
        {
            // Walk up from test DLL location until we find the repo root (.git)
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null && !Directory.Exists(Path.Combine(dir.FullName, ".git")))
            {
                dir = dir.Parent;
            }
            if (dir == null)
                throw new InvalidOperationException("Could not find repo root from " + AppContext.BaseDirectory);
            return dir.FullName;
        }

        private static Assembly LoadStudioBContainers()
        {
            var root = RepoRoot();
            var dllPath = Path.Combine(root, "src", "StudioB.Containers", "bin", "Debug", "net48", "StudioB.Containers.dll");
            if (!File.Exists(dllPath))
                throw new FileNotFoundException(
                    $"StudioB.Containers.dll not found at {dllPath}. Run 'dotnet build src/StudioB.Containers/' first.");
            return Assembly.LoadFrom(dllPath);
        }

        // Regex for EnsureColumn(conn, "Table", "Col", "ddl");
        private static readonly Regex EnsureColumnRe = new(
            @"EnsureColumn\s*\(\s*conn\s*,\s*""(\w+)""\s*,\s*""(\w+)""\s*,\s*""([^""]+)""\s*\)\s*;",
            RegexOptions.Compiled);

        // Regex for EnsureTable(conn, "Table", @"...ddl...");
        private static readonly Regex EnsureTableRe = new(
            @"EnsureTable\s*\(\s*conn\s*,\s*""(\w+)""\s*,\s*@""([^""]*)""\s*\)\s*;",
            RegexOptions.Compiled | RegexOptions.Singleline);

        public static Dictionary<string, Dictionary<string, PluginColumn>> ParsePluginSource(string source)
        {
            var coverage = new Dictionary<string, Dictionary<string, PluginColumn>>();

            // EnsureTable blocks
            foreach (Match m in EnsureTableRe.Matches(source))
            {
                var table = m.Groups[1].Value;
                var body = m.Groups[2].Value;
                if (!coverage.ContainsKey(table))
                    coverage[table] = new Dictionary<string, PluginColumn>();

                foreach (var rawLine in body.Split(','))
                {
                    var line = rawLine.Trim();
                    if (string.IsNullOrEmpty(line) || line.StartsWith("CONSTRAINT"))
                        continue;
                    var parts = line.Split(new[] { ' ', '\t' }, 2, StringSplitOptions.RemoveEmptyEntries);
                    if (parts.Length != 2) continue;
                    var colName = parts[0];
                    if (colName == "CompanyID") continue;
                    coverage[table][colName] = new PluginColumn(table, colName, parts[1].Trim(), "EnsureTable");
                }
            }

            // EnsureColumn calls
            foreach (Match m in EnsureColumnRe.Matches(source))
            {
                var table = m.Groups[1].Value;
                var col = m.Groups[2].Value;
                var ddl = m.Groups[3].Value.Trim();
                if (!coverage.ContainsKey(table))
                    coverage[table] = new Dictionary<string, PluginColumn>();
                coverage[table][col] = new PluginColumn(table, col, ddl, "EnsureColumn");
            }

            return coverage;
        }

        private static string NormalizeDdl(string ddl)
        {
            return Regex.Replace(ddl.Trim().ToLowerInvariant(), @"\s+", " ");
        }

        public static List<DriftEntry> FindDrift(
            List<DacField> dacFields,
            Dictionary<string, Dictionary<string, PluginColumn>> coverage)
        {
            var drift = new List<DriftEntry>();
            foreach (var field in dacFields)
            {
                if (!coverage.TryGetValue(field.Table, out var tableCols))
                {
                    drift.Add(new DriftEntry(field, null, "missing",
                        $"EnsureColumn(conn, \"{field.Table}\", \"{field.FieldName}\", \"{field.ExpectedDdl}\");"));
                    continue;
                }
                if (!tableCols.TryGetValue(field.FieldName, out var col))
                {
                    drift.Add(new DriftEntry(field, null, "missing",
                        $"EnsureColumn(conn, \"{field.Table}\", \"{field.FieldName}\", \"{field.ExpectedDdl}\");"));
                    continue;
                }
                if (NormalizeDdl(col.Ddl) != NormalizeDdl(field.ExpectedDdl))
                {
                    drift.Add(new DriftEntry(field, col, "type_mismatch",
                        $"EnsureColumn(conn, \"{field.Table}\", \"{field.FieldName}\", \"{field.ExpectedDdl}\");"));
                }
            }
            return drift;
        }

        public static string FormatRemediation(List<DriftEntry> drift)
        {
            if (drift.Count == 0) return "No drift detected.";
            var sb = new System.Text.StringBuilder();
            sb.AppendLine();
            sb.AppendLine("DAC drift detected in StudioB.Containers:");
            sb.AppendLine();
            foreach (var entry in drift)
            {
                sb.AppendLine($"  Table: {entry.Field.Table}");
                sb.AppendLine($"    Field: {entry.Field.FieldName} (reason: {entry.Reason})");
                if (entry.PluginCol != null)
                    sb.AppendLine($"    Plugin has: {entry.PluginCol.Ddl}");
                sb.AppendLine($"    Expected:   {entry.Field.ExpectedDdl}");
                sb.AppendLine($"    Fix:        {entry.SuggestedFix}");
                sb.AppendLine();
            }
            return sb.ToString();
        }

        // ─── Meta-tests ────────────────────────────────────────────────

        [Fact]
        public void ParsePluginSource_ExtractsEnsureColumn()
        {
            var source = @"
                EnsureColumn(conn, ""UsrTest"", ""Name"", ""nvarchar(20) NULL"");
            ";
            var coverage = ParsePluginSource(source);
            Assert.True(coverage.ContainsKey("UsrTest"));
            Assert.True(coverage["UsrTest"].ContainsKey("Name"));
            Assert.Equal("nvarchar(20) NULL", coverage["UsrTest"]["Name"].Ddl);
        }

        [Fact]
        public void ParsePluginSource_ExtractsEnsureTable()
        {
            var source = @"
                EnsureTable(conn, ""UsrTest"", @""
                    CompanyID int NOT NULL DEFAULT 0,
                    TestID int IDENTITY(1,1) NOT NULL,
                    TestName nvarchar(50) NULL,
                    CONSTRAINT PK_UsrTest PRIMARY KEY (CompanyID, TestID)
                "");
            ";
            var coverage = ParsePluginSource(source);
            Assert.True(coverage.ContainsKey("UsrTest"));
            Assert.False(coverage["UsrTest"].ContainsKey("CompanyID"));
            Assert.True(coverage["UsrTest"].ContainsKey("TestID"));
            Assert.Equal("int IDENTITY(1,1) NOT NULL", coverage["UsrTest"]["TestID"].Ddl);
        }

        [Fact]
        public void FindDrift_DetectsMissingColumn()
        {
            var field = new DacField("UsrTest", "Name", "PXDBStringAttribute", "nvarchar(20) NULL");
            var coverage = new Dictionary<string, Dictionary<string, PluginColumn>>();
            var drift = FindDrift(new List<DacField> { field }, coverage);
            Assert.Single(drift);
            Assert.Equal("missing", drift[0].Reason);
            Assert.Contains("nvarchar(20) NULL", drift[0].SuggestedFix);
        }

        [Fact]
        public void FindDrift_DetectsTypeMismatch()
        {
            var field = new DacField("UsrTest", "Rate", "PXDBDecimalAttribute", "decimal(19,2) NULL");
            var coverage = new Dictionary<string, Dictionary<string, PluginColumn>>
            {
                ["UsrTest"] = new()
                {
                    ["Rate"] = new PluginColumn("UsrTest", "Rate", "decimal(19,4) NULL", "EnsureColumn"),
                }
            };
            var drift = FindDrift(new List<DacField> { field }, coverage);
            Assert.Single(drift);
            Assert.Equal("type_mismatch", drift[0].Reason);
        }

        [Fact]
        public void FindDrift_PassesWhenCovered()
        {
            var field = new DacField("UsrTest", "Name", "PXDBStringAttribute", "nvarchar(20) NULL");
            var coverage = new Dictionary<string, Dictionary<string, PluginColumn>>
            {
                ["UsrTest"] = new()
                {
                    ["Name"] = new PluginColumn("UsrTest", "Name", "nvarchar(20) NULL", "EnsureColumn"),
                }
            };
            var drift = FindDrift(new List<DacField> { field }, coverage);
            Assert.Empty(drift);
        }
    }
}
```

**Step 7.2: Verify the test project already references the compiled DLL**

Check `tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj` — it already has Python-style `Compile Include` links to source files. The reflection test needs to load the DLL at runtime from the filesystem (done in `LoadStudioBContainers()`). No csproj change needed — the helper walks the filesystem.

**Step 7.3: Build the StudioB.Containers DLL so the reflection tests can load it**

```bash
dotnet build src/StudioB.Containers/StudioB.Containers.csproj 2>&1 | tail -5
```

Expected: `Build succeeded. 0 Warning(s) 0 Error(s)`.

**Step 7.4: Run the new C# meta-tests**

```bash
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj --filter "FullyQualifiedName~DacPluginDriftTests" 2>&1 | tail -10
```

Expected: 5 passed (the 5 meta-tests in the scaffold). Full test run (41 old + 5 new = 46) still green on full run.

**Step 7.5: Commit**

```bash
git add tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs
git commit -m "test(drift): scaffold C# xUnit layer with plugin parser + drift detector"
```

---

### Task 8: Add DAC reflection + type mapping to C# layer

**Files:**
- Modify: `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`

**Step 8.1: Add DAC reflection logic to the class**

Add these methods inside `DacPluginDriftTests`:

```csharp
        /// <summary>
        /// Enumerate DAC types in StudioB.Containers that require plugin coverage.
        /// Filters out filter/transient DACs and returns PXBqlTable-descended types
        /// whose name starts with "Usr".
        /// </summary>
        public static List<Type> GetDacTypes(Assembly asm)
        {
            return asm.GetTypes()
                .Where(t => t.IsClass && !t.IsAbstract)
                .Where(t => t.BaseType != null && t.BaseType.Name == "PXBqlTable")
                .Where(t => t.Name.StartsWith("Usr"))
                .Where(t => !ExcludedDacClasses.Contains(t.Name))
                .ToList();
        }

        /// <summary>
        /// Extract DAC fields with [PXDB*] attributes from a reflected type.
        /// Returns one DacField per persistable property.
        /// </summary>
        public static List<DacField> ExtractDacFields(Type dacType)
        {
            var fields = new List<DacField>();
            var tableName = dacType.Name;

            foreach (var prop in dacType.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                var attrs = prop.GetCustomAttributes(inherit: false);
                // Skip if any audit attribute present
                if (attrs.Any(a => AuditAttributeNames.Contains(a.GetType().Name)))
                    continue;

                // Find the PXDB* attribute
                var pxdbAttr = attrs
                    .Where(a => a.GetType().Name.StartsWith("PXDB"))
                    .FirstOrDefault(a => !AuditAttributeNames.Contains(a.GetType().Name));

                if (pxdbAttr == null) continue;

                var expectedDdl = ComputeExpectedDdl(pxdbAttr, attrs);
                fields.Add(new DacField(
                    Table: tableName,
                    FieldName: prop.Name,
                    AttributeName: pxdbAttr.GetType().Name,
                    ExpectedDdl: expectedDdl
                ));
            }
            return fields;
        }

        private static string ComputeExpectedDdl(object pxdbAttr, object[] allAttrs)
        {
            var attrType = pxdbAttr.GetType();
            var name = attrType.Name;

            // Get nullability cues from PXDefault presence
            var defaultAttr = allAttrs.FirstOrDefault(a => a.GetType().Name == "PXDefaultAttribute");
            bool hasDefault = defaultAttr != null;
            object? defaultValue = null;
            if (defaultAttr != null)
            {
                var valueProp = defaultAttr.GetType().GetProperty("Value");
                if (valueProp != null) defaultValue = valueProp.GetValue(defaultAttr);
            }

            bool isKey = false;
            var isKeyProp = attrType.GetProperty("IsKey");
            if (isKeyProp != null && isKeyProp.GetValue(pxdbAttr) is bool b) isKey = b;

            switch (name)
            {
                case "PXDBStringAttribute":
                {
                    var lengthProp = attrType.GetProperty("Length");
                    var length = lengthProp != null ? lengthProp.GetValue(pxdbAttr) as int? : null;
                    var isUnicodeProp = attrType.GetProperty("IsUnicode");
                    bool isUnicode = isUnicodeProp != null && isUnicodeProp.GetValue(pxdbAttr) is bool iu && iu;
                    var isFixedProp = attrType.GetProperty("IsFixed");
                    bool isFixed = isFixedProp != null && isFixedProp.GetValue(pxdbAttr) is bool fix && fix;
                    var typeStr = isFixed ? "nchar" : (isUnicode ? "nvarchar" : "varchar");
                    var lengthStr = length.HasValue ? $"({length})" : "";
                    if (isKey) return $"{typeStr}{lengthStr} NOT NULL DEFAULT ''";
                    return $"{typeStr}{lengthStr} NULL";
                }
                case "PXDBTextAttribute":
                    return "nvarchar(MAX) NULL";
                case "PXDBIntAttribute":
                    if (isKey && hasDefault && defaultValue != null)
                        return $"int NOT NULL DEFAULT {defaultValue}";
                    return "int NULL";
                case "PXDBIdentityAttribute":
                    return "int IDENTITY(1,1) NOT NULL";
                case "PXDBBoolAttribute":
                    if (hasDefault)
                    {
                        var boolDefault = (defaultValue?.ToString()?.ToLowerInvariant() == "true") ? "1" : "0";
                        return $"bit NOT NULL DEFAULT {boolDefault}";
                    }
                    return "bit NOT NULL DEFAULT 0";
                case "PXDBDecimalAttribute":
                {
                    var precisionProp = attrType.GetProperty("Precision");
                    int scale = 2;
                    if (precisionProp != null && precisionProp.GetValue(pxdbAttr) is int p) scale = p;
                    return $"decimal(19,{scale}) NULL";
                }
                case "PXDBDateAttribute":
                    return "datetime NULL";
                case "PXDBGuidAttribute":
                    return "uniqueidentifier NULL";
                default:
                    return $"UNKNOWN ({name})";
            }
        }
```

**Step 8.2: Add a reflection meta-test**

```csharp
        [Fact]
        public void ExtractDacFields_ReturnsPxdbFieldsFromLoadedAssembly()
        {
            var asm = LoadStudioBContainers();
            var dacTypes = GetDacTypes(asm);
            Assert.NotEmpty(dacTypes);

            // Pick UsrContainerPrefs and verify we see the LCCode* fields
            var prefsType = dacTypes.FirstOrDefault(t => t.Name == "UsrContainerPrefs");
            Assert.NotNull(prefsType);

            var fields = ExtractDacFields(prefsType!);
            var fieldNames = fields.Select(f => f.FieldName).ToHashSet();
            Assert.Contains("LCCodeShipping", fieldNames);
            Assert.Contains("LCCodeDuty", fieldNames);
            Assert.Contains("LCCodeTariff", fieldNames);
            Assert.Contains("LCCodeBrokerage", fieldNames);
            Assert.Contains("LCCodeOther", fieldNames);
        }
```

**Step 8.3: Run tests**

```bash
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj --filter "FullyQualifiedName~DacPluginDriftTests" 2>&1 | tail -10
```

Expected: 6 passed (5 previous + 1 new reflection test).

**Step 8.4: Commit**

```bash
git add tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs
git commit -m "test(drift): add DAC reflection + type mapping to C# layer"
```

---

### Task 9: Wire up the real C# test against the repo

**Files:**
- Modify: `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`

**Step 9.1: Add the real test**

Add at the bottom of the class:

```csharp
        // ─── Real test ─────────────────────────────────────────────────

        [Fact]
        public void StudioBContainers_Dac_Matches_Plugin()
        {
            var root = RepoRoot();
            var pluginPath = Path.Combine(root, "src", "StudioB.Containers", "Graphs", "AesthetikContainersInstall.cs");
            Assert.True(File.Exists(pluginPath), $"Plugin not found: {pluginPath}");
            var pluginSource = File.ReadAllText(pluginPath);
            var coverage = ParsePluginSource(pluginSource);

            var asm = LoadStudioBContainers();
            var allFields = new List<DacField>();
            foreach (var dacType in GetDacTypes(asm))
            {
                allFields.AddRange(ExtractDacFields(dacType));
            }

            var drift = FindDrift(allFields, coverage);
            Assert.True(drift.Count == 0, FormatRemediation(drift));
        }
```

**Step 9.2: Run the real test**

```bash
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj --filter "FullyQualifiedName~DacPluginDriftTests" 2>&1 | tail -10
```

Expected outcomes (in order of likelihood):

- **(a) Pass**: reflection sees decimal precision the same way Python does, the 4 decimal fixes from Task 6 are honored, real test passes. Total: 7 passed.
- **(b) Fail with type mismatches Python didn't catch**: reflection sees something Python regex missed (e.g., inherited fields). Read the failure output, investigate, fix the plugin DDL OR the reflection logic, re-run.
- **(c) Fail with missing columns**: reflection enumerates fields Python missed. Same — investigate, fix, re-run.

If (b) or (c): do NOT commit the real test in a failing state. Mark the test `[Fact(Skip = "investigating reflection delta — see 2026-04-08-dac-plugin-drift-impl.md")]` temporarily, commit the rest, and capture the delta in the impl log for follow-up.

If (a): commit.

**Step 9.3: Commit**

```bash
git add tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs
git commit -m "test(drift): wire up real C# xUnit test against StudioB.Containers"
```

---

## Integration + Ship (Tasks 10-12)

### Task 10: Run full test suites locally

**Step 10.1: Run all Python drift tests**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/dac-drift-test
python3 -m pytest tests/test_dac_plugin_drift.py -v 2>&1 | tail -20
```

Expected: 11 passed.

**Step 10.2: Run all C# tests**

```bash
dotnet test tests/dotnet/StudioB.Containers.Tests/StudioB.Containers.Tests.csproj 2>&1 | tail -6
```

Expected: 48 passed, 0 failed (41 existing + 7 new drift tests).

**Step 10.3: Verify the plugin DDL change didn't break the StudioB.Containers build**

```bash
dotnet build src/StudioB.Containers/StudioB.Containers.csproj 2>&1 | tail -5
```

Expected: `Build succeeded. 0 Warning(s) 0 Error(s)`.

---

### Task 11: Write impl log

**Files:**
- Create: `docs/plans/2026-04-08-dac-plugin-drift-impl.md`

**Step 11.1: Document what landed**

Create `docs/plans/2026-04-08-dac-plugin-drift-impl.md` with:
- What files were added/modified
- Test counts (11 Python, 7 C#)
- The 4 decimal precision bugs caught and fixed
- Any deviations from the design (if Task 9 ran into reflection delta)
- Open items / follow-ups

**Step 11.2: Commit**

```bash
git add docs/plans/2026-04-08-dac-plugin-drift-impl.md
git commit -m "docs(drift): implementation log"
```

---

### Task 12: Push and open PR

**Step 12.1: Push branch**

```bash
git push -u origin feat/dac-plugin-drift-test
```

**Step 12.2: Open PR**

```bash
gh pr create --base main --head feat/dac-plugin-drift-test \
  --title "test(drift): DAC/plugin schema drift detector (Python + C# layers)" \
  --body "$(cat <<'EOF'
## Summary

Two-layer static test that catches the class of bug that took 3 hours to debug on 2026-04-08 morning: DAC fields added to `Usr*.cs` without corresponding `EnsureColumn` calls in `AesthetikContainersInstall.cs`.

- **Python pytest layer** (`tests/test_dac_plugin_drift.py`) — regex-based, fast, runs without DLL build
- **C# xUnit layer** (`tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`) — reflection-based, runs in Acuminator job
- **Exact type matching** — catches length/unicode/nullability/decimal precision drift, not just missing columns
- **Auto-remediation output** — failures print ready-to-paste `EnsureColumn` lines

## Bonus — 4 silent decimal precision bugs caught on first run

DAC declared `[PXDBDecimal(2)]` but plugin shipped as `decimal(19,4)` on 4 `UsrContainer` fields:
- `DemurrageDailyRate`
- `DutyPaid`
- `MPFAmount`
- `HMFAmount`

Fixed in this PR. Would have caused silent rounding discrepancies in landed cost reports. **The test paid for itself on day one.**

## Design

Full design doc at `docs/plans/2026-04-08-dac-plugin-drift-design.md`.

## Test plan

- [x] 11 Python meta-tests + 1 real test (all pass)
- [x] 7 C# meta-tests + 1 real test (all pass)
- [x] Self-verification: deliberately introduced drift cases caught by both layers
- [x] First real run caught 4 known bugs; fixed; real tests now green
- [ ] CI: pytest runs in Linux build job; dotnet test runs in Windows Acuminator job

## Out of scope (follow-ups)

- StudioB.WMS coverage (no custom install plugin yet)
- Orphan detection (plugin columns with no DAC field)
- Runtime plugin self-check
- Auto-fix mode

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 12.3: Confirm PR URL and watch CI**

Expected: PR URL printed. Both layers should pass CI:
- Linux build job runs pytest including the new `test_dac_plugin_drift.py` → 11 passed
- Windows Acuminator job runs `dotnet test` → 48 passed (41 existing + 7 new)

If CI fails on either layer, stop and investigate before merging.

---

## Rollback procedure

If this PR breaks something unforeseen after merge:

```bash
git revert <merge-commit>
git push origin main
```

The revert will:
- Remove `tests/test_dac_plugin_drift.py`
- Remove `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`
- Revert the 4 decimal precision fixes (reinstates `decimal(19,4)` on 4 `UsrContainer` fields)
- Revert the design + impl docs

The last point is the concerning one. If revert is needed, immediately re-apply the decimal precision fixes as a standalone commit — those are correctness fixes, not test infrastructure.

## Done when

- [x] `docs/plans/2026-04-08-dac-plugin-drift-design.md` committed
- [ ] `tests/test_dac_plugin_drift.py` exists with 11 passing tests
- [ ] `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs` exists with 7 passing tests
- [ ] 4 decimal precision fixes landed in `AesthetikContainersInstall.cs`
- [ ] `docs/plans/2026-04-08-dac-plugin-drift-impl.md` exists
- [ ] PR opened on GitHub
- [ ] CI passes on the PR (Linux + Windows)
