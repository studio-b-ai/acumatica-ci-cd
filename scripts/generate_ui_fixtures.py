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


# ── Critical Screen Floor ─────────────────────────────────────────────────────
# These screens are always included in smoke tests regardless of audit data.
# Audit data adds dynamically discovered screens on top of this floor.
#
# Source: SM205510 audit config review (2026-04-02) + Heritage Fabrics daily ops.
# Screens marked (audited) have audit trail enabled; others are gaps.

CRITICAL_SCREENS: dict[str, str] = {
    # Sales — core daily workflow
    "SO301000": "Sales Orders",              # audited
    "SO302000": "Shipments",                 # audited
    "SO303000": "Invoices",                  # NOT audited
    # Purchasing
    "PO301000": "Purchase Orders",           # audited
    "PO302000": "Purchase Receipts",         # NOT audited
    # Inventory
    "IN202500": "Stock Items",               # NOT audited
    "IN301000": "Inventory Receipts",        # NOT audited
    "IN304000": "Transfers",                 # audited
    # AR / AP
    "AP301000": "Bills and Adjustments",     # audited
    "AR301000": "Invoices and Memos",        # NOT audited
    "AR302000": "Payments and Applications", # NOT audited
    "AR303000": "Customers",                 # audited
    "AP303000": "Vendors",                   # NOT audited
}


def _merge_critical_screens(screens: dict[str, dict]) -> dict[str, dict]:
    """Ensure all critical screens are present, even without audit data."""
    for sid, name in CRITICAL_SCREENS.items():
        if sid not in screens:
            screens[sid] = {
                "screen_id": sid,
                "screen_name": name,
                "record_count": 0,
                "custom_fields": set(),
                "tables_touched": set(),
                "operations": set(),
                "last_seen": "",
                "source": "critical_screen_floor",
            }
    return screens


def generate_ui_fixtures(days: int = 30, output: str = "tests/fixtures/ui_screens.json") -> list[dict]:
    """Pull audit data and generate UI screen fixtures.

    Merges live audit data with a static list of critical screens so that
    all important screens are smoke-tested even if audit trail isn't enabled.

    Returns list of screen fixture dicts (also written to output path).
    """
    fetcher = AuditFetcher()
    records = fetcher.fetch_days(days=days, top=1000, max_pages=20)

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

    # Merge critical screens floor — always tested even without audit data
    screens = _merge_critical_screens(screens)

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

    audit_count = sum(1 for f in fixtures if f["record_count"] > 0)
    floor_count = sum(1 for f in fixtures if f["record_count"] == 0)
    print(f"Generated {len(fixtures)} screen fixtures ({audit_count} from audit data, {floor_count} from critical screen floor)")
    for entry in fixtures:
        source = "audit" if entry["record_count"] > 0 else "floor"
        custom = f" (custom: {', '.join(entry['custom_fields'])})" if entry["custom_fields"] else ""
        print(f"  [{source}] {entry['screen_id']} — {entry['screen_name']}{custom}")

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
