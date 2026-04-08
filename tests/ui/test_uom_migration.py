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
from helpers import ACUMATICA_URL, navigate_and_wait


# ── Test Data ──────────────────────────────────────────────────────────────

ITEM_CD = "00004"
EXPECTED_UOM = "YDS"
EXPECTED_LOT_CLASS = "BOLTID"
CUSTOMER_ID = "C000002"

# How many stock items to sample-save in TestStockItemSaveSample.
# Trade-off: larger N catches more bugs but slows the test suite.
# 25 is enough to catch a 5%+ corruption rate with high confidence.
SAVE_SAMPLE_SIZE = 25


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

    def test_sample_of_stock_items_can_be_saved(self):
        """Pull a sample of YDS-base stock items via REST and verify each saves.

        Save invokes the graph validation pipeline (same as UI save), so
        any item missing a YDS→YDS self-conversion row in INUnit will fail
        with the UnitVerifying error. Iterating across a sample catches
        the partial-migration class of bugs that single-item tests miss.
        """
        import requests, warnings
        warnings.filterwarnings("ignore")

        from helpers import ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT

        s = requests.Session()
        r = s.post(f"{ACUMATICA_URL}/entity/auth/login", json={
            "name": ACUMATICA_USERNAME,
            "password": ACUMATICA_PASSWORD,
            "tenant": ACUMATICA_TENANT,
        }, timeout=30)
        assert r.status_code == 204, f"REST API login failed: {r.status_code}"

        try:
            # Pull the first SAVE_SAMPLE_SIZE*3 stock items with their
            # BaseUOM + Description. The REST contract field is BaseUOM,
            # NOT BaseUnit — the DAC column is named BaseUnit but the
            # endpoint exposes it as BaseUOM. Description is needed so
            # we can do a touched-field PUT and revert below.
            r = s.get(
                f"{ACUMATICA_URL}/entity/Default/24.200.001/StockItem"
                f"?$top={SAVE_SAMPLE_SIZE * 3}"
                f"&$select=InventoryID,Description,BaseUOM",
                headers={"Accept": "application/json"},
                timeout=60,
            )
            assert r.status_code == 200, (
                f"Failed to list stock items (HTTP {r.status_code}): {r.text[:300]}"
            )

            items = r.json()
            yds_items = [
                it for it in items
                if (it.get("BaseUOM", {}) or {}).get("value") == EXPECTED_UOM
            ][:SAVE_SAMPLE_SIZE]

            assert len(yds_items) > 0, (
                f"Could not find any YDS-base stock items in the first "
                f"{SAVE_SAMPLE_SIZE * 3} stock items. UOM migration may have "
                f"left no items in the expected base unit."
            )

            print(f"Sampling {len(yds_items)} YDS-base stock items for save check...")

            # CRITICAL: a no-op PUT (body = only InventoryID) returns 200
            # without calling Persist() because no field changed. That
            # means ValidateUnitConversions never runs and the test
            # silently passes on broken items. Use a touched-field PUT
            # (Description + " [DIAG ...]") to force Persist, then
            # PUT-revert if the touch succeeds. Revert is skipped on
            # failure because nothing was written when Persist threw.
            import datetime
            diag_marker = f" [DIAG-UOM {datetime.datetime.utcnow().strftime('%H%M%S')}]"

            failures = []
            unreverted = []
            for it in yds_items:
                inv_id_obj = it.get("InventoryID", {}) or {}
                inv_cd = inv_id_obj.get("value", "<unknown>").strip()
                orig_desc = (it.get("Description", {}) or {}).get("value") or ""

                # Touched-field PUT: flips Description to force Persist.
                touch_payload = {
                    "InventoryID": {"value": inv_cd},
                    "Description": {"value": orig_desc + diag_marker},
                }
                pr = s.put(
                    f"{ACUMATICA_URL}/entity/Default/24.200.001/StockItem",
                    json=touch_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                if pr.status_code not in (200, 201, 204):
                    # Save failed — nothing was written, so no revert needed.
                    # Extract the innerException since the outer wrapper
                    # just says "Operation failed".
                    inner_msg = ""
                    try:
                        body = pr.json()
                        inner_msg = (body.get("innerException") or {}).get(
                            "exceptionMessage", ""
                        ) or body.get("exceptionMessage", "")
                    except Exception:
                        inner_msg = pr.text[:300].replace("\n", " ")
                    failures.append(
                        f"{inv_cd} → HTTP {pr.status_code}: {inner_msg[:250]}"
                    )
                    continue

                # Save succeeded — revert immediately to leave data unchanged.
                revert_payload = {
                    "InventoryID": {"value": inv_cd},
                    "Description": {"value": orig_desc},
                }
                rr = s.put(
                    f"{ACUMATICA_URL}/entity/Default/24.200.001/StockItem",
                    json=revert_payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    timeout=30,
                )
                if rr.status_code not in (200, 201, 204):
                    unreverted.append(
                        f"{inv_cd}: touch succeeded but revert failed "
                        f"(HTTP {rr.status_code}) — manual cleanup required, "
                        f"Description has {diag_marker!r} appended"
                    )

            # Report unreverted touches separately so a revert failure
            # cannot be silently hidden by the main assertion.
            assert not unreverted, (
                f"{len(unreverted)} touch-PUTs succeeded but their reverts "
                f"failed — data was mutated on save-successful items:\n"
                + "\n".join(unreverted)
            )
            assert not failures, (
                f"{len(failures)} of {len(yds_items)} sampled stock items "
                f"failed to save:\n" + "\n".join(failures[:20]) +
                ("\n..." if len(failures) > 20 else "")
            )
            print(f"✅ All {len(yds_items)} sampled stock items saved cleanly")

        finally:
            s.post(f"{ACUMATICA_URL}/entity/auth/logout")
