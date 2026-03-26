#!/usr/bin/env python3
"""
Acumatica Customization Semantic Validator

Cross-references DAC field declarations in C# code against SQL column creation
statements. Catches bugs like declaring a field in a DAC extension without
creating the corresponding database column.

Usage:
    from semantic_checks import parse_dac_fields, parse_sql_columns
"""

import re
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
