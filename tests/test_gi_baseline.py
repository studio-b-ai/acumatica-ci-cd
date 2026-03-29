"""Tests for gi_baseline.diff_baselines (pure logic, no API calls)."""

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from gi_baseline import diff_baselines, report_diff


def test_no_changes():
    """Identical before/after produces no issues."""
    before = [
        {"name": "InventoryAllocationDetail", "status": "reachable"},
        {"name": "LotAvailability", "status": "reachable"},
    ]
    after = [
        {"name": "InventoryAllocationDetail", "status": "reachable"},
        {"name": "LotAvailability", "status": "reachable"},
    ]
    diff = diff_baselines(before, after)
    assert diff["added"] == []
    assert diff["removed"] == []
    assert diff["degraded"] == []
    assert diff["duplicates"] == []


def test_new_gi_detected():
    """A GI present in after but not before shows as added."""
    before = [{"name": "InventoryAllocationDetail", "status": "reachable"}]
    after = [
        {"name": "InventoryAllocationDetail", "status": "reachable"},
        {"name": "NewCustomGI", "status": "reachable"},
    ]
    diff = diff_baselines(before, after)
    assert len(diff["added"]) == 1
    assert diff["added"][0]["name"] == "NewCustomGI"
    assert diff["removed"] == []
    assert diff["duplicates"] == []


def test_removed_gi_detected():
    """A GI present in before but not after shows as removed."""
    before = [
        {"name": "InventoryAllocationDetail", "status": "reachable"},
        {"name": "LotAvailability", "status": "reachable"},
    ]
    after = [{"name": "InventoryAllocationDetail", "status": "reachable"}]
    diff = diff_baselines(before, after)
    assert len(diff["removed"]) == 1
    assert diff["removed"][0]["name"] == "LotAvailability"
    assert diff["added"] == []


def test_duplicate_gi_detected():
    """Same GI name appearing twice in after is flagged as duplicate."""
    before = [{"name": "InventoryAllocationDetail", "status": "reachable"}]
    after = [
        {"name": "InventoryAllocationDetail", "status": "reachable"},
        {"name": "InventoryAllocationDetail", "status": "reachable"},
    ]
    diff = diff_baselines(before, after)
    assert "InventoryAllocationDetail" in diff["duplicates"]


def test_degraded_gi_detected():
    """A GI that was reachable but now returns HTTP 500 is flagged as degraded."""
    before = [{"name": "InventoryAllocationDetail", "status": "reachable"}]
    after = [{"name": "InventoryAllocationDetail", "status": "HTTP 500"}]
    diff = diff_baselines(before, after)
    assert len(diff["degraded"]) == 1
    assert diff["degraded"][0]["name"] == "InventoryAllocationDetail"
    assert diff["degraded"][0]["before"] == "reachable"
    assert diff["degraded"][0]["after"] == "HTTP 500"


def test_report_diff_returns_false_on_clean():
    """report_diff returns False when there are no errors."""
    diff = {"added": [], "removed": [], "degraded": [], "duplicates": []}
    assert report_diff(diff) is False


def test_report_diff_returns_true_on_duplicates():
    """report_diff returns True when duplicates exist."""
    diff = {"added": [], "removed": [], "degraded": [], "duplicates": ["SomeGI"]}
    assert report_diff(diff) is True
