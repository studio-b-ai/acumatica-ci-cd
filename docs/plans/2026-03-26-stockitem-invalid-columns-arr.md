# ARR: StockItem Invalid Column Production Error

**Date:** 2026-03-26
**Severity:** P0 — Production outage (StockItem API 500, Shipments screen broken)
**Duration:** ~45 minutes (4:00 PM - 4:45 PM ET)
**Impact:** All StockItem/InventoryItem queries returned HTTP 500. Shipments, Sales Orders, and Inventory screens showed JavaScript alert with invalid column errors. Affected all users.

## What Happened

At ~4:00 PM ET, the Acumatica Shipments screen (SO302000) began showing a JavaScript alert:

```
Invalid column name '[InventoryItem].[UsrHTSCode]'
Invalid column name '[InventoryItem].[UsrDutyRate]'
Invalid column name '[InventoryItem].[UsrCountryOfOrigin]'
Invalid column name '[InventoryItem].[UsrFiberContent]'
Invalid column name '[InventoryItem].[UsrPreferentialTariff]'
Invalid column name '[InventoryItem].[UsrFreightClass]'
```

The REST API returned HTTP 500 for all StockItem queries.

## Root Cause

The `AesthetikContainers` customization project contained a `StockItemExt` DAC extension with 6 `[PXDB*]` field declarations (UsrHTSCode, UsrDutyRate, etc.) that reference database columns. However:

1. The project had a `System.TypeCode` compilation error (using unqualified `TypeCode.Decimal` instead of `System.TypeCode.Decimal`) that prevented successful publishing for weeks.
2. The project was listed in `ALSO_PUBLISH_PROJECTS` GitHub variable, meaning it was imported and co-published on every CI/CD deploy.
3. At some point the TypeCode error was worked around or the project was restructured, allowing compilation to succeed.
4. The C# DAC extensions compiled and registered the 6 InventoryItem fields in Acumatica's metadata.
5. But the SQL `ALTER TABLE` statements to create the corresponding database columns either didn't execute or were missing.
6. At runtime, Acumatica's ORM tried to SELECT these columns from the InventoryItem table → SQL error.

## Why CI/CD Didn't Catch It

**Three process failures combined:**

### 1. Co-published projects were never validated

The CI/CD pipeline (`deploy-customization.yml`) only ran `validate-project.py` on the primary project (`AesthetikWMS`). Co-published projects in `ALSO_PUBLISH_PROJECTS` were imported and published but **never validated**. AesthetikContainers sailed through without any semantic checks.

### 2. No TypeCode qualification check

The semantic validator had no check for unqualified `TypeCode` usage. `[PXDefault(TypeCode.Decimal, "0")]` compiles intermittently depending on Acumatica's namespace resolution — sometimes it works, sometimes it causes CS0104. The correct form is `System.TypeCode.Decimal`.

### 3. Stale ALSO_PUBLISH_PROJECTS variable

The GitHub variable `ALSO_PUBLISH_PROJECTS` contained projects that no longer exist on the instance or in the repo:
- `AesthetikContainers` — project with broken DAC extensions
- `HeritageFabricsPOv5` — merged into AesthetikWMS weeks ago

No automated check verified that entries in `ALSO_PUBLISH_PROJECTS` corresponded to valid, tested projects.

## Resolution

1. **Immediate:** Deleted AesthetikContainers from Acumatica instance (SM204505), clicked UNPUBLISH ALL to force clean recompile. StockItem API restored.
2. **Config fix:** Removed `AesthetikContainers` and `HeritageFabricsPOv5` from `ALSO_PUBLISH_PROJECTS` GitHub variable.

## Preventive Measures (this PR)

### Process Fix
- CI/CD now validates ALL co-published projects, not just the primary. Every project in `ALSO_PUBLISH_PROJECTS` with a `project.xml` in the repo runs through `validate-project.py` with full semantic checks.

### 9 New Semantic Checks

| # | Check | Severity | Prevents |
|---|-------|----------|----------|
| 1 | `System.TypeCode` qualification | ERROR | CS0104 ambiguous TypeCode reference |
| 2 | `IsActive()` required on extensions | ERROR | Silently disabled extensions |
| 3 | `<Table>` elements banned | ERROR | NullReferenceException on cloud |
| 4 | `Microsoft.Data.SqlClient` banned | ERROR | Assembly not found on cloud |
| 5 | `string.Contains(char)` banned | ERROR | .NET Framework CS1061 |
| 6 | CRM DAC on non-CRM graphs | ERROR | Runtime selector crashes |
| 7 | ASPX duplicate control IDs | ERROR | Silent publish failures |
| 8 | Ghost package detection | WARNING | Stale code compiling unnoticed |
| 9 | Versioned project names | ERROR | Subsystem corruption |
| 10 | Unbound `[PX*]` on Usr fields | WARNING | Fields that don't persist |

### Existing checks (already in place, 11 total)
1. DAC fields without SQL columns
2. PXDB → SQL type compatibility
3. Table name mapping (DAC → SQL)
4. Extension reference validation
5. Cross-project duplicate fields
6. Namespace consistency
7. Orphaned SQL columns
8. External .cs file path validation
9. PXDefault vs SQL DEFAULT consistency
10. Manifest coverage
11. XML format validation

**Total: 21 semantic checks in CI/CD pipeline.**

## Lessons Learned

1. **Validate everything you publish.** If a project is in the co-publish list, it gets compiled. If it gets compiled, it must be validated.
2. **`ALSO_PUBLISH_PROJECTS` is a deployment manifest.** Treat it like code — audit it, don't let stale entries accumulate.
3. **DAC compilation ≠ correctness.** C# compiling successfully does not mean the runtime will work. The gap between "compiles" and "runs" is where column-mismatch errors live.
4. **Unpublishing doesn't remove compiled code.** Unchecking "Published" in SM204505 and republishing may not clean the assembly if `isMergeWithExistingPackages` is true. Deleting the project + UNPUBLISH ALL is the nuclear option that works.
