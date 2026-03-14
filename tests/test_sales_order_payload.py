#!/usr/bin/env python3
"""
Unit tests for the acumatica_create_sales_order tool payload builder.

Run with:  python3 -m pytest tests/test_sales_order_payload.py -v
Or:        python3 tests/test_sales_order_payload.py

These tests import _build_sales_order_payload directly from server.py and
exercise every branch: Note inclusion/exclusion, Description coexistence,
line items with and without warehouse, and the order-type default.
"""

import sys
import os
import types as builtin_types

# ---------------------------------------------------------------------------
# Minimal stubs so server.py can be imported without live env-vars or network
# ---------------------------------------------------------------------------

# Stub out external packages before importing server.py
import importlib
import unittest.mock as mock

# Stub mcp packages
mcp_stub = builtin_types.ModuleType("mcp")
mcp_server_stub = builtin_types.ModuleType("mcp.server")
mcp_types_stub = builtin_types.ModuleType("mcp")

class _FakeServer:
    def __init__(self, name): pass
    def list_tools(self): return lambda f: f
    def call_tool(self): return lambda f: f

class _FakeTool:
    def __init__(self, **kwargs): pass

class _FakeTextContent:
    def __init__(self, **kwargs): pass

mcp_server_stub.Server = _FakeServer
mcp_types_stub.types = builtin_types.ModuleType("mcp.types")
mcp_types_stub.types.Tool = _FakeTool
mcp_types_stub.types.TextContent = _FakeTextContent

sys.modules.setdefault("mcp", mcp_stub)
sys.modules.setdefault("mcp.server", mcp_server_stub)
sys.modules.setdefault("mcp.types", mcp_types_stub.types)

# Stub httpx, dotenv
for mod in ("httpx", "dotenv"):
    stub = builtin_types.ModuleType(mod)
    stub.Client = mock.MagicMock
    stub.load_dotenv = lambda: None
    sys.modules.setdefault(mod, stub)

# Patch os.getenv so server.py module-level code doesn't fail on missing vars
_orig_getenv = os.getenv
os.getenv = lambda key, default=None: default

# Now import the payload builder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import _build_sales_order_payload  # noqa: E402

# Restore getenv
os.getenv = _orig_getenv

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

import unittest


class TestBuildSalesOrderPayload(unittest.TestCase):

    # ── Defaults ─────────────────────────────────────────────────────────────

    def test_required_fields_present(self):
        """OrderType and CustomerID are always included."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
        })
        self.assertEqual(payload["OrderType"]["value"], "SO")
        self.assertEqual(payload["CustomerID"]["value"], "C000123")

    def test_order_type_defaults_to_SO(self):
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
        })
        self.assertEqual(payload["OrderType"]["value"], "SO")

    def test_order_type_overridable(self):
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "order_type": "RM",
            "line_items": [],
        })
        self.assertEqual(payload["OrderType"]["value"], "RM")

    # ── Note / comments ──────────────────────────────────────────────────────

    def test_note_included_when_comments_provided(self):
        """Non-empty comments → Note field present with prefix."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "comments": "Please ship ASAP",
        })
        self.assertIn("Note", payload)
        self.assertEqual(
            payload["Note"]["value"],
            "Customer comment from samples form: Please ship ASAP",
        )

    def test_note_excluded_when_comments_absent(self):
        """No comments kwarg → Note field must NOT be in payload."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
        })
        self.assertNotIn("Note", payload)

    def test_note_excluded_when_comments_empty_string(self):
        """Empty-string comments → Note field must NOT be in payload."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "comments": "",
        })
        self.assertNotIn("Note", payload)

    def test_note_excluded_when_comments_whitespace_only(self):
        """Whitespace-only comments strip to empty → Note excluded."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "comments": "   \t  ",
        })
        self.assertNotIn("Note", payload)

    def test_note_excluded_when_comments_none(self):
        """Explicit None comments → Note field must NOT be in payload."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "comments": None,
        })
        self.assertNotIn("Note", payload)

    def test_note_strips_leading_trailing_whitespace_from_comment(self):
        """Comments are stripped before prefixing."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "comments": "  handle with care  ",
        })
        self.assertEqual(
            payload["Note"]["value"],
            "Customer comment from samples form: handle with care",
        )

    # ── Description coexistence ──────────────────────────────────────────────

    def test_description_and_note_coexist(self):
        """Description and Note are independent — both survive together."""
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
            "description": "Samples request #42",
            "comments": "Rush order",
        })
        self.assertIn("Description", payload)
        self.assertEqual(payload["Description"]["value"], "Samples request #42")
        self.assertIn("Note", payload)
        self.assertIn("Rush order", payload["Note"]["value"])

    def test_description_excluded_when_absent(self):
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
        })
        self.assertNotIn("Description", payload)

    # ── Line items ───────────────────────────────────────────────────────────

    def test_line_items_mapped_correctly(self):
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [
                {"inventory_id": "FABRIC-001", "quantity": 5},
                {"inventory_id": "FABRIC-002", "quantity": 10, "warehouse_id": "MAIN"},
            ],
        })
        self.assertIn("Details", payload)
        details = payload["Details"]
        self.assertEqual(len(details), 2)

        self.assertEqual(details[0]["InventoryID"]["value"], "FABRIC-001")
        self.assertEqual(details[0]["Quantity"]["value"], 5)
        self.assertNotIn("WarehouseID", details[0])

        self.assertEqual(details[1]["InventoryID"]["value"], "FABRIC-002")
        self.assertEqual(details[1]["Quantity"]["value"], 10)
        self.assertEqual(details[1]["WarehouseID"]["value"], "MAIN")

    def test_empty_line_items_omits_details_key(self):
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "line_items": [],
        })
        self.assertNotIn("Details", payload)

    # ── Payload shape (Acumatica contract-based format) ──────────────────────

    def test_all_scalar_values_wrapped_in_value_dict(self):
        """
        Acumatica contract endpoints require {"value": ...} wrappers on every
        scalar field.  Spot-check that nothing is bare.
        """
        payload = _build_sales_order_payload({
            "customer_id": "C000123",
            "order_type": "SO",
            "description": "Test",
            "line_items": [{"inventory_id": "X", "quantity": 1}],
            "comments": "Some comment",
        })
        for key in ("OrderType", "CustomerID", "Description", "Note"):
            self.assertIsInstance(payload[key], dict, f"{key} must be a dict")
            self.assertIn("value", payload[key], f"{key} must have a 'value' key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
