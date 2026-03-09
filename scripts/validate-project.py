#!/usr/bin/env python3
"""
Acumatica Customization Project XML Validator

Validates project.xml format before packaging into a .zip for deployment.
Catches common format errors that cause silent failures or NullReferenceExceptions.

Usage:
    python validate-project.py Customization/_project/project.xml
    python validate-project.py --strict Customization/_project/project.xml
"""

import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

errors = []
warnings = []


def error(msg: str):
    errors.append(msg)
    print(f"{RED}[ERROR]{RESET} {msg}")


def warn(msg: str):
    warnings.append(msg)
    print(f"{YELLOW}[WARN]{RESET}  {msg}")


def ok(msg: str):
    print(f"{GREEN}[OK]{RESET}    {msg}")


def validate(path: str, strict: bool = False):
    """Validate an Acumatica customization project.xml file."""

    file_path = Path(path)
    if not file_path.exists():
        error(f"File not found: {path}")
        return False

    # Parse XML
    try:
        tree = ET.parse(str(file_path))
        root = tree.getroot()
    except ET.ParseError as e:
        error(f"XML parse error: {e}")
        return False

    ok("XML is well-formed")

    # Check 1: Root element must be <Customization>
    if root.tag != "Customization":
        error(f"Root element is <{root.tag}>, must be <Customization>")
        error("This may be a developer-format project.xml (not import format)")
        return False
    ok("Root element is <Customization>")

    # Check 2: level attribute
    level = root.get("level")
    if level is None:
        warn("Missing 'level' attribute on <Customization> (should be \"0\")")
    else:
        ok(f"level=\"{level}\"")

    # Check 3: product-version attribute
    pv = root.get("product-version")
    if pv is None:
        warn("Missing 'product-version' attribute (e.g., \"24.208\")")
    else:
        ok(f"product-version=\"{pv}\"")

    # Check 4: Validate <Sql> elements (ALTER TABLE column creation)
    sql_elements = root.findall(".//Sql")
    for elem in sql_elements:
        name = elem.get("Name", "(unnamed)")
        source = elem.get("Script", "")
        cdata = elem.find("CDATA")
        if cdata is None or not (cdata.text or "").strip():
            error(f"<Sql Name=\"{name}\"> missing or empty CDATA")
        else:
            sql_text = cdata.text or ""
            if "ALTER TABLE" in sql_text and "IF NOT EXISTS" not in sql_text:
                warn(f"<Sql Name=\"{name}\"> has ALTER TABLE without IF NOT EXISTS guard")
            ok(f"<Sql Name=\"{name}\"> validated")

    # Check 5: <Table> elements with IsNewColumn="True"
    # Required for first-time column creation, but causes NullReferenceException
    # on re-import if columns already exist. Warn (not error) so CI passes on
    # initial deploy; remove <Table> elements after first successful publish.
    table_elements = root.findall(".//Table")
    for table in table_elements:
        table_name = table.get("TableName", "(unnamed)")
        columns = table.findall("Column")
        new_columns = [c for c in columns if c.get("IsNewColumn") == "True"]
        if new_columns:
            col_names = ", ".join(c.get("ColumnName", "?") for c in new_columns)
            warn(
                f"<Table TableName=\"{table_name}\"> has IsNewColumn=\"True\" columns: {col_names}\n"
                f"         Required for first-time column creation. REMOVE after first publish\n"
                f"         to avoid NullReferenceException on re-import."
            )
        elif strict:
            warn(
                f"<Table TableName=\"{table_name}\"> present (no IsNewColumn). "
                f"Consider removing — DAC attributes handle column creation."
            )

    if not table_elements:
        ok("No <Table> elements (columns auto-created by DAC attributes)")

    # Check 6: Validate <Graph> elements
    graphs = root.findall(".//Graph")
    if not graphs:
        warn("No <Graph> elements found (no C# code in this project)")
    else:
        for graph in graphs:
            class_name = graph.get("ClassName", "(missing)")
            source = graph.get("Source")
            file_type = graph.get("FileType")

            if not graph.get("ClassName"):
                error("<Graph> missing 'ClassName' attribute")
            if source != "#CDATA":
                error(f"<Graph ClassName=\"{class_name}\"> Source should be \"#CDATA\", got \"{source}\"")
            if file_type != "NewFile":
                warn(f"<Graph ClassName=\"{class_name}\"> FileType should be \"NewFile\", got \"{file_type}\"")

            # Check CDATA content
            cdata = graph.find("CDATA")
            if cdata is None:
                error(f"<Graph ClassName=\"{class_name}\"> missing <CDATA> child element")
                continue

            code = cdata.text or ""
            if not code.strip():
                error(f"<Graph ClassName=\"{class_name}\"> has empty CDATA (no C# code)")
                continue

            # Basic C# validation
            validate_csharp(class_name, code, strict)

            # Runtime safety checks (GetExtension patterns, inquiry guards)
            validate_extension_safety(class_name, code, strict)

            # CRM DAC compatibility checks
            validate_crm_dac_safety(class_name, code, strict)

        ok(f"Found {len(graphs)} <Graph> element(s)")

    # Check 7: Validate <SqlScript> elements
    # NOTE: SM204505 IMPORT rejects <SqlScript> ("Unknown tag SqlScript").
    # DAC [PXDB*] attributes auto-create columns, so SQL is rarely needed.
    # If present, warn that it must be removed before .zip import.
    sql_scripts = root.findall(".//SqlScript")
    for script in sql_scripts:
        name = script.get("Name", "(missing)")
        warn(
            f"<SqlScript Name=\"{name}\"> will be REJECTED by SM204505 import "
            f"(\"Unknown tag SqlScript\"). Remove before packaging .zip — "
            f"DAC [PXDB*] attributes auto-create columns. "
            f"Add SQL via Customization Project Editor if truly needed."
        )
        source = script.get("Source")
        if source != "#CDATA":
            error(f"<SqlScript Name=\"{name}\"> Source should be \"#CDATA\", got \"{source}\"")

        cdata = script.find("CDATA")
        if cdata is None:
            error(f"<SqlScript Name=\"{name}\"> missing <CDATA> child element")
        elif not (cdata.text or "").strip():
            error(f"<SqlScript Name=\"{name}\"> has empty CDATA (no SQL)")
        else:
            sql_text = cdata.text
            # Check for IF NOT EXISTS guards
            if "ALTER TABLE" in sql_text and "IF NOT EXISTS" not in sql_text:
                warn(f"<SqlScript Name=\"{name}\"> has ALTER TABLE without IF NOT EXISTS guard")

    if sql_scripts:
        ok(f"Found {len(sql_scripts)} <SqlScript> element(s) (remove before import)")

    return len(errors) == 0


def validate_csharp(class_name: str, code: str, strict: bool):
    """Basic C# code validation for CDATA blocks."""

    # Check for balanced braces
    open_count = code.count("{")
    close_count = code.count("}")
    if open_count != close_count:
        error(
            f"{class_name}: Unbalanced braces — {open_count} open, {close_count} close"
        )

    # Check for namespace
    if "namespace " not in code:
        warn(f"{class_name}: No namespace declaration found")

    # Check for IsActive method (required for extensions)
    if "PXCacheExtension" in code or "PXGraphExtension" in code:
        if "IsActive" not in code:
            error(f"{class_name}: Extension class missing IsActive() method")

    # Check for known problematic types (skip comments)
    code_no_comments = re.sub(r"///.*$", "", code, flags=re.MULTILINE)  # strip /// doc comments
    code_no_comments = re.sub(r"//.*$", "", code_no_comments, flags=re.MULTILINE)  # strip // comments
    code_no_comments = re.sub(r"/\*.*?\*/", "", code_no_comments, flags=re.DOTALL)  # strip /* */ blocks
    problematic_types = {
        "ARCustomerClass": "Not a public type in v24.2 (CS0246). Use PX.Objects.AR.CustomerClass",
    }
    for bad_type, fix in problematic_types.items():
        if bad_type in code_no_comments:
            error(f"{class_name}: References '{bad_type}' — {fix}")

    # Check custom field naming convention
    field_pattern = re.findall(r"public\s+\w+\??\s+(Usr\w+)\s*\{", code)
    for field in field_pattern:
        if not field.startswith("Usr"):
            warn(f"{class_name}: Field '{field}' should start with 'Usr' prefix")

    # Check BQL field naming (should be lowercase first letter)
    bql_pattern = re.findall(r"public\s+abstract\s+class\s+(\w+)\s*:", code)
    for bql_class in bql_pattern:
        if bql_class[0].isupper() and bql_class.startswith("Usr"):
            warn(
                f"{class_name}: BQL field class '{bql_class}' should start lowercase "
                f"(e.g., 'usr{bql_class[3:]}')"
            )

    if strict:
        # Check for PXUIField on all PXDBx fields
        pxdb_fields = re.findall(r"\[PXDB\w+[^\]]*\]\s*\n\s*(?!\[PXUIField)", code)
        if pxdb_fields:
            warn(f"{class_name}: Some [PXDB*] fields may be missing [PXUIField] attribute")


def validate_extension_safety(class_name: str, code: str, strict: bool):
    """Detect unsafe extension patterns that compile but crash at runtime.

    These patterns cause NullReferenceException or InvalidCastException on
    inquiry result DACs and foreign-graph records where extension collections
    may not be initialized.
    """

    # Strip comments to avoid false positives
    clean = re.sub(r"///.*$", "", code, flags=re.MULTILINE)
    clean = re.sub(r"//.*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)

    # Rule 1: e.Row.GetExtension<T>() in inquiry/projection graph extensions
    # HIGH risk — crashes on inquiry result DACs (InventoryAllocDetEnqResult, etc.)
    # Safe alternative: e.Cache.GetValue(e.Row, "FieldName")
    # Only flag in inquiry graphs (*Enq*) where DAC rows are projections.
    # In normal entry graphs (POOrderEntry, etc.), e.Row is the real DAC and this is safe.
    is_inquiry_graph = bool(re.search(r"PXGraphExtension<\w*Enq\w*>", clean))
    row_ext_matches = re.findall(r"e\.Row\.GetExtension<(\w+)>\(\)", clean)
    for match in row_ext_matches:
        if is_inquiry_graph:
            msg = (
                f"{class_name}: e.Row.GetExtension<{match}>() in inquiry extension — HIGH RISK\n"
                f"         Crashes on inquiry/projection DACs. Use:\n"
                f"         e.Cache.GetValue(e.Row, \"FieldName\") / e.Cache.SetValue(...)"
            )
            if strict:
                error(msg)
            else:
                warn(msg)
        else:
            # In normal graphs, instance GetExtension on e.Row is generally safe
            # but still worth a note in strict mode
            if strict:
                warn(
                    f"{class_name}: e.Row.GetExtension<{match}>() — consider using\n"
                    f"         e.Cache.GetValue/SetValue for defensive coding"
                )

    # Rule 2: Instance .GetExtension<T>() on PXSelect results (not via PXCache<T>)
    # MEDIUM risk — unsafe on records from foreign graphs
    # Safe alternative: PXCache<Entity>.GetExtension<Ext>(record)
    # Find all .GetExtension<T>() calls, then exclude safe patterns
    for m in re.finditer(r"\.GetExtension<(\w+)>\(\)", clean):
        ext_type = m.group(1)
        # Get context before the match to check if it's a safe pattern
        prefix = clean[:m.start()]
        # Skip if already caught by Rule 1 (e.Row.GetExtension)
        if prefix.rstrip().endswith("e.Row"):
            continue
        # Skip if it's the safe static form: PXCache<T>.GetExtension
        if re.search(r"PXCache<\w+>\s*$", prefix):
            continue
        msg = (
            f"{class_name}: Instance .GetExtension<{ext_type}>() — MEDIUM RISK\n"
            f"         Use static PXCache<Entity>.GetExtension<{ext_type}>(record) instead"
        )
        if strict and is_inquiry_graph:
            error(msg)
        else:
            warn(msg)

    # Rule 3: Inquiry graph extension with RowSelected but no try-catch
    # HIGH risk — inquiry DACs are most fragile for extension failures
    is_inquiry_ext = bool(re.search(r"PXGraphExtension<\w*Enq\w*>", clean))
    has_row_selected = bool(re.search(r"RowSelected", clean))
    has_catch = "catch" in clean
    if is_inquiry_ext and has_row_selected and not has_catch:
        msg = (
            f"{class_name}: Inquiry graph extension with RowSelected but no try-catch\n"
            f"         Inquiry result DACs are projection types — extension access is fragile.\n"
            f"         Wrap handler body in try-catch to prevent screen crashes."
        )
        if strict:
            error(msg)
        else:
            warn(msg)


def validate_crm_dac_safety(class_name: str, code: str, strict: bool):
    """Detect CRM DAC usage on non-CRM graphs.

    CRM DACs (CRRelation, CRPMTimeActivity, CRActivity, PMTimeActivity) have
    [PXSelector] field attributes that reference CRM views. When these DACs are
    used in PXSelect views on non-CRM graphs (POOrderEntry, INReceiptEntry, etc.),
    the graph crashes at runtime even though it compiles successfully.

    CI/CD smoke tests may pass (HTTP 200 on entity query) but the screen itself
    will fail with "The view doesn't exist" when opened in the browser.
    """

    # Strip comments
    clean = re.sub(r"///.*$", "", code, flags=re.MULTILINE)
    clean = re.sub(r"//.*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL)

    # CRM DACs that are incompatible with non-CRM graphs
    crm_dacs = {
        "CRRelation": "CRM Relations DAC — has [PXSelector] on EntityID/ContactID referencing CRM views",
        "CRPMTimeActivity": "CRM Activities projection — joins PMTimeActivity + CRActivity (both CRM-dependent)",
        "CRActivity": "CRM Activity DAC — field attributes reference CRM-only views",
        "PMTimeActivity": "PM Time Activity DAC — field attributes reference CRM-only views",
        "CRRelationsList": "Removed in Acumatica 2022 R2 — type does not exist in 24.2",
        "CRActivityList": "Removed in Acumatica 24.2 — type does not exist",
    }

    # Non-CRM graphs where CRM DACs will crash
    non_crm_graphs = [
        "POOrderEntry", "POReceiptEntry", "INReceiptEntry",
        "APInvoiceEntry", "APPaymentEntry", "INTransferEntry",
        "INIssueEntry", "INAdjustmentEntry",
    ]

    # Detect which graph this extension targets
    graph_match = re.search(r"PXGraphExtension<(\w+)>", clean)
    if not graph_match:
        return  # Not a graph extension — skip

    target_graph = graph_match.group(1)
    is_non_crm = target_graph in non_crm_graphs

    # Check for CRM DAC usage
    for dac, reason in crm_dacs.items():
        # Match usage in PXSelect, PXSelectBase, field declarations, etc.
        # But skip if it's just in a comment or string
        pattern = rf"\b{re.escape(dac)}\b"
        if re.search(pattern, clean):
            if is_non_crm:
                msg = (
                    f"{class_name}: Uses '{dac}' on non-CRM graph '{target_graph}' — WILL CRASH AT RUNTIME\n"
                    f"         {reason}\n"
                    f"         Solution: Create custom DACs (e.g., UsrPORelation) with custom tables.\n"
                    f"         See lessons-learned.md: 'CRM DACs Are Fundamentally Incompatible with Non-CRM Graphs'"
                )
                error(msg)
            else:
                # On CRM graphs it's fine, but note it
                if strict:
                    warn(
                        f"{class_name}: Uses CRM DAC '{dac}' — ensure target graph has CRM infrastructure"
                    )

    # Also detect CRRelationDetailsExt on non-CRM graphs
    cr_ext_match = re.search(r"CRRelationDetailsExt<(\w+)", clean)
    if cr_ext_match:
        ext_target = cr_ext_match.group(1)
        if ext_target in non_crm_graphs:
            error(
                f"{class_name}: CRRelationDetailsExt<{ext_target}> — WILL CRASH AT RUNTIME\n"
                f"         CRRelationDetailsExt requires CRM infrastructure (contact/address views).\n"
                f"         Non-CRM graph '{ext_target}' does not provide these views.\n"
                f"         Solution: Use custom DACs with custom tables instead."
            )


def main():
    strict = "--strict" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not args:
        print("Usage: python validate-project.py [--strict] <project.xml>")
        print()
        print("Validates Acumatica customization project XML format.")
        print("  --strict  Enable additional warnings for best practices")
        sys.exit(1)

    path = args[0]
    print(f"Validating: {path}")
    print("=" * 60)

    success = validate(path, strict)

    print("=" * 60)
    if success:
        if warnings:
            print(f"{YELLOW}PASSED with {len(warnings)} warning(s){RESET}")
        else:
            print(f"{GREEN}PASSED — no issues found{RESET}")
        sys.exit(0)
    else:
        print(f"{RED}FAILED — {len(errors)} error(s), {len(warnings)} warning(s){RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
