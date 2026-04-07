# Test Before Deploy — Run UI Tests After Test Tenant Publish

**Date:** 2026-04-06
**Status:** Design
**Problem:** UI tests run after production deploy. By then it's too late — broken screens are already in production.

## Current Flow

```
build → qualify → test-tenant-gate (publish to test tenant) → deploy (publish to prod) → post-deploy-validation (UI tests)
```

The test-tenant-gate publishes and runs verify.py (API-level checks only). UI tests run in post-deploy-validation — after production is already deployed.

## Proposed Flow

```
build → qualify → test-tenant-gate (publish to test tenant + UI tests) → deploy (publish to prod) → post-deploy-validation (verify.py only)
```

Move UI tests into the test-tenant-gate job, running against the test tenant. If any screen crashes (like SB501000 with missing columns), the pipeline stops before touching production.

## Why This Works

Heritage Fabrics staging and test tenants are on the **same Acumatica instance** as production. Every publish restarts the app pool and recompiles ALL customization projects across all tenants. So:

- SQL scripts (ALTER TABLE) run during the test tenant publish — columns exist for all tenants
- Compiled DLLs are shared across tenants — if a DAC field references a missing column, it crashes on any tenant
- If SB501000 loads on the test tenant, it will load on production

## Changes

### 1. Add UI test steps to test-tenant-gate job

After the existing verify.py step in test-tenant-gate, add:

```yaml
- name: Install test dependencies
  run: |
    pip install playwright pytest pytest-timeout
    playwright install chromium

- name: Generate UI fixtures from audit data
  timeout-minutes: 3
  env:
    ACUMATICA_URL: ${{ secrets.ACUMATICA_PROD_URL }}
    ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
    ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
    ACUMATICA_TENANT: ${{ vars.ACUMATICA_TEST_TENANT }}
  run: |
    if [ -f scripts/heritage/generate_ui_fixtures.py ]; then
      python scripts/heritage/generate_ui_fixtures.py --days 30 --output tests/fixtures/ui_screens.json
    fi

- name: Run container tracking tests
  timeout-minutes: 10
  env:
    ACUMATICA_URL: ${{ secrets.ACUMATICA_PROD_URL }}
    ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
    ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
    ACUMATICA_TENANT: ${{ vars.ACUMATICA_TEST_TENANT }}
  run: |
    if [ -f tests/ui/test_container_tracking.py ]; then
      python -m pytest tests/ui/test_container_tracking.py -v --tb=long --timeout=120 || {
        echo "::warning::Container tracking tests failed — see logs above"
        exit 1
      }
    fi

- name: Run core UI tests
  timeout-minutes: 8
  env:
    ACUMATICA_URL: ${{ secrets.ACUMATICA_PROD_URL }}
    ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
    ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
    ACUMATICA_TENANT: ${{ vars.ACUMATICA_TEST_TENANT }}
  run: |
    if [ -d tests/ui/ ]; then
      python -m pytest tests/ui/ --ignore=tests/ui/test_container_tracking.py -v --tb=long --timeout=120 || {
        echo "::warning::Core UI tests failed — see logs above"
        exit 1
      }
    fi
```

Note: `ACUMATICA_URL` points to the production URL (same instance), `ACUMATICA_TENANT` points to the test tenant. Tests run against test tenant data on the shared instance.

### 2. Simplify post-deploy-validation

Post-deploy-validation becomes verify.py only (API-level smoke test against production tenant). UI tests are no longer needed here since they already ran against the test tenant on the same instance.

```yaml
post-deploy-validation:
  name: Post-Deploy Verification
  needs: [build, deploy]
  ...
  steps:
    - name: Run post-deploy smoke test
      run: python scripts/verify.py --environment production ...
```

### 3. Test-tenant-gate becomes the hard gate

The deploy job already has `needs: [build, qualify, test-tenant-gate]`. If UI tests fail in test-tenant-gate, the job fails, and deploy never runs. No changes needed to the dependency chain.

## What This Catches

| Failure type | Caught by | Before this change |
|---|---|---|
| Missing DB columns | UI tests crash on test tenant | Only caught after prod deploy |
| Screen layout errors | UI tests crash on test tenant | Only caught after prod deploy |
| DAC type-not-found | UI tests crash on test tenant | Only caught after prod deploy |
| API entity 403/401 | verify.py (already in test-tenant-gate) | Same |
| Custom field missing from DOM | UI tests (find_custom_fields) | Only caught after prod deploy |

## What Doesn't Change

- Build and qualify jobs
- Deploy job (still publishes to production)
- verify.py checks (still run in both test-tenant-gate and post-deploy)
- UI test content (same test files, same assertions)
