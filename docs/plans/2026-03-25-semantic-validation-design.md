# Semantic Validation for Acumatica CI/CD

**Date:** 2026-03-25
**Status:** Approved
**Trigger:** INLotSerClass missing columns — DAC extension declared 4 fields, SQL initialization never created them. Validator checked XML structure and C# syntax but never cross-referenced DAC fields against SQL columns.

## Problem

`validate-project.py` catches structural issues (XML format, C# syntax, CRM DAC incompatibility) but is blind to semantic mismatches between DAC field declarations and SQL column creation. This class of bug compiles successfully, publishes without error, and only surfaces at runtime when a screen queries the missing column.

## Solution

New module `scripts/semantic_checks.py` with 11 checks across 3 phases. Imported by `validate-project.py` after existing structural checks. Controlled by `--no-semantic` flag for emergency bypasses.

## Architecture

```
validate-project.py (existing)
  └─ imports semantic_checks.py (new)
     └─ run_semantic_checks(project_path, strict, also_publish, manifest_path)
        ├─ Parsers: parse_dac_fields(), parse_sql_columns()
        ├─ Phase 1: field-to-sql cross-reference, type/precision matching, table name validation
        ├─ Phase 2: DAC extension references, cross-project duplicates, namespace consistency
        └─ Phase 3: orphaned SQL, path normalization, PXDefault, manifest coverage
```

## Phase 1 — Prevents Data Corruption

### Check 1: DAC fields without SQL columns (CRITICAL → ERROR)
Parse `[PXDBDecimal]`, `[PXDBBool]`, `[PXDBString]`, `[PXDBInt]`, `[PXDBDate]` from C# code. Parse `ALTER TABLE ... ADD` from initializer code and `<Sql>` elements. Every DAC field must have a matching SQL column.

### Check 2: Decimal precision mismatch (CRITICAL → ERROR)
`[PXDBDecimal(2)]` must match `decimal(18,2)` in SQL. `[PXDBString(100)]` must match `nvarchar(100)`.

### Check 3: Field type mismatch (CRITICAL → ERROR)
Type mapping: `[PXDBBool]→bit`, `[PXDBInt]→int`, `[PXDBDecimal]→decimal`, `[PXDBString]→nvarchar`, `[PXDBDate]→datetime`. Error when C# attribute and SQL type disagree.

### Check 4: SQL table name validation (CRITICAL → ERROR/WARN)
Hardcoded DAC→table mapping (~30 entries). Key mappings: `INLotSerialClass→INLotSerClass`, `Customer→BAccount`, `Vendor→BAccount`. Error on known mismatches, warn on unmapped DACs.

## Phase 2 — Prevents Runtime Crashes

### Check 5: Graph extensions referencing non-existent DAC extensions (HIGH → WARN)
Collect all declared `PXCacheExtension<T>` class names. Flag `GetExtension<T>()` calls where T is not declared in the project and not a known base framework extension.

### Check 6: Cross-project duplicate fields (HIGH → ERROR)
For each project in ALSO_PUBLISH_PROJECTS, parse DAC fields. Error on any field+table combination that appears in multiple projects. Scoped to ALSO_PUBLISH only (not all Customization/ projects).

### Check 7: Namespace consistency (HIGH → WARN)
All .cs files in a project should share a root namespace. Flag mismatches between external files, and between inline CDATA and external files for the same class.

## Phase 3 — Code Quality

### Check 8: Orphaned SQL columns (HIGH → WARN)
SQL creates column but no DAC field declares it. Might be intentional for raw SQL access, so warn only.

### Check 9: External .cs path normalization (MEDIUM → ERROR)
Normalize `\` to `/` in Source attributes. Case-insensitive file existence check on Linux CI runners.

### Check 10: PXDefault without SQL DEFAULT (MEDIUM → WARN)
`[PXDefault(TypeCode.Decimal, "1.00")]` without `DEFAULT (1.00)` in SQL means raw SQL inserts get NULL.

### Check 11: Publish-manifest coverage (MEDIUM → WARN)
Compare collected DAC fields against publish-manifest.json. Flag fields not in manifest. Auto-generate suggested manifest entries.

## DAC→Table Mapping Registry

```python
DAC_TO_TABLE = {
    "SOOrder": "SOOrder",
    "SOLine": "SOLine",
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
    "Shipment": "SOShipment",
    "SOShipment": "SOShipment",
    "SOShipLine": "SOShipLine",
    "SOPackageDetailEx": "SOPackageDetail",
    "CRCase": "CRCase",
    "Contact": "Contact",
    "Address": "Address",
    "EPEmployee": "BAccountR",
    "CSAnswers": "CSAnswers",
    "Note": "Note",
    "NoteDoc": "NoteDoc",
}
```

## Integration

```python
# End of validate-project.py validate() function:
if not no_semantic:
    from semantic_checks import run_semantic_checks
    sem_errors, sem_warnings = run_semantic_checks(
        project_path=path,
        strict=strict,
        also_publish=os.environ.get("ALSO_PUBLISH_PROJECTS", "").split(","),
        manifest_path=find_manifest(path),
    )
    errors.extend(sem_errors)
    warnings.extend(sem_warnings)
```

## Out of Scope

- Runtime API validation (validate-publish.py, post-deploy)
- Cross-repo validation (webhook-router field references)
- ISV package internals (third-party .zip)
