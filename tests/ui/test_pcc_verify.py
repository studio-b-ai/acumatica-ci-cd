"""PCC (SB501000) post-deploy verification — PR #366 bug fixes + IIG date fields.

Verifies:
1. Detail panel syncs when clicking different grid rows
2. KPI tiles show non-zero counts
3. Metrics row visible (htmlKPITiles Height=280px)
4. New Shipping & Delivery date fields render in frmDetail
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from acumatica_screen import AcumaticaScreen
from helpers import ACUMATICA_URL, ACUMATICA_USERNAME


pytestmark = [pytest.mark.ui]

if not ACUMATICA_USERNAME:
    pytest.skip("ACUMATICA_USERNAME not set", allow_module_level=True)


class TestPCCBugFixes:
    """Verify the 3 P0 bug fixes from PR #366."""

    def test_screen_loads(self, acumatica_screen):
        """SB501000 loads without error after PR #366."""
        screen = acumatica_screen("SB501000")
        screen.assert_no_errors()

    def test_detail_panel_syncs_on_row_click(self, acumatica_screen):
        """Bug 1: Clicking different grid rows should update the detail panel.

        After fixing DataMember="Containers" on frmTimeline + frmDetail,
        the Container.Current should sync when grid selection changes.
        """
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)

        # Get the grid rows
        grid = screen.locator("[id*='gridContainers']")
        assert grid.count() > 0, "gridContainers not found"

        # Find clickable data rows (skip header)
        rows = screen.locator("[id*='gridContainers'] tr.GridRow, [id*='gridContainers'] [class*='Row']")
        screen.page.wait_for_timeout(2000)

        row_count = rows.count()
        if row_count < 2:
            pytest.skip("Need at least 2 container rows to test detail sync")

        # Click first row, read container nbr from detail
        rows.nth(0).click()
        screen.page.wait_for_timeout(2000)

        first_container = screen.get_field("edContainerCD") or screen.get_field("ContainerCD")

        # Click second row, read container nbr from detail
        rows.nth(1).click()
        screen.page.wait_for_timeout(2000)

        second_container = screen.get_field("edContainerCD") or screen.get_field("ContainerCD")

        # They should be different — detail panel is syncing
        assert first_container != second_container, (
            f"Detail panel did not sync: both rows show '{first_container}'. "
            "Bug 1 (DataMember sync) may not be fixed."
        )

        # Click a third row if available
        if row_count >= 3:
            rows.nth(2).click()
            screen.page.wait_for_timeout(2000)
            third_container = screen.get_field("edContainerCD") or screen.get_field("ContainerCD")
            assert third_container != second_container, (
                f"Detail panel did not sync on 3rd click: still shows '{second_container}'"
            )

    def test_kpi_tiles_show_counts(self, acumatica_screen):
        """Bug 3: KPI tiles should show non-zero counts for ACTION/WATCH/CLEAR.

        After adding real doc counts to RowSelected<ContainerFilter>,
        the risk aggregation should produce non-zero bucket counts.
        """
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)

        # Read the KPI tiles HTML content
        kpi_html = screen.evaluate(
            "() => { const el = document.querySelector('[id*=\"htmlKPITiles\"]'); "
            "return el ? el.innerHTML : ''; }"
        )

        assert kpi_html, "KPI tiles HTML is empty — htmlKPITiles not rendering"

        # Check that at least one tile shows a non-zero count
        # The tiles render as HTML with count values — at least one should be > 0
        # since we have known containers in sandbox
        import re
        numbers = re.findall(r'>(\d+)<', kpi_html)
        total = sum(int(n) for n in numbers if n.isdigit())
        assert total > 0, (
            f"All KPI tile counts are zero. Extracted numbers: {numbers}. "
            "Bug 3 (real doc counts in risk aggregation) may not be fixed."
        )

    def test_metrics_row_visible(self, acumatica_screen):
        """Bug 2: Metrics row should be visible below KPI tiles.

        After changing htmlKPITiles Height from 160px to 280px,
        the metrics row (OPEN PO VALUE / CROSS-DOCK RATE / UNCOVERED VALUE)
        should not be clipped.
        """
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)

        # Check the htmlKPITiles element has sufficient height
        height = screen.evaluate(
            "() => { const el = document.querySelector('[id*=\"htmlKPITiles\"]'); "
            "if (!el) return 0; "
            "return el.offsetHeight || parseInt(el.style.height) || 0; }"
        )

        assert height and int(height) >= 200, (
            f"htmlKPITiles height is {height}px — expected >= 200px for metrics row visibility"
        )

        # Verify the metrics row content exists in the HTML
        kpi_html = screen.evaluate(
            "() => { const el = document.querySelector('[id*=\"htmlKPITiles\"]'); "
            "return el ? el.innerHTML.toLowerCase() : ''; }"
        )

        # Check for metrics row keywords
        has_metrics = any(
            keyword in kpi_html
            for keyword in ["open po", "cross-dock", "uncovered", "po value"]
        )
        assert has_metrics, (
            "Metrics row content not found in KPI tiles HTML. "
            "Expected OPEN PO VALUE / CROSS-DOCK RATE / UNCOVERED VALUE."
        )


class TestPCCDateFields:
    """Verify new IIG parity date fields render in the detail form."""

    # Fields added in PR #366 — Shipping & Delivery group
    SHIPPING_DELIVERY_FIELDS = [
        "edCargoReadyDate",
        "edFactoryPickupDate",
        "edOnBoardDate",
        "edShipmentWindowStart",
        "edShipmentWindowEnd",
        "edDrayageAppointmentDate",
        "edDeliveryOrderDate",
        "edPaymentDueDate",
    ]

    def test_shipping_delivery_fields_exist(self, acumatica_screen):
        """All 8 new Shipping & Delivery date fields should be in the DOM."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)

        # Navigate to a record so the detail form renders
        last_btn = screen.locator("div[icon='Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            screen.page.wait_for_timeout(2000)

        missing = []
        for field_id in self.SHIPPING_DELIVERY_FIELDS:
            count = screen.locator(f"[id*='{field_id}']").count()
            if count == 0:
                missing.append(field_id)

        assert not missing, (
            f"Missing date fields in DOM: {missing}. "
            "Expected all Shipping & Delivery fields from PR #366."
        )


class TestPCCTabs:
    """Verify all tabs load without error."""

    TAB_NAMES = ["Events", "PO Links", "Costs", "Documents", "ETA History", "Lead Time"]

    @pytest.mark.parametrize("tab_name", TAB_NAMES)
    def test_tab_loads(self, acumatica_screen, tab_name):
        """Each tab should load without error when clicked."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(2000)

        # Navigate to a record first
        last_btn = screen.locator("div[icon='Last'], [id*='btnLast']").first
        if last_btn.is_visible(timeout=3000):
            last_btn.click()
            screen.page.wait_for_timeout(2000)

        # Click the tab
        tab = screen.locator(f"span:has-text('{tab_name}')").first
        if tab.is_visible(timeout=3000):
            tab.click()
            screen.page.wait_for_timeout(1500)

        screen.assert_no_errors()
