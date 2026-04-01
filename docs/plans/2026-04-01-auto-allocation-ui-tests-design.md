# Auto-Allocation UI Test Suite — Design

**Date:** 2026-04-01
**Status:** Approved

## Problem

Auto-allocation bugs manifest as UI-level issues: error dialogs, silently changed field values, incorrect split data in the Line Details popup. REST API tests can't catch these. We need browser-level tests that replicate the exact workflow Sarah demonstrated.

## Solution

Python + Playwright test suite targeting Heritage Test (live). Tests create real PC orders via SO301000, validate auto-allocation behavior through the UI, and delete test orders on teardown.

## Architecture

```
tests/
  ui/
    conftest.py              — Fixtures: login, page setup, order cleanup
    test_auto_allocation.py  — 4 test scenarios
```

**Framework:** Python + `playwright` (sync API). Matches existing test stack.

**Target:** Heritage Test (`heritagefabrics.acumatica.com`), configured via env vars.

**Credentials:** `ACUMATICA_URL`, `ACUMATICA_USERNAME`, `ACUMATICA_PASSWORD`, `ACUMATICA_TENANT` — same pattern as `smoke-e2e.py` and `validate-publish.py`.

## Test Scenarios

### 1. test_partial_allocation_preserves_qty

Reproduces Sarah's exact bug. Creates PC order for DRAPERY HOUSE (C000221), adds item 28021 (118 Super Batiste - White Snow) warehouse 98 with qty 40.00 PIECE. Saves. Validates:
- OrderQty field still shows 40.00 (not reduced)
- No browser error dialog appeared during save
- Line Details popup shows bolt splits with lot serials + one unallocated remainder split
- Split quantities sum to 40.00
- Order description contains "[AUTO-ALLOC"

### 2. test_full_allocation_no_remainder

Creates PC order with a small quantity that available bolts can fully cover. Validates:
- All splits have lot serial numbers
- No unallocated remainder split exists
- No error dialogs

### 3. test_no_bolts_marks_po_create

Creates PC order for a PIECENBR item at a warehouse with zero available bolts. Validates:
- Order saves without error
- Line has POCreate checked (or back-order indicator)

### 4. test_no_negative_inventory_error

Creates PC order, saves, and explicitly checks no "quantity will go negative" browser dialog appeared. This was the most user-visible bug from Sarah's report.

## Fixtures

### acumatica_page

- Launches Chromium (headless by default, `--headed` for debug)
- Navigates to Acumatica login page
- Fills username/password, selects tenant, clicks Sign In
- Waits for main menu to load
- Yields authenticated `Page` object
- On teardown: closes browser

### create_pc_order

Helper function that:
1. Navigates to SO301000
2. Clicks "+" to create new order
3. Sets Order Type = PC
4. Sets Customer
5. Adds line item (inventory ID, warehouse, qty, UOM)
6. Returns order number for later validation/cleanup

### order_cleanup

Collects order numbers created during test session. On teardown:
1. Navigates to each order
2. Deletes it (Actions > Delete or keyboard shortcut)
3. Confirms deletion

## Test Data

- **Customer:** C000221 (DRAPERY HOUSE) — same as Sarah's test
- **Item:** 28021 (118 Super Batiste - White Snow) — PIECENBR lot class
- **Warehouse:** 98
- **Qty for partial test:** 40.00 PIECE (exceeds available bolts)
- **Qty for full test:** 1.00 PIECE (should be coverable by a single bolt)

## Error Detection

Tests install a Playwright dialog handler that captures any browser `alert()` or `confirm()` dialogs. After each save operation, assert no error dialogs were triggered. If one was, capture its message for the test failure output.

## Run Command

```bash
# Install deps
pip install playwright pytest
playwright install chromium

# Run tests (headless)
ACUMATICA_URL=https://heritagefabrics.acumatica.com \
ACUMATICA_USERNAME=... \
ACUMATICA_PASSWORD=... \
ACUMATICA_TENANT="Heritage Fabrics" \
pytest tests/ui/ -v

# Run tests (headed, for debugging)
pytest tests/ui/ -v --headed
```

## Constraints

- Tests run against live Heritage Test — be careful with test data cleanup
- Acumatica UI is slow — expect 30-60s per test
- Auto-allocation runs on Persist (save) — must actually save the order to trigger it
- Deploy window applies — tests that save orders should only run after-hours if they'd trigger app pool restart (they won't — just creating orders)
