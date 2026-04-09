# DAC / Plugin Schema Drift Verification — Implementation Log

**Date:** 2026-04-08
**Branch:** `feat/dac-plugin-drift-test`
**Design:** `docs/plans/2026-04-08-dac-plugin-drift-design.md`
**Plan:** `docs/plans/2026-04-08-dac-plugin-drift.md`

## Outcome

- `tests/test_dac_plugin_drift.py` — 781 lines, 18 tests, all green.
- 6 real drift bugs discovered in `main` and fixed in-branch (4 decimal precision + 1 scale mismatch + 1 fixed-length char mismatch).
- No new CI jobs, no new workflow triggers. The test joins the existing pytest suite and will run on every PR via the `Build Customization Package` job.
- Total elapsed time: roughly one working session including brainstorming, spec drafting, subagent iteration, and bug fixing.

## What shipped

| File | Purpose |
|---|---|
| `docs/plans/2026-04-08-dac-plugin-drift-design.md` | Design doc with type mapping table, pipeline, fail output format |
| `docs/plans/2026-04-08-dac-plugin-drift.md` | 12-task TDD implementation plan |
| `docs/plans/2026-04-08-dac-plugin-drift-impl.md` | This log |
| `tests/test_dac_plugin_drift.py` | Python drift detector with 17 meta-tests and 1 real-repo test |
| `src/StudioB.Containers/DACs/UsrContainer.cs` | 4 decimal scale corrections |
| `src/StudioB.Containers/DACs/UsrContainerCost.cs` | 1 decimal scale correction |
| `src/StudioB.Containers/DACs/UsrContainerPOLink.cs` | 1 fixed-length→variable-length correction |

## Decisions

### Two-layer design → one-layer in practice

The design doc called for a second C# xUnit layer using reflection on the compiled `StudioB.Containers.dll` as belt-and-suspenders against Python parser bugs. During implementation the C# layer hit a cross-framework assembly loading issue: `StudioB.Containers.dll` targets net48 and references `PX.Data.dll` with `<Private>False</Private>`, so the SDK DLLs live in `lib/` and are never copied to `bin/`. `Assembly.LoadFrom(...).GetTypes()` triggers type resolution which fails with `FileNotFoundException: PX.Data`.

Three resolution paths were considered:

- **A.** Drop the C# layer.
- **B.** Rewrite the C# layer to parse DAC source with regex (no reflection).
- **C.** Use `MetadataLoadContext` for cross-framework metadata-only inspection.

Chose **A**. Rationale:

1. The Python layer already caught 6 real drift bugs on its first run against `main`.
2. Every `Usr*.cs` DAC in `StudioB.Containers` inherits `PXBqlTable` directly — no custom base classes, no `#define` expansion. Reflection would see the same fields the regex sees, so the C# layer's unique value proposition evaporated.
3. Both layers parse the plugin via regex regardless (the plugin's DDL lives in C# string literals with no runtime metadata), so the C# layer would only have been more authoritative on the DAC half.
4. The AcuOps Deploy sandbox gate is an independent second line of defense against any publish-time schema error, so dropping the C# drift layer does not eliminate defense-in-depth — it eliminates a redundant first line.
5. Chasing `MetadataLoadContext` in a mixed net48/net10 project was an unknown-cost rat hole that would have kept the 6 caught bugs unfixed in `main` longer.

A comment at the top of `test_dac_plugin_drift.py` notes the decision and the conditions under which reflection-based coverage should be revisited (introduction of DAC inheritance or macro expansion).

### Exact type matching scoped in (not just presence)

The first draft of the design scoped type matching out. That decision was reversed during Section 3 review because the whole point of the test is to catch the bugs that hurt — and a decimal precision mismatch is exactly that class of bug. Scoping type matching in is what caught the 4 `PXDBDecimal(2)` vs `decimal(19,4)` mismatches in my own `UsrContainer.cs` from Phase A. Without exact type matching, this test would have shipped and immediately been useless on the first bug it was meant to catch.

### Path Y for drift bug fixes (relax DAC, not narrow plugin)

When the first real-repo run produced 6 drift entries, two paths existed:

- **X.** Narrow the plugin DDL to match the DAC (e.g. change `decimal(19,4)` to `decimal(19,2)`). Requires a prod schema migration and risks truncating already-landed data.
- **Y.** Relax the DAC to match the plugin DDL (e.g. change `[PXDBDecimal(2)]` to `[PXDBDecimal(4)]`). No migration, no data risk, plugin is the source of truth.

Chose **Y**. The plugin had been in place longer and any customer data in those columns was already stored at the plugin's precision. Narrowing the DAC would have thrown away the low digits on any landed value.

Not a universal rule — it happened to work here because every drift was in the more-permissive direction. If a future drift is a length narrowing (DAC says `PXDBString(100)`, plugin says `nvarchar(50)`) the call will go the other way.

## Parser details worth preserving

A few parser decisions made during Task 2–4 that are easy to get wrong:

- **`_find_regions` uses `.search`, not `.match`.** DAC `#region` lines are indented (8 spaces is typical), so anchoring at column 0 misses them.
- **`_split_top_level_commas`.** `body.split(",")` breaks `int IDENTITY(1,1)` into two pieces. A paren-depth tracking splitter is required.
- **`[PXDBDefault(typeof(...))]` implies `NOT NULL`.** This is how Acumatica propagates a parent row's ID to a child row's ID column at insert time — the column can never be null on insert. The parser has to treat it as equivalent to `NOT NULL DEFAULT <parent>`.
- **`[PXDBDecimal(N)]` specifies scale only.** Precision is the plugin author's choice. The comparison normalizes both sides to `decimal(*,N)` before diffing, so a DAC `[PXDBDecimal(4)]` matches `decimal(19,4)` or `decimal(10,4)` but not `decimal(19,2)`.
- **`DEFAULT` clauses are stripped before comparison.** The DAC cannot express a DEFAULT and the plugin often has one, so the comparison ignores that column.
- **Whitespace around punctuation is normalized.** `nvarchar ( 15 )` and `nvarchar(15)` are the same column.
- **Audit fields and `[PXNote]` are skipped.** `EnsureTable` boilerplate includes them in every table, so the test does not flag them regardless of plugin coverage.

All of the above live in `_normalize_ddl`, `_compute_expected_ddl`, and the parser helpers, with meta-tests asserting each one.

## Drift bugs caught and fixed

First run of the real-repo test against `main` produced these 6 drift entries:

| Field | DAC had | Plugin has | Fix |
|---|---|---|---|
| `UsrContainer.DemurrageDailyRate` | `PXDBDecimal(2)` | `decimal(19,4) NULL` | Changed DAC to `PXDBDecimal(4)` |
| `UsrContainer.DutyPaid` | `PXDBDecimal(2)` | `decimal(19,4) NULL` | Changed DAC to `PXDBDecimal(4)` |
| `UsrContainer.MPFAmount` | `PXDBDecimal(2)` | `decimal(19,4) NULL` | Changed DAC to `PXDBDecimal(4)` |
| `UsrContainer.HMFAmount` | `PXDBDecimal(2)` | `decimal(19,4) NULL` | Changed DAC to `PXDBDecimal(4)` |
| `UsrContainerCost.Amount` | `PXDBDecimal(2)` | `decimal(19,4) NULL` | Changed DAC to `PXDBDecimal(4)` |
| `UsrContainerPOLink.OrderType` | `PXDBString(2, IsFixed = true, IsUnicode = true)` | `nvarchar(2) NULL` | Removed `IsFixed = true` from DAC |

The design doc predicted 4 decimal precision bugs from a quick audit. The detector found 6 — a 5th decimal precision bug in `UsrContainerCost.Amount` that the manual audit missed, and a 6th nchar/nvarchar mismatch in `UsrContainerPOLink.OrderType` that the manual audit didn't look for. Both were silent bugs that would have surfaced months later as precision loss or indexing weirdness. The test paid for itself on day one.

## Commits

```
a9700d1 fix(dacs): relax DAC scale/type to match plugin DDL + enable drift test
155b2bf test(drift): wire up real test; 6 known bugs xfailed temporarily
8c73771 test(drift): fix parser for Acumatica semantics — PXDBDefault, decimal scale, DEFAULT strip
a3b8d06 test(drift): harden _normalize_ddl for whitespace-around-punctuation
b5155a9 test(drift): add type mismatch detection and auto-remediation formatter
f11e2ac test(drift): add parse_plugin_file for EnsureTable/EnsureColumn extraction
3af1184 test(drift): address code review — fix DDL fallback, default quoting, rename, add tests
12535ea test(drift): add parse_dac_file for C# DAC source extraction
f8d0ee9 test(drift): scaffold DAC/plugin drift detector with first meta-test
01ceee6 docs(tests): implementation plan for DAC/plugin drift detector
5d3f6b4 docs(tests): design for DAC/plugin schema drift verification
```

## Verification

- `python3 -m pytest tests/test_dac_plugin_drift.py -v` → **18 passed in 0.08s**
- `git diff --stat origin/main -- src/StudioB.Containers/DACs/` → 3 files, 6 insertions, 6 deletions
- `StudioB.Containers.dll` rebuilds clean with 0 warnings, 0 errors after the DAC changes

## Followups

- None blocking. The test is green, shipping as-is.
- If a future DAC introduces a custom base class or macro-expanded `[PXDB*]` attributes, reconsider reflection-based coverage at that time.
- The design doc's `StudioB.WMS` gap (no custom install plugin) is unchanged — that repo still relies on `*Ext.cs` base-table auto-creation and is out of scope for this test.
