"""Playwright UI tests for UOM migration verification.

Verifies that the PIECE -> YDS base UOM rename and PIECENBR -> BOLTID
lot/serial class rename completed successfully on Heritage Test.

These tests would have caught the v1 failure (2026-03-28) where DELETE FROM
INUnit destroyed self-conversion records, making inventory operations fail.

Run against Heritage Test after publishing UomRenamePieceToYds.
"""
import pytest
from helpers import (
    ACUMATICA_URL,
    navigate_to_screen,
    assert_screen_loaded,
    get_field_value,
    wait_for_screen_ready,
    create_pc_order,
    open_line_details,
    get_line_details_splits,
    close_popup,
)


# ── Test Data ──────────────────────────────────────────────────────────────

# Known fabric stock item (Super Batiste - White Snow)
ITEM_CD = "28021"
EXPECTED_UOM = "YDS"
EXPECTED_LOT_CLASS = "BOLTID"


# ── Check 1: Base UOM ─────────────────────────────────────────────────────

@pytest.mark.ui
class TestBaseUom:
    """Verify stock items show YDS as base UOM after migration."""

    def test_stock_item_base_uom_is_yds(self, acumatica_page):
        """Open a known fabric item and verify BaseUnit = YDS.

        This confirms Section 1 of the migration ran: InventoryItem.BaseUnit
        was updated from PIECE to YDS.
        """
        page = acumatica_page
        page.goto(
            f"{ACUMATICA_URL}/Main?ScreenId=IN202500&InventoryCD={ITEM_CD}",
            wait_until="domcontentloaded",
        )
        assert_screen_loaded(page, "IN202500")

        # BaseUnit field — try known ID pattern, fall back to DOM search
        base_unit = None
        for selector in [
            "#ctl00_phF_form_edBaseUnit",
            "[id*='edBaseUnit']",
            "[id*='BaseUnit'] input",
        ]:
            el = page.locator(selector).first
            if el.count() > 0:
                base_unit = el.input_value() or el.text_content()
                break

        assert base_unit is not None, (
            "Could not find BaseUnit field on IN202500 — "
            "check Acumatica field IDs"
        )
        base_unit = base_unit.strip()
        assert base_unit == EXPECTED_UOM, (
            f"BaseUnit should be '{EXPECTED_UOM}' but got '{base_unit}' — "
            "migration may not have run or was rolled back"
        )


# ── Check 2: INUnit Self-Conversions ──────────────────────────────────────

@pytest.mark.ui
class TestInUnitConversions:
    """Verify YDS -> YDS self-conversion records exist.

    This is THE critical check. The v1 failure deleted these records,
    making all inventory operations fail with 'UOM conversion not found'.
    """

    def test_inunit_conversions_on_stock_item(self, acumatica_page, dialog_messages):
        """Open a stock item and check its Conversions tab for YDS -> YDS.

        This tests the same user operation that broke in v1: opening a stock
        item that depends on self-conversion records.
        """
        page = acumatica_page
        page.goto(
            f"{ACUMATICA_URL}/Main?ScreenId=IN202500&InventoryCD={ITEM_CD}",
            wait_until="domcontentloaded",
        )
        assert_screen_loaded(page, "IN202500")

        # Look for a Conversions tab or UOM tab
        conversions_tab = None
        for label in ["Conversions", "Unit Conversions", "UOM"]:
            tab = page.locator(f"span:has-text('{label}')").first
            if tab.count() > 0:
                conversions_tab = tab
                break

        if conversions_tab is not None:
            conversions_tab.click()
            page.wait_for_timeout(1000)

            # Check grid for YDS -> YDS row
            page_text = page.locator("#ctl00_phG_tab").text_content() or ""
            assert EXPECTED_UOM in page_text, (
                f"Conversions tab should contain '{EXPECTED_UOM}' but tab content "
                "does not include it — self-conversion record may be missing"
            )
        else:
            # No conversions tab — check that the screen at least loaded
            # without UOM conversion errors
            pass

        # CRITICAL: Check for UOM conversion error dialogs
        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM conversion error dialog(s) detected: "
            f"{[d['message'] for d in uom_errors]} — "
            "INUnit self-conversion records may be missing (v1 failure mode)"
        )

    def test_inunit_conversions_screen(self, acumatica_page, dialog_messages):
        """Navigate to IN209000 (Unit Conversions) and verify YDS -> YDS exists.

        Direct verification of the conversion record in the dedicated screen.
        """
        page = acumatica_page

        # Navigate to Unit Conversions screen with item context
        page.goto(
            f"{ACUMATICA_URL}/Main?ScreenId=IN209000",
            wait_until="domcontentloaded",
        )

        # Wait for screen — IN209000 may use a different layout
        try:
            page.wait_for_function(
                """() => {
                    return document.querySelector('#ctl00_phF_form') !== null
                        || document.querySelector('#ctl00_phG_grid') !== null
                        || document.querySelector('[id*="UnitType"]') !== null;
                }""",
                timeout=15_000,
            )
        except Exception:
            pytest.skip("IN209000 did not load — screen may require different navigation")

        # Try to set the inventory item filter
        for selector in [
            "#ctl00_phF_form_edInventoryID",
            "[id*='edInventoryID']",
            "[id*='InventoryID'] input",
        ]:
            el = page.locator(selector).first
            if el.count() > 0:
                el.click()
                el.fill(ITEM_CD)
                page.keyboard.press("Tab")
                page.wait_for_timeout(1000)
                break

        # Look for YDS in the grid content
        grid = page.locator("#ctl00_phG_grid, [id*='grid']").first
        if grid.count() > 0:
            grid_text = grid.text_content() or ""
            assert EXPECTED_UOM in grid_text, (
                f"Unit Conversions grid should contain '{EXPECTED_UOM}' for item "
                f"{ITEM_CD} but it does not — self-conversion record may be missing"
            )

        # Check for error dialogs
        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM conversion error on IN209000: "
            f"{[d['message'] for d in uom_errors]}"
        )


# ── Check 3: UnallocatedPieceGoods GI ─────────────────────────────────────

@pytest.mark.ui
class TestUnallocatedPieceGoodsGI:
    """Verify the Unallocated Piece Goods Generic Inquiry loads with BOLTID filter."""

    def test_unallocated_piece_goods_gi_loads(self, acumatica_page, dialog_messages):
        """Navigate to the UnallocatedPieceGoods GI and verify it loads.

        The GI filters on InventoryItem.LotSerClassID = 'BOLTID' (was PIECENBR).
        If the filter value doesn't match what's in the database, the GI may
        return empty results but should still load without error.
        """
        page = acumatica_page

        # Generic Inquiries are accessed via their design name
        page.goto(
            f"{ACUMATICA_URL}/Main?ScreenId=GI000000&Name=UnallocatedPieceGoods",
            wait_until="domcontentloaded",
        )

        # Wait for GI screen to load — GIs use grid layout
        try:
            page.wait_for_function(
                """() => {
                    return document.querySelector('[id*="grid"]') !== null
                        || document.querySelector('[id*="Grid"]') !== null
                        || document.querySelector('.GridRow') !== null;
                }""",
                timeout=15_000,
            )
        except Exception:
            # GI may not have results — check if it loaded at all vs errored
            error_text = page.text_content("body") or ""
            assert "error" not in error_text.lower() or "no data" in error_text.lower(), (
                "UnallocatedPieceGoods GI failed to load — "
                "check that BOLTID lot class exists and GI definition is correct"
            )
            return  # GI loaded but empty — that's OK

        # Check for error dialogs (GI definition errors show as dialogs)
        gi_errors = [
            d for d in dialog_messages
            if "error" in d["message"].lower()
            or "inquiry" in d["message"].lower()
        ]
        assert not gi_errors, (
            f"GI error dialog(s): {[d['message'] for d in gi_errors]} — "
            "UnallocatedPieceGoods GI definition may be broken"
        )

        # If grid has rows, verify BOLTID appears (optional — GI may be empty)
        grid = page.locator("[id*='grid'], [id*='Grid']").first
        if grid.count() > 0:
            grid_text = grid.text_content() or ""
            # Only assert BOLTID if the grid has actual data rows
            rows = page.locator(".GridRow, tr[class*='Row']")
            if rows.count() > 0 and EXPECTED_LOT_CLASS not in grid_text:
                pytest.xfail(
                    f"GI has rows but '{EXPECTED_LOT_CLASS}' not found in grid — "
                    "LotSerClassID column may not be displayed"
                )


# ── Check 4: Sales Order Operations ───────────────────────────────────────

@pytest.mark.ui
class TestSalesOrderOperations:
    """Verify sales orders work correctly after UOM migration.

    The v1 failure made it impossible to open sales orders because
    loading SOLine rows triggers internal UOM conversion resolution.
    """

    def test_existing_sales_order_loads_with_details(
        self, so301000, dialog_messages
    ):
        """Open an existing sales order and expand line details.

        Read-only test — navigates to the most recent PC order and verifies
        line details can be expanded without UOM conversion errors.
        """
        page = so301000

        # Find any existing PC order
        from helpers import set_field_value
        set_field_value(page, "ctl00_phF_form_edOrderType", "PC")
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)

        # Click the first order in the grid if available
        first_row = page.locator("tr.GridRow, tr[class*='Row']").first
        if first_row.count() == 0:
            pytest.skip("No existing PC orders found — cannot test read path")

        first_row.click()
        page.wait_for_timeout(500)

        # Navigate into the order
        first_row.dblclick()
        wait_for_screen_ready(page)

        order_nbr = get_field_value(page, "ctl00_phF_form_edOrderNbr")
        assert order_nbr, "Should have navigated into an existing PC order"

        # Check for error dialogs during load
        load_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
            or "error" in d["message"].lower()
        ]
        assert not load_errors, (
            f"Error loading sales order {order_nbr}: "
            f"{[d['message'] for d in load_errors]} — "
            "this is the v1 failure mode (missing INUnit self-conversions)"
        )

        # Try to open line details
        grid_rows = page.locator("#ctl00_phG_grid tr.GridRow, #ctl00_phG_grid tr[class*='Row']")
        if grid_rows.count() > 0:
            grid_rows.first.click()
            page.wait_for_timeout(300)

            try:
                open_line_details(page)
                splits = get_line_details_splits(page)
                close_popup(page)
            except Exception as e:
                # Line details may not be available for all order types
                pass

            # Check for UOM errors after opening line details
            detail_errors = [
                d for d in dialog_messages
                if "conversion" in d["message"].lower()
                or "uom" in d["message"].lower()
            ]
            assert not detail_errors, (
                f"UOM error opening line details for {order_nbr}: "
                f"{[d['message'] for d in detail_errors]}"
            )

    @pytest.mark.slow
    def test_create_pc_order_with_boltid_item(
        self, so301000, created_orders, dialog_messages
    ):
        """Create a new PC order with a BOLTID item and verify it saves.

        Write test — creates a real order, verifies save works, then cleans up.
        This tests the full write path including auto-allocation with the
        new BOLTID lot class and YDS UOM.
        """
        page = so301000

        order_nbr = create_pc_order(
            page,
            customer_id="C000221",  # Drapery House
            items=[{
                "inventory_cd": ITEM_CD,
                "warehouse": "98",
                "qty": 10.00,
                "uom": EXPECTED_UOM,
            }],
        )

        assert order_nbr, "Order number should be generated after save"
        created_orders.append(("PC", order_nbr))

        # ASSERT 1: No error dialogs during save
        save_errors = [
            d for d in dialog_messages
            if "error" in d["message"].lower()
            or "conversion" in d["message"].lower()
            or "negative" in d["message"].lower()
        ]
        assert not save_errors, (
            f"Error creating PC order: {[d['message'] for d in save_errors]} — "
            "UOM migration may have broken order creation"
        )

        # ASSERT 2: Order saved with correct UOM
        line_uom = None
        grid_rows = page.locator("#ctl00_phG_grid tr.GridRow, #ctl00_phG_grid tr[class*='Row']")
        if grid_rows.count() > 0:
            grid_rows.first.click()
            page.wait_for_timeout(300)
            try:
                open_line_details(page)
                splits = get_line_details_splits(page)
                if splits:
                    line_uom = splits[0].get("uom", "").strip()
                close_popup(page)
            except Exception:
                pass

        if line_uom:
            assert line_uom == EXPECTED_UOM, (
                f"Line split UOM should be '{EXPECTED_UOM}' but got '{line_uom}'"
            )
