"""Playwright UI tests for UOM migration verification.

Verifies that the PIECE -> YDS base UOM rename and BOLTID -> BOLTID
lot/serial class rename completed successfully.

NOTE: Acumatica renders all screen content inside a 'main' iframe.
All DOM interactions must use page.frame("main"), not page directly.

GOTCHA fixed 2026-04-08: this file historically tested ONE item (00004)
which was a happy-path item that the UOM migration v3 cleanly handled.
Item 00006 (and an unknown number of others) had its BaseUnit flipped
to YDS by Section 2 of the migration, but never received a YDS→YDS
self-conversion row from Section 1 (which only seeded from existing
PIECE→PIECE rows). Save fails on those items with:
  "The PIECE value specified in the To Unit box differs from the YDS
   base unit specified for the <item> item."
The new TestStockItemSaveSample class iterates a sample of items and
verifies each can be saved via the REST API (which exercises the same
graph validation as a UI save). Pairs with EnsureItemUomConsistency in
AesthetikContainersInstall.cs which idempotently INSERTs the missing
self-conversions on every publish.
"""
import pytest
from helpers import ACUMATICA_URL
from acumatica_screen import AcumaticaScreen


# ── Test Data ──────────────────────────────────────────────────────────────

ITEM_CD = "00004"
EXPECTED_UOM = "YDS"
EXPECTED_LOT_CLASS = "BOLTID"
CUSTOMER_ID = "C000002"

# How many stock items to sample-save in TestStockItemSaveSample.
# Trade-off: larger N catches more bugs but slows the test suite.
# 5 items × ~15s each = ~75s — fits within the 300s timeout.
# 5 is enough to catch a 20%+ corruption rate with ~67% confidence.
# Reduced from 10 → 5 to fit within the 8-minute core-UI-tests step
# budget (sandbox-gate run 24569665633 timed out at exactly 8 min).
SAVE_SAMPLE_SIZE = 5


# ── Check 1: Base UOM ─────────────────────────────────────────────────────

@pytest.mark.ui
class TestBaseUom:

    def test_stock_item_base_uom_is_yds(self, acumatica_screen):
        """Open item 00004 and verify BaseUnit = YDS.

        Uses AcumaticaScreen.get_field() which retries on the known
        iframe-read flake (frame.evaluate() returning empty string).
        An additional wait after navigation gives Acumatica time to
        populate the field (the default 3x500ms retry was too short
        on sandbox where app-pool warmup delays field rendering).
        """
        screen = acumatica_screen("IN202500", params=f"InventoryCD={ITEM_CD}")
        # Extra wait for field population after app-pool warmup
        screen.page.wait_for_timeout(3000)

        base_unit = screen.get_field("edBaseUnit_text")

        assert base_unit is not None and base_unit != "", (
            "Could not read BaseUnit field on IN202500 — "
            "evaluate() returned empty after retries"
        )
        assert base_unit.strip() == EXPECTED_UOM, (
            f"BaseUnit should be '{EXPECTED_UOM}' but got '{base_unit.strip()}'"
        )


# ── Check 2: INUnit Self-Conversions ──────────────────────────────────────

@pytest.mark.ui
class TestInUnitConversions:

    def test_inunit_conversions_on_stock_item(self, acumatica_screen, dialog_messages):
        """Open a stock item — if it loads without UOM errors, conversions work."""
        screen = acumatica_screen("IN202500", params=f"InventoryCD={ITEM_CD}")

        base_unit = screen.get_field("edBaseUnit_text")
        assert base_unit is not None, "Stock item screen did not load"

        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM conversion error(s): {[d['message'] for d in uom_errors]} — "
            "INUnit self-conversion records may be missing"
        )

    def test_inunit_conversions_screen(self, acumatica_screen, dialog_messages):
        """Navigate to IN209000 and verify it loads without errors."""
        try:
            screen = acumatica_screen("IN209000")
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

    def test_unallocated_piece_goods_gi_loads(self, acumatica_screen, dialog_messages):
        """Navigate to the UnallocatedPieceGoods GI and verify it loads."""
        screen = acumatica_screen("GI000000", params="Name=UnallocatedPieceGoods")

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

    def test_existing_sales_order_loads_with_details(self, acumatica_screen, dialog_messages):
        """Open the Sales Orders screen — if it loads without UOM errors, conversions work."""
        screen = acumatica_screen("SO301000")

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


# ── Check 5: Stock Item Save Sample ────────────────────────────────────────
#
# Catches the 2026-04-08 incident class: items where UOM Migration v3
# Section 1 didn't seed a YDS→YDS self-conversion (because the item
# never had a PIECE→PIECE row to seed from), so save fails on graph
# validation. The pre-existing TestBaseUom + TestInUnitConversions
# tests verified ONE item (00004) and only checked LOAD, not SAVE —
# they passed even after item 00006 was broken.
#
# This test:
#   1. Pulls a sample of YDS-base StockItems via REST API
#   2. PUT-saves each one (no-op edit) and verifies a 200/204 response
#   3. Aggregates failures into one assertion so the report names every
#      broken item, not just the first

@pytest.mark.ui
class TestStockItemSaveSample:
    """Click-Save an item in the UI and listen for alert() dialogs.

    History: an earlier version of this class used REST-API touched-field
    PUTs to trigger ValidateUnitConversions. On 2026-04-09 we discovered
    that the contract-based REST API does NOT fire the same validator
    path as the UI save — touched-field PUTs return HTTP 200 even for
    items that are definitively broken (their IN202500 UI Save shows
    \"The PIECE value specified in the To Unit box differs from the YDS
    base unit\" in a JavaScript alert dialog). Every PR from 2026-04-08
    shipped a sandbox-gate green based on the broken REST test.

    The reliable reproduction is: open the item in the UI, dirty a field,
    click Save, and listen for ``dialog`` events via Playwright. This class
    does exactly that. It is the ONLY save test that provably reproduces
    the "PIECE value" corruption the users reported.
    """

    @pytest.mark.timeout(300)
    def test_sample_of_stock_items_can_be_saved_via_ui(self, acumatica_page):
        from playwright.sync_api import Page
        import re

        page: Page = acumatica_page

        # Listen for native alert/confirm/prompt dialogs and collect them.
        # The validator error surfaces as a JavaScript alert().
        collected_dialogs: list[str] = []

        def on_dialog(d):
            collected_dialogs.append(d.message)
            try:
                d.accept()
            except Exception:
                pass

        page.on("dialog", on_dialog)

        # Pull a YDS-base sample via REST (just for the list — the actual
        # save happens through the UI).
        import requests, warnings
        warnings.filterwarnings("ignore")
        from helpers import ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT

        s = requests.Session()
        r = s.post(f"{ACUMATICA_URL}/entity/auth/login", json={
            "name": ACUMATICA_USERNAME,
            "password": ACUMATICA_PASSWORD,
            "tenant": ACUMATICA_TENANT,
        }, timeout=30, verify=False)
        assert r.status_code == 204, f"REST API login failed: {r.status_code}"
        try:
            r = s.get(
                f"{ACUMATICA_URL}/entity/Default/24.200.001/StockItem"
                f"?$top={SAVE_SAMPLE_SIZE * 4}"
                f"&$select=InventoryID,BaseUOM",
                headers={"Accept": "application/json"},
                timeout=60,
                verify=False,
            )
            items = r.json() if r.status_code == 200 else []
        finally:
            s.post(f"{ACUMATICA_URL}/entity/auth/logout", verify=False)

        yds_items = [
            (it.get("InventoryID", {}) or {}).get("value", "").strip()
            for it in items
            if (it.get("BaseUOM", {}) or {}).get("value") == EXPECTED_UOM
        ]
        yds_items = [iid for iid in yds_items if iid][:SAVE_SAMPLE_SIZE]

        assert len(yds_items) > 0, (
            f"No YDS-base items found in first {SAVE_SAMPLE_SIZE * 4} StockItems"
        )

        print(f"UI click-Save sample: {len(yds_items)} items")

        # Dirty-then-save JS (idempotent — re-sets Description to original).
        # Reads the header Description input (phF_form_edDescr), appends a
        # space, fires input+change events, then restores the original
        # value and fires events again. The appearance of a non-empty
        # "dirty" state is enough to trigger Persist on Save click.
        dirty_js = """() => {
            const desc = document.getElementById("ctl00_phF_form_edDescr");
            if (!desc) return {ok: false, reason: "no edDescr"};
            const orig = desc.value || "";
            desc.focus();
            desc.value = orig + " ";
            desc.dispatchEvent(new Event("input", {bubbles: true}));
            desc.dispatchEvent(new Event("change", {bubbles: true}));
            desc.value = orig;
            desc.dispatchEvent(new Event("input", {bubbles: true}));
            desc.dispatchEvent(new Event("change", {bubbles: true}));
            return {ok: true, orig: orig};
        }"""

        # Click Save (not SaveCloseToList — that navigates before the
        # dialog can be captured on some fast items).
        click_save_js = """() => {
            const candidates = Array.from(document.querySelectorAll(\"[title='Save']\"))
                .filter(el => el.offsetParent !== null && !(el.id || "").includes("Close"));
            if (candidates.length === 0) {
                const fallback = Array.from(document.querySelectorAll(\"[id*='ToolBar_Save']\"))
                    .filter(el => el.offsetParent !== null);
                if (fallback.length === 0) return {ok: false, reason: "no Save button"};
                fallback[0].click();
                return {ok: true, id: fallback[0].id};
            }
            candidates[0].click();
            return {ok: true, id: candidates[0].id};
        }"""

        failures = []
        for iid in yds_items:
            collected_dialogs.clear()

            screen = AcumaticaScreen.navigate(page, "IN202500", params=f"InventoryCD={iid}")

            dirty_result = screen.evaluate(dirty_js, retries=1, delay_ms=0)
            if not dirty_result or not dirty_result.get("ok"):
                failures.append(f"{iid}: could not dirty header ({dirty_result})")
                continue

            screen.evaluate(click_save_js, retries=1, delay_ms=0)
            # Give Acumatica time to round-trip and fire the dialog.
            page.wait_for_timeout(5000)

            # Any dialog whose text mentions the UOM validator phrases
            # is a save failure.
            for msg in collected_dialogs:
                if re.search(
                    r"(PIECE|YDS).{0,100}(unit|base)|conversion rule|not found",
                    msg,
                    re.IGNORECASE,
                ):
                    failures.append(f"{iid}: {msg[:250]}")
                    break

        assert not failures, (
            f"{len(failures)} of {len(yds_items)} sampled YDS items failed UI "
            f"click-Save with a UOM validator error:\n"
            + "\n".join(failures[:25])
            + ("\n..." if len(failures) > 25 else "")
        )
        print(f"✅ All {len(yds_items)} sampled YDS items saved cleanly in the UI")

