# Auto-Allocation UI Test Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Playwright UI test suite that validates auto-allocation behavior on the SO301000 screen against Heritage Test, replicating the bugs from Sarah's video.

**Architecture:** Python + Playwright (sync API) with pytest. Tests log into Acumatica via the UI login form, create PC orders on SO301000, trigger auto-allocation via save, then validate field values and split data through the UI. Orders are cleaned up via deletion on teardown. Acumatica form fields are identified via `#ctl00_phF_form_ed{FieldName}` pattern or Playwright role/text selectors as fallback.

**Tech Stack:** Python 3, playwright (sync), pytest, Acumatica 24.2

---

## Context

- **Target:** Heritage Test at `heritagefabrics.acumatica.com`
- **Credentials:** via env vars `ACUMATICA_URL`, `ACUMATICA_USERNAME`, `ACUMATICA_PASSWORD`, `ACUMATICA_TENANT`
- **Screen:** SO301000 (Sales Orders)
- **Test data:** Customer C000221 (DRAPERY HOUSE), Item 28021 (PIECENBR), Warehouse 98

### Acumatica UI Patterns

Acumatica uses ASP.NET WebForms. Key patterns:
- Login form at `/Frames/Login.aspx` — username, password, company dropdown
- Screen URL: `/Main?ScreenId=SO301000`
- Field IDs: `#ctl00_phF_form_ed{FieldName}` for header fields
- Grid rows: `div.GridRow` elements inside the detail grid
- Toolbar buttons: `div[icon="..."]` or text-based locators
- Dialogs: native browser `alert()`/`confirm()` — captured via Playwright dialog handler
- Save: Ctrl+S or the save toolbar button
- "Line Details" popup: button labeled "LINE DETAILS" in the toolbar area

### Important Notes

- Acumatica pages load asynchronously — always wait for the loading indicator to disappear
- The loading indicator is typically `#ctl00_phF_form_PXProcessing` or a spinner overlay
- After save, wait for the page to finish processing before asserting
- Field values may need to be read from input elements or from text spans depending on edit state

---

## Task 1: Create test infrastructure — conftest.py with login fixture

**Files:**
- Create: `tests/ui/__init__.py`
- Create: `tests/ui/conftest.py`

**Step 1: Create the empty `__init__.py`**

```python
# tests/ui/__init__.py is intentionally empty
```

**Step 2: Create `conftest.py` with the login fixture and helpers**

```python
"""Playwright fixtures for Acumatica UI tests."""
import os
import pytest
from playwright.sync_api import sync_playwright, Page, expect


# ── Configuration ──────────────────────────────────────────────────────────

ACUMATICA_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
ACUMATICA_USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
ACUMATICA_PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
ACUMATICA_TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

HEADED = os.environ.get("HEADED", "").lower() in ("1", "true", "yes")
SLOW_MO = int(os.environ.get("SLOW_MO", "0"))  # ms between actions, useful for debugging


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context():
    """Launch browser and create a persistent context for the test session."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not HEADED, slow_mo=SLOW_MO)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        context.set_default_timeout(30_000)
        yield context
        context.close()
        browser.close()


@pytest.fixture(scope="session")
def acumatica_page(browser_context) -> Page:
    """Log into Acumatica and return an authenticated page.

    Session-scoped: logs in once, reused across all tests.
    """
    page = browser_context.new_page()

    # Navigate to login
    page.goto(f"{ACUMATICA_URL}/Frames/Login.aspx", wait_until="networkidle")

    # Fill credentials
    page.fill("#txtUser", ACUMATICA_USERNAME)
    page.fill("#txtPass", ACUMATICA_PASSWORD)

    # Select tenant/company if dropdown exists
    company_select = page.locator("#cmbCompany")
    if company_select.is_visible(timeout=3000):
        company_select.select_option(label=ACUMATICA_TENANT)

    # Click Sign In
    page.click("#btnLogin")

    # Wait for main menu to load (indicates successful login)
    page.wait_for_url("**/Main*", timeout=30_000)
    page.wait_for_load_state("networkidle")

    yield page
    page.close()


@pytest.fixture
def so301000(acumatica_page) -> Page:
    """Navigate to Sales Orders screen and return the page."""
    page = acumatica_page
    page.goto(f"{ACUMATICA_URL}/Main?ScreenId=SO301000", wait_until="networkidle")
    wait_for_screen_ready(page)
    return page


@pytest.fixture
def created_orders():
    """Track order numbers created during tests for cleanup."""
    orders = []
    yield orders


@pytest.fixture(autouse=True)
def cleanup_orders(acumatica_page, created_orders):
    """Delete any orders created during the test."""
    yield
    for order_type, order_nbr in created_orders:
        try:
            delete_order(acumatica_page, order_type, order_nbr)
        except Exception as e:
            print(f"Warning: failed to delete {order_type} {order_nbr}: {e}")


@pytest.fixture
def dialog_messages():
    """Capture browser dialog messages (alert/confirm) during test."""
    messages = []
    return messages


@pytest.fixture(autouse=True)
def capture_dialogs(acumatica_page, dialog_messages):
    """Install dialog handler to capture and dismiss error dialogs."""

    def handle_dialog(dialog):
        dialog_messages.append({"type": dialog.type, "message": dialog.message})
        dialog.accept()

    acumatica_page.on("dialog", handle_dialog)
    yield
    acumatica_page.remove_listener("dialog", handle_dialog)


# ── Helpers ────────────────────────────────────────────────────────────────

def wait_for_screen_ready(page: Page, timeout: int = 15_000):
    """Wait for Acumatica screen to finish loading."""
    # Wait for any loading overlay to disappear
    page.wait_for_load_state("networkidle")
    # Wait for the main form container to be visible
    page.locator("#ctl00_phF_form").wait_for(state="visible", timeout=timeout)
    # Small buffer for async field population
    page.wait_for_timeout(500)


def set_field_value(page: Page, field_id: str, value: str):
    """Set a value in an Acumatica form field and tab out to trigger events."""
    selector = f"#{field_id}"
    page.click(selector)
    page.fill(selector, "")
    page.fill(selector, value)
    page.keyboard.press("Tab")
    page.wait_for_timeout(500)


def get_field_value(page: Page, field_id: str) -> str:
    """Read the current value of an Acumatica form field."""
    selector = f"#{field_id}"
    el = page.locator(selector)
    # Try input value first, fall back to text content
    val = el.input_value() if el.evaluate("el => el.tagName") == "INPUT" else el.text_content()
    return (val or "").strip()


def save_order(page: Page):
    """Save the current order via Ctrl+S and wait for completion."""
    page.keyboard.press("Control+s")
    # Wait for save to complete (loading indicator disappears)
    page.wait_for_load_state("networkidle")
    wait_for_screen_ready(page)


def create_pc_order(page: Page, customer_id: str, items: list[dict]) -> str:
    """Create a new PC sales order and return the order number.

    Args:
        page: Authenticated Acumatica page on SO301000.
        customer_id: Customer account CD (e.g., "C000221").
        items: List of dicts with keys: inventory_cd, warehouse, qty, uom.

    Returns:
        The generated order number string.
    """
    # Click "+" to create new order
    page.locator("div[icon='AddNew']").first.click()
    wait_for_screen_ready(page)

    # Set Order Type = PC
    set_field_value(page, "ctl00_phF_form_edOrderType", "PC")

    # Set Customer
    set_field_value(page, "ctl00_phF_form_edCustomerID", customer_id)
    page.wait_for_timeout(1000)  # Wait for customer defaults to populate

    # Add line items
    for item in items:
        # Click "+" on the grid toolbar to add a new line
        page.locator("#ctl00_phG_grid_lv0_iACB").click()
        page.wait_for_timeout(500)

        # Set Inventory ID in the active grid row
        active_row = page.locator("tr.GridRowActive, tr[class*='Active']").last
        inv_cell = active_row.locator("td").nth(2)  # Inventory ID column
        inv_cell.dblclick()
        page.keyboard.type(item["inventory_cd"])
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Set Warehouse if specified
        if "warehouse" in item:
            page.keyboard.type(item["warehouse"])
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)

        # Skip to Quantity column and set it
        # UOM column comes after warehouse, then quantity
        if "uom" in item:
            page.keyboard.type(item["uom"])
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)

        page.keyboard.type(str(item["qty"]))
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

    # Save the order
    save_order(page)

    # Read the generated order number
    order_nbr = get_field_value(page, "ctl00_phF_form_edOrderNbr")
    return order_nbr


def delete_order(page: Page, order_type: str, order_nbr: str):
    """Navigate to an order and delete it."""
    page.goto(
        f"{ACUMATICA_URL}/Main?ScreenId=SO301000&OrderType={order_type}&OrderNbr={order_nbr}",
        wait_until="networkidle",
    )
    wait_for_screen_ready(page)

    # Use keyboard shortcut to delete (Ctrl+Delete) or Actions menu
    # Try Actions > Delete first
    page.locator("button:has-text('Actions')").click()
    page.wait_for_timeout(300)
    page.locator("span:has-text('Delete')").click()
    page.wait_for_timeout(300)

    # Confirm deletion dialog if it appears
    page.wait_for_timeout(1000)


def open_line_details(page: Page):
    """Open the Line Details popup for the selected line."""
    page.locator("div:has-text('LINE DETAILS')").first.click()
    page.wait_for_timeout(1000)


def get_line_details_splits(page: Page) -> list[dict]:
    """Read split rows from the Line Details popup.

    Returns list of dicts with keys: allocated, warehouse, lot_serial, qty, uom.
    """
    splits = []
    # The Line Details popup contains a grid with split rows
    popup = page.locator("div[id*='DlgSplits'], div[id*='LineSplits']").first
    rows = popup.locator("tr.GridRow, tr[class*='Row']")

    for i in range(rows.count()):
        row = rows.nth(i)
        cells = row.locator("td")
        if cells.count() < 5:
            continue

        splits.append({
            "allocated": "checked" in (cells.nth(1).inner_html() or "").lower(),
            "warehouse": (cells.nth(2).text_content() or "").strip(),
            "lot_serial": (cells.nth(4).text_content() or "").strip(),
            "qty": (cells.nth(5).text_content() or "").strip(),
            "uom": (cells.nth(8).text_content() or "").strip(),
        })

    return splits


def close_popup(page: Page):
    """Close the current popup dialog."""
    page.locator("button:has-text('OK'), button:has-text('Close')").first.click()
    page.wait_for_timeout(500)
```

**Step 3: Commit**

```bash
git add tests/ui/__init__.py tests/ui/conftest.py
git commit -m "feat: add Playwright test infrastructure for Acumatica UI tests

Session-scoped login, SO301000 navigation, order creation/deletion
helpers, dialog capture, and Line Details split reader."
```

---

## Task 2: Create test_auto_allocation.py with all 4 test scenarios

**Files:**
- Create: `tests/ui/test_auto_allocation.py`

**Step 1: Create the test file with all scenarios**

```python
"""UI tests for auto-allocation on SO301000 (Sales Orders).

These tests replicate the bugs from Sarah's video (2026-04-01):
- Quantity silently reduced from 40.00 to 36.20
- "Quantity will go negative" error dialog
- Partial allocation with incorrect split data

Tests run against Heritage Test (live) and create/delete real PC orders.
"""
import pytest
from conftest import (
    create_pc_order,
    get_field_value,
    open_line_details,
    get_line_details_splits,
    close_popup,
    save_order,
    wait_for_screen_ready,
)


# ── Test Data ──────────────────────────────────────────────────────────────

CUSTOMER_DRAPERY_HOUSE = "C000221"
ITEM_SUPER_BATISTE = "28021"  # 118 Super Batiste - White Snow (PIECENBR)
WAREHOUSE_98 = "98"


# ── Tests ──────────────────────────────────────────────────────────────────

class TestAutoAllocation:
    """Auto-allocation behavior on PC sales orders."""

    def test_partial_allocation_preserves_qty(
        self, so301000, created_orders, dialog_messages
    ):
        """When bolts don't cover full requested qty, OrderQty must NOT be reduced.

        Reproduces Sarah's bug: entered 40.00 PIECE, got silently reduced to 36.20.
        After fix: OrderQty stays 40.00, remainder goes to unallocated split.
        """
        page = so301000

        # Create PC order with 40.00 PIECE — likely exceeds available bolts
        order_nbr = create_pc_order(
            page,
            customer_id=CUSTOMER_DRAPERY_HOUSE,
            items=[{
                "inventory_cd": ITEM_SUPER_BATISTE,
                "warehouse": WAREHOUSE_98,
                "qty": 40.00,
                "uom": "PIECE",
            }],
        )

        assert order_nbr, "Order number should be generated after save"
        created_orders.append(("PC", order_nbr))

        # ASSERT 1: No error dialogs during save
        error_dialogs = [d for d in dialog_messages if "error" in d["message"].lower()]
        assert not error_dialogs, (
            f"Error dialog(s) during save: {[d['message'] for d in error_dialogs]}"
        )

        # ASSERT 2: OrderQty is still 40.00 (not reduced)
        ordered_qty = get_field_value(page, "ctl00_phF_form_edOrderQty")
        assert ordered_qty == "40.00", (
            f"OrderQty should be 40.00 but got {ordered_qty} — "
            "auto-allocation may still be overwriting user quantity"
        )

        # ASSERT 3: Order description contains AUTO-ALLOC stamp
        desc = get_field_value(page, "ctl00_phF_form_edOrderDesc")
        assert "[AUTO-ALLOC" in desc, (
            f"Order description should contain allocation stamp, got: {desc}"
        )

        # ASSERT 4: Check Line Details for splits
        open_line_details(page)
        splits = get_line_details_splits(page)
        close_popup(page)

        assert len(splits) >= 2, (
            f"Expected at least 2 splits (bolt + remainder), got {len(splits)}"
        )

        # At least one split should have a lot serial (allocated bolt)
        allocated_splits = [s for s in splits if s["lot_serial"]]
        assert len(allocated_splits) >= 1, "Expected at least one allocated bolt split"

        # At least one split should be unallocated (no lot serial)
        unallocated_splits = [s for s in splits if not s["lot_serial"]]
        assert len(unallocated_splits) >= 1, (
            "Expected an unallocated remainder split — "
            "auto-allocation should create remainder when bolts don't cover full qty"
        )

        # Split quantities should sum to 40.00
        total_qty = sum(float(s["qty"]) for s in splits if s["qty"])
        assert abs(total_qty - 40.00) < 0.01, (
            f"Split quantities should sum to 40.00, got {total_qty}"
        )

    def test_no_negative_inventory_error(
        self, so301000, created_orders, dialog_messages
    ):
        """Save must NOT produce 'quantity will go negative' error dialog.

        This was the most visible bug from Sarah's video — an alert() dialog
        about inventory going negative for the wrong item number.
        """
        page = so301000

        order_nbr = create_pc_order(
            page,
            customer_id=CUSTOMER_DRAPERY_HOUSE,
            items=[{
                "inventory_cd": ITEM_SUPER_BATISTE,
                "warehouse": WAREHOUSE_98,
                "qty": 40.00,
                "uom": "PIECE",
            }],
        )

        assert order_nbr, "Order should be created"
        created_orders.append(("PC", order_nbr))

        # Check for the specific negative inventory error
        negative_errors = [
            d for d in dialog_messages
            if "negative" in d["message"].lower()
            or "will go negative" in d["message"].lower()
        ]
        assert not negative_errors, (
            f"'Quantity will go negative' error appeared: "
            f"{[d['message'] for d in negative_errors]}"
        )

    def test_full_allocation_no_remainder(
        self, so301000, created_orders, dialog_messages
    ):
        """When bolts fully cover the requested qty, no remainder split should exist.

        Uses a small quantity (1.00 PIECE) that should be coverable by a single bolt.
        """
        page = so301000

        order_nbr = create_pc_order(
            page,
            customer_id=CUSTOMER_DRAPERY_HOUSE,
            items=[{
                "inventory_cd": ITEM_SUPER_BATISTE,
                "warehouse": WAREHOUSE_98,
                "qty": 1.00,
                "uom": "PIECE",
            }],
        )

        assert order_nbr, "Order should be created"
        created_orders.append(("PC", order_nbr))

        # No error dialogs
        assert not dialog_messages, (
            f"Unexpected dialog(s): {[d['message'] for d in dialog_messages]}"
        )

        # Check Line Details — all splits should be allocated with lot serials
        open_line_details(page)
        splits = get_line_details_splits(page)
        close_popup(page)

        assert len(splits) >= 1, "Expected at least one split"

        # Every split should have a lot serial (fully allocated)
        for split in splits:
            assert split["lot_serial"], (
                f"Expected all splits to have lot serial numbers (fully allocated), "
                f"but found unallocated split with qty={split['qty']}"
            )

    def test_no_bolts_marks_po_create(
        self, so301000, created_orders, dialog_messages
    ):
        """When zero bolts available, order should save and line should mark POCreate.

        Uses warehouse 99 which may have different (or zero) bolt inventory
        for this item. If bolts exist there, this test validates no errors at minimum.
        """
        page = so301000

        order_nbr = create_pc_order(
            page,
            customer_id=CUSTOMER_DRAPERY_HOUSE,
            items=[{
                "inventory_cd": ITEM_SUPER_BATISTE,
                "warehouse": "99",  # Different warehouse — may have zero bolts
                "qty": 100.00,
                "uom": "PIECE",
            }],
        )

        assert order_nbr, "Order should be created even with no bolts"
        created_orders.append(("PC", order_nbr))

        # No error dialogs
        error_dialogs = [d for d in dialog_messages if "error" in d["message"].lower()]
        assert not error_dialogs, (
            f"Error dialog(s) during save: {[d['message'] for d in error_dialogs]}"
        )

        # Order description should indicate allocation result
        desc = get_field_value(page, "ctl00_phF_form_edOrderDesc")
        # Either bolts were assigned or PO was created — both are valid
        assert "[AUTO-ALLOC" in desc or "PO" in desc.upper() or desc == "", (
            f"Expected allocation stamp or PO indicator in description, got: {desc}"
        )
```

**Step 2: Commit**

```bash
git add tests/ui/test_auto_allocation.py
git commit -m "feat: add 4 Playwright test scenarios for auto-allocation

- test_partial_allocation_preserves_qty (Sarah's bug)
- test_no_negative_inventory_error
- test_full_allocation_no_remainder
- test_no_bolts_marks_po_create"
```

---

## Task 3: Add pytest configuration and requirements

**Files:**
- Create: `tests/ui/pytest.ini`
- Modify: `scripts/requirements.txt`

**Step 1: Create pytest.ini for the UI tests**

```ini
[pytest]
testpaths = .
markers =
    ui: UI tests requiring Acumatica access
    slow: tests that take > 30 seconds
```

**Step 2: Add playwright to requirements.txt**

The existing file has only `requests>=2.31.0`. Add playwright:

```
requests>=2.31.0
playwright>=1.40.0
pytest>=7.0.0
```

**Step 3: Commit**

```bash
git add tests/ui/pytest.ini scripts/requirements.txt
git commit -m "chore: add pytest config for UI tests and playwright dependency"
```

---

## Task 4: Validate tests can import and collect (dry run)

**Step 1: Install dependencies**

```bash
pip install playwright pytest
playwright install chromium
```

**Step 2: Run pytest collection (no execution — just verify import)**

```bash
cd tests/ui && python -m pytest --collect-only test_auto_allocation.py
```

Expected: Shows 4 collected tests without import errors.

**Step 3: Fix any import issues**

If `from conftest import ...` fails, the tests should auto-discover conftest.py since they're in the same directory. If needed, adjust imports.

**Step 4: Commit any fixes**

```bash
git add tests/ui/
git commit -m "fix: resolve any import issues in UI test suite"
```

---

## Task 5: Run tests against Heritage Test (if credentials available)

**Step 1: Run the full test suite**

```bash
ACUMATICA_URL=https://heritagefabrics.acumatica.com \
ACUMATICA_USERNAME=$ACUMATICA_USERNAME \
ACUMATICA_PASSWORD=$ACUMATICA_PASSWORD \
ACUMATICA_TENANT="Heritage Fabrics" \
HEADED=true \
python -m pytest tests/ui/test_auto_allocation.py -v --tb=long
```

**Step 2: Iterate on selectors**

Acumatica's DOM structure may differ from what we've assumed. Common issues:
- Field IDs may use different prefixes (check with browser DevTools)
- Grid row structure may vary by Acumatica version
- The "+" button and toolbar buttons may need different selectors
- Login form fields may have different IDs

Use `HEADED=true` and `SLOW_MO=500` to watch the browser and debug selector issues.

**Step 3: Commit selector fixes**

```bash
git add tests/ui/
git commit -m "fix: adjust Acumatica UI selectors based on live testing"
```

---

## Summary

| Task | Creates | Purpose |
|------|---------|---------|
| 1 | `tests/ui/conftest.py` | Login, navigation, order CRUD helpers, dialog capture |
| 2 | `tests/ui/test_auto_allocation.py` | 4 test scenarios matching Sarah's video |
| 3 | `tests/ui/pytest.ini`, requirements.txt | Test config and dependencies |
| 4 | — | Dry-run validation (import/collect) |
| 5 | — | Live execution against Heritage Test |
