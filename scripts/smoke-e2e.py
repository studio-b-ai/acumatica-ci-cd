#!/usr/bin/env python3
"""
E2E View-Level Smoke Test for Acumatica Customization CI/CD

Reads e2e_probes from publish-manifest.json and executes $select queries
that force SQL column resolution on custom DAC extension fields.

Catches view/table mismatches that $adHocSchema and $top=1 miss.
Example: VendorExt targeting Vendor (view) when columns live on BAccount (table)
→ SELECT [Vendor_Vendor].[UsrFoo] → "Invalid column name" → HTTP 500.

See: docs/plans/2026-03-30-e2e-smoke-test-design.md

Usage:
    python scripts/smoke-e2e.py --manifest publish-manifest.json

Environment variables:
    ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import json
import os
import sys

# Reuse AcumaticaSession from validate-publish.py (same login retry logic)
# The filename uses a hyphen, so we need importlib to import it.
import importlib.util

_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)  # so validate-publish.py can find its own imports
_spec = importlib.util.spec_from_file_location(
    "validate_publish", os.path.join(_script_dir, "validate-publish.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

AcumaticaSession = _mod.AcumaticaSession
log = _mod.log
ok = _mod.ok
fail = _mod.fail
warn = _mod.warn

passed = 0
failed = 0


def run_probe(session, probe):
    """Execute a single e2e probe — $select query forcing column resolution."""
    global passed, failed

    entity = probe["entity"]
    fields = probe["select_fields"]
    note = probe.get("note", "")
    select = ",".join(fields)

    label = f"{entity} → $select={select}"
    if note:
        label += f"  ({note})"

    log(f"Probing: {label}")

    code, body = session.query_entity(entity, top=1, select=select)

    if code == 200:
        ok(f"{entity}: all {len(fields)} fields resolved (HTTP 200)")
        passed += 1
        return True

    if code == 204:
        # No records but query executed — view resolution succeeded
        ok(f"{entity}: query executed, no records (HTTP 204) — view resolution OK")
        passed += 1
        return True

    if code in (401, 403):
        warn(f"{entity}: HTTP {code} — permission issue, not a code bug")
        return True

    # HTTP 500 or other error — parse body for diagnostic info
    error_detail = ""
    if isinstance(body, str):
        if "Invalid column name" in body:
            # Extract the column name from the error
            import re
            match = re.search(r"Invalid column name '([^']+)'", body)
            col = match.group(1) if match else "unknown"
            error_detail = f"Invalid column name {col} — DAC targets wrong view/table"
        elif "does not exist" in body.lower():
            error_detail = "Entity or view does not exist"
        else:
            # Truncate to first 200 chars for readability
            error_detail = body[:200]

    fail(f"{entity}: HTTP {code} — {error_detail or 'unknown error'}")
    failed += 1
    return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="E2E view-level smoke test for Acumatica customizations"
    )
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    parser.add_argument("--tenant", default=os.environ.get("ACUMATICA_TENANT", ""))
    parser.add_argument("--manifest", default="publish-manifest.json")
    args = parser.parse_args()

    if not args.url or not args.username or not args.password:
        print(
            "Error: --url, --username, --password required "
            "(or set ACUMATICA_* env vars)"
        )
        sys.exit(1)

    # Load manifest
    manifest_path = args.manifest
    if not os.path.exists(manifest_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        manifest_path = os.path.join(script_dir, "..", "publish-manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: manifest not found: {args.manifest}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    probes = manifest.get("e2e_probes", [])
    if not probes:
        log("No e2e_probes in manifest — nothing to test")
        sys.exit(0)

    log(f"Loaded {len(probes)} e2e probes from manifest")

    # Authenticate
    session = AcumaticaSession(args.url, args.username, args.password, args.tenant)
    log("Authenticating...")

    if not session.login():
        print("::error::E2E smoke test — login failed")
        sys.exit(1)
    ok("Authenticated")

    try:
        for probe in probes:
            run_probe(session, probe)
    finally:
        session.logout()

    # Summary
    print()
    total = passed + failed
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"

    if failed == 0:
        print(f"{GREEN}E2E SMOKE TEST PASSED{RESET} — {passed}/{total} probes passed")
        sys.exit(0)
    else:
        print(f"{RED}E2E SMOKE TEST FAILED{RESET} — {failed}/{total} probes failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
