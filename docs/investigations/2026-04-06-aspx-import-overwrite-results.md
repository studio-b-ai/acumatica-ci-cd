# ASPX Import Overwrite — Root Cause Analysis

**Date:** 2026-04-06
**Incident:** 2026-04-05 — SB501000.aspx stuck on TabView.master across 3 deploys
**Investigated by:** Claude (automated reproduction test against sandbox)

## Root Cause

**Acumatica's CustomizationApi/Import ignores CDATA content in project.xml for ASPX files.** Only physical `.aspx` files included in the zip package overwrite existing files on the instance.

The SB501000 incident had two contributing factors:
1. The standalone `Pages/SB/SB501000.aspx` file in the repo still referenced `TabView.master` while the CDATA in `project.xml` had the correct `FormDetail.master`
2. The pipeline packages both into the zip, but only the physical file matters — so the wrong master page persisted across deploys

PR #221 fixed the standalone file, which is why it finally resolved the issue.

## Reproduction Test Results

Automated test ran three scenarios against `heritagefabrics-sandbox.acumatica.com`, injecting unique HTML comment markers into the ASPX for SB302000 and checking if they survived import + publish:

| Scenario | CDATA Overwritten | Physical File Overwritten |
|----------|:-:|:-:|
| CDATA only (project.xml modified, physical file unchanged) | No | No |
| Physical file only (standalone .aspx modified, CDATA unchanged) | No | **Yes** |
| Both CDATA + physical file modified | No | **Yes** |

**Key finding:** CDATA changes are accepted by the import API without error, but they are never applied to the actual ASPX files on the instance. The physical file in the zip is the sole mechanism for ASPX deployment.

**Additional discovery:** Acumatica's export (`getProject`) converts all CDATA entries to `FileID=` references with standalone files. The CDATA format is an import-only artifact with no functional effect on published customizations.

## Contributing Factors

1. **Source-of-truth divergence:** project.xml CDATA had the old "Container Maintenance" simple form view (`PrimaryView="Container"`) while the standalone file had the current "Procurement Command Center" dashboard (`PrimaryView="Filter"`). These were completely different screens — not just a master page difference.

2. **No ASPX verification in pipeline:** `validate-publish.py` only checked entity reachability and custom DAC fields. A stale ASPX file was invisible to the pipeline. Deploys reported success while the screen didn't update.

3. **Dual-source packaging:** The zip packaging step (`zip -r`) includes both `project.xml` (with CDATA) and the standalone `.aspx` files. No deduplication or precedence logic exists in the packaging.

## Fixes Applied

### 1. CDATA Synced (this PR)
Updated `project.xml` CDATA for SB501000.aspx to match the standalone file. While CDATA is functionally irrelevant, keeping it in sync prevents confusion.

### 2. ASPX Verification Added (acuops-pipeline PR)
Added `validate_aspx_files()` to `validate-publish.py`:
- Exports the published project via `getProject` API after deploy
- Extracts ASPX files from the exported zip
- Compares against the original deployed package
- Reports mismatches with line-level diff output
- New CLI args: `--package` (deployed zip path) and `--project` (project name)

### 3. Reproduction Test Script
`scripts/test-aspx-overwrite.py` — reusable test that can verify ASPX overwrite behavior on any Acumatica instance.

## Recommendations

1. **Physical files are the source of truth.** When making ASPX changes, always update the standalone file in `Pages/SB/`. The CDATA in project.xml is metadata only.

2. **Consider removing CDATA for ASPX files entirely.** Since Acumatica ignores it and the export format doesn't use it, the CDATA blocks are dead weight that creates a maintenance burden. Replace `Source="#CDATA"` with `Source="#FILE"` pointing to the physical files. (Requires testing to verify Acumatica accepts this format on import.)

3. **ASPX verification catches silent failures.** The new pipeline check will flag any case where ASPX files don't match post-deploy, preventing a repeat of this incident.

4. **If ASPX changes don't take effect after deploy:** Delete the stale file from SM204505 (Customization Projects > Files tab) and redeploy. This forces Acumatica to accept the new file.

## Files Changed

| Repo | File | Change |
|------|------|--------|
| acumatica-ci-cd | `Customization/AesthetikContainers/project.xml` | Synced SB501000 CDATA |
| acumatica-ci-cd | `scripts/test-aspx-overwrite.py` | Reproduction test script |
| acumatica-ci-cd | `docs/investigations/2026-04-06-aspx-import-overwrite-results.md` | This document |
| acuops-pipeline | `scripts/validate-publish.py` | ASPX verification function |
