"""Playwright fixtures for Acumatica UI tests."""
import os
import pytest
from playwright.sync_api import sync_playwright, Page, expect


# -- Configuration ------------------------------------------------------------

ACUMATICA_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
ACUMATICA_USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
ACUMATICA_PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
ACUMATICA_TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

HEADED = os.environ.get("HEADED", "").lower() in ("1", "true", "yes")
SLOW_MO = int(os.environ.get("SLOW_MO", "0"))  # ms between actions, useful for debugging


# -- Fixtures -----------------------------------------------------------------

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


# -- Helpers ------------------------------------------------------------------

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
