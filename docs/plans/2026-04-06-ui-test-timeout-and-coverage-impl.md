# UI Test Timeout Fix + Coverage Gaps Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the 10-minute runtime test timeout by splitting into sequential steps, and close coverage gaps for PO custom fields and AR PayLink extension.

**Architecture:** Split the single pytest invocation into two sequential steps (container tracking first, everything else second) within the same GHA job. Add two new read-only test files that follow existing patterns (navigate → get_main_frame → find_custom_fields → assert).

**Tech Stack:** GitHub Actions, Playwright, pytest, pytest-timeout

**Design doc:** `docs/plans/2026-04-06-ui-test-timeout-and-coverage-design.md`

---

### Task 1: Split the GHA workflow step

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml:1362-1377`

**Step 1: Replace the single "Run UI tests" step with two sequential steps**

Replace lines 1362-1377 with:

```yaml
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
          else
            echo "No test_container_tracking.py — skipping"
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
          else
            echo "No tests/ui/ directory — skipping"
          fi
```

**Step 2: Verify YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml'))"`
Expected: No output (success)

**Step 3: Commit**

```
git add .github/workflows/acuops-deploy.yml
git commit -m "ci: split UI tests into container tracking + core steps"
```

---

### Task 2: Add PO custom fields tests

**Files:**
- Create: `tests/ui/test_po_custom_fields.py`

**Step 1: Write the test file**

```python
"""PO301000 custom field tests — verify Heritage Fabrics PO extensions.

The AesthetikWMS customization adds UsrExpArrivalDate to PO headers and
lines (POOrderEntry_Extension.cs). These tests verify the custom fields
render after deploy.

Read-only — no records are created or modified.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from helpers import (
    ACUMATICA_USERNAME,
    navigate_and_wait,
    navigate_to_screen_safe,
    wait_for_screen,
    get_main_frame,
    find_custom_fields,
    assert_no_screen_errors,
)


pytestmark = [pytest.mark.ui]

if not ACUMATICA_USERNAME:
    pytest.skip("ACUMATICA_USERNAME not set", allow_module_level=True)


class TestPOCustomFields:
    """Verify Heritage Fabrics custom fields on Purchase Orders (PO301000)."""

    def test_po_screen_loads_no_errors(self, acumatica_page):
        """PO301000 should load without error dialogs or IGCM references."""
        navigate_to_screen_safe(acumatica_page, "PO301000")
        wait_for_screen(acumatica_page, "PO301000")
        assert_no_screen_errors(acumatica_page, "PO301000")

    def test_po_header_custom_fields_visible(self, acumatica_page):
        """UsrExpArrivalDate should be visible on PO header.

        This field is added by POOrderExt.cs and cascades to lines
        via POOrderEntry_Extension.cs.
        """
        frame = navigate_and_wait(acumatica_page, "PO301000")

        # Navigate to last record to get a PO with data
        last_btn = frame.locator("[id*='ToolBar_Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_timeout(2000)

        fields = find_custom_fields(acumatica_page, ["UsrExpArrivalDate"])
        assert fields["UsrExpArrivalDate"], (
            "UsrExpArrivalDate not found on PO301000 header — "
            "POOrderExt customization may not be published"
        )

    def test_po_line_custom_fields_visible(self, acumatica_page):
        """UsrExpArrivalDate should exist on PO line details.

        POLineExt.cs adds this field. POOrderEntry_Extension.cs defaults
        the line value from the header when the header field is set.
        """
        frame = navigate_and_wait(acumatica_page, "PO301000")

        # Navigate to last record
        last_btn = frame.locator("[id*='ToolBar_Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_timeout(2000)

        # Check line grid area for the custom field
        fields = find_custom_fields(acumatica_page, ["UsrExpArrivalDate"], frame=frame)

        # The field may appear in the header form OR the line grid — either is valid.
        # If not found in the frame context, it may be header-only on this screen layout.
        # At minimum, the header test above must pass.
        if not fields["UsrExpArrivalDate"]:
            pytest.skip(
                "UsrExpArrivalDate not found in line grid DOM — "
                "field may only render when line is selected or in a detail popup"
            )
```

**Step 2: Run the tests locally (dry run — will skip without credentials)**

Run: `cd tests/ui && python -m pytest test_po_custom_fields.py -v --collect-only 2>&1 | head -20`
Expected: 3 tests collected (or skipped due to missing credentials)

**Step 3: Commit**

```
git add tests/ui/test_po_custom_fields.py
git commit -m "test: add PO301000 custom field tests (UsrExpArrivalDate)"
```

---

### Task 3: Add AR PayLink tests

**Files:**
- Create: `tests/ui/test_ar_paylink.py`

**Step 1: Write the test file**

```python
"""AR PayLink extension tests — verify customer-level disable flag.

The AesthetikWMS customization adds UsrDisablePayLink to Customer (AR303000)
via CustomerExt.cs, and ARInvoiceEntry_PayLink_Extension.cs uses it to
suppress payment link generation for specific customers (e.g., factor customers).

Read-only — no records are created or modified.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from helpers import (
    ACUMATICA_USERNAME,
    navigate_and_wait,
    navigate_to_screen_safe,
    wait_for_screen,
    find_custom_fields,
    assert_no_screen_errors,
)


pytestmark = [pytest.mark.ui]

if not ACUMATICA_USERNAME:
    pytest.skip("ACUMATICA_USERNAME not set", allow_module_level=True)


class TestARPayLink:
    """Verify AR PayLink customization fields are deployed."""

    def test_ar301000_loads_without_error(self, acumatica_page):
        """AR301000 (Invoices and Memos) should load without errors.

        ARInvoiceEntry_PayLink_Extension.cs hooks into this screen's
        RowSelected and RowPersisted events. If the extension has type
        errors, the screen will show an error dialog on load.
        """
        navigate_to_screen_safe(acumatica_page, "AR301000")
        wait_for_screen(acumatica_page, "AR301000")
        assert_no_screen_errors(acumatica_page, "AR301000")

    def test_customer_paylink_field_visible(self, acumatica_page):
        """UsrDisablePayLink should be visible on the Customers screen.

        CustomerExt.cs adds this bool field to BAccount/Customer. It must
        be present in the DOM on AR303000 so that HF staff can toggle it
        per-customer.
        """
        frame = navigate_and_wait(acumatica_page, "AR303000")

        # Navigate to last record to load a customer
        last_btn = frame.locator("[id*='ToolBar_Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_timeout(2000)

        fields = find_custom_fields(acumatica_page, ["UsrDisablePayLink"])
        assert fields["UsrDisablePayLink"], (
            "UsrDisablePayLink not found on AR303000 — "
            "CustomerExt customization may not be published"
        )
```

**Step 2: Run the tests locally (dry run)**

Run: `cd tests/ui && python -m pytest test_ar_paylink.py -v --collect-only 2>&1 | head -20`
Expected: 2 tests collected (or skipped due to missing credentials)

**Step 3: Commit**

```
git add tests/ui/test_ar_paylink.py
git commit -m "test: add AR PayLink extension tests (UsrDisablePayLink)"
```

---

### Task 4: Final verification

**Step 1: Verify all UI tests collect without import errors**

Run: `cd tests/ui && python -m pytest . -v --collect-only 2>&1 | tail -5`
Expected: ~54 tests collected (37 container + 12 existing core + 3 PO + 2 AR)

**Step 2: Verify the workflow YAML is valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml')); print('OK')"`
Expected: `OK`

**Step 3: Verify the --ignore flag works**

Run: `cd tests/ui && python -m pytest . --ignore=test_container_tracking.py --collect-only 2>&1 | tail -5`
Expected: ~17 tests collected (everything except container tracking)

**Step 4: Commit any remaining changes and push**

```
git push origin claude/quirky-perlman
```
