"""Playwright fixtures for Acumatica UI tests."""
import json
import pytest
from playwright.sync_api import sync_playwright, Page

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from helpers import (  # noqa: E402
    ACUMATICA_URL,
    ACUMATICA_USERNAME,
    ACUMATICA_PASSWORD,
    ACUMATICA_TENANT,
    HEADED,
    SLOW_MO,
    wait_for_screen_ready,
    delete_order,
)


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

    page.goto(f"{ACUMATICA_URL}/Frames/Login.aspx", wait_until="networkidle")

    page.fill("#txtUser", ACUMATICA_USERNAME)
    page.fill("#txtPass", ACUMATICA_PASSWORD)

    company_select = page.locator("#cmbCompany")
    if company_select.is_visible(timeout=3000):
        company_select.select_option(label=ACUMATICA_TENANT)

    page.click("#btnLogin")

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


FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ui_screens.json")


def load_screen_fixtures():
    """Load UI screen fixtures from JSON file."""
    if not os.path.exists(FIXTURES_PATH):
        return []
    with open(FIXTURES_PATH) as f:
        return json.load(f)


@pytest.fixture
def screen_page(acumatica_page):
    """Return the authenticated page for screen navigation tests.

    Unlike so301000 which navigates to a specific screen, this just
    returns the authenticated page for the test to navigate wherever needed.
    """
    return acumatica_page
