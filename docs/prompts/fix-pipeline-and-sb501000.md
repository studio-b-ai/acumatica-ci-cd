# Fix CI/CD Pipeline + SB501000 Production Error

## Context

Read `docs/prompts/debug-pipeline-post-publish.md` for full diagnosis.

Friday 2026-04-03 session deployed SB501000 (Container Maintenance) screen via `<ScreenWithRights>` XML and added IGCM data migration to CustomizationPlugin. PRs #141-150 in acumatica-ci-cd.

## Current State

- **Heritage Test:** SB501000 loads and routes correctly
- **Production:** SB501000 shows "Error Has Occurred" (not redirect-to-home — it's in SiteMap but something fails at runtime). Need to capture the stack trace via "Show Trace" link.
- **Pipeline:** Every deploy shows FAILURE despite successful publish. Three bugs in post-publish steps.
- **Data migration:** Reported success but no row counts logged. Unknown if IGCMPOLandedCost data was actually migrated.

## Tasks

### 1. Capture SB501000 production error trace

Navigate to `https://heritagefabrics.acumatica.com/Main?ScreenId=SB501000` on production. Click "Show Trace". The stack trace will tell us if the failure is:
- ASPX compilation (graph type not found)
- SiteMap registration incomplete
- Graph runtime error (DAC/view initialization)

Fix based on what the trace says.

### 2. Fix the pipeline (acuops-pipeline repo)

Three issues, all in the post-publish steps:

**a) `validate_publish_gi` ModuleNotFoundError**
- `acuops-pipeline/scripts/validate-publish.py` line 32 imports `validate_publish_gi` which doesn't exist
- Fix: guard the import with try/except ImportError, or create the module
- Same check needed for `smoke-e2e.py`

**b) Auto-rollback triggers on script crashes**
- `acumatica-ci-cd/.github/workflows/acuops-deploy.yml` line ~901
- Rollback fires when `steps.verify.outcome == 'failure'` — but a Python ImportError is not a field validation failure
- Fix: only rollback when the deploy step itself fails, not post-validation. Or check if snapshot exists before attempting rollback.

**c) `--no-merge` on production**
- Currently hardcoded because orphaned IIG publish metadata crashes `merge=True`
- Decide: keep permanently (safer, slower) or clean registry and revert

### 3. Verify data migration

Check if `IGCMPOLandedCost` table still has data on production. The `MigrateIGCMContainers()` method logged success but no row counts — either the OBJECT_ID check skipped it (table gone) or the migration ran on 0 rows.

If table exists with data but UsrContainer is empty, the migration SQL may need debugging. Check column names against actual table schema (we already fixed RefNbr → LandedCostNbr but there may be other mismatches).

### 4. Clean up ALSO_PUBLISH_PROJECTS

Current production value still includes ISV packages that may cause issues on future deploys. Audit against what's actually published on SM204505 and sync the variable.

## Key Files

| File | Repo | Purpose |
|------|------|---------|
| `Customization/AesthetikContainers/project.xml` | acumatica-ci-cd | ScreenWithRights + CustomizationPlugin with migration |
| `.github/workflows/acuops-deploy.yml` | acumatica-ci-cd | Deploy workflow with broken post-publish steps |
| `scripts/validate-publish.py` | acuops-pipeline | Crashes on missing sibling module import |
| `scripts/smoke-e2e.py` | acuops-pipeline | May have same import issue |
| `docs/prompts/debug-pipeline-post-publish.md` | acumatica-ci-cd | Full diagnosis with fix options per root cause |

## Constraints

- After-hours deploys only (publishes restart app pool)
- Read `memory/feedback_stop-on-first-failure.md` — stop on first unexpected error on prod
- Read `memory/context/lessons-learned.md` before touching project.xml
- Never commit directly to main — always branch + PR
