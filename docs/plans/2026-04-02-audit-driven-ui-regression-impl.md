# Audit-Driven UI Regression Tests — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-generate Playwright UI smoke tests from live audit data so every deploy validates that all user-facing screens still load and custom fields are present.

**Architecture:** A new script (`generate_ui_fixtures.py`) pulls audit data from the StudioBAuditTrail GI via OData, groups by screen_id, and writes `tests/fixtures/ui_screens.json`. A new parameterized Playwright test file (`tests/ui/test_screen_smoke.py`) consumes that fixture and navigates to each screen, asserting load success and custom field presence. The CI pipeline runs the generator before the tests.

**Tech Stack:** Python 3.11, Playwright (sync API), pytest, urllib (stdlib OData), existing `workflow_extractor` package.

---

### Task 1: Create `generate_ui_fixtures.py` — the OData-to-fixture script

**Files:**
- Create: `scripts/generate_ui_fixtures.py`
- Read (reference only): `scripts/workflow_extractor/fetcher.py`, `scripts/workflow_extractor/parser.py`

**Step 1: Write the script**

This script reuses `AuditFetcher` from the workflow extractor. It pulls audit data, groups by screen_id, and writes a JSON fixture.

```python
#!/usr/bin/env python3
"""
Generate UI test fixtures from Acumatica audit trail data.

Pulls from StudioBAuditTrail GI via OData, groups by screen_id,
and writes tests/fixtures/ui_screens.json for Playwright smoke tests.

Usage:
    python scripts/generate_ui_fixtures.py --days 30 --output tests/fixtures/ui_screens.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

# Add scripts/ to path so workflow_extractor is importable
sys.path.insert(0, os.path.dirname(__file__))

from workflow_extractor.fetcher import AuditFetcher
from workflow_extractor.parser import screen_name


def generate_ui_fixtures(days: int = 30, output: str = "tests/fixtures/ui_screens.json") -> list[dict]:
    """Pull audit data and generate UI screen fixtures.

    Returns list of screen fixture dicts (also written to output path).
    """
    fetcher = AuditFetcher()
    records = fetcher.fetch_days(days=days, top=1000, max_pages=20)

    if not records:
        print("WARNING: No audit records returned — writing empty fixture")
        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w") as f:
            json.dump([], f, indent=2)
        return []

    # Group by screen_id
    screens: dict[str, dict] = {}
    for r in records:
        sid = r.screen_id
        if not sid:
            continue

        if sid not in screens:
            screens[sid] = {
                "screen_id": sid,
                "screen_name": screen_name(sid),
                "record_count": 0,
                "custom_fields": set(),
                "tables_touched": set(),
                "operations": set(),
                "last_seen": r.change_date.isoformat(),
            }

        entry = screens[sid]
        entry["record_count"] += 1
        entry["tables_touched"].add(r.table_name)
        entry["operations"].add(r.operation)
        if r.change_date.isoformat() > entry["last_seen"]:
            entry["last_seen"] = r.change_date.isoformat()

        for field_name in r.modified_fields:
            if field_name.startswith("Usr"):
                entry["custom_fields"].add(field_name)

    # Convert sets to sorted lists for JSON serialization
    fixtures = []
    for sid in sorted(screens.keys()):
        entry = screens[sid]
        entry["custom_fields"] = sorted(entry["custom_fields"])
        entry["tables_touched"] = sorted(entry["tables_touched"])
        entry["operations"] = sorted(entry["operations"])
        fixtures.append(entry)

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w") as f:
        json.dump(fixtures, f, indent=2)

    print(f"Generated {len(fixtures)} screen fixtures from {len(records)} audit records")
    for entry in fixtures:
        custom = f" (custom: {', '.join(entry['custom_fields'])})" if entry["custom_fields"] else ""
        print(f"  {entry['screen_id']} — {entry['screen_name']} — {entry['record_count']} records{custom}")

    return fixtures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate UI test fixtures from audit data")
    parser.add_argument("--days", type=int, default=30, help="Fetch last N days of audit data")
    parser.add_argument("--output", type=str, default="tests/fixtures/ui_screens.json",
                        help="Output fixture file path")
    args = parser.parse_args()

    fixtures = generate_ui_fixtures(days=args.days, output=args.output)
    if not fixtures:
        sys.exit(1)
```

**Step 2: Run it locally to verify it works**

Run: `cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/gifted-sutherland && python scripts/generate_ui_fixtures.py --days 30`

Expected: Prints screen fixtures and writes `tests/fixtures/ui_screens.json`. If no Acumatica creds are set locally, it will error with "ACUMATICA_URL is required" — that's fine, the script is correct.

**Step 3: Commit**

```bash
git add scripts/generate_ui_fixtures.py
git commit -m "feat: add generate_ui_fixtures.py — OData audit data to UI test fixtures"
```

---

### Task 2: Add screen navigation helpers to `tests/ui/helpers.py`

**Files:**
- Modify: `tests/ui/helpers.py` (append new functions after existing code)

**Step 1: Add the helpers**

Append these functions to the end of `tests/ui/helpers.py`:

```python
def navigate_to_screen(page: Page, screen_id: str, timeout: int = 30_000):
    """Navigate to an Acumatica screen by screen ID."""
    url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
    page.goto(url, wait_until="networkidle", timeout=timeout)


def assert_screen_loaded(page: Page, screen_id: str, timeout: int = 15_000):
    """Assert that an Acumatica screen loaded successfully.

    Checks for either a form container or a grid — different screens use different layouts.
    """
    # Acumatica screens have either a form (#ctl00_phF_form) or a grid (#ctl00_phG_grid)
    form = page.locator("#ctl00_phF_form")
    grid = page.locator("#ctl00_phG_grid")

    try:
        # Wait for either form or grid to appear
        page.wait_for_function(
            """() => {
                return document.querySelector('#ctl00_phF_form') !== null
                    || document.querySelector('#ctl00_phG_grid') !== null
                    || document.querySelector('#ctl00_phG_tab') !== null;
            }""",
            timeout=timeout,
        )
    except Exception:
        raise AssertionError(
            f"Screen {screen_id} did not load — no form, grid, or tab container found within {timeout}ms"
        )


def find_custom_fields(page: Page, field_names: list[str]) -> dict[str, bool]:
    """Check which custom fields are present in the DOM.

    Args:
        page: Authenticated Acumatica page.
        field_names: List of field names (e.g., ["UsrHubSpotDealId", "UsrBoltID"]).

    Returns:
        Dict mapping field_name -> True if found in DOM, False if not.
    """
    results = {}
    for field_name in field_names:
        # Acumatica renders custom fields with IDs containing the field name
        # e.g., ctl00_phF_form_edUsrHubSpotDealId or similar patterns
        locator = page.locator(f"[id*='{field_name}']")
        results[field_name] = locator.count() > 0
    return results
```

**Step 2: Commit**

```bash
git add tests/ui/helpers.py
git commit -m "feat: add navigate_to_screen, assert_screen_loaded, find_custom_fields helpers"
```

---

### Task 3: Add shared `screen_fixture` fixture to `tests/ui/conftest.py`

**Files:**
- Modify: `tests/ui/conftest.py` (add imports and new fixtures)

**Step 1: Add fixture loading and generic screen navigation**

Add these imports at the top of `conftest.py` (after existing imports):

```python
import json
```

Add these fixtures after the existing `capture_dialogs` fixture:

```python
FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ui_screens.json")


def load_screen_fixtures():
    """Load UI screen fixtures from JSON file."""
    if not os.path.exists(FIXTURES_PATH):
        return []
    with open(FIXTURES_PATH) as f:
        return json.load(f)


@pytest.fixture
def screen_page(acumatica_page):
    """Return the authenticated page for screen navigation tests.

    Unlike so301000 which navigates to a specific screen, this just
    returns the authenticated page for the test to navigate wherever needed.
    """
    return acumatica_page
```

**Step 2: Commit**

```bash
git add tests/ui/conftest.py
git commit -m "feat: add screen fixture loading to conftest.py"
```

---

### Task 4: Create `tests/ui/test_screen_smoke.py` — the parameterized smoke tests

**Files:**
- Create: `tests/ui/test_screen_smoke.py`

**Step 1: Write the test file**

```python
"""Audit-driven UI smoke tests — verify all user-facing screens load after deploy.

Fixtures are generated by scripts/generate_ui_fixtures.py from live
StudioBAuditTrail OData data. Each test navigates to a screen, asserts
it loads, and checks that custom fields (Usr*) are present in the DOM.

Usage:
    pytest tests/ui/test_screen_smoke.py -v

Requires:
    - tests/fixtures/ui_screens.json (generated by generate_ui_fixtures.py)
    - ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD env vars
"""

import json
import os

import pytest

from helpers import (
    navigate_to_screen,
    assert_screen_loaded,
    find_custom_fields,
)


# ── Fixture Loading ──────────────────────────────────────────────────────────

FIXTURES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "ui_screens.json"
)


def _load_screen_fixtures():
    if not os.path.exists(FIXTURES_PATH):
        return []
    with open(FIXTURES_PATH) as f:
        return json.load(f)


def _screen_ids():
    return [f["screen_id"] for f in _load_screen_fixtures()]


_FIXTURES = _load_screen_fixtures()

# Skip everything if no fixtures or no credentials
_has_fixtures = len(_FIXTURES) > 0
_has_acumatica = all(
    os.environ.get(v)
    for v in ("ACUMATICA_URL", "ACUMATICA_USERNAME", "ACUMATICA_PASSWORD")
)


# ── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.ui
@pytest.mark.skipif(not _has_fixtures, reason="No ui_screens.json fixture file")
@pytest.mark.skipif(not _has_acumatica, reason="No Acumatica credentials")
class TestScreenSmoke:
    """Smoke tests: navigate to each audit-observed screen and verify it loads."""

    @pytest.mark.parametrize("fixture", _FIXTURES, ids=_screen_ids())
    def test_screen_loads(self, fixture, screen_page, dialog_messages):
        """Screen navigates and loads without errors."""
        screen_id = fixture["screen_id"]

        navigate_to_screen(screen_page, screen_id)
        assert_screen_loaded(screen_page, screen_id)

        # Check no error dialogs fired during navigation
        error_dialogs = [
            d for d in dialog_messages
            if "error" in d["message"].lower() or "exception" in d["message"].lower()
        ]
        assert not error_dialogs, (
            f"Screen {screen_id} ({fixture.get('screen_name', '')}) "
            f"produced error dialog(s): {[d['message'] for d in error_dialogs]}"
        )

    @pytest.mark.parametrize(
        "fixture",
        [f for f in _FIXTURES if f.get("custom_fields")],
        ids=[f["screen_id"] for f in _FIXTURES if f.get("custom_fields")],
    )
    def test_custom_fields_visible(self, fixture, screen_page):
        """Custom fields observed in audit data are present in screen DOM."""
        screen_id = fixture["screen_id"]
        custom_fields = fixture["custom_fields"]

        navigate_to_screen(screen_page, screen_id)
        assert_screen_loaded(screen_page, screen_id)

        results = find_custom_fields(screen_page, custom_fields)
        missing = [f for f, found in results.items() if not found]

        assert not missing, (
            f"Screen {screen_id} ({fixture.get('screen_name', '')}): "
            f"custom fields missing from DOM: {missing}. "
            f"These fields were observed in production audit data but are no longer "
            f"rendered — possible customization regression."
        )
```

**Step 2: Commit**

```bash
git add tests/ui/test_screen_smoke.py
git commit -m "feat: add audit-driven UI screen smoke tests"
```

---

### Task 5: Wire fixture generation into CI pipeline

**Files:**
- Modify: `.github/workflows/deploy-customization.yml` (lines ~958-974, the `post-deploy-validation` job)

**Step 1: Add the fixture generation step**

In the `post-deploy-validation` job, insert a new step **between** "Install test dependencies" and "Run UI tests":

```yaml
      - name: Generate UI fixtures from audit data
        timeout-minutes: 3
        env:
          ACUMATICA_URL: ${{ secrets.ACUMATICA_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PASSWORD }}
          ACUMATICA_TENANT: ${{ vars.ACUMATICA_TEST_TENANT }}
        run: python scripts/generate_ui_fixtures.py --days 30 --output tests/fixtures/ui_screens.json
```

The existing "Run UI tests" step already runs `pytest tests/ui/` which will pick up the new `test_screen_smoke.py` automatically.

**Step 2: Verify the full job looks correct**

The `post-deploy-validation` job should now have these steps in order:
1. Checkout repository
2. Setup Python
3. Install test dependencies (playwright, pytest, pytest-timeout)
4. **Generate UI fixtures from audit data** (new)
5. Run UI tests

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "feat: add audit fixture generation step to CI post-deploy validation"
```

---

### Task 6: Add unit tests for `generate_ui_fixtures.py`

**Files:**
- Create: `tests/test_generate_ui_fixtures.py`

**Step 1: Write tests with mocked OData responses**

```python
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
        """No audit records → empty JSON array, not a crash."""
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
```

**Step 2: Run the tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/gifted-sutherland && python -m pytest tests/test_generate_ui_fixtures.py -v`

Expected: All 4 tests pass.

**Step 3: Commit**

```bash
git add tests/test_generate_ui_fixtures.py
git commit -m "test: add unit tests for generate_ui_fixtures.py"
```

---

### Task 7: End-to-end verification

**Step 1: Verify all existing tests still pass**

Run: `cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/gifted-sutherland && python -m pytest tests/test_generate_ui_fixtures.py tests/test_poc_user_audit_trail.py -v --timeout=30`

Expected: All tests pass. UI tests are skipped (no Acumatica creds in local env).

**Step 2: Verify the test_screen_smoke.py is discovered by pytest**

Run: `cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/gifted-sutherland && python -m pytest tests/ui/test_screen_smoke.py --collect-only 2>&1 | head -20`

Expected: Shows "no tests ran" or "skipped" (because ui_screens.json doesn't exist yet and no creds). The point is it doesn't crash on import.

**Step 3: Final commit with all files**

If any loose changes remain:
```bash
git add -A
git commit -m "chore: audit-driven UI regression tests — ready for CI"
```

---

## Summary of Deliverables

| # | What | File |
|---|------|------|
| 1 | Fixture generator script | `scripts/generate_ui_fixtures.py` |
| 2 | Screen navigation helpers | `tests/ui/helpers.py` (modified) |
| 3 | Shared fixture loading | `tests/ui/conftest.py` (modified) |
| 4 | Parameterized smoke tests | `tests/ui/test_screen_smoke.py` |
| 5 | CI pipeline integration | `.github/workflows/deploy-customization.yml` (modified) |
| 6 | Unit tests for generator | `tests/test_generate_ui_fixtures.py` |

## Data Flow

```
[Deploy completes] → CI post-deploy-validation job:
  1. generate_ui_fixtures.py --days 30  →  tests/fixtures/ui_screens.json
  2. pytest tests/ui/                    →  test_screen_smoke.py reads fixture
                                            → navigates each screen
                                            → asserts load + custom fields
```
