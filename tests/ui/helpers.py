"""Acumatica UI test helpers — shared between conftest.py and test files."""
import os
from playwright.sync_api import Page


# ── Configuration ──────────────────────────────────────────────────────────

ACUMATICA_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
ACUMATICA_USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
ACUMATICA_PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
ACUMATICA_TENANT = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

HEADED = os.environ.get("HEADED", "").lower() in ("1", "true", "yes")
SLOW_MO = int(os.environ.get("SLOW_MO", "0"))


# ── Screen Helpers ─────────────────────────────────────────────────────────

def wait_for_screen_ready(page: Page, timeout: int = 15_000):
    """Wait for Acumatica screen to finish loading."""
    page.wait_for_load_state("domcontentloaded")
    page.locator("#ctl00_phF_form").wait_for(state="visible", timeout=timeout)
    page.wait_for_timeout(500)


def set_field_value(page: Page, field_id: str, value: str):
    """Set a value in an Acumatica form field and tab out to trigger events."""
    frame = get_main_frame(page)
    selector = f"#{field_id}"
    frame.click(selector)
    frame.fill(selector, "")
    frame.fill(selector, value)
    frame.evaluate("document.activeElement.blur()")
    frame.wait_for_timeout(500)


def get_field_value(page: Page, field_id: str) -> str:
    """Read the current value of an Acumatica form field."""
    frame = get_main_frame(page)
    selector = f"#{field_id}"
    el = frame.locator(selector)
    val = el.input_value() if el.evaluate("el => el.tagName") == "INPUT" else el.text_content()
    return (val or "").strip()


def save_order(page: Page):
    """Save the current order via Ctrl+S and wait for completion."""
    page.keyboard.press("Control+s")
    page.wait_for_load_state("domcontentloaded")
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
    page.locator("div[icon='AddNew']").first.click()
    wait_for_screen_ready(page)

    set_field_value(page, "ctl00_phF_form_edOrderType", "PC")
    set_field_value(page, "ctl00_phF_form_edCustomerID", customer_id)
    page.wait_for_timeout(1000)

    for item in items:
        page.locator("#ctl00_phG_grid_lv0_iACB").click()
        page.wait_for_timeout(500)

        active_row = page.locator("tr.GridRowActive, tr[class*='Active']").last
        inv_cell = active_row.locator("td").nth(2)
        inv_cell.dblclick()
        page.keyboard.type(item["inventory_cd"])
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        if "warehouse" in item:
            page.keyboard.type(item["warehouse"])
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)

        if "uom" in item:
            page.keyboard.type(item["uom"])
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)

        page.keyboard.type(str(item["qty"]))
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

    save_order(page)

    order_nbr = get_field_value(page, "ctl00_phF_form_edOrderNbr")
    return order_nbr


def delete_order(page: Page, order_type: str, order_nbr: str):
    """Navigate to an order and delete it."""
    page.goto(
        f"{ACUMATICA_URL}/Main?ScreenId=SO301000&OrderType={order_type}&OrderNbr={order_nbr}",
        wait_until="domcontentloaded",
    )
    wait_for_screen_ready(page)

    page.locator("button:has-text('Actions')").click()
    page.wait_for_timeout(300)
    page.locator("span:has-text('Delete')").click()
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


# ── Generic Screen Navigation ─────────────────────────────────────────────

def navigate_to_screen(page: Page, screen_id: str, timeout: int = 30_000):
    """Navigate to an Acumatica screen by screen ID."""
    url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)


def assert_screen_loaded(page: Page, screen_id: str, timeout: int = 15_000):
    """Assert that an Acumatica screen loaded successfully.

    Checks for either a form container or a grid — different screens use different layouts.
    """
    try:
        page.wait_for_function(
            """() => {
                return document.querySelector('#ctl00_phF_form') !== null
                    || document.querySelector('#ctl00_phG_grid') !== null
                    || document.querySelector('#ctl00_phG_tab') !== null;
            }""",
            timeout=timeout,
        )
    except Exception:
        raise AssertionError(
            f"Screen {screen_id} did not load — no form, grid, or tab container found within {timeout}ms"
        )


def find_custom_fields(page: Page, field_names: list[str]) -> dict[str, bool]:
    """Check which custom fields are present in the DOM (searches main frame).

    Args:
        page: Authenticated Acumatica page.
        field_names: List of field names (e.g., ["UsrHubSpotDealId", "UsrBoltID"]).

    Returns:
        Dict mapping field_name -> True if found in DOM, False if not.
    """
    frame = get_main_frame(page)
    results = {}
    for field_name in field_names:
        locator = frame.locator(f"[id*='{field_name}']")
        results[field_name] = locator.count() > 0
    return results


# ── Screen Error Detection ────────────────────────────────────────────────

def navigate_to_screen_safe(page: Page, screen_id: str, timeout: int = 60_000):
    """Navigate to screen without networkidle (Acumatica keeps polling)."""
    url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(3000)


def wait_for_screen(page: Page, screen_id: str, timeout: int = 30_000):
    """Wait for an Acumatica screen to load and check for errors."""
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5000)
    current_url = page.url
    assert "ScreenId=ERROR" not in current_url, \
        f"Screen {screen_id} redirected to error page"


def assert_no_screen_errors(page: Page, screen_id: str = ""):
    """Comprehensive error check on current page.

    Checks: ERROR redirect, type-not-found, IGCM references, exceptions.
    """
    url = page.url
    assert "ScreenId=ERROR" not in url, \
        f"{screen_id} redirected to error page"

    body = (page.locator("body").text_content() or "").lower()
    assert "type is not found" not in body, \
        f"{screen_id} has 'type is not found' error"
    assert "type not found" not in body, \
        f"{screen_id} has 'type not found' error"
    assert "igcm.dac" not in body, \
        f"{screen_id} references IGCM.DAC types"


def get_main_frame(page: Page):
    """Get the 'main' iframe where Acumatica renders screen content.

    Acumatica wraps all screen content in an iframe named 'main'.
    Top-level page only has the sidebar and frameset shell.
    """
    frame = page.frame("main")
    if frame is None:
        return page  # Fallback to page if no iframe (e.g., direct URL)
    return frame


def assert_grid_visible(page: Page, screen_id: str = "", timeout: int = 10_000):
    """Assert that a GI grid rendered in the main frame."""
    frame = get_main_frame(page)
    try:
        frame.wait_for_function(
            """() => {
                return document.querySelector('[id*=grid]') !== null
                    || document.querySelector('.GridRow') !== null
                    || document.querySelector('[class*=Grid]') !== null
                    || document.querySelector('table[id*=grid]') !== null;
            }""",
            timeout=timeout,
        )
    except Exception:
        raise AssertionError(f"{screen_id} — no grid found within {timeout}ms")


def assert_grid_has_columns(page: Page, expected_columns: list[str], screen_id: str = ""):
    """Verify GI grid rendered with expected column headers in the main frame."""
    frame = get_main_frame(page)
    header_text = ""
    for selector in ["[class*='GridHeader']", "th", "[class*='Header'] [class*='Cell']",
                     "[id*='grid_header']", "[id*='grid'] th"]:
        headers = frame.locator(selector)
        if headers.count() > 0:
            header_text = " ".join(
                (headers.nth(i).text_content() or "") for i in range(headers.count())
            ).lower()
            break

    if not header_text:
        header_text = (frame.locator("[id*='grid']").first.text_content() or "").lower()

    missing = [col for col in expected_columns if col.lower() not in header_text]
    assert not missing, \
        f"{screen_id} missing columns: {missing}. Found headers: {header_text[:300]}"


def assert_field_has_selector_data(page: Page, field_id: str):
    """Click a PXSelector field and verify dropdown populates with rows."""
    frame = get_main_frame(page)
    selector = f"[id*='{field_id}']"
    field = frame.locator(selector).first

    field.click()
    frame.wait_for_timeout(300)

    # Click the dropdown button
    dropdown_btn = frame.locator(f"[id*='{field_id}_ddBtn']").first
    if dropdown_btn.is_visible(timeout=1000):
        dropdown_btn.click()
        frame.wait_for_timeout(1000)

    # Check if dropdown rows appeared
    dropdown_rows = frame.locator("[class*='SelectorRow'], [class*='GridRow']")
    row_count = dropdown_rows.count()
    assert row_count > 0, \
        f"PXSelector {field_id} dropdown has no rows — master table may be empty"

    frame.evaluate("document.activeElement.blur()")
    frame.wait_for_timeout(300)


def save_record(page: Page):
    """Save the current record via toolbar Save button or Ctrl+S."""
    frame = get_main_frame(page)
    save_btn = frame.locator("[id*='ToolBar_Save']").first
    if save_btn.is_visible(timeout=2000):
        save_btn.click()
    else:
        page.keyboard.press("Control+s")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)


def click_add_new(page: Page):
    """Click Add New Record (Insert) button in the main frame toolbar."""
    frame = get_main_frame(page)
    add_btn = frame.locator("[id*='ToolBar_Insert'], [id*='btnInsert']").first
    add_btn.click()
    frame.wait_for_timeout(2000)


def click_delete(page: Page):
    """Click Delete button on current record in the main frame toolbar."""
    frame = get_main_frame(page)
    del_btn = frame.locator("[id*='ToolBar_Delete'], [id*='btnDelete']").first
    del_btn.click()
    frame.wait_for_timeout(500)
    # Confirm deletion dialog if present
    confirm = frame.locator("button:has-text('Yes'), button:has-text('OK')")
    if confirm.count() > 0 and confirm.first.is_visible(timeout=2000):
        confirm.first.click()
    frame.wait_for_timeout(1000)
