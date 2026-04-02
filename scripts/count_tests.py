#!/usr/bin/env python3
"""
Count all validation checks in the CI/CD pipeline and publish metrics.

Combines:
1. pytest --collect-only counts (unit tests, UI tests, audit-derived tests)
2. Known validation script check counts (hardcoded, updated when scripts change)
3. CI pipeline gate counts

Outputs JSON to stdout and optionally POSTs to a webhook-router endpoint.

Usage:
    python scripts/count_tests.py                          # JSON to stdout
    python scripts/count_tests.py --post https://url/api/ci-metrics  # POST metrics
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ── Known validation script checks ──────────────────────────────────────────
# These are manually maintained counts of discrete checks in validation scripts.
# Update when validation scripts are significantly modified.

VALIDATION_SCRIPT_CHECKS = {
    "validate-project.py": 9,       # XML parse, root element, comments, level, Sql guards, Table flags, File format, plugin detection, semantic checks
    "validate-publish.py": 5,       # entity reachability, custom fields, SQL columns, session retry, login
    "validate_publish_gi.py": 3,    # GI health probes, corruption detection, HTTP 500
    "smoke-e2e.py": 4,              # screen smoke, entity checks, login, view-level POST/GET
    "test_semantic_checks.py": 4,   # anonymous methods, DAC signatures, SQL injection, field consistency
}

CI_PIPELINE_GATES = {
    "heritage-test-gate": 1,        # hard gate before production
    "rollback-test": 1,             # failure injection + entity smoke
    "pre-deploy-snapshot": 1,       # snapshot for rollback
    "post-deploy-validation": 1,    # UI tests after deploy
}


def count_pytest_tests(test_dirs: list[str]) -> dict[str, int]:
    """Count pytest test cases via --collect-only.

    Returns dict mapping category -> count.
    """
    counts = {}

    for test_path in test_dirs:
        if not os.path.exists(test_path):
            continue

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_path, "--collect-only", "-q", "--ignore=tests/ui"],
                capture_output=True, text=True, timeout=30,
            )
            # Last line is like "93 tests collected in 3.81s"
            match = re.search(r"(\d+) tests? collected", result.stdout + result.stderr)
            if match:
                counts["unit_tests"] = int(match.group(1))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return counts


def count_ui_tests() -> dict[str, int]:
    """Count UI test cases — these need Playwright so we count by parsing files."""
    counts = {}
    ui_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "ui")

    # Count test functions in test_auto_allocation.py
    alloc_file = os.path.join(ui_dir, "test_auto_allocation.py")
    if os.path.exists(alloc_file):
        with open(alloc_file) as f:
            content = f.read()
        counts["ui_regression_tests"] = len(re.findall(r"def test_", content))

    # Count screen smoke tests — parameterized over CRITICAL_SCREENS + audit data
    smoke_file = os.path.join(ui_dir, "test_screen_smoke.py")
    if os.path.exists(smoke_file):
        # Count from critical screens floor (minimum)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        try:
            from generate_ui_fixtures import CRITICAL_SCREENS
            # test_screen_loads × N screens + test_custom_fields_visible × ~half
            screen_count = len(CRITICAL_SCREENS)
            counts["ui_smoke_tests"] = screen_count + (screen_count // 2)
        except ImportError:
            counts["ui_smoke_tests"] = 19  # fallback estimate

    return counts


def count_audit_derived_tests() -> int:
    """Count audit-derived parameterized tests."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "audit_derived")
    if not os.path.isdir(fixtures_dir):
        return 0
    fixture_count = len([f for f in os.listdir(fixtures_dir) if f.endswith(".json")])
    # 2 test functions per fixture (entity_reachable + custom_fields_exist)
    return fixture_count * 2


def collect_metrics() -> dict:
    """Collect all test/validation metrics."""
    repo_root = os.path.join(os.path.dirname(__file__), "..")

    # pytest unit tests
    pytest_counts = count_pytest_tests([os.path.join(repo_root, "tests")])

    # UI tests (parsed from source)
    ui_counts = count_ui_tests()

    # Audit-derived tests
    audit_count = count_audit_derived_tests()

    # Validation scripts
    validation_count = sum(VALIDATION_SCRIPT_CHECKS.values())

    # CI gates
    gate_count = sum(CI_PIPELINE_GATES.values())

    breakdown = {
        "unit_tests": pytest_counts.get("unit_tests", 0),
        "ui_smoke_tests": ui_counts.get("ui_smoke_tests", 0),
        "ui_regression_tests": ui_counts.get("ui_regression_tests", 0),
        "api_regression_tests": audit_count,
        "validation_scripts": validation_count,
        "ci_pipeline_gates": gate_count,
    }

    total = sum(breakdown.values())

    # Get commit SHA
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, text=True, timeout=5,
        ).strip()
    except Exception:
        sha = "unknown"

    return {
        "total_checks": total,
        "breakdown": breakdown,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "commit_sha": sha,
    }


def post_metrics(url: str, metrics: dict, token: str = "") -> bool:
    """POST metrics JSON to a webhook-router endpoint."""
    data = json.dumps(metrics).encode()
    headers = {
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Posted metrics: HTTP {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Failed to post metrics: HTTP {e.code} — {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"Failed to post metrics: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Count CI/CD validation checks")
    parser.add_argument("--post", type=str, help="POST metrics to this URL")
    parser.add_argument("--token", type=str, default=os.environ.get("CI_METRICS_TOKEN", ""),
                        help="Bearer token for POST auth")
    args = parser.parse_args()

    metrics = collect_metrics()
    print(json.dumps(metrics, indent=2))

    if args.post:
        post_metrics(args.post, metrics, args.token)
