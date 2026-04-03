# Debug: CI/CD Pipeline Post-Publish Failures

## Priority: P1 — every production deploy shows red despite successful publish

## Problem Statement

The AcuOps Deploy pipeline (`acuops-deploy.yml`) successfully publishes customization packages to Acumatica but reports FAILURE on every run. Two post-publish steps crash, triggering an auto-rollback that also fails. Net result: publish lands correctly, but the pipeline is always red, masking real failures.

## Failure Chain

```
Import + Publish → ✅ succeeds (Deployment complete!)
Post-publish field validation → ❌ ModuleNotFoundError: validate_publish_gi
E2E view-level smoke test → ❌ same or similar import error
Auto-rollback → ❌ no snapshot available (exit 127)
Job status → FAILURE (despite successful publish)
```

## Root Cause 1: Missing `validate_publish_gi` module

**File:** `acuops-pipeline/scripts/validate-publish.py` line 32
**Error:** `from validate_publish_gi import check_gi_health` → `ModuleNotFoundError`

The `validate-publish.py` script imports a sibling module `validate_publish_gi` that either:
- Doesn't exist in the `acuops-pipeline` repo
- Exists but under a different name
- Was deleted or never committed

**Where it runs:** Two steps in `acuops-deploy.yml`:
1. **Post-publish field validation** (line ~887): `cd pipeline/scripts && python validate-publish.py --manifest ../../publish-manifest.json`
2. **E2E view-level smoke test** (line ~898): `cd pipeline/scripts && python smoke-e2e.py --manifest ../../publish-manifest.json`

Both have `continue-on-error: true` so they don't block the job directly, but their failure outcome feeds into the auto-rollback condition.

### Fix Options
1. **Create `validate_publish_gi.py`** in `acuops-pipeline/scripts/` with the `check_gi_health()` function
2. **Remove the import** if GI health checks aren't needed yet — make it a conditional import with graceful skip
3. **Guard the import**: `try: from validate_publish_gi import check_gi_health; except ImportError: check_gi_health = None`

## Root Cause 2: Auto-rollback triggers on validation failure

**File:** `acuops-deploy.yml` line ~901-907
```yaml
- name: Auto-rollback on verification failure
  if: >
    steps.deploy.outcome == 'success' &&
    (steps.verify.outcome == 'failure' || steps.e2e.outcome == 'failure') &&
    steps.env.outputs.target == 'production'
```

The `continue-on-error: true` on verify/e2e steps means the job continues, but `steps.verify.outcome` is still `'failure'`. The rollback step sees this and tries to restore a snapshot.

The rollback then fails because:
- The snapshot step uses `continue-on-error: true`
- If snapshot failed or wasn't saved, there's nothing to restore
- Exit code 127 (command not found) suggests a script path issue in the rollback step too

### Fix Options
1. **Don't trigger rollback on import errors** — only rollback on actual field validation failures (non-zero field mismatches), not script crashes
2. **Make rollback conditional on snapshot existence**: check if `backups/*.zip` exists before attempting
3. **Separate "script crash" from "validation failure"** — a Python ImportError is not a field mismatch

## Root Cause 3: `--no-merge` needed permanently (or orphan cleanup)

Production publish required `--no-merge` because orphaned IIG publish metadata in the registry caused `merge=True` to crash with "An error has occurred".

**Current state:** `--no-merge` is hardcoded in the production deploy step. This works but means every publish is a clean compile (slower, ~280s vs ~150s).

### Fix Options
1. **Keep `--no-merge` permanently** — safest, prevents future orphan issues. Slower but reliable.
2. **Clean the publish registry** — Kevin does Unpublish All once on production, then revert to `merge=True`. Risk: any future ISV removal could re-create the problem.
3. **Make it configurable** — add a `merge_mode` input to workflow_dispatch so Kevin can choose per-deploy.

## SB501000 Screen Status

The `<ScreenWithRights>` registration for SB501000 was added (PR #141). On Heritage Test it works — screen loads. On production it shows "Error Has Occurred" (not redirect-to-home, which is progress). The error trace needs to be captured to determine if it's:
- ASPX compilation error (missing graph type)
- SiteMap registration incomplete (ScreenWithRights processed but missing fields)
- Graph runtime error (ContainerMaint can't initialize)

**Action:** Click "Show Trace" on the error page at `ScreenId=SB501000` on production and paste the stack trace.

## Data Migration Status

The `MigrateIGCMContainers()` method in `AesthetikContainersInstall` reported success but showed no row counts. Either:
- `IGCMPOLandedCost` table was dropped when Kevin did Unpublish All (unlikely — Acumatica doesn't drop data tables)
- The OBJECT_ID check found the table but the SELECT returned 0 rows (possible if data was in a different CompanyID/tenant)
- The migration ran but WriteLog for row counts wasn't reached (method structure issue)

**Action:** Verify table existence and row counts. If Kevin gets Direct SQL access, run:
```sql
SELECT OBJECT_ID('IGCMPOLandedCost', 'U') AS table_exists;
SELECT COUNT(*) AS rows FROM IGCMPOLandedCost;
SELECT COUNT(*) AS migrated FROM UsrContainer;
```

## Files to Fix

| File | Repo | Issue |
|------|------|-------|
| `scripts/validate-publish.py` | acuops-pipeline | Missing `validate_publish_gi` import |
| `scripts/smoke-e2e.py` | acuops-pipeline | May have same sibling import issue |
| `.github/workflows/acuops-deploy.yml` | acumatica-ci-cd | Auto-rollback condition too broad |
| `.github/workflows/acuops-deploy.yml` | acumatica-ci-cd | `--no-merge` decision (keep or revert) |

## Session Context

This was discovered during the 2026-04-03 Friday night session deploying SB501000 (Container Maintenance) screen registration + IGCM data migration. PRs #141-150 in `acumatica-ci-cd`. The publish itself works — the pipeline reporting is what's broken.
