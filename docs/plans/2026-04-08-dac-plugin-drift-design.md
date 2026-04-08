# DAC / Plugin Schema Drift Verification — Design

**Date:** 2026-04-08
**Status:** Approved (brainstorm sections 1-3 approved)
**Repo:** `acumatica-ci-cd`
**Motivation:** Prevent the class of bug that took 3 hours to debug on 2026-04-08 morning — a DAC field existed in `UsrContainerPrefs.cs` but the corresponding `EnsureColumn` call was never added to `AesthetikContainersInstall.cs`. Sandbox publish silently ran without the column, and every screen that SELECT'd from `UsrContainerPrefs` redirected to `ScreenId=ERROR` with `Invalid column name 'LCCodeShipping'`.

## Context

`AesthetikContainersInstall.cs` is a `CustomizationPlugin` that runs on every customization publish. Its role is to create/update the custom tables the `StudioB.Containers` assembly uses. The established pattern is:

- `EnsureTable(conn, "TableName", @"... column DDL ...")` — IF NOT EXISTS CREATE TABLE. Runs once on first install; never adds columns to existing tables.
- `EnsureColumn(conn, "TableName", "ColumnName", "nvarchar(15) NULL")` — IF NOT EXISTS ALTER TABLE ADD. Runs on every publish, idempotent, safe.

**Failure mode:** when a DAC field is added to an existing table's `Usr*.cs` file, the DAC declares the column with `[PXDB*]` attributes. Acumatica's built-in publish-time schema updater is supposed to detect new fields and add them automatically, but in practice it does NOT reliably do this on existing tables — especially when multiple customizations co-publish or when tables have ISV legacy history. The only reliable fix is an explicit `EnsureColumn` call in the plugin. This is easy to forget and has bitten this project twice:

1. **PR #232 (2026-04-06) Bucket B Phase 2** — added 5 `LCCode*` fields to `UsrContainerPrefs.cs` DAC. Did NOT update the plugin. Sandbox DB drifted. Discovered 2 days later.
2. **PR #275 (2026-04-08) SB501000 Phase A** — added 17 fields to `UsrContainer.cs` DAC + 3 new child tables. Did NOT update the plugin. Would have hit the same bug the moment a fresh company tried to use the new fields. Caught by PR #285 schema backfill same night.

Both bugs had the same root cause. Both would have been caught in <5 seconds by a static test that compares DAC field declarations against plugin DDL.

## Goals

1. **Catch any DAC field declared with a `[PXDB*]` attribute that has no matching `EnsureTable` DDL or `EnsureColumn` call in the plugin.**
2. **Catch type mismatches** between DAC and plugin — length, unicode, nullability, decimal precision.
3. **Auto-remediation output** — when drift is found, print the exact `EnsureColumn` line the developer should paste into the plugin.
4. **Belt-and-suspenders** — two independent test layers (Python and C#) so a blind spot in one is caught by the other.

## Non-goals

- Runtime plugin self-check (YAGNI; static tests strictly beat runtime warnings).
- `StudioB.WMS` DAC coverage — no custom install plugin exists there; all WMS DACs are `*Ext.cs` extensions of Acumatica base tables.
- Generic Inquiry (GI) validation — separate test suite (`tests/test_validate_gi_*.py`).
- `MUIWorkspace` / `SiteMap` DML — separate concern; `hungry-shannon` owns `EnsureWorkspace` work.
- Auto-fix mode that rewrites source files — footgun.
- Orphan detection (plugin columns with no DAC field) — YAGNI; legacy migration columns would false-positive.

## Architecture

Two layers, no shared code, same failure semantics.

### Layer 1 — Python pytest (`tests/test_dac_plugin_drift.py`)

Parses C# source files with regex. Fast (~1s), runs without a built DLL, joins the existing `tests/` suite.

**Pipeline:**

1. Walk `src/StudioB.Containers/DACs/Usr*.cs` (excludes `ContainerFilter.cs`, `AddPOLineFilter.cs`, and `*Ext.cs` extensions).
2. For each DAC file, extract `[PXCacheName("...")]` for the table name, then iterate `#region FieldName` blocks.
3. Parse each field's attributes via regex: `\[PXDB(String|Int|Bool|Decimal|Date|Guid|Identity|Timestamp|Text)(?:\(([^)]*)\))?\]`.
4. Extract `[PXDefault(...)]` presence to determine nullability.
5. Skip fields with no `PXDB*` attribute (unbound).
6. Skip standard audit fields (`[PXDBCreatedByID]`, etc.) and `[PXNote]`.
7. Walk `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs`.
8. Extract `EnsureTable(conn, "TableName", @"... DDL ...")` blocks — parse the DDL string column-by-column.
9. Extract `EnsureColumn(conn, "TableName", "ColumnName", "type spec")` calls — build a flat list.
10. Merge table-level DDL + standalone `EnsureColumn` calls into a single `plugin_coverage[table_name]` dict.
11. For each DAC field: compute `expected_ddl` from the attribute, look up in `plugin_coverage[table][field_name]`, compare case-insensitive + whitespace-normalized.
12. Collect drift entries. Fail with auto-remediation block.

**Fail output format** (example from the LCCode* bug):

```
FAIL tests/test_dac_plugin_drift.py::test_dac_plugin_drift

DAC drift detected in StudioB.Containers:

Table: UsrContainerPrefs (DAC: src/StudioB.Containers/DACs/UsrContainerPrefs.cs)
  Missing plugin coverage for 5 field(s):

  Paste the following into AesthetikContainersInstall.cs after the existing
  UsrContainerPrefs EnsureColumn block:

      EnsureColumn(conn, "UsrContainerPrefs", "LCCodeShipping",  "nvarchar(15) NULL");
      EnsureColumn(conn, "UsrContainerPrefs", "LCCodeDuty",      "nvarchar(15) NULL");
      EnsureColumn(conn, "UsrContainerPrefs", "LCCodeTariff",    "nvarchar(15) NULL");
      EnsureColumn(conn, "UsrContainerPrefs", "LCCodeBrokerage", "nvarchar(15) NULL");
      EnsureColumn(conn, "UsrContainerPrefs", "LCCodeOther",     "nvarchar(15) NULL");

  Source of truth: lines 55, 62, 69, 76, 83 of UsrContainerPrefs.cs.
```

For new tables with no `EnsureTable` call at all, the output is a full `EnsureTable` block with every DAC field translated to DDL.

### Layer 2 — C# xUnit (`tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs`)

Uses reflection on the compiled DLL. Authoritative check because reflection sees inherited properties and actual runtime attribute resolution.

**Pipeline:**

1. Load `src/StudioB.Containers/bin/Debug/net48/StudioB.Containers.dll` via `Assembly.LoadFrom`.
2. Enumerate types descending from `PX.Data.PXBqlTable` in `StudioB.Containers` namespace, filter to `Usr*` classes (exclude filters).
3. For each type, iterate `PropertyInfo[]` and inspect attributes that descend from `PXDBFieldAttribute`.
4. Extract field metadata (SQL length, precision, nullability) from attribute properties via reflection.
5. Read `AesthetikContainersInstall.cs` as text (the plugin's DDL is C# string literals — no runtime metadata to reflect).
6. Parse the same way as the Python layer (regex).
7. Diff. Fail with the same auto-remediation format.

**Why both layers exist:**

| Drift case | Python | C# |
|---|---|---|
| Field in `.cs` file but not in plugin | ✅ | ✅ |
| Field inherited from a base DAC class | ❌ | ✅ |
| Attribute expanded from a `#define` | ❌ | ✅ |
| Plugin source typo in column name | ✅ | ✅ |
| Length / precision / nullability mismatch | ✅ | ✅ |
| Runs without DLL built | ✅ | ❌ |
| Catches attribute resolution edge cases | ❌ | ✅ |

Python is the fast-feedback canary. C# is the strict authoritative check. Both must pass to merge.

## Scope

**In:**
- `src/StudioB.Containers/DACs/Usr*.cs` — custom tables in the scope of the plugin
- `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs` — the install plugin
- Exact type matching (length, unicode, nullability, decimal precision)

**Out:**
- Filter DACs (`ContainerFilter.cs`, `AddPOLineFilter.cs`) — non-persistent
- `*Ext.cs` DAC extensions — use Acumatica base-table auto-creation
- `StudioB.WMS` — no custom install plugin
- Audit fields (`[PXDBCreated*]`, `[PXDBLastModified*]`, `[PXDBTimestamp]`, `[PXNote]`) — always included in `EnsureTable` boilerplate
- `CompanyID` synthetic column — always added by `EnsureTable`
- `CONSTRAINT PK_*` clauses — synthesized from `IsKey = true` fields

## Type mapping table

Canonical rule, not heuristic.

| DAC attribute pattern | Expected plugin DDL |
|---|---|
| `[PXDBString(N, IsUnicode = true)]` | `nvarchar(N) NULL` |
| `[PXDBString(N, IsUnicode = true, IsFixed = true)]` | `nchar(N) NULL` |
| `[PXDBString(N, IsUnicode = true, IsKey = true)]` | `nvarchar(N) NOT NULL DEFAULT ''` |
| `[PXDBString(N)]` (no IsUnicode) | `varchar(N) NULL` |
| `[PXDBText(IsUnicode = true)]` | `nvarchar(MAX) NULL` |
| `[PXDBInt]` | `int NULL` |
| `[PXDBInt(IsKey = true)]` + `[PXDefault(1)]` | `int NOT NULL DEFAULT 1` |
| `[PXDBIdentity]` | `int IDENTITY(1,1) NOT NULL` |
| `[PXDBBool]` alone | `bit NOT NULL DEFAULT 0` |
| `[PXDBBool]` + `[PXDefault(true)]` | `bit NOT NULL DEFAULT 1` |
| `[PXDBDecimal(N)]` | `decimal(19,N) NULL` |
| `[PXDBDate]` or `[PXDBDate(PreserveTime = true)]` | `datetime NULL` |
| `[PXDBGuid]` | `uniqueidentifier NULL` |
| `[PXRSACryptString(N, IsUnicode = true)]` | `nvarchar(N) NULL` |

`InputMask` is parsed but ignored (UI-only concern).

## Unbound field exclusion

Fields with no attribute starting with `PXDB` are unbound (computed at row-selected time) and must be skipped. Examples:

```csharp
// SKIPPED — no PXDB prefix
[PXString(1)]
[PXUIField(DisplayName = "●", Enabled = false)]
public string RiskLevel { get; set; }

// CHECKED — has PXDBDate
[PXDBDate]
[PXUIField(DisplayName = "Last Free Day")]
public DateTime? LastFreeDay { get; set; }
```

## Drift direction

One direction only: **every DAC field must have plugin coverage**. The reverse (orphan plugin columns with no DAC) is not checked because legacy migration columns from `MigrateIGCMContainers` would false-positive. YAGNI.

## Self-verification (meta-tests)

Both layers ship with test-of-the-test cases. Each creates a small DAC + plugin fixture in-memory and asserts the drift detector behaves correctly.

**Test cases each layer must pass:**

1. `test_detector_catches_missing_column` — DAC has field, plugin has neither `EnsureTable` nor `EnsureColumn` for it → drift detected, auto-remediation line present.
2. `test_detector_catches_missing_table` — DAC exists, no matching `EnsureTable` at all → drift detected, full `EnsureTable` block suggested.
3. `test_detector_catches_length_mismatch` — DAC says `PXDBString(50)`, plugin says `nvarchar(20)` → drift detected.
4. `test_detector_catches_unicode_mismatch` — DAC says `PXDBString(N, IsUnicode = true)`, plugin says `varchar(N)` → drift detected.
5. `test_detector_catches_nullability_mismatch` — DAC has `PXDefault(true)` (implies `NOT NULL`), plugin has `NULL` → drift detected.
6. `test_detector_catches_decimal_precision_mismatch` — DAC says `PXDBDecimal(2)`, plugin says `decimal(19,4)` → drift detected.
7. `test_detector_passes_when_all_covered` — happy path, no drift, test passes.
8. `test_detector_skips_unbound_fields` — field with `[PXString]` (no PXDB) is not flagged.
9. `test_detector_skips_audit_fields` — `[PXDBCreatedByID]` etc. are not flagged regardless of plugin coverage.

## CI integration

Both tests run in the existing pipeline with zero new gating:

| Layer | Runs in | Runner | Trigger |
|---|---|---|---|
| Python pytest | Existing `tests/` suite (pytest) | Linux `Build Customization Package` job | Every PR and push |
| C# xUnit | Existing `dotnet test tests/dotnet/StudioB.Containers.Tests/` | Windows `Build + Acuminator` job | Every PR and push with `customization_changes == 'true'` or `src/**` touched |

Test failures propagate to `build` → blocks PR merge via existing `build-validate` gate. Same behavior as the unit tests already in the project.

No new workflow jobs, no new triggers, no new config.

## Immediate bonus — first run catches 4 of my own bugs

I grep'd my Phase A commits and found that the schema fix PR #285 shipped 4 silent decimal precision mismatches:

| Field | DAC | Plugin | Correct |
|---|---|---|---|
| `UsrContainer.DemurrageDailyRate` | `[PXDBDecimal(2)]` | `decimal(19,4) NULL` | `decimal(19,2) NULL` |
| `UsrContainer.DutyPaid` | `[PXDBDecimal(2)]` | `decimal(19,4) NULL` | `decimal(19,2) NULL` |
| `UsrContainer.MPFAmount` | `[PXDBDecimal(2)]` | `decimal(19,4) NULL` | `decimal(19,2) NULL` |
| `UsrContainer.HMFAmount` | `[PXDBDecimal(2)]` | `decimal(19,4) NULL` | `decimal(19,2) NULL` |

The first run of this test against `main` will catch all four. Each is a silent precision-loss bug that would only surface as rounding discrepancies in landed cost reports months down the road. A follow-up PR corrects the plugin DDL — trivial, test-gated, no deploy risk.

**This test pays for itself on day one.**

## Files that will land

| File | Purpose | Rough size |
|---|---|---|
| `tests/test_dac_plugin_drift.py` | Python pytest layer + 9 meta-tests | ~350 lines |
| `tests/dotnet/StudioB.Containers.Tests/DacPluginDriftTests.cs` | C# xUnit layer + 9 meta-tests | ~300 lines |
| `tests/fixtures/dac_plugin_drift/` | 6 small DAC+plugin fixture pairs for meta-tests | ~200 lines total |
| `docs/plans/2026-04-08-dac-plugin-drift-design.md` | This doc | ~350 lines |
| `docs/plans/2026-04-08-dac-plugin-drift-impl.md` | Implementation log (written during execution) | TBD |

## Rough effort estimate

- Python pytest layer + meta-tests: 1.5 hours
- C# xUnit layer + meta-tests: 1.5 hours
- Fixtures + verification: 0.5 hour
- Fix the 4 decimal precision bugs found by first run: 0.25 hour
- **Total: ~4 hours of focused work**

## Open questions (none blocking)

- Should the test also accept `decimal(19,4)` as a valid match for `[PXDBDecimal(4)]`? Yes — the canonical rule already says "N from DAC must match N in plugin". Both sides must agree.
- Should we add the test to a pre-commit hook? Not in v1. The CI gate is sufficient.
- Should we extend to cover `StudioB.WMS` once it gets a custom install plugin? Yes, when that plugin exists. Currently N/A.
