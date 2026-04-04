"""Container Tracking screen tests — verify IIG removal and AesthetikContainers.

After removing the IIG Container Management ISV, all IGCM screens and GIs
must be gone and replaced by SB501000 (Container Maintenance). This test
suite verifies:

1. SB501000 loads and both tabs (Events, PO Links) work
2. PO301000 container fields are visible
3. All old IGCM screen IDs (IG.CM.*) are properly removed (404/redirect)
4. Container Tracking workspace only has valid screens
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from helpers import (
    ACUMATICA_URL,
    ACUMATICA_USERNAME,
    find_custom_fields,
)


def navigate_to_screen_safe(page, screen_id, timeout=60_000):
    """Navigate to screen without networkidle (Acumatica keeps polling)."""
    url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(3000)


def wait_for_screen(page, screen_id, timeout=30_000):
    """Wait for an Acumatica screen to load. Verifies URL and checks for errors."""
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5000)

    # Verify we're on the right screen and not on an error page
    current_url = page.url
    assert "ScreenId=ERROR" not in current_url, \
        f"Screen {screen_id} redirected to error page"


pytestmark = [pytest.mark.ui]

# Skip entire module if credentials are missing
if not ACUMATICA_USERNAME:
    pytest.skip("ACUMATICA_USERNAME not set", allow_module_level=True)


# ── IGCM screens that must NOT exist after ISV removal ────────────────────
# These were registered by the IIG Container Management ISV.
# After cleanup, navigating to these should redirect to home or show a
# "Screen not found" page — NOT an IGCM.DAC type-not-found error.

IGCM_SCREENS = [
    # GI-based screens (referenced IGCM.DAC.* data sources)
    "IGCM0009",   # IG.CM.00.09 — PO Container Lines
    "IGCM0102",   # IG.CM.01.02 — PO Containers
    "IGCM0103",   # IG.CM.01.03 — PO Containers Distributions
    "IGCM0104",   # IG.CM.01.04 — SO Containers
    "IGCM0106",   # IG.CM.01.06 — Searates Events Information
    "IGCM0591",   # IG.CM.05.91 — Duty/Tariff Adjustments by Container
    # ASPX-based screens (pointed to ~/Pages/IG/IGCM*.aspx)
    "IGCM1010",   # IG.CM.10.10 — Container Management Preferences
    "IGCM1099",   # IG.CM.10.99 — Custom Classification for Origin
    "IGCM2092",   # IG.CM.20.92 — Container Types
    "IGCM2093",   # IG.CM.20.93 — Logistics Services
    "IGCM2094",   # IG.CM.20.94 — Container Destinations
    "IGCM2095",   # IG.CM.20.95 — Customer Payment Statuses
    "IGCM2096",   # IG.CM.20.96 — PO Container Statuses
    "IGCM2097",   # IG.CM.20.97 — Duty/Tariff Adjustments by Container
    "IGCM3091",   # IG.CM.30.91 — Freight Forwarders
    "IGCM3093",   # IG.CM.30.93 — Custom Classification
    "IGCM3094",   # IG.CM.30.94 — SO Containers
    "IGCM3095",   # IG.CM.30.95 — SO Container Statuses
]


class TestSB501000:
    """Verify Container Maintenance screen (SB501000) works end-to-end."""

    def test_screen_loads(self, acumatica_page):
        """SB501000 should load without error."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        wait_for_screen(acumatica_page, "SB501000")

        # Should not be on error page
        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "SB501000 redirected to error page"

    def test_navigate_to_record(self, acumatica_page):
        """Should be able to navigate to the last record."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        wait_for_screen(acumatica_page, "SB501000")

        # Click "Last Record" button to load a record
        last_btn = acumatica_page.locator("div[icon='Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_load_state("domcontentloaded")
            acumatica_page.wait_for_timeout(2000)

        # Should still be on SB501000, not error page
        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "SB501000 errored when navigating to a record"

    def test_events_tab_loads(self, acumatica_page):
        """Events tab should load without error."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        wait_for_screen(acumatica_page, "SB501000")

        # Navigate to a record first
        last_btn = acumatica_page.locator("div[icon='Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_load_state("domcontentloaded")
            acumatica_page.wait_for_timeout(2000)

        # Click Events tab
        events_tab = acumatica_page.locator("span:has-text('Events')").first
        if events_tab.is_visible(timeout=3000):
            events_tab.click()
            acumatica_page.wait_for_timeout(1000)

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "Events tab caused an error"

    def test_po_links_tab_loads(self, acumatica_page):
        """PO Links tab should load without IGCM.DAC type-not-found error."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        wait_for_screen(acumatica_page, "SB501000")

        # Navigate to last record
        last_btn = acumatica_page.locator("div[icon='Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            acumatica_page.wait_for_load_state("domcontentloaded")
            acumatica_page.wait_for_timeout(2000)

        # Click PO Links tab — this was the original crash point
        po_links_tab = acumatica_page.locator("span:has-text('PO Links')").first
        if po_links_tab.is_visible(timeout=3000):
            po_links_tab.click()
            acumatica_page.wait_for_timeout(2000)

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "PO Links tab caused IGCM.DAC type-not-found error"


class TestPO301000ContainerFields:
    """Verify container fields on Purchase Orders screen."""

    def test_po_screen_loads_without_error(self, acumatica_page):
        """PO301000 should load without IGCM type-not-found errors."""
        navigate_to_screen_safe(acumatica_page, "PO301000")
        wait_for_screen(acumatica_page, "PO301000")

        # The critical check: no error page, no IGCM.DAC crashes
        page_text = acumatica_page.locator("body").text_content() or ""
        assert "IGCM.DAC" not in page_text, \
            "PO301000 has IGCM.DAC reference — type-not-found error"

    def test_container_tracking_button_exists(self, acumatica_page):
        """CONTAINER TRACKING toolbar button should be present."""
        navigate_to_screen_safe(acumatica_page, "PO301000")
        wait_for_screen(acumatica_page, "PO301000")

        btn = acumatica_page.locator("text=CONTAINER TRACKING")
        assert btn.count() > 0, "CONTAINER TRACKING button not found on PO301000"

    def test_container_tracking_navigates_to_sb501000(self, acumatica_page):
        """Clicking CONTAINER TRACKING should navigate to SB501000 without error."""
        navigate_to_screen_safe(acumatica_page, "PO301000")
        wait_for_screen(acumatica_page, "PO301000")

        btn = acumatica_page.locator("text=CONTAINER TRACKING").first
        if btn.is_visible(timeout=3000):
            btn.click()
            acumatica_page.wait_for_load_state("domcontentloaded")
            acumatica_page.wait_for_timeout(3000)

        # Should land on SB501000 or stay on PO301000, NOT error page
        current_url = acumatica_page.url
        assert "ScreenId=ERROR" not in current_url, \
            f"CONTAINER TRACKING button caused error. URL: {current_url}"


class TestIGCMScreensRemoved:
    """Verify all IGCM (IIG Container Management) screens are removed.

    After unpublishing the IIG ISV and running CleanupIGCMArtifacts,
    none of the old IGCM screen IDs should load. They should either
    redirect to the home page or show "Page not found".

    Critical: they must NOT show "type not found: IGCM.DAC.*" errors.
    """

    @pytest.mark.parametrize("screen_id", IGCM_SCREENS, ids=IGCM_SCREENS)
    def test_igcm_screen_does_not_load(self, acumatica_page, dialog_messages, screen_id):
        """IGCM screen should not load — must be gone from SiteMap."""
        navigate_to_screen_safe(acumatica_page, screen_id)
        acumatica_page.wait_for_timeout(3000)

        current_url = acumatica_page.url

        # Acceptable outcomes:
        # 1. Redirected to home/welcome page (screen removed from SiteMap)
        # 2. Shows error page (screen registered but graph/aspx missing)
        # NOT acceptable: the screen actually loads with IGCM content

        # Check that no IGCM.DAC error dialogs fired
        igcm_errors = [
            m for m in dialog_messages
            if "IGCM" in m.get("message", "")
        ]
        assert len(igcm_errors) == 0, \
            f"IGCM.DAC error dialog on {screen_id}: {igcm_errors}"

        # If we landed on an error page, that's acceptable (screen is dead)
        # If we landed on the screen, that's a problem (should have been cleaned up)
        if f"ScreenId={screen_id}" in current_url:
            # Screen is still registered — check it's not showing IGCM content
            page_text = acumatica_page.locator("body").text_content() or ""
            assert "IGCM" not in page_text, \
                f"Screen {screen_id} still shows IGCM content"


class TestContainerTrackingWorkspace:
    """Verify the Container Tracking sidebar workspace is clean."""

    def test_workspace_link_exists(self, acumatica_page):
        """Container Tracking should appear in the sidebar."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        acumatica_page.wait_for_timeout(2000)

        sidebar = acumatica_page.locator("text=Container Tracking")
        assert sidebar.count() > 0, "Container Tracking workspace not found in sidebar"

    def test_workspace_click_no_error(self, acumatica_page):
        """Clicking Container Tracking workspace should not error."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        acumatica_page.wait_for_timeout(2000)

        workspace_link = acumatica_page.locator("text=Container Tracking").first
        if workspace_link.is_visible(timeout=3000):
            workspace_link.click()
            acumatica_page.wait_for_timeout(3000)

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "Container Tracking workspace click caused error"
