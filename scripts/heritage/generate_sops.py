#!/usr/bin/env python3
"""
Workflow Extractor CLI — fetch audit data, detect patterns, generate SOPs + tests.

Incremental by default: fetches new records since last run, updates the pattern
catalog, and generates SOPs/tests only for patterns that just crossed the threshold.

Usage:
    # Incremental run (uses last_fetched from catalog)
    python scripts/generate_sops.py

    # Full rebuild from last N days
    python scripts/generate_sops.py --full --days 90

    # Dry run — show patterns without generating
    python scripts/generate_sops.py --dry-run

    # Custom threshold
    python scripts/generate_sops.py --threshold 5

Environment variables:
    ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import argparse
import os
import sys
from datetime import datetime

# Add scripts/ to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow_extractor.fetcher import AuditFetcher
from workflow_extractor.grouper import extract_patterns
from workflow_extractor.catalog import PatternCatalog
from workflow_extractor.sop_generator import generate_sop
from workflow_extractor.test_generator import generate_fixtures, suggest_manifest_updates
from workflow_extractor.parser import screen_name


# ── Colors ────────────────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"


def log(msg: str) -> None:
    print(f"{BLUE}[EXTRACT]{RESET} {msg}")


def ok(msg: str) -> None:
    print(f"{GREEN}[  OK  ]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[ WARN ]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"{RED}[FAIL  ]{RESET} {msg}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract workflows from audit data → SOPs + test fixtures"
    )
    parser.add_argument("--days", type=int, default=90,
                        help="Fetch audit data from last N days (default: 90)")
    parser.add_argument("--full", action="store_true",
                        help="Full rebuild (ignore last_fetched, re-scan all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show patterns without generating SOPs/tests")
    parser.add_argument("--threshold", type=int, default=3,
                        help="Min occurrences to trigger generation (default: 3)")
    parser.add_argument("--catalog", type=str, default="workflow_patterns.json",
                        help="Path to pattern catalog file")
    parser.add_argument("--sop-dir", type=str, default="docs/sops",
                        help="Output directory for DOCX SOPs")
    parser.add_argument("--fixture-dir", type=str, default="tests/fixtures/audit_derived",
                        help="Output directory for test fixtures")
    parser.add_argument("--top", type=int, default=5000,
                        help="Max records per fetch page (default: 5000)")
    args = parser.parse_args()

    # ── Load catalog ──────────────────────────────────────────────────────
    catalog = PatternCatalog(path=args.catalog, threshold=args.threshold)
    summary = catalog.summary()
    log(f"Catalog: {summary['total_patterns']} patterns, "
        f"{summary['above_threshold']} above threshold "
        f"(threshold={args.threshold})")

    # ── Fetch audit data ──────────────────────────────────────────────────
    fetcher = AuditFetcher()

    since = None
    if not args.full and catalog.last_fetched:
        since = datetime.fromisoformat(catalog.last_fetched)
        log(f"Incremental fetch since {catalog.last_fetched}")
    else:
        log(f"Full fetch — last {args.days} days")

    records = fetcher.fetch_days(days=args.days, top=args.top) if since is None \
        else fetcher.fetch_since(since=since, top=args.top)

    log(f"Fetched {len(records)} audit records")

    if not records:
        warn("No new records found. Nothing to do.")
        return

    # ── Extract patterns ──────────────────────────────────────────────────
    pattern_groups = extract_patterns(records)
    log(f"Detected {len(pattern_groups)} unique workflow patterns")

    # ── Update catalog ────────────────────────────────────────────────────
    newly_crossed = catalog.update(pattern_groups)
    catalog.last_fetched = datetime.now().isoformat()

    # ── Display summary ───────────────────────────────────────────────────
    if newly_crossed:
        ok(f"{len(newly_crossed)} patterns just crossed threshold ({args.threshold}):")
        for entry in newly_crossed:
            screen = screen_name(entry.screen_id)
            print(f"    {screen} ({entry.screen_id}) — {entry.count} occurrences")
            for sig in entry.step_signatures[:3]:
                print(f"      {sig}")
    else:
        log("No new patterns crossed threshold this run.")

    # Show all patterns above threshold
    above = catalog.patterns_above_threshold()
    if above:
        log(f"\nAll patterns above threshold ({len(above)}):")
        for entry in above:
            screen = screen_name(entry.screen_id)
            status = "✓ SOP" if entry.sop_generated else "  ---"
            print(f"    [{status}] {screen}: {entry.count}x")

    if args.dry_run:
        log("Dry run — skipping generation.")
        catalog.save()
        return

    # ── Generate SOPs ─────────────────────────────────────────────────────
    needing = catalog.patterns_needing_generation()
    if needing:
        log(f"\nGenerating SOPs for {len(needing)} patterns...")
        for entry in needing:
            try:
                filepath = generate_sop(
                    entry,
                    all_records=records,
                    output_dir=args.sop_dir,
                )
                entry.sop_generated = filepath
                ok(f"SOP: {filepath}")
            except Exception as e:
                fail(f"SOP generation failed for {entry.screen_id}: {e}")

    # ── Generate test fixtures ────────────────────────────────────────────
    log("\nGenerating test fixtures...")
    try:
        fixture_files = generate_fixtures(
            records,
            output_dir=args.fixture_dir,
        )
        for fp in fixture_files:
            ok(f"Fixture: {fp}")

        # Mark patterns as having tests generated
        for entry in needing:
            if not entry.test_generated:
                entry.test_generated = args.fixture_dir
    except Exception as e:
        fail(f"Fixture generation failed: {e}")

    # ── Manifest suggestions ──────────────────────────────────────────────
    suggestions = suggest_manifest_updates(records)
    if suggestions["suggested_probes"]:
        warn(f"\nSuggested additions to publish-manifest.json:")
        for probe in suggestions["suggested_probes"]:
            print(f"    {probe['entity']}: {probe['select_fields']}")

    # ── Save catalog ──────────────────────────────────────────────────────
    catalog.save()
    ok(f"\nCatalog saved to {args.catalog}")

    final = catalog.summary()
    log(f"Final: {final['total_patterns']} patterns, "
        f"{final['above_threshold']} above threshold, "
        f"{final['needing_generation']} still need generation")


if __name__ == "__main__":
    main()
