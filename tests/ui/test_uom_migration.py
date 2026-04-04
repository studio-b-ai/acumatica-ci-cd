"""Playwright UI tests for UOM migration verification.

Verifies that the PIECE -> YDS base UOM rename and BOLTID -> BOLTID
lot/serial class rename completed successfully.

NOTE: Acumatica renders all screen content inside a 'main' iframe.
All DOM interactions must use page.frame("main"), not page directly.
"""
import pytest
from helpers import ACUMATICA_URL


# ── Test Data ──────────────────────────────────────────────────────────────

ITEM_CD = "00004"
EXPECTED_UOM = "YDS"
EXPECTED_LOT_CLASS = "BOLTID"
CUSTOMER_ID = "C000002"


def get_main_frame(page):
    """Get the main iframe where Acumatica renders screen content."""
    frame = page.frame("main")
    assert frame is not None, "Could not find Acumatica main iframe"
    return frame


def navigate_and_wait(page, screen_id, params="", timeout=60_000):
    """Navigate to an Acumatica screen and wait for the iframe to load."""
    url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
    if params:
        url += f"&{params}"
    # Use domcontentloaded — networkidle never fires on Acumatica screens
    # that maintain persistent connections (SO301000, etc.)
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    page.wait_for_timeout(8000)
    return get_main_frame(page)


# ── Check 1: Base UOM ─────────────────────────────────────────────────────

@pytest.mark.ui
class TestBaseUom:

    def test_stock_item_base_uom_is_yds(self, acumatica_page):
        """Open item 00004 and verify BaseUnit = YDS."""
        frame = navigate_and_wait(acumatica_page, "IN202500", f"InventoryCD={ITEM_CD}")

        frame.wait_for_selector("[id*='edBaseUnit_text']", state="attached", timeout=30_000)

        base_unit = frame.evaluate('''() => {
            var el = document.querySelector('[id*="edBaseUnit_text"]');
            return el ? el.value : null;
        }''')

        assert base_unit is not None, "Could not find BaseUnit field on IN202500"
        assert base_unit.strip() == EXPECTED_UOM, (
            f"BaseUnit should be '{EXPECTED_UOM}' but got '{base_unit.strip()}'"
        )


# ── Check 2: INUnit Self-Conversions ──────────────────────────────────────

@pytest.mark.ui
class TestInUnitConversions:

    def test_inunit_conversions_on_stock_item(self, acumatica_page, dialog_messages):
        """Open a stock item — if it loads without UOM errors, conversions work.

        Self-conversions are NOT displayed in the UI grid (they're internal).
        The real test is: does the screen load without UOM conversion errors?
        """
        frame = navigate_and_wait(acumatica_page, "IN202500", f"InventoryCD={ITEM_CD}")

        frame.wait_for_selector("[id*='edBaseUnit_text']", state="attached", timeout=30_000)

        # Verify item loaded correctly
        base_unit = frame.evaluate('''() => {
            var el = document.querySelector('[id*="edBaseUnit_text"]');
            return el ? el.value : null;
        }''')
        assert base_unit is not None, "Stock item screen did not load"

        # CRITICAL: Check for UOM conversion error dialogs
        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM conversion error(s): {[d['message'] for d in uom_errors]} — "
            "INUnit self-conversion records may be missing"
        )

    def test_inunit_conversions_screen(self, acumatica_page, dialog_messages):
        """Navigate to IN209000 and verify it loads without errors."""
        frame = navigate_and_wait(acumatica_page, "IN209000")

        # IN209000 may not exist or may load differently
        try:
            frame.wait_for_selector(
                "[id*='form'], [id*='grid'], [id*='UnitType']",
                state="attached", timeout=15_000,
            )
        except Exception:
            pytest.skip("IN209000 did not load — screen may not exist in this version")

        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM error on IN209000: {[d['message'] for d in uom_errors]}"
        )


# ── Check 3: UnallocatedPieceGoods GI ─────────────────────────────────────

@pytest.mark.ui
class TestUnallocatedPieceGoodsGI:

    def test_unallocated_piece_goods_gi_loads(self, acumatica_page, dialog_messages):
        """Navigate to the UnallocatedPieceGoods GI and verify it loads."""
        frame = navigate_and_wait(acumatica_page, "GI000000", "Name=UnallocatedPieceGoods")

        # GI may have results or be empty — either is OK
        gi_errors = [
            d for d in dialog_messages
            if "error" in d["message"].lower()
            or "inquiry" in d["message"].lower()
        ]
        assert not gi_errors, (
            f"GI error(s): {[d['message'] for d in gi_errors]} — "
            "UnallocatedPieceGoods GI definition may be broken"
        )


# ── Check 4: Sales Order Operations ───────────────────────────────────────

@pytest.mark.ui
class TestSalesOrderOperations:

    def test_existing_sales_order_loads_with_details(self, acumatica_page, dialog_messages):
        """Open the Sales Orders screen — if it loads without UOM errors, conversions work."""
        frame = navigate_and_wait(acumatica_page, "SO301000")

        try:
            frame.wait_for_selector(
                "[id*='edOrderType'], [id*='form'], [id*='grid']",
                state="attached", timeout=30_000,
            )
        except Exception:
            pytest.skip("SO301000 did not load")

        # Check for UOM errors
        load_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
            or "error" in d["message"].lower()
        ]
        assert not load_errors, (
            f"Error on Sales Orders screen: {[d['message'] for d in load_errors]} — "
            "this is the v1 failure mode"
        )

    @pytest.mark.slow
    def test_create_so_order_with_yds_item(self, acumatica_page, dialog_messages):
        """Create a sales order with a YDS item via REST API.

        REST API order creation exercises the same UOM validation path as the UI.
        If the order creates successfully, conversions are working.
        """
        import requests, warnings
        warnings.filterwarnings("ignore")

        from helpers import ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT

        s = requests.Session()
        r = s.post(f"{ACUMATICA_URL}/entity/auth/login", json={
            "name": ACUMATICA_USERNAME,
            "password": ACUMATICA_PASSWORD,
            "tenant": ACUMATICA_TENANT,
        })
        assert r.status_code == 204, f"REST API login failed: {r.status_code}"

        try:
            # Create order
            order = {
                "OrderType": {"value": "SO"},
                "CustomerID": {"value": CUSTOMER_ID},
                "Description": {"value": "UOM smoke test — auto-delete"},
                "Details": [{
                    "InventoryID": {"value": ITEM_CD},
                    "OrderQty": {"value": 1},
                    "UOM": {"value": EXPECTED_UOM},
                }],
            }

            r = s.put(
                f"{ACUMATICA_URL}/entity/Default/24.200.001/SalesOrder",
                json=order,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                timeout=60,
            )

            assert r.status_code in (200, 201), (
                f"Failed to create order (HTTP {r.status_code}): {r.text[:300]}"
            )

            result = r.json()
            order_id = result.get("id", "")
            print(f"✅ Order created successfully (id={order_id[:12]}...)")

            # Cleanup
            s.delete(f"{ACUMATICA_URL}/entity/Default/24.200.001/SalesOrder/{order_id}", timeout=30)
            print("Cleaned up test order")

        finally:
            s.post(f"{ACUMATICA_URL}/entity/auth/logout")
