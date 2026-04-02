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
