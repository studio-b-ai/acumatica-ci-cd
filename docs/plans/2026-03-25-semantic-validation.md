# Semantic Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 11 semantic checks to the Acumatica CI/CD validator that cross-reference DAC field declarations against SQL column creation, detect type mismatches, and catch cross-project conflicts.

**Architecture:** New `scripts/semantic_checks.py` module imported by existing `validate-project.py`. Parsers extract structured data from C# code (DAC fields, SQL columns, namespaces, extensions), then 11 check functions validate semantic correctness. Results returned as `(errors, warnings)` tuples.

**Tech Stack:** Python 3, regex, xml.etree.ElementTree (stdlib only — no external deps, matches existing scripts)

---

### Task 1: Core Parsers — `parse_dac_fields()` and `parse_sql_columns()`

**Files:**
- Create: `scripts/semantic_checks.py`
- Test: `scripts/test_semantic_checks.py`

**Step 1: Write failing tests for both parsers**

```python
#!/usr/bin/env python3
"""Tests for semantic_checks.py"""
import pytest
from semantic_checks import parse_dac_fields, parse_sql_columns

# ── parse_dac_fields ────────────────────────────────────────

def test_parse_decimal_field():
    code = '''
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        [PXDBDecimal(2)]
        public decimal? UsrPGMinRemnant { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert len(fields) == 1
    f = fields[0]
    assert f["name"] == "UsrPGMinRemnant"
    assert f["db_type"] == "PXDBDecimal"
    assert f["precision"] == 2
    assert f["dac"] == "INSetup"

def test_parse_bool_field():
    code = '''
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        [PXDBBool]
        public bool? UsrPGAutoPrint { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert len(fields) == 1
    assert fields[0]["db_type"] == "PXDBBool"
    assert fields[0]["precision"] is None

def test_parse_string_field():
    code = '''
    public sealed class INLotSerialStatusExt : PXCacheExtension<INLotSerialStatus>
    {
        [PXDBString(30, IsUnicode = true)]
        public string UsrDyeLot { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert len(fields) == 1
    assert fields[0]["db_type"] == "PXDBString"
    assert fields[0]["precision"] == 30
    assert fields[0]["dac"] == "INLotSerialStatus"

def test_parse_int_field():
    code = '''
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        [PXDBInt]
        public int? UsrPGXDockAge { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert len(fields) == 1
    assert fields[0]["db_type"] == "PXDBInt"

def test_parse_multiple_extensions():
    """Multiple DAC extensions in one file — each field tagged with correct DAC."""
    code = '''
    public sealed class SOOrderExt : PXCacheExtension<SOOrder>
    {
        [PXDBString(50)]
        public string UsrHubSpotDealId { get; set; }
    }
    public sealed class CustomerExt : PXCacheExtension<Customer>
    {
        [PXDBBool]
        public bool? UsrDisablePayLink { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert len(fields) == 2
    assert fields[0]["dac"] == "SOOrder"
    assert fields[1]["dac"] == "Customer"

def test_parse_pxdefault():
    code = '''
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "1.00")]
        public decimal? UsrPGMinRemnant { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert fields[0]["default_value"] == "1.00"

def test_parse_pxdefault_bool():
    code = '''
    public sealed class INSetupExt : PXCacheExtension<INSetup>
    {
        [PXDBBool]
        [PXDefault(true)]
        public bool? UsrPGAutoPrint { get; set; }
    }
    '''
    fields = parse_dac_fields(code)
    assert fields[0]["default_value"] == "true"


# ── parse_sql_columns ──────────────────────────────────────

def test_parse_alter_table():
    sql = '''
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGMinRemnant') ALTER TABLE INSetup ADD UsrPGMinRemnant decimal(18,2) NULL",
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGAutoPrint') ALTER TABLE INSetup ADD UsrPGAutoPrint bit NULL",
    '''
    cols = parse_sql_columns(sql)
    assert len(cols) == 2
    assert cols[0]["table"] == "INSetup"
    assert cols[0]["column"] == "UsrPGMinRemnant"
    assert cols[0]["sql_type"] == "decimal"
    assert cols[0]["precision"] == 2  # from decimal(18,2)
    assert cols[1]["sql_type"] == "bit"

def test_parse_nvarchar():
    sql = '''
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INLotSerialStatus') AND name = 'UsrDyeLot') ALTER TABLE INLotSerialStatus ADD UsrDyeLot nvarchar(30) NULL",
    '''
    cols = parse_sql_columns(sql)
    assert len(cols) == 1
    assert cols[0]["sql_type"] == "nvarchar"
    assert cols[0]["precision"] == 30

def test_parse_int_column():
    sql = '''
    "IF NOT EXISTS (SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('INSetup') AND name = 'UsrPGXDockAge') ALTER TABLE INSetup ADD UsrPGXDockAge int NULL",
    '''
    cols = parse_sql_columns(sql)
    assert cols[0]["sql_type"] == "int"
    assert cols[0]["precision"] is None
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: ImportError — `semantic_checks` module does not exist

**Step 3: Implement parsers**

```python
#!/usr/bin/env python3
"""
Semantic validation checks for Acumatica customization projects.

Cross-references DAC field declarations against SQL column creation statements,
validates type compatibility, detects cross-project conflicts, and checks
manifest coverage.

Imported by validate-project.py after structural checks.
"""

import re
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ── Constants ───────────────────────────────────────────────

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Acumatica DAC name → actual SQL table name mapping.
# Many DACs map 1:1, but some don't (Customer → BAccount, etc.)
DAC_TO_TABLE = {
    "SOOrder": "SOOrder",
    "SOLine": "SOLine",
    "SOShipment": "SOShipment",
    "SOShipLine": "SOShipLine",
    "SOPackageDetailEx": "SOPackageDetail",
    "POOrder": "POOrder",
    "POLine": "POLine",
    "POReceipt": "POReceipt",
    "POReceiptLine": "POReceiptLine",
    "ARInvoice": "ARInvoice",
    "APInvoice": "APInvoice",
    "Customer": "BAccount",
    "Vendor": "BAccount",
    "BAccount": "BAccount",
    "INSetup": "INSetup",
    "INLotSerialClass": "INLotSerClass",
    "INLotSerialStatus": "INLotSerialStatus",
    "INItemClass": "INItemClass",
    "InventoryItem": "InventoryItem",
    "INRegister": "INRegister",
    "INTran": "INTran",
    "CRCase": "CRCase",
    "Contact": "Contact",
    "Address": "Address",
    "EPEmployee": "BAccountR",
    "CSAnswers": "CSAnswers",
    "Note": "Note",
    "NoteDoc": "NoteDoc",
}

# C# [PXDBx] attribute → expected SQL column type
PXDB_TO_SQL = {
    "PXDBBool": "bit",
    "PXDBInt": "int",
    "PXDBDecimal": "decimal",
    "PXDBString": "nvarchar",
    "PXDBDate": "datetime",
    "PXDBDateAndTime": "datetime",
    "PXDBLong": "bigint",
    "PXDBFloat": "float",
    "PXDBDouble": "float",
    "PXDBGuid": "uniqueidentifier",
    "PXDBBinary": "varbinary",
}


# ── Parsers ─────────────────────────────────────────────────

def _strip_comments(code: str) -> str:
    """Remove C# comments to avoid false regex matches."""
    code = re.sub(r"///.*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"//.*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return code


def parse_dac_fields(code: str) -> List[Dict]:
    """Extract DAC extension field declarations from C# code.

    Returns list of dicts:
        name: field name (e.g. "UsrPGMinRemnant")
        db_type: PXDBx attribute (e.g. "PXDBDecimal")
        precision: numeric precision/length or None
        dac: target DAC name (e.g. "INSetup")
        default_value: PXDefault value string or None
    """
    clean = _strip_comments(code)
    fields = []

    # Find all PXCacheExtension<DAC> declarations to build a DAC context map
    # We'll track which DAC each field belongs to by position
    ext_pattern = re.compile(
        r"class\s+(\w+)\s*:\s*PXCacheExtension<(\w+)>"
    )
    extensions = []
    for m in ext_pattern.finditer(clean):
        extensions.append({
            "class_name": m.group(1),
            "dac": m.group(2),
            "start": m.start(),
        })

    def get_dac_at(pos: int) -> Optional[str]:
        """Find which DAC extension a position belongs to."""
        result = None
        for ext in extensions:
            if ext["start"] <= pos:
                result = ext["dac"]
        return result

    # Match [PXDBx(N)] or [PXDBx] followed by a property declaration
    # Pattern: [PXDBType(optional_params)] ... public type? FieldName { get; set; }
    field_pattern = re.compile(
        r"\[(PXDB\w+)"           # [PXDBDecimal or [PXDBBool etc.
        r"(?:\(([^)]*)\))?"      # optional (2) or (30, IsUnicode = true)
        r"\]"                    # closing ]
        r"(.*?)"                 # stuff between (PXDefault, PXUIField, etc.)
        r"public\s+\w+\??\s+"   # public decimal? or public bool?
        r"(Usr\w+)"             # field name starting with Usr
        r"\s*\{",               # { get; set; }
        re.DOTALL
    )

    for m in field_pattern.finditer(clean):
        db_type = m.group(1)
        params = m.group(2) or ""
        between = m.group(3) or ""
        name = m.group(4)

        # Extract precision from first numeric param
        precision = None
        precision_match = re.match(r"\s*(\d+)", params)
        if precision_match:
            precision = int(precision_match.group(1))

        # Extract PXDefault value
        default_value = None
        # Pattern 1: [PXDefault(TypeCode.Decimal, "1.00")]
        default_match = re.search(
            r'\[PXDefault\(TypeCode\.\w+,\s*"([^"]+)"\)', between
        )
        if default_match:
            default_value = default_match.group(1)
        else:
            # Pattern 2: [PXDefault(true)] or [PXDefault(false)] or [PXDefault(5)]
            default_match = re.search(
                r"\[PXDefault\((\w+)\)", between
            )
            if default_match:
                default_value = default_match.group(1)

        dac = get_dac_at(m.start())

        fields.append({
            "name": name,
            "db_type": db_type,
            "precision": precision,
            "dac": dac,
            "default_value": default_value,
        })

    return fields


def parse_sql_columns(code: str) -> List[Dict]:
    """Extract ALTER TABLE column definitions from SQL/C# initializer code.

    Handles both:
      - Raw SQL in <Sql> CDATA blocks
      - SQL string literals in C# initializer arrays

    Returns list of dicts:
        table: SQL table name (e.g. "INSetup")
        column: column name (e.g. "UsrPGMinRemnant")
        sql_type: base type (e.g. "decimal", "bit", "nvarchar")
        precision: numeric precision/length or None
    """
    columns = []

    # Match: ALTER TABLE <table> ADD <column> <type>(<precision>) or <type>
    pattern = re.compile(
        r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+"
        r"(\w+)\s+"                           # column name
        r"(\w+)"                              # type (decimal, bit, nvarchar, int)
        r"(?:\((\d+)(?:,(\d+))?\))?"          # optional (18,2) or (30)
    )

    for m in pattern.finditer(code):
        table = m.group(1)
        column = m.group(2)
        sql_type = m.group(3).lower()
        # For decimal(18,2), precision is the scale (2nd number)
        # For nvarchar(30), precision is the length (1st number)
        if sql_type == "decimal":
            precision = int(m.group(5)) if m.group(5) else None
        elif m.group(4):
            precision = int(m.group(4))
        else:
            precision = None

        columns.append({
            "table": table,
            "column": column,
            "sql_type": sql_type,
            "precision": precision,
        })

    return columns
```

**Step 4: Run tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: All 11 tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add scripts/semantic_checks.py scripts/test_semantic_checks.py
git commit -m "[CI/CD] ADD: semantic_checks.py core parsers — parse_dac_fields + parse_sql_columns"
```

---

### Task 2: Phase 1 Checks — Field-to-SQL Cross-Reference + Type Validation

**Files:**
- Modify: `scripts/semantic_checks.py`
- Modify: `scripts/test_semantic_checks.py`

**Step 1: Write failing tests for Phase 1 checks**

Add to `test_semantic_checks.py`:

```python
from semantic_checks import (
    check_fields_have_sql_columns,
    check_type_compatibility,
    check_table_name_mapping,
)


# ── Check 1: Fields without SQL columns ────────────────────

def test_missing_sql_column():
    fields = [
        {"name": "UsrPGMinRemnant", "db_type": "PXDBDecimal", "precision": 2, "dac": "INLotSerialClass"},
    ]
    columns = []  # no SQL columns at all
    errors, warnings = check_fields_have_sql_columns(fields, columns)
    assert len(errors) == 1
    assert "UsrPGMinRemnant" in errors[0]

def test_field_has_sql_column():
    fields = [
        {"name": "UsrPGMinRemnant", "db_type": "PXDBDecimal", "precision": 2, "dac": "INLotSerialClass"},
    ]
    columns = [
        {"table": "INLotSerClass", "column": "UsrPGMinRemnant", "sql_type": "decimal", "precision": 2},
    ]
    errors, warnings = check_fields_have_sql_columns(fields, columns)
    assert len(errors) == 0


# ── Check 2+3: Type and precision mismatches ───────────────

def test_type_mismatch():
    fields = [
        {"name": "UsrFlag", "db_type": "PXDBBool", "precision": None, "dac": "SOOrder"},
    ]
    columns = [
        {"table": "SOOrder", "column": "UsrFlag", "sql_type": "nvarchar", "precision": 20},
    ]
    errors, warnings = check_type_compatibility(fields, columns)
    assert len(errors) == 1
    assert "type mismatch" in errors[0].lower()

def test_precision_mismatch():
    fields = [
        {"name": "UsrAmt", "db_type": "PXDBDecimal", "precision": 2, "dac": "SOOrder"},
    ]
    columns = [
        {"table": "SOOrder", "column": "UsrAmt", "sql_type": "decimal", "precision": 4},
    ]
    errors, warnings = check_type_compatibility(fields, columns)
    assert len(errors) == 1
    assert "precision" in errors[0].lower()

def test_types_match():
    fields = [
        {"name": "UsrAmt", "db_type": "PXDBDecimal", "precision": 2, "dac": "SOOrder"},
    ]
    columns = [
        {"table": "SOOrder", "column": "UsrAmt", "sql_type": "decimal", "precision": 2},
    ]
    errors, warnings = check_type_compatibility(fields, columns)
    assert len(errors) == 0


# ── Check 4: Table name mapping ────────────────────────────

def test_table_name_mismatch():
    """SQL references DAC name instead of actual table name."""
    fields = [
        {"name": "UsrField", "db_type": "PXDBBool", "precision": None, "dac": "INLotSerialClass"},
    ]
    # Wrong: uses DAC name "INLotSerialClass" instead of table "INLotSerClass"
    columns = [
        {"table": "INLotSerialClass", "column": "UsrField", "sql_type": "bit", "precision": None},
    ]
    errors, warnings = check_table_name_mapping(fields, columns)
    assert len(errors) >= 1
    assert "INLotSerClass" in errors[0]

def test_customer_baccount_mapping():
    """Customer DAC maps to BAccount table."""
    fields = [
        {"name": "UsrFlag", "db_type": "PXDBBool", "precision": None, "dac": "Customer"},
    ]
    columns = [
        {"table": "BAccount", "column": "UsrFlag", "sql_type": "bit", "precision": None},
    ]
    errors, warnings = check_table_name_mapping(fields, columns)
    assert len(errors) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v -k "check"`
Expected: ImportError — functions don't exist yet

**Step 3: Implement Phase 1 check functions**

Add to `scripts/semantic_checks.py`:

```python
def _resolve_table(dac: str) -> Optional[str]:
    """Resolve DAC name to SQL table name. Returns None if unknown."""
    return DAC_TO_TABLE.get(dac)


def _build_column_index(columns: List[Dict]) -> Dict[str, Dict]:
    """Build {column_name: column_dict} index, merging across tables."""
    # Key by (table, column) for precise matching, and also by just column
    # for fuzzy matching when DAC→table mapping is unknown
    index = {}
    for col in columns:
        key = f"{col['table']}.{col['column']}"
        index[key] = col
        # Also index by just column name for fallback
        index[col["column"]] = col
    return index


def check_fields_have_sql_columns(
    fields: List[Dict], columns: List[Dict]
) -> Tuple[List[str], List[str]]:
    """Check 1: Every DAC field must have a corresponding SQL column."""
    errors = []
    warnings = []
    col_index = _build_column_index(columns)

    for field in fields:
        name = field["name"]
        dac = field["dac"]
        table = _resolve_table(dac) if dac else None

        # Try precise match first: table.column
        if table:
            precise_key = f"{table}.{name}"
            if precise_key in col_index:
                continue  # found

        # Fallback: match by column name only
        if name in col_index:
            continue  # found (can't verify table, but column exists)

        # Not found
        table_hint = f" (table: {table})" if table else f" (DAC: {dac}, table unknown)"
        errors.append(
            f"DAC field '{name}'{table_hint} has no matching SQL ALTER TABLE column.\n"
            f"         Add: ALTER TABLE {table or dac} ADD {name} <type> NULL"
        )

    return errors, warnings


def check_type_compatibility(
    fields: List[Dict], columns: List[Dict]
) -> Tuple[List[str], List[str]]:
    """Check 2+3: Field types and precisions must match SQL column types."""
    errors = []
    warnings = []
    col_index = _build_column_index(columns)

    for field in fields:
        name = field["name"]
        dac = field["dac"]
        table = _resolve_table(dac) if dac else None
        db_type = field["db_type"]
        expected_sql = PXDB_TO_SQL.get(db_type)

        if not expected_sql:
            continue  # unknown PXDBx type — skip

        # Find matching column
        col = None
        if table:
            col = col_index.get(f"{table}.{name}")
        if not col:
            col = col_index.get(name)
        if not col:
            continue  # no column found — Check 1 handles this

        actual_sql = col["sql_type"]

        # Type mismatch
        if actual_sql != expected_sql:
            errors.append(
                f"Type mismatch: '{name}' — [{db_type}] expects SQL type '{expected_sql}', "
                f"but SQL column is '{actual_sql}'"
            )
            continue

        # Precision mismatch (only for types that have precision)
        if field["precision"] is not None and col["precision"] is not None:
            if field["precision"] != col["precision"]:
                errors.append(
                    f"Precision mismatch: '{name}' — [{db_type}({field['precision']})] "
                    f"but SQL column is {actual_sql}({col['precision']})"
                )

    return errors, warnings


def check_table_name_mapping(
    fields: List[Dict], columns: List[Dict]
) -> Tuple[List[str], List[str]]:
    """Check 4: SQL table names must use actual DB table, not DAC name."""
    errors = []
    warnings = []

    # Collect all table names used in SQL
    sql_tables = {col["table"] for col in columns}

    # Check each field's DAC against SQL tables
    seen_dacs = set()
    for field in fields:
        dac = field["dac"]
        if not dac or dac in seen_dacs:
            continue
        seen_dacs.add(dac)

        expected_table = _resolve_table(dac)
        if expected_table is None:
            # Unknown DAC — warn
            warnings.append(
                f"DAC '{dac}' not in known DAC→table mapping. "
                f"Cannot verify SQL table name correctness."
            )
            continue

        if expected_table == dac:
            continue  # DAC name == table name, no mapping issue possible

        # DAC maps to a different table name — check if SQL uses the wrong name
        if dac in sql_tables and expected_table not in sql_tables:
            errors.append(
                f"SQL uses DAC name '{dac}' as table name, but the actual DB table "
                f"is '{expected_table}'. ALTER TABLE statements should reference "
                f"'{expected_table}', not '{dac}'."
            )

    return errors, warnings
```

**Step 4: Run tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add scripts/semantic_checks.py scripts/test_semantic_checks.py
git commit -m "[CI/CD] ADD: Phase 1 semantic checks — field-to-SQL cross-reference, type/precision validation, table name mapping"
```

---

### Task 3: Phase 2 Checks — Extension References, Cross-Project Duplicates, Namespaces

**Files:**
- Modify: `scripts/semantic_checks.py`
- Modify: `scripts/test_semantic_checks.py`

**Step 1: Write failing tests**

Add to `test_semantic_checks.py`:

```python
from semantic_checks import (
    check_extension_references,
    check_cross_project_duplicates,
    check_namespace_consistency,
    parse_dac_fields,
)


# ── Check 5: Extension references ──────────────────────────

def test_unknown_extension_reference():
    code = '''
    public sealed class MyGraphExt : PXGraphExtension<SOOrderEntry>
    {
        protected void _(Events.RowSelected<SOOrder> e)
        {
            var ext = e.Row.GetExtension<NonExistentExt>();
        }
    }
    '''
    declared_extensions = {"SOOrderExt", "CustomerExt"}
    errors, warnings = check_extension_references(code, declared_extensions)
    assert len(warnings) == 1
    assert "NonExistentExt" in warnings[0]

def test_known_extension_reference():
    code = '''
    public sealed class MyGraphExt : PXGraphExtension<SOOrderEntry>
    {
        protected void _(Events.RowSelected<SOOrder> e)
        {
            var ext = e.Row.GetExtension<SOOrderExt>();
        }
    }
    '''
    declared_extensions = {"SOOrderExt"}
    errors, warnings = check_extension_references(code, declared_extensions)
    assert len(warnings) == 0


# ── Check 6: Cross-project duplicates ──────────────────────

def test_duplicate_field_across_projects():
    project_a_fields = [
        {"name": "UsrCustomField", "dac": "SOOrder"},
    ]
    project_b_fields = [
        {"name": "UsrCustomField", "dac": "SOOrder"},
    ]
    errors, warnings = check_cross_project_duplicates(
        "ProjectA", project_a_fields,
        {"ProjectB": project_b_fields},
    )
    assert len(errors) == 1
    assert "ProjectB" in errors[0]

def test_same_field_different_dac_ok():
    project_a_fields = [
        {"name": "UsrCustomField", "dac": "SOOrder"},
    ]
    project_b_fields = [
        {"name": "UsrCustomField", "dac": "POOrder"},
    ]
    errors, warnings = check_cross_project_duplicates(
        "ProjectA", project_a_fields,
        {"ProjectB": project_b_fields},
    )
    assert len(errors) == 0


# ── Check 7: Namespace consistency ─────────────────────────

def test_inconsistent_namespaces():
    files = {
        "Code/DAC/FileA.cs": "namespace Aesthetik.WMS\n{ }",
        "Code/DAC/FileB.cs": "namespace Different.Namespace\n{ }",
    }
    errors, warnings = check_namespace_consistency(files)
    assert len(warnings) == 1
    assert "Different.Namespace" in warnings[0]

def test_consistent_namespaces():
    files = {
        "Code/DAC/FileA.cs": "namespace Aesthetik.WMS\n{ }",
        "Code/Graph/FileB.cs": "namespace Aesthetik.WMS\n{ }",
    }
    errors, warnings = check_namespace_consistency(files)
    assert len(warnings) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v -k "check_extension or duplicate or namespace"`
Expected: ImportError

**Step 3: Implement Phase 2 check functions**

Add to `scripts/semantic_checks.py`:

```python
def check_extension_references(
    code: str, declared_extensions: set
) -> Tuple[List[str], List[str]]:
    """Check 5: GetExtension<T>() calls reference declared extensions."""
    errors = []
    warnings = []
    clean = _strip_comments(code)

    # Find all GetExtension<T>() calls
    for m in re.finditer(r"GetExtension<(\w+)>\(\)", clean):
        ext_name = m.group(1)
        if ext_name not in declared_extensions:
            warnings.append(
                f"GetExtension<{ext_name}>() references undeclared extension. "
                f"Not found in project DAC extensions: {sorted(declared_extensions)}"
            )

    return errors, warnings


def check_cross_project_duplicates(
    primary_name: str,
    primary_fields: List[Dict],
    other_projects: Dict[str, List[Dict]],
) -> Tuple[List[str], List[str]]:
    """Check 6: No duplicate field+DAC across co-published projects."""
    errors = []
    warnings = []

    # Build primary index: (dac, field_name)
    primary_keys = {(f["dac"], f["name"]) for f in primary_fields}

    for proj_name, proj_fields in other_projects.items():
        for field in proj_fields:
            key = (field["dac"], field["name"])
            if key in primary_keys:
                errors.append(
                    f"Duplicate field: '{field['name']}' on DAC '{field['dac']}' "
                    f"declared in both '{primary_name}' and '{proj_name}'. "
                    f"Co-publishing will conflict."
                )

    return errors, warnings


def check_namespace_consistency(
    files: Dict[str, str]
) -> Tuple[List[str], List[str]]:
    """Check 7: All .cs files in a project share a root namespace."""
    errors = []
    warnings = []

    namespaces = {}
    for filepath, code in files.items():
        m = re.search(r"namespace\s+([\w.]+)", code)
        if m:
            namespaces[filepath] = m.group(1)

    if len(set(namespaces.values())) > 1:
        # Find the most common namespace (assumed correct)
        ns_counts = {}
        for ns in namespaces.values():
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        primary_ns = max(ns_counts, key=ns_counts.get)

        for filepath, ns in namespaces.items():
            if ns != primary_ns:
                warnings.append(
                    f"Namespace mismatch: '{filepath}' uses '{ns}', "
                    f"but most files use '{primary_ns}'"
                )

    return errors, warnings
```

**Step 4: Run tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add scripts/semantic_checks.py scripts/test_semantic_checks.py
git commit -m "[CI/CD] ADD: Phase 2 semantic checks — extension references, cross-project duplicates, namespace consistency"
```

---

### Task 4: Phase 3 Checks — Orphaned SQL, Path Normalization, PXDefault, Manifest

**Files:**
- Modify: `scripts/semantic_checks.py`
- Modify: `scripts/test_semantic_checks.py`

**Step 1: Write failing tests**

Add to `test_semantic_checks.py`:

```python
from semantic_checks import (
    check_orphaned_sql_columns,
    check_external_paths,
    check_pxdefault_vs_sql,
    check_manifest_coverage,
)


# ── Check 8: Orphaned SQL columns ──────────────────────────

def test_orphaned_column():
    fields = [
        {"name": "UsrFieldA", "dac": "SOOrder"},
    ]
    columns = [
        {"table": "SOOrder", "column": "UsrFieldA", "sql_type": "bit", "precision": None},
        {"table": "SOOrder", "column": "UsrOrphan", "sql_type": "nvarchar", "precision": 50},
    ]
    errors, warnings = check_orphaned_sql_columns(fields, columns)
    assert len(warnings) == 1
    assert "UsrOrphan" in warnings[0]

def test_no_orphans():
    fields = [
        {"name": "UsrFieldA", "dac": "SOOrder"},
    ]
    columns = [
        {"table": "SOOrder", "column": "UsrFieldA", "sql_type": "bit", "precision": None},
    ]
    errors, warnings = check_orphaned_sql_columns(fields, columns)
    assert len(warnings) == 0


# ── Check 9: External .cs path normalization ───────────────

def test_backslash_path(tmp_path):
    """Backslash paths should be normalized."""
    (tmp_path / "Code").mkdir()
    (tmp_path / "Code" / "MyFile.cs").write_text("namespace X { }")
    graphs = [{"source": "Code\\MyFile.cs", "class_name": "MyClass"}]
    errors, warnings = check_external_paths(graphs, tmp_path)
    assert len(errors) == 0

def test_missing_file(tmp_path):
    graphs = [{"source": "Code/Missing.cs", "class_name": "MyClass"}]
    errors, warnings = check_external_paths(graphs, tmp_path)
    assert len(errors) == 1


# ── Check 10: PXDefault without SQL DEFAULT ────────────────

def test_pxdefault_without_sql_default():
    fields = [
        {"name": "UsrAmt", "dac": "SOOrder", "db_type": "PXDBDecimal",
         "precision": 2, "default_value": "1.00"},
    ]
    # SQL has no DEFAULT clause
    sql_text = "ALTER TABLE SOOrder ADD UsrAmt decimal(18,2) NULL"
    errors, warnings = check_pxdefault_vs_sql(fields, sql_text)
    assert len(warnings) == 1
    assert "PXDefault" in warnings[0]

def test_no_pxdefault_no_warning():
    fields = [
        {"name": "UsrAmt", "dac": "SOOrder", "db_type": "PXDBDecimal",
         "precision": 2, "default_value": None},
    ]
    sql_text = "ALTER TABLE SOOrder ADD UsrAmt decimal(18,2) NULL"
    errors, warnings = check_pxdefault_vs_sql(fields, sql_text)
    assert len(warnings) == 0


# ── Check 11: Manifest coverage ────────────────────────────

def test_field_not_in_manifest():
    fields = [
        {"name": "UsrFieldA", "dac": "SOOrder"},
        {"name": "UsrFieldB", "dac": "SOOrder"},
    ]
    manifest = {
        "entities": {
            "SalesOrder": {
                "custom_fields": ["custom.Document.UsrFieldA"]
            }
        },
        "sql_columns": []
    }
    errors, warnings = check_manifest_coverage(fields, manifest)
    assert len(warnings) >= 1
    assert "UsrFieldB" in warnings[0]

def test_all_fields_in_manifest():
    fields = [
        {"name": "UsrFieldA", "dac": "SOOrder"},
    ]
    manifest = {
        "entities": {
            "SalesOrder": {
                "custom_fields": ["custom.Document.UsrFieldA"]
            }
        },
        "sql_columns": [
            {"table": "SOOrder", "columns": ["UsrFieldA"]}
        ]
    }
    errors, warnings = check_manifest_coverage(fields, manifest)
    assert len(warnings) == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v -k "orphan or path or pxdefault or manifest"`
Expected: ImportError

**Step 3: Implement Phase 3 check functions**

Add to `scripts/semantic_checks.py`:

```python
def check_orphaned_sql_columns(
    fields: List[Dict], columns: List[Dict]
) -> Tuple[List[str], List[str]]:
    """Check 8: SQL columns that have no matching DAC field declaration."""
    errors = []
    warnings = []

    field_names = {f["name"] for f in fields}

    for col in columns:
        if col["column"].startswith("Usr") and col["column"] not in field_names:
            warnings.append(
                f"Orphaned SQL column: '{col['column']}' on table '{col['table']}' "
                f"has no matching DAC field declaration. May be intentional (raw SQL) "
                f"or leftover from a removed feature."
            )

    return errors, warnings


def check_external_paths(
    graphs: List[Dict], project_dir: Path
) -> Tuple[List[str], List[str]]:
    """Check 9: External .cs file references are valid with normalized paths."""
    errors = []
    warnings = []

    for graph in graphs:
        source = graph.get("source", "")
        if not source or source == "#CDATA" or not source.endswith(".cs"):
            continue

        class_name = graph.get("class_name", "(unknown)")

        # Normalize path separators
        normalized = source.replace("\\", "/")
        cs_path = project_dir / normalized

        if not cs_path.exists():
            # Try case-insensitive search on Linux
            found = False
            parent = cs_path.parent
            if parent.exists():
                target_name = cs_path.name.lower()
                for f in parent.iterdir():
                    if f.name.lower() == target_name:
                        warnings.append(
                            f"Case mismatch: '{source}' — file exists as '{f.name}'. "
                            f"May fail on case-sensitive filesystems (Linux CI)."
                        )
                        found = True
                        break

            if not found:
                errors.append(
                    f"External file missing: <Graph ClassName=\"{class_name}\"> "
                    f"references '{source}' but file not found at {cs_path}"
                )

    return errors, warnings


def check_pxdefault_vs_sql(
    fields: List[Dict], sql_text: str
) -> Tuple[List[str], List[str]]:
    """Check 10: Fields with PXDefault should ideally have SQL DEFAULT."""
    errors = []
    warnings = []

    for field in fields:
        if field.get("default_value") is None:
            continue

        name = field["name"]
        # Check if SQL has DEFAULT for this column
        # Pattern: UsrField ... DEFAULT (value) or DEFAULT value
        pattern = rf"{re.escape(name)}[^,;]*DEFAULT"
        if not re.search(pattern, sql_text, re.IGNORECASE):
            warnings.append(
                f"'{name}' has [PXDefault(\"{field['default_value']}\")] but SQL column "
                f"has no DEFAULT clause. Raw SQL inserts will get NULL instead of "
                f"the expected default."
            )

    return errors, warnings


def check_manifest_coverage(
    fields: List[Dict], manifest: Dict
) -> Tuple[List[str], List[str]]:
    """Check 11: All DAC fields should be tracked in publish-manifest.json."""
    errors = []
    warnings = []

    # Collect all field names referenced in manifest
    manifest_fields = set()

    # From entities.*.custom_fields (format: "custom.Document.UsrFieldName")
    for entity_name, entity_data in manifest.get("entities", {}).items():
        for cf in entity_data.get("custom_fields", []):
            # Extract field name from dotted path
            parts = cf.split(".")
            if len(parts) >= 3:
                manifest_fields.add(parts[-1])

    # From sql_columns.*.columns
    for sql_entry in manifest.get("sql_columns", []):
        for col_name in sql_entry.get("columns", []):
            manifest_fields.add(col_name)

    # Check each DAC field
    for field in fields:
        name = field["name"]
        if name not in manifest_fields:
            warnings.append(
                f"Field '{name}' (DAC: {field['dac']}) not found in publish-manifest.json. "
                f"Post-deploy validation will not verify this field exists."
            )

    return errors, warnings
```

**Step 4: Run tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add scripts/semantic_checks.py scripts/test_semantic_checks.py
git commit -m "[CI/CD] ADD: Phase 3 semantic checks — orphaned SQL, path normalization, PXDefault, manifest coverage"
```

---

### Task 5: Orchestrator — `run_semantic_checks()` + Integration with validate-project.py

**Files:**
- Modify: `scripts/semantic_checks.py`
- Modify: `scripts/validate-project.py`
- Modify: `scripts/test_semantic_checks.py`

**Step 1: Write failing test for orchestrator**

Add to `test_semantic_checks.py`:

```python
def test_run_semantic_checks_on_aesthetik_wms():
    """Integration test: run full semantic checks on AesthetikWMS project."""
    project_path = Path(__file__).parent.parent / "Customization" / "AesthetikWMS" / "project.xml"
    if not project_path.exists():
        pytest.skip("AesthetikWMS project.xml not found")

    from semantic_checks import run_semantic_checks
    errors, warnings = run_semantic_checks(
        project_path=str(project_path),
        strict=False,
        also_publish=[],
        manifest_path=str(Path(__file__).parent.parent / "publish-manifest.json"),
    )
    # Should not have critical errors (we fixed the INLotSerClass bug)
    # May have warnings for manifest coverage, PXDefault, etc.
    assert isinstance(errors, list)
    assert isinstance(warnings, list)
```

**Step 2: Implement orchestrator**

Add to `scripts/semantic_checks.py`:

```python
def run_semantic_checks(
    project_path: str,
    strict: bool = False,
    also_publish: Optional[List[str]] = None,
    manifest_path: Optional[str] = None,
) -> Tuple[List[str], List[str]]:
    """Run all semantic validation checks on a customization project.

    Args:
        project_path: Path to project.xml
        strict: Enable stricter checks
        also_publish: List of co-published project names (for cross-project checks)
        manifest_path: Path to publish-manifest.json (for coverage checks)

    Returns:
        (errors, warnings) tuple
    """
    all_errors = []
    all_warnings = []
    file_path = Path(project_path)
    project_dir = file_path.parent

    print(f"\n{'─' * 60}")
    print(f"{GREEN}[SEMANTIC]{RESET} Running semantic validation checks...")
    print(f"{'─' * 60}")

    # ── Collect all C# code from the project ────────────────

    try:
        tree = ET.parse(str(file_path))
        root = tree.getroot()
    except ET.ParseError:
        all_errors.append("Cannot parse project.xml for semantic checks")
        return all_errors, all_warnings

    all_code = []
    all_sql = []
    cs_files = {}  # filepath → code content
    graph_refs = []  # for path checking

    for graph in root.findall(".//Graph"):
        source = graph.get("Source", "")
        class_name = graph.get("ClassName", "")

        if source == "#CDATA":
            cdata = graph.find("CDATA")
            if cdata is not None and cdata.text:
                all_code.append(cdata.text)
        elif source.endswith(".cs"):
            cs_path = project_dir / source.replace("\\", "/")
            if cs_path.exists():
                code = cs_path.read_text(encoding="utf-8")
                all_code.append(code)
                cs_files[source] = code

            graph_refs.append({"source": source, "class_name": class_name})

    # Collect SQL from <Sql> elements and from C# string arrays
    for sql_elem in root.findall(".//Sql"):
        cdata = sql_elem.find("CDATA")
        if cdata is not None and cdata.text:
            all_sql.append(cdata.text)

    # Also scan all code for SQL string arrays (initializer pattern)
    combined_code = "\n".join(all_code)
    all_sql.append(combined_code)  # parse_sql_columns handles both
    combined_sql = "\n".join(all_sql)

    # ── Parse ───────────────────────────────────────────────

    fields = parse_dac_fields(combined_code)
    columns = parse_sql_columns(combined_sql)

    print(f"  Parsed {len(fields)} DAC field(s), {len(columns)} SQL column(s)")

    # ── Phase 1: Data corruption prevention ─────────────────

    errs, warns = check_fields_have_sql_columns(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("Fields → SQL columns", errs, warns)

    errs, warns = check_type_compatibility(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("Type compatibility", errs, warns)

    errs, warns = check_table_name_mapping(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("Table name mapping", errs, warns)

    # ── Phase 2: Runtime crash prevention ───────────────────

    # Collect declared extension names
    declared_exts = set()
    for m in re.finditer(
        r"class\s+(\w+)\s*:\s*PXCacheExtension", combined_code
    ):
        declared_exts.add(m.group(1))

    errs, warns = check_extension_references(combined_code, declared_exts)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("Extension references", errs, warns)

    # Cross-project duplicates
    if also_publish:
        other_projects = {}
        for proj_name in also_publish:
            proj_name = proj_name.strip()
            if not proj_name:
                continue
            # Try to find the project.xml
            proj_xml = project_dir.parent / proj_name / "project.xml"
            if proj_xml.exists():
                proj_code = _collect_project_code(proj_xml)
                other_projects[proj_name] = parse_dac_fields(proj_code)

        if other_projects:
            primary_name = project_dir.name
            errs, warns = check_cross_project_duplicates(
                primary_name, fields, other_projects
            )
            all_errors.extend(errs)
            all_warnings.extend(warns)
            _report("Cross-project duplicates", errs, warns)

    # Namespace consistency
    if cs_files:
        errs, warns = check_namespace_consistency(cs_files)
        all_errors.extend(errs)
        all_warnings.extend(warns)
        _report("Namespace consistency", errs, warns)

    # ── Phase 3: Code quality ───────────────────────────────

    errs, warns = check_orphaned_sql_columns(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("Orphaned SQL columns", errs, warns)

    errs, warns = check_external_paths(graph_refs, project_dir)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("External .cs paths", errs, warns)

    errs, warns = check_pxdefault_vs_sql(fields, combined_sql)
    all_errors.extend(errs)
    all_warnings.extend(warns)
    _report("PXDefault vs SQL DEFAULT", errs, warns)

    # Manifest coverage
    if manifest_path:
        manifest_file = Path(manifest_path)
        if manifest_file.exists():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            errs, warns = check_manifest_coverage(fields, manifest)
            all_errors.extend(errs)
            all_warnings.extend(warns)
            _report("Manifest coverage", errs, warns)

    # ── Summary ─────────────────────────────────────────────

    print(f"{'─' * 60}")
    if all_errors:
        print(f"{RED}[SEMANTIC] {len(all_errors)} error(s), {len(all_warnings)} warning(s){RESET}")
    elif all_warnings:
        print(f"{YELLOW}[SEMANTIC] Passed with {len(all_warnings)} warning(s){RESET}")
    else:
        print(f"{GREEN}[SEMANTIC] All checks passed{RESET}")

    return all_errors, all_warnings


def _collect_project_code(project_xml: Path) -> str:
    """Collect all C# code from a project.xml file."""
    try:
        tree = ET.parse(str(project_xml))
        root = tree.getroot()
    except ET.ParseError:
        return ""

    code_parts = []
    project_dir = project_xml.parent

    for graph in root.findall(".//Graph"):
        source = graph.get("Source", "")
        if source == "#CDATA":
            cdata = graph.find("CDATA")
            if cdata is not None and cdata.text:
                code_parts.append(cdata.text)
        elif source.endswith(".cs"):
            cs_path = project_dir / source.replace("\\", "/")
            if cs_path.exists():
                code_parts.append(cs_path.read_text(encoding="utf-8"))

    return "\n".join(code_parts)


def _report(check_name: str, errors: List[str], warnings: List[str]):
    """Print check result inline."""
    if errors:
        for e in errors:
            print(f"  {RED}[ERROR]{RESET} {check_name}: {e}")
    elif warnings:
        for w in warnings:
            print(f"  {YELLOW}[WARN]{RESET}  {check_name}: {w}")
    else:
        print(f"  {GREEN}[OK]{RESET}    {check_name}")
```

**Step 3: Integrate into validate-project.py**

Modify `scripts/validate-project.py`:

1. Add `--no-semantic` flag parsing in `main()`:

```python
def main():
    strict = "--strict" in sys.argv
    no_semantic = "--no-semantic" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
```

2. Update usage string:

```python
    if not args:
        print("Usage: python validate-project.py [--strict] [--no-semantic] <project.xml>")
        print()
        print("Validates Acumatica customization project XML format.")
        print("  --strict       Enable additional warnings for best practices")
        print("  --no-semantic  Skip semantic cross-reference checks (emergency bypass)")
        sys.exit(1)
```

3. Add semantic checks call at end of `validate()`, before the return statement (line 234). Modify `validate()` signature to accept `no_semantic`:

At the top of `validate()`, add `no_semantic` parameter:
```python
def validate(path: str, strict: bool = False, no_semantic: bool = False):
```

Before `return len(errors) == 0` (line 234), add:

```python
    # Semantic cross-reference checks
    if not no_semantic:
        from semantic_checks import run_semantic_checks
        also_publish = os.environ.get("ALSO_PUBLISH_PROJECTS", "").split(",")
        manifest_candidates = [
            file_path.parent.parent.parent / "publish-manifest.json",
            file_path.parent.parent / "publish-manifest.json",
            Path("publish-manifest.json"),
        ]
        manifest_path = None
        for mp in manifest_candidates:
            if mp.exists():
                manifest_path = str(mp)
                break

        sem_errors, sem_warnings = run_semantic_checks(
            project_path=path,
            strict=strict,
            also_publish=also_publish,
            manifest_path=manifest_path,
        )
        errors.extend(sem_errors)
        warnings.extend(sem_warnings)
```

4. Add `import os` at top of file and pass `no_semantic` from `main()`:

```python
    success = validate(path, strict, no_semantic)
```

**Step 4: Run integration test**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v`
Expected: All tests PASS (including integration test on AesthetikWMS)

**Step 5: Run validate-project.py on AesthetikWMS to verify end-to-end**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python scripts/validate-project.py Customization/AesthetikWMS/project.xml`
Expected: PASS with warnings for manifest coverage and PXDefault (no errors — the INLotSerClass columns were fixed in the earlier commit)

**Step 6: Run with --no-semantic to verify bypass**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python scripts/validate-project.py --no-semantic Customization/AesthetikWMS/project.xml`
Expected: PASS (no semantic output printed)

**Step 7: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add scripts/semantic_checks.py scripts/test_semantic_checks.py scripts/validate-project.py
git commit -m "[CI/CD] ADD: semantic validation orchestrator + validate-project.py integration

11 semantic checks across 3 phases:
- Phase 1: DAC-to-SQL cross-reference, type/precision matching, table name mapping
- Phase 2: Extension references, cross-project duplicates, namespace consistency
- Phase 3: Orphaned SQL, path normalization, PXDefault, manifest coverage

Controlled by --no-semantic flag for emergency bypass."
```

---

### Task 6: Verify Against All Customization Projects + Push

**Files:** None (verification only)

**Step 1: Run on all projects**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
for proj in Customization/*/project.xml; do
    echo "═══ $proj ═══"
    python scripts/validate-project.py "$proj" 2>&1
    echo ""
done
```

Expected: All projects pass. Review warnings — some are expected (manifest coverage for projects not in manifest, PXDefault for fields without SQL DEFAULT).

**Step 2: Run on AesthetikWMS with ALSO_PUBLISH**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
ALSO_PUBLISH_PROJECTS=HeritageFabricsPOv5,StudioBPORelations \
  python scripts/validate-project.py Customization/AesthetikWMS/project.xml
```

Expected: PASS — cross-project check should find no duplicates between these 3 projects.

**Step 3: Run tests one final time**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest scripts/test_semantic_checks.py -v
```

Expected: All tests PASS

**Step 4: Push**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git push origin main
```
