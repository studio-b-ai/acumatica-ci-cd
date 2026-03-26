#!/usr/bin/env python3
"""
Acumatica Customization Semantic Validator

Cross-references DAC field declarations in C# code against SQL column creation
statements. Catches bugs like declaring a field in a DAC extension without
creating the corresponding database column.

Usage:
    from semantic_checks import parse_dac_fields, parse_sql_columns, run_semantic_checks
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

# ── Colour codes ──────────────────────────────────────────────────────────
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"

# ── DAC class name → SQL table name ──────────────────────────────────────
# Most Acumatica DAC class names match the SQL table exactly.  This mapping
# covers the known exceptions where the C# class differs from the physical
# table.  Unmapped DACs are assumed to have the same name as the table.
DAC_TO_TABLE: dict[str, str] = {
    # Accounts
    "Customer": "BAccount",
    "Vendor": "BAccount",
    "BAccount": "BAccount",
    "EPEmployee": "BAccountR",
    # Inventory
    "InventoryItem": "InventoryItem",
    "INLotSerialStatus": "INLotSerialStatus",
    "INLotSerialClass": "INLotSerClass",
    "INSetup": "INSetup",
    "INItemClass": "INItemClass",
    "INRegister": "INRegister",
    "INTran": "INTran",
    # Purchase
    "POOrder": "POOrder",
    "POLine": "POLine",
    "POReceipt": "POReceipt",
    "POReceiptLine": "POReceiptLine",
    # Sales
    "SOOrder": "SOOrder",
    "SOLine": "SOLine",
    "SOShipment": "SOShipment",
    "SOShipLine": "SOShipLine",
    "SOPackageDetailEx": "SOPackageDetail",
    # AR/AP
    "ARInvoice": "ARRegister",
    "APInvoice": "APRegister",
    "ARPayment": "ARRegister",
    "APPayment": "APRegister",
    # CRM
    "CRCase": "CRCase",
    "CRLead": "Contact",
    "Contact": "Contact",
    "Address": "Address",
    # Other
    "CSAnswers": "CSAnswers",
    "Note": "Note",
    "NoteDoc": "NoteDoc",
}

# ── PXDB attribute → expected SQL type family ────────────────────────────
# Keys are the PX.Data attribute names (without brackets), values are the
# canonical SQL Server type that Acumatica maps them to.
PXDB_TO_SQL: dict[str, str] = {
    "PXDBBool": "bit",
    "PXDBInt": "int",
    "PXDBDecimal": "decimal",
    "PXDBString": "nvarchar",
    "PXDBDate": "datetime",
    "PXDBDateTime": "datetime",
    "PXDBFloat": "float",
    "PXDBDouble": "float",
    "PXDBLong": "bigint",
    "PXDBShort": "smallint",
    "PXDBByte": "tinyint",
    "PXDBGuid": "uniqueidentifier",
    "PXDBBinary": "varbinary",
    "PXDBText": "nvarchar",
    "PXDBPackedIntegerArray": "varbinary",
}


def _strip_comments(code: str) -> str:
    """Remove C# single-line and multi-line comments from source code.

    Respects string literals — won't strip ``//`` inside a quoted string.
    Good enough for attribute/property parsing; does NOT handle raw strings
    or interpolated expressions with embedded quotes.
    """
    # Multi-line comments  /* ... */
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    # Single-line comments  // ...
    code = re.sub(r"//[^\n]*", "", code)
    return code


# ── DAC field parser ─────────────────────────────────────────────────────

# Matches:  PXCacheExtension<SomeDAC>
_RE_CACHE_EXT = re.compile(
    r"class\s+\w+\s*:\s*PXCacheExtension<([A-Za-z0-9_.]+)>"
)

# Matches:  [PXDBDecimal(2)]  or  [PXDBBool]  or  [PXDBString(30, IsUnicode = true)]
_RE_PXDB_ATTR = re.compile(
    r"\[\s*(PXDB\w+)"          # attribute name
    r"(?:\(([^)]*)\))?"        # optional parenthesised args
    r"\s*\]"
)

# Matches:  [PXDefault(TypeCode.Decimal, "1.00")]  or  [PXDefault(true)]  or
#           [PXDefault(false, PersistingCheck = ...)]  or  [PXDefault(5)]
_RE_PXDEFAULT = re.compile(
    r"\[\s*PXDefault\s*\(([^)]*)\)\s*\]"
)

# Matches the property declaration:  public decimal? UsrFoo { get; set; }
_RE_PROPERTY = re.compile(
    r"public\s+\w+\??\s+(Usr\w+)\s*\{\s*get\s*;"
)


def _extract_precision(attr_name: str, args_str: Optional[str]) -> Optional[int]:
    """Pull the first integer argument from a PXDB attribute's argument list."""
    if args_str is None:
        return None
    # Take the first token that looks like a bare integer
    m = re.match(r"\s*(\d+)", args_str)
    return int(m.group(1)) if m else None


def _extract_default(block: str) -> Optional[str]:
    """Extract the default value from a [PXDefault(...)] attribute in a block."""
    m = _RE_PXDEFAULT.search(block)
    if not m:
        return None
    args = m.group(1).strip()

    # TypeCode pattern:  TypeCode.Decimal, "1.00"
    tc = re.match(r'TypeCode\.\w+\s*,\s*"([^"]*)"', args)
    if tc:
        return tc.group(1)

    # Simple literal:  true / false / integer / negative integer
    # Strip trailing named args like ", PersistingCheck = ..."
    first_arg = args.split(",")[0].strip()
    if re.match(r"^-?\d+$", first_arg):
        return first_arg
    if first_arg.lower() in ("true", "false"):
        return first_arg.lower()

    # String literal:  "-C{0}"
    sq = re.match(r'^"([^"]*)"', first_arg)
    if sq:
        return sq.group(1)

    return None


def parse_dac_fields(code: str) -> list[dict]:
    """Parse C# DAC extension source code and extract persisted field declarations.

    Returns a list of dicts, each with keys:
        name         – field name (e.g. "UsrPGMinRemnant")
        db_type      – PXDB attribute name (e.g. "PXDBDecimal")
        precision    – first numeric arg from attribute, or None
        dac          – base DAC class name (e.g. "INSetup")
        default_value – extracted default, or None
    """
    code = _strip_comments(code)

    results: list[dict] = []

    # Walk the code looking for PXCacheExtension declarations to track current DAC
    # Strategy: split into class-level blocks by finding each extension header,
    # then parse fields within each block.

    # Find all extension start positions
    ext_matches = list(_RE_CACHE_EXT.finditer(code))
    if not ext_matches:
        return results

    for i, ext_match in enumerate(ext_matches):
        dac_name = ext_match.group(1)
        # Strip namespace prefix if present (e.g. "PX.Objects.SO.SOShipment" → "SOShipment")
        if "." in dac_name:
            dac_name = dac_name.rsplit(".", 1)[1]

        start = ext_match.start()
        end = ext_matches[i + 1].start() if i + 1 < len(ext_matches) else len(code)
        block = code[start:end]

        # Find all PXDB attributes and the Usr* property that follows
        # We scan for [PXDB...] then look ahead for the property declaration
        pos = 0
        while pos < len(block):
            attr_m = _RE_PXDB_ATTR.search(block, pos)
            if not attr_m:
                break

            attr_name = attr_m.group(1)
            attr_args = attr_m.group(2)

            # Look for the property declaration after this attribute
            prop_m = _RE_PROPERTY.search(block, attr_m.end())
            if not prop_m:
                pos = attr_m.end()
                continue

            # Make sure there isn't another PXDB attribute between this one
            # and the property (which would mean this attribute belongs to a
            # different field)
            next_attr = _RE_PXDB_ATTR.search(block, attr_m.end())
            if next_attr and next_attr.start() < prop_m.start():
                pos = attr_m.end()
                continue

            field_name = prop_m.group(1)
            precision = _extract_precision(attr_name, attr_args)

            # Extract default from the block between attribute and property
            attr_block = block[attr_m.start():prop_m.end()]
            default_value = _extract_default(attr_block)

            results.append({
                "name": field_name,
                "db_type": attr_name,
                "precision": precision,
                "dac": dac_name,
                "default_value": default_value,
            })

            pos = prop_m.end()

    return results


# ── SQL column parser ────────────────────────────────────────────────────

# Matches ALTER TABLE ... ADD ... patterns (both bare and IF NOT EXISTS wrapped)
_RE_ALTER_TABLE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+(\w+)\s+"
    r"(\w+)"                     # sql type name
    r"(?:\((\d+(?:,\s*\d+)?)\))?"  # optional (precision) or (precision, scale)
    r"\s*NULL",
    re.IGNORECASE,
)


def parse_sql_columns(code: str) -> list[dict]:
    """Parse SQL ALTER TABLE ADD statements from project XML or raw SQL.

    Returns a list of dicts, each with keys:
        table     – table name
        column    – column name
        sql_type  – SQL type (lowercase, e.g. "decimal", "bit", "nvarchar")
        precision – for decimal(p,s) returns the *scale* (s); for nvarchar(n)
                    returns n; for types without precision returns None
    """
    results: list[dict] = []

    for m in _RE_ALTER_TABLE.finditer(code):
        table = m.group(1)
        column = m.group(2)
        sql_type = m.group(3).lower()
        size_str = m.group(4)

        precision: Optional[int] = None
        if size_str:
            parts = [p.strip() for p in size_str.split(",")]
            if len(parts) == 2:
                # decimal(18, 2) → scale is the second number
                precision = int(parts[1])
            else:
                # nvarchar(30) → the single number
                precision = int(parts[0])

        results.append({
            "table": table,
            "column": column,
            "sql_type": sql_type,
            "precision": precision,
        })

    return results


# ── Phase 1 check functions ────────────────────────────────────────────

def _resolve_table(dac: str) -> str:
    """Resolve a DAC class name to its SQL table name."""
    return DAC_TO_TABLE.get(dac, dac)


def _match_field_to_column(
    field: dict, columns: list[dict]
) -> Optional[dict]:
    """Find the SQL column matching a DAC field, using DAC_TO_TABLE resolution."""
    table = _resolve_table(field["dac"])
    for col in columns:
        if col["column"] == field["name"] and col["table"] == table:
            return col
    # Fallback: match by column name only (for unmapped DACs or custom tables)
    for col in columns:
        if col["column"] == field["name"]:
            return col
    return None


def check_fields_have_sql_columns(
    fields: list[dict], columns: list[dict]
) -> tuple[list[str], list[str]]:
    """Every DAC field must have a matching SQL column.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []
    for field in fields:
        col = _match_field_to_column(field, columns)
        if col is None:
            table = _resolve_table(field["dac"])
            errors.append(
                f"DAC field {field['dac']}.{field['name']} has no SQL column "
                f"(expected ALTER TABLE {table} ADD {field['name']})"
            )
    return errors, warnings


def check_type_compatibility(
    fields: list[dict], columns: list[dict]
) -> tuple[list[str], list[str]]:
    """Verify PXDB attribute → SQL type and precision consistency.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []
    for field in fields:
        col = _match_field_to_column(field, columns)
        if col is None:
            continue  # Missing column is caught by check_fields_have_sql_columns

        expected_sql = PXDB_TO_SQL.get(field["db_type"])
        if expected_sql is None:
            warnings.append(
                f"Unknown PXDB type '{field['db_type']}' on {field['dac']}.{field['name']}"
            )
            continue

        if col["sql_type"] != expected_sql:
            errors.append(
                f"Type mismatch: {field['dac']}.{field['name']} is {field['db_type']} "
                f"(expects SQL {expected_sql}) but SQL column is {col['sql_type']}"
            )

        if field["precision"] is not None and col["precision"] is not None:
            if field["precision"] != col["precision"]:
                errors.append(
                    f"Precision mismatch: {field['dac']}.{field['name']} has "
                    f"{field['db_type']}({field['precision']}) but SQL is "
                    f"{col['sql_type']}(...,{col['precision']})"
                )

    return errors, warnings


def check_table_name_mapping(
    fields: list[dict], columns: list[dict]
) -> tuple[list[str], list[str]]:
    """Check if SQL uses DAC name as table name when it should use the mapped name.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build reverse mapping: table → set of known DAC names that map to it
    table_to_dacs: dict[str, set[str]] = {}
    for dac, table in DAC_TO_TABLE.items():
        table_to_dacs.setdefault(table, set()).add(dac)

    # Collect all SQL table names used
    sql_tables = {col["table"] for col in columns}

    # Collect all DAC names from fields
    dac_names = {f["dac"] for f in fields}

    for dac in dac_names:
        if dac not in DAC_TO_TABLE:
            # Check if a SQL table matches the DAC name — if it does, fine
            # If not, warn about unmapped DAC
            if dac not in sql_tables:
                warnings.append(
                    f"DAC '{dac}' not in DAC_TO_TABLE mapping and no SQL table "
                    f"with that name found"
                )
            continue

        expected_table = DAC_TO_TABLE[dac]
        if dac == expected_table:
            continue  # Same name, no risk

        # Check if SQL uses the DAC name instead of the correct table name
        if dac in sql_tables:
            errors.append(
                f"SQL uses table name '{dac}' but this DAC maps to table "
                f"'{expected_table}' — ALTER TABLE should reference '{expected_table}'"
            )

    return errors, warnings


# ── Phase 2 check functions ────────────────────────────────────────────

_RE_GET_EXTENSION = re.compile(r"GetExtension<(\w+)>\s*\(\s*\)")


def check_extension_references(
    code: str, declared_extensions: set[str]
) -> tuple[list[str], list[str]]:
    """Check that GetExtension<T>() calls reference declared extensions.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []
    clean = _strip_comments(code)
    for m in _RE_GET_EXTENSION.finditer(clean):
        ext_name = m.group(1)
        if ext_name not in declared_extensions:
            warnings.append(
                f"GetExtension<{ext_name}>() references undeclared extension "
                f"(may be a base framework extension)"
            )
    return errors, warnings


def check_cross_project_duplicates(
    primary_name: str,
    primary_fields: list[dict],
    other_projects: dict[str, list[dict]],
) -> tuple[list[str], list[str]]:
    """Detect the same (dac, field_name) declared in multiple projects.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build index: (dac, name) → list of project names
    field_owners: dict[tuple[str, str], list[str]] = {}
    for f in primary_fields:
        key = (f["dac"], f["name"])
        field_owners.setdefault(key, []).append(primary_name)

    for proj_name, proj_fields in other_projects.items():
        for f in proj_fields:
            key = (f["dac"], f["name"])
            field_owners.setdefault(key, []).append(proj_name)

    for (dac, name), owners in field_owners.items():
        if len(owners) > 1:
            errors.append(
                f"Duplicate field {dac}.{name} declared in: {', '.join(owners)}"
            )

    return errors, warnings


_RE_NAMESPACE = re.compile(r"^\s*namespace\s+([\w.]+)", re.MULTILINE)


def check_namespace_consistency(
    files: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Warn if any file uses a different namespace than the majority.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    ns_to_files: dict[str, list[str]] = {}
    for filepath, code in files.items():
        m = _RE_NAMESPACE.search(code)
        if m:
            ns = m.group(1)
            ns_to_files.setdefault(ns, []).append(filepath)

    if len(ns_to_files) <= 1:
        return errors, warnings

    # Find majority namespace
    majority_ns = max(ns_to_files, key=lambda ns: len(ns_to_files[ns]))
    for ns, file_list in ns_to_files.items():
        if ns != majority_ns:
            for fp in file_list:
                warnings.append(
                    f"'{fp}' uses namespace '{ns}' (majority is '{majority_ns}')"
                )

    return errors, warnings


# ── Phase 3 check functions ────────────────────────────────────────────


def check_orphaned_sql_columns(
    fields: list[dict], columns: list[dict]
) -> tuple[list[str], list[str]]:
    """Warn for SQL columns starting with 'Usr' that have no matching DAC field.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    field_names = {f["name"] for f in fields}

    for col in columns:
        if col["column"].startswith("Usr") and col["column"] not in field_names:
            warnings.append(
                f"SQL column {col['table']}.{col['column']} has no matching DAC field"
            )

    return errors, warnings


def check_external_paths(
    graphs: list[dict], project_dir: str
) -> tuple[list[str], list[str]]:
    """Check that external .cs file references in <Graph> elements exist.

    Args:
        graphs: list of dicts with keys: source, class_name
        project_dir: path to project directory (parent of project.xml)

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    project_path = Path(project_dir)

    for graph in graphs:
        source = graph.get("source", "")
        class_name = graph.get("class_name", "(unknown)")

        if not source or source == "#CDATA" or not source.endswith(".cs"):
            continue

        # Normalize backslashes to forward slashes
        normalized = source.replace("\\", "/")
        cs_path = project_path / normalized

        if cs_path.exists():
            continue

        # Try case-insensitive match
        found_case_mismatch = False
        parent = cs_path.parent
        if parent.exists():
            target_name = cs_path.name.lower()
            for entry in parent.iterdir():
                if entry.name.lower() == target_name:
                    warnings.append(
                        f"<Graph ClassName=\"{class_name}\"> path case mismatch: "
                        f"'{source}' → actual '{entry.name}'"
                    )
                    found_case_mismatch = True
                    break

        if not found_case_mismatch:
            errors.append(
                f"<Graph ClassName=\"{class_name}\"> references missing file: {source}"
            )

    return errors, warnings


def check_pxdefault_vs_sql(
    fields: list[dict], sql_text: str
) -> tuple[list[str], list[str]]:
    """Warn for fields with PXDefault but no SQL DEFAULT near that column.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    sql_upper = sql_text.upper()

    for field in fields:
        if field["default_value"] is None:
            continue

        # Look for DEFAULT near the column name in SQL
        # Pattern: column name followed (within ~100 chars) by DEFAULT
        pattern = re.compile(
            re.escape(field["name"]) + r".{0,100}DEFAULT",
            re.IGNORECASE,
        )
        if not pattern.search(sql_text):
            warnings.append(
                f"{field['dac']}.{field['name']} has PXDefault({field['default_value']}) "
                f"but no SQL DEFAULT clause"
            )

    return errors, warnings


def check_manifest_coverage(
    fields: list[dict], manifest: dict
) -> tuple[list[str], list[str]]:
    """Warn for fields not found in the publish manifest.

    Args:
        manifest: parsed JSON from publish-manifest.json

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Collect all field names from manifest custom_fields and sql_columns
    manifest_fields: set[str] = set()

    entities = manifest.get("entities", {})
    for entity_data in entities.values():
        for cf in entity_data.get("custom_fields", []):
            # custom_fields are like "custom.Document.UsrHubSpotDealId"
            parts = cf.split(".")
            if parts:
                manifest_fields.add(parts[-1])

    for sql_entry in manifest.get("sql_columns", []):
        for col_name in sql_entry.get("columns", []):
            manifest_fields.add(col_name)

    if not manifest_fields:
        return errors, warnings

    for field in fields:
        if field["name"] not in manifest_fields:
            warnings.append(
                f"{field['dac']}.{field['name']} not in publish-manifest.json"
            )

    return errors, warnings


# ── Orchestrator ────────────────────────────────────────────────────────


def _collect_project_code(project_xml_path: str) -> tuple[str, str, list[dict], dict[str, str]]:
    """Parse project.xml and extract all C# code, SQL text, graph info, and file contents.

    Returns:
        (combined_cs_code, combined_sql_text, graph_list, file_code_map)

    graph_list: list of dicts with keys: source, class_name
    file_code_map: dict of {filepath: code_content} for namespace checking
    """
    tree = ET.parse(project_xml_path)
    root = tree.getroot()
    project_dir = str(Path(project_xml_path).parent)

    cs_parts: list[str] = []
    sql_parts: list[str] = []
    graph_list: list[dict] = []
    file_code_map: dict[str, str] = {}

    # Collect from <Graph> elements
    for graph in root.findall(".//Graph"):
        class_name = graph.get("ClassName", "(missing)")
        source = graph.get("Source", "")

        graph_list.append({"source": source, "class_name": class_name})

        if source == "#CDATA":
            cdata = graph.find("CDATA")
            if cdata is not None and cdata.text:
                cs_parts.append(cdata.text)
                file_code_map[f"inline:{class_name}"] = cdata.text
        elif source and source.endswith(".cs"):
            normalized = source.replace("\\", "/")
            cs_path = Path(project_dir) / normalized
            if cs_path.exists():
                code = cs_path.read_text(encoding="utf-8")
                cs_parts.append(code)
                file_code_map[str(cs_path)] = code

    # Collect from <Sql> elements
    for sql_elem in root.findall(".//Sql"):
        cdata = sql_elem.find("CDATA")
        if cdata is not None and cdata.text:
            sql_parts.append(cdata.text)

    # Also extract SQL from C# initializer string arrays (common pattern for schema installers)
    # Look for quoted SQL strings in C# code
    combined_cs = "\n".join(cs_parts)
    sql_from_cs = re.findall(
        r'"(IF NOT EXISTS.*?ALTER TABLE.*?NULL.*?)"', combined_cs, re.DOTALL
    )
    for sql_str in sql_from_cs:
        sql_parts.append(sql_str)

    return combined_cs, "\n".join(sql_parts), graph_list, file_code_map


def run_semantic_checks(
    project_path: str,
    strict: bool = False,
    also_publish: Optional[list[str]] = None,
    manifest_path: Optional[str] = None,
) -> tuple[list[str], list[str]]:
    """Run all semantic checks on a customization project.

    Args:
        project_path: Path to the project.xml file or its parent directory.
        strict: If True, treat warnings as errors for some checks.
        also_publish: List of other project names to check for cross-project duplicates.
        manifest_path: Path to publish-manifest.json for coverage checks.

    Returns (errors, warnings).
    """
    all_errors: list[str] = []
    all_warnings: list[str] = []

    project_xml = Path(project_path)
    if project_xml.is_dir():
        project_xml = project_xml / "project.xml"
    if not project_xml.exists():
        all_errors.append(f"project.xml not found: {project_xml}")
        return all_errors, all_warnings

    print(f"\n{CYAN}── Semantic Checks ──{RESET}")

    # Parse project and collect code
    try:
        cs_code, sql_text, graphs, file_code_map = _collect_project_code(
            str(project_xml)
        )
    except ET.ParseError as e:
        all_errors.append(f"XML parse error in semantic checks: {e}")
        return all_errors, all_warnings

    # Parse fields and columns
    fields = parse_dac_fields(cs_code)
    columns = parse_sql_columns(sql_text)

    if not fields and not columns:
        print(f"{YELLOW}[SKIP]{RESET}  No DAC fields or SQL columns found")
        return all_errors, all_warnings

    print(f"{GREEN}[OK]{RESET}    Parsed {len(fields)} DAC fields, {len(columns)} SQL columns")

    # ── Phase 1: DAC-to-SQL cross-reference ──

    errs, warns = check_fields_have_sql_columns(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    errs, warns = check_type_compatibility(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    errs, warns = check_table_name_mapping(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    # ── Phase 2: Extension references, cross-project, namespaces ──

    # Collect declared extension class names from the code
    declared_extensions: set[str] = set()
    for m in re.finditer(r"class\s+(\w+)\s*:\s*PXCacheExtension", cs_code):
        declared_extensions.add(m.group(1))

    errs, warns = check_extension_references(cs_code, declared_extensions)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    # Cross-project duplicate check
    if also_publish:
        project_name = project_xml.parent.name
        other_projects: dict[str, list[dict]] = {}

        for other_name in also_publish:
            other_name = other_name.strip()
            if not other_name or other_name == project_name:
                continue
            # Look for sibling project directory
            other_xml = project_xml.parent.parent / other_name / "project.xml"
            if other_xml.exists():
                try:
                    other_cs, _, _, _ = _collect_project_code(str(other_xml))
                    other_fields = parse_dac_fields(other_cs)
                    if other_fields:
                        other_projects[other_name] = other_fields
                except Exception:
                    pass  # Skip unparseable sibling projects

        if other_projects:
            errs, warns = check_cross_project_duplicates(
                project_name, fields, other_projects
            )
            all_errors.extend(errs)
            all_warnings.extend(warns)

    errs, warns = check_namespace_consistency(file_code_map)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    # ── Phase 3: Orphaned SQL, paths, defaults, manifest ──

    errs, warns = check_orphaned_sql_columns(fields, columns)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    errs, warns = check_external_paths(graphs, str(project_xml.parent))
    all_errors.extend(errs)
    all_warnings.extend(warns)

    errs, warns = check_pxdefault_vs_sql(fields, sql_text)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    if manifest_path:
        manifest_file = Path(manifest_path)
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                errs, warns = check_manifest_coverage(fields, manifest)
                all_errors.extend(errs)
                all_warnings.extend(warns)
            except (json.JSONDecodeError, OSError):
                all_warnings.append(f"Could not parse manifest: {manifest_path}")

    # ── Print results ──

    for e in all_errors:
        print(f"{RED}[ERROR]{RESET} {e}")
    for w in all_warnings:
        print(f"{YELLOW}[WARN]{RESET}  {w}")

    if not all_errors and not all_warnings:
        print(f"{GREEN}[OK]{RESET}    All semantic checks passed")
    elif not all_errors:
        print(f"{YELLOW}[OK]{RESET}    Semantic checks passed with {len(all_warnings)} warning(s)")
    else:
        print(
            f"{RED}[FAIL]{RESET}  Semantic checks: "
            f"{len(all_errors)} error(s), {len(all_warnings)} warning(s)"
        )

    return all_errors, all_warnings
