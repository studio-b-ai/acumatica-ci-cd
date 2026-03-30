"""Pre/post-deploy GI baseline capture and diff.

Captures the list of Generic Inquiries before and after a customization publish.
Detects unexpected additions, removals, and duplicates.
"""
import argparse
import json
import os
import sys
import requests

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def capture_baseline(session: requests.Session, base_url: str) -> list[dict]:
    """Capture current GI list by probing known GIs.

    Since there's no 'list all GIs' endpoint, we probe known GIs and
    any GIs specified in the GI_BASELINE_EXTRA environment variable.
    """
    base_url = base_url.rstrip("/")
    baseline = []

    # Default known GIs that should exist on Heritage Fabrics instances
    known_gis = [
        "InventoryAllocationDetail",
        "LotAvailability",
        "StockItemsChristmasWishList",
        "UserAuditTrail",
    ]

    # Add any extra GIs from env var (comma-separated)
    extra = os.environ.get("GI_BASELINE_EXTRA", "")
    if extra:
        known_gis.extend(g.strip() for g in extra.split(",") if g.strip())

    for gi_name in known_gis:
        try:
            resp = session.get(
                f"{base_url}/entity/Default/24.200.001/{gi_name}",
                params={"$top": "1"},
                timeout=15,
            )
            status = "reachable" if resp.status_code == 200 else f"HTTP {resp.status_code}"
            baseline.append({"name": gi_name, "status": status})
        except Exception as exc:
            baseline.append({"name": gi_name, "status": f"error: {exc}"})

    return baseline


def diff_baselines(before: list[dict], after: list[dict]) -> dict:
    """Compare pre-deploy and post-deploy GI baselines."""
    before_names = {gi["name"] for gi in before}
    after_names = [gi["name"] for gi in after]
    after_names_set = set(after_names)

    added = [gi for gi in after if gi["name"] not in before_names]
    removed = [gi for gi in before if gi["name"] not in after_names_set]

    # Detect status changes (was reachable, now broken)
    degraded = []
    for b in before:
        for a in after:
            if b["name"] == a["name"]:
                if b["status"] == "reachable" and a["status"] != "reachable":
                    degraded.append({"name": a["name"], "before": b["status"], "after": a["status"]})

    # Detect duplicates (same name appearing multiple times)
    seen = set()
    duplicates = []
    for name in after_names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)

    return {"added": added, "removed": removed, "degraded": degraded, "duplicates": duplicates}


def report_diff(diff: dict) -> bool:
    """Print diff report. Returns True if there are errors (duplicates or degraded)."""
    has_errors = False

    if diff["duplicates"]:
        for name in diff["duplicates"]:
            print(f"{RED}[ERROR ]{RESET} DUPLICATE GI detected: {name}")
        has_errors = True

    if diff["degraded"]:
        for gi in diff["degraded"]:
            print(f"{RED}[ERROR ]{RESET} GI degraded: {gi['name']} was {gi['before']}, now {gi['after']}")
        has_errors = True

    if diff["removed"]:
        for gi in diff["removed"]:
            print(f"{YELLOW}[ WARN ]{RESET} GI no longer probed after deploy: {gi['name']}")

    if diff["added"]:
        for gi in diff["added"]:
            print(f"{GREEN}[ INFO ]{RESET} New GI after deploy: {gi['name']}")

    if not has_errors and not diff["added"] and not diff["removed"]:
        print(f"{GREEN}[  OK  ]{RESET} GI baseline unchanged")

    return has_errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GI baseline capture/diff")
    parser.add_argument("action", choices=["capture", "diff"])
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    parser.add_argument("--tenant", default=os.environ.get("ACUMATICA_TENANT", ""))
    parser.add_argument("--baseline-file", default="/tmp/gi-baseline.json")
    args = parser.parse_args()

    # Create authenticated session
    session = requests.Session()
    if args.username and args.password:
        payload = {"name": args.username, "password": args.password}
        if args.tenant:
            payload["tenant"] = args.tenant
        resp = session.post(f"{args.url}/entity/auth/login", json=payload, timeout=30)
        if resp.status_code not in (200, 204):
            print(f"Login failed: HTTP {resp.status_code}")
            sys.exit(1)

    if args.action == "capture":
        baseline = capture_baseline(session, args.url)
        with open(args.baseline_file, "w") as f:
            json.dump(baseline, f, indent=2)
        print(f"Captured {len(baseline)} GIs to {args.baseline_file}")

    elif args.action == "diff":
        with open(args.baseline_file) as f:
            before = json.load(f)
        after = capture_baseline(session, args.url)
        result = diff_baselines(before, after)
        has_errors = report_diff(result)
        if has_errors:
            sys.exit(1)
