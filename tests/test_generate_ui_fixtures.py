"""Tests for generate_ui_fixtures.py — no live Acumatica connection needed."""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from workflow_extractor.models import AuditRecord
from datetime import datetime


def _make_record(screen_id, table_name, operation="Modified", fields=None, change_date=None):
    """Helper to create an AuditRecord for testing."""
    return AuditRecord(
        batch_id=1,
        change_id=1,
        screen_id=screen_id,
        operation=operation,
        change_date=change_date or datetime(2026, 4, 1, 12, 0, 0),
        table_name=table_name,
        combined_key=["TEST"],
        modified_fields=fields or {},
        username="testuser",
    )


class TestFixtureGeneration:
    """Test the grouping and output logic without OData calls."""

    def test_groups_by_screen_id(self, tmp_path):
        """Records from different screens produce separate fixture entries."""
        from generate_ui_fixtures import generate_ui_fixtures
        from unittest.mock import patch

        records = [
            _make_record("SO301000", "SOOrder"),
            _make_record("SO301000", "SOLine"),
            _make_record("PO301000", "POOrder"),
        ]

        output = str(tmp_path / "ui_screens.json")
        with patch("generate_ui_fixtures.AuditFetcher") as MockFetcher:
            MockFetcher.return_value.fetch_days.return_value = records
            fixtures = generate_ui_fixtures(days=30, output=output)

        assert len(fixtures) == 2
        screen_ids = [f["screen_id"] for f in fixtures]
        assert "SO301000" in screen_ids
        assert "PO301000" in screen_ids

    def test_extracts_custom_fields(self, tmp_path):
        """Usr* fields appear in the custom_fields list."""
        from generate_ui_fixtures import generate_ui_fixtures
        from unittest.mock import patch

        records = [
            _make_record("SO301000", "SOOrder", fields={
                "Status": "Open",
                "UsrHubSpotDealId": "12345",
                "UsrBoltID": "B001",
            }),
        ]

        output = str(tmp_path / "ui_screens.json")
        with patch("generate_ui_fixtures.AuditFetcher") as MockFetcher:
            MockFetcher.return_value.fetch_days.return_value = records
            fixtures = generate_ui_fixtures(days=30, output=output)

        so_fixture = fixtures[0]
        assert "UsrHubSpotDealId" in so_fixture["custom_fields"]
        assert "UsrBoltID" in so_fixture["custom_fields"]
        assert "Status" not in so_fixture["custom_fields"]

    def test_empty_records_writes_empty_fixture(self, tmp_path):
        """No audit records -> empty JSON array, not a crash."""
        from generate_ui_fixtures import generate_ui_fixtures
        from unittest.mock import patch

        output = str(tmp_path / "ui_screens.json")
        with patch("generate_ui_fixtures.AuditFetcher") as MockFetcher:
            MockFetcher.return_value.fetch_days.return_value = []
            fixtures = generate_ui_fixtures(days=30, output=output)

        assert fixtures == []
        with open(output) as f:
            assert json.load(f) == []

    def test_fixture_file_is_valid_json(self, tmp_path):
        """Output file is parseable JSON with expected structure."""
        from generate_ui_fixtures import generate_ui_fixtures
        from unittest.mock import patch

        records = [
            _make_record("IN202500", "InventoryItem", fields={"UsrFabricType": "Linen"}),
        ]

        output = str(tmp_path / "ui_screens.json")
        with patch("generate_ui_fixtures.AuditFetcher") as MockFetcher:
            MockFetcher.return_value.fetch_days.return_value = records
            generate_ui_fixtures(days=30, output=output)

        with open(output) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert all("screen_id" in entry for entry in data)
        assert all("custom_fields" in entry for entry in data)
        assert all("record_count" in entry for entry in data)
