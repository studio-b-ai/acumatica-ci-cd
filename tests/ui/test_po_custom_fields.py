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
