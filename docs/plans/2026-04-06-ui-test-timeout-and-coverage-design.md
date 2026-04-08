# UI Test Timeout Fix + Coverage Gaps

**Date:** 2026-04-06
**Status:** Design
**Problem:** Runtime UI tests hit the 10-minute GitHub Actions timeout. Test coverage outside container tracking is thin.

## Part 1: Sequential Split

Split the single "Run UI tests" step into two sequential steps within the same `post-deploy-validation` job. No parallel jobs — both steps hit the same Acumatica tenant and concurrent sessions risk data conflicts.

### Step 1 — Container Tracking Tests

```yaml
- name: Run container tracking tests
  timeout-minutes: 10
  run: python -m pytest tests/ui/test_container_tracking.py -v --tb=long --timeout=120
```

37 tests covering IGCM removal, SB501000 CRUD, GI columns, workspace integrity, cross-screen E2E. This is the heaviest suite and the most stable (rarely changes).

### Step 2 — Core UI Tests

```yaml
- name: Run core UI tests
  timeout-minutes: 8
  run: python -m pytest tests/ui/ --ignore=tests/ui/test_container_tracking.py -v --tb=long --timeout=120
```

Runs everything else: auto-allocation, UOM migration, screen smoke, and the new test files below. Gets its own Playwright login (~15s overhead).

### Metrics

"Publish test metrics" step stays at the end with `if: always()`.

## Part 2: New Test Files

### test_po_custom_fields.py (3 tests)

Tests the `POOrderEntry_Extension.cs` customization — `UsrExpArrivalDate` cascading from PO header to lines.

1. **test_po_header_custom_fields_visible** — Navigate to PO301000, load an existing PO, verify `UsrExpArrivalDate` and `UsrHubSpotDealId` fields exist in the DOM.
2. **test_po_line_custom_fields_visible** — On the same PO, verify `UsrExpArrivalDate` exists on the line detail grid.
3. **test_po_screen_no_errors** — Navigate PO301000 with no record loaded, verify no error dialogs or IGCM references.

Pattern: uses `navigate_and_wait` → `get_main_frame` → `find_custom_fields`. Read-only — no record creation.

### test_ar_paylink.py (2 tests)

Tests the `ARInvoiceEntry_PayLink_Extension.cs` customization — `UsrDisablePayLink` customer-level override.

1. **test_ar301000_loads_without_error** — Navigate to AR301000 (Invoices and Memos), verify screen loads, no error dialogs.
2. **test_customer_paylink_field_visible** — Navigate to AR303000 (Customers), load a customer, verify `UsrDisablePayLink` field exists in the DOM.

Pattern: uses `navigate_and_wait` → `get_main_frame` → `find_custom_fields`. Read-only.

## What's NOT in scope

- **AsthetikTheme** — Cosmetic, low risk, no functional tests needed.
- **StudioBAcuOps** — Infrastructure customization tested by the pipeline itself running.
- **Visual regression** — No screenshot comparison. All tests are DOM-based.

## File changes

| File | Change |
|------|--------|
| `.github/workflows/acuops-deploy.yml` | Split "Run UI tests" into two sequential steps |
| `tests/ui/test_po_custom_fields.py` | New file — 3 tests |
| `tests/ui/test_ar_paylink.py` | New file — 2 tests |
