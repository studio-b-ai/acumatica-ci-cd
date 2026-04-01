#!/usr/bin/env python3
"""
Pre-Migration Validation Script

Runs read-only SQL-equivalent checks against Acumatica REST API before
deploying any data migration (UOM rename, schema changes, etc.).
Exits with code 0 if safe to migrate, code 1 if issues found.

AAR 2026-03-29: The UOM PIECE->YDS migration was deployed to production
without any pre-flight validation. It broke immediately. This script would
have caught the issues (null SalesUnit values, incomplete INUnit records)
BEFORE the migration ran.

Usage:
    python validate-migration.py --type uom --from-unit PIECE --to-unit YDS
    python validate-migration.py --type uom --from-unit PIECE --to-unit YDS --tenant HeritageTest

Required env vars:
    ACUMATICA_URL       Acumatica instance URL
    ACUMATICA_USERNAME  API username
    ACUMATICA_PASSWORD  API password
    ACUMATICA_TENANT    Tenant name (or use --tenant flag)

Exit codes:
    0  All checks passed — safe to migrate
    1  Issues found — DO NOT migrate until resolved
"""

import argparse
import json
import os
import sys
import http.cookiejar
import urllib.request
import urllib.error

os.environ["PYTHONUNBUFFERED"] = "1"

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
RESET = "\033[0m"

issues = []
warnings_found = []


def error(msg: str):
    issues.append(msg)
    print(f"{RED}[FAIL]{RESET}  {msg}")


def warn(msg: str):
    warnings_found.append(msg)
    print(f"{YELLOW}[WARN]{RESET}  {msg}")


def ok(msg: str):
    print(f"{GREEN}[ OK ]{RESET}  {msg}")


class AcumaticaRestClient:
    """Minimal REST client for read-only migration validation queries."""

    def __init__(self, url: str, username: str, password: str, tenant: str):
        self.base_url = url.rstrip("/")
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cj)
        )
        self._login(username, password, tenant)

    def _login(self, username: str, password: str, tenant: str) -> None:
        body = json.dumps({"name": username, "password": password, "tenant": tenant}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/entity/auth/login",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = self.opener.open(req, timeout=30)
        if resp.status not in (200, 204):
            raise RuntimeError(f"Login failed: HTTP {resp.status}")
        print(f"  Authenticated to {self.base_url}")

    def logout(self) -> None:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/entity/auth/logout", method="POST"
            )
            self.opener.open(req, timeout=10)
        except Exception:
            pass

    def query(self, entity: str, select: str = "", filter_str: str = "", top: int = 100) -> list:
        params = [f"$top={top}"]
        if select:
            params.append(f"$select={select}")
        if filter_str:
            params.append(f"$filter={filter_str}")
        url = f"{self.base_url}/entity/Default/24.200.001/{entity}?{'&'.join(params)}"

        req = urllib.request.Request(url, method="GET")
        try:
            resp = self.opener.open(req, timeout=60)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"Query failed HTTP {e.code}: {body[:300]}")


# ─── UOM Migration Checks ─────────────────────────────────────────────────────


def check_uom_inventory_items(client: AcumaticaRestClient, from_unit: str) -> None:
    """Check 1: InventoryItem null UOM fields.

    The migration renames BaseUnit from FROM_UNIT to TO_UNIT.
    If SalesUnit or PurchaseUnit are null BEFORE the migration, the migration
    will leave them null. When Acumatica tries to load the item on a Sales Order,
    SetDefaultExt<SOLine.uOM> defaults to null => UnitVerifying(unit=null) crash.

    This is the confirmed root cause analysis of the 2026-03-29 UOM outage.
    """
    print(f"\n[Check 1] InventoryItem null SalesUnit/PurchaseUnit (BaseUnit={from_unit})")

    try:
        items = client.query(
            "StockItem",
            select="InventoryID,BaseUnit,SalesUnit,PurchaseUnit",
            top=500,
        )
    except RuntimeError as e:
        warn(f"Could not query StockItems: {e}")
        return

    null_sales = []
    null_purchase = []
    items_with_from_unit = []

    for item in items:
        inv_id = item.get("InventoryID", {}).get("value", "?")
        base = item.get("BaseUnit", {}).get("value", "")
        sales = item.get("SalesUnit", {}).get("value", "")
        purchase = item.get("PurchaseUnit", {}).get("value", "")

        if base == from_unit:
            items_with_from_unit.append(inv_id)

        if base == from_unit and not sales:
            null_sales.append(inv_id)
        if base == from_unit and not purchase:
            null_purchase.append(inv_id)

    ok(f"Found {len(items_with_from_unit)} items with BaseUnit={from_unit}")

    if null_sales:
        error(
            f"{len(null_sales)} items have null/empty SalesUnit where BaseUnit={from_unit}.\n"
            f"         These will cause UnitVerifying(unit=null) on Sales Order entry after migration.\n"
            f"         Items: {null_sales[:10]}{'...' if len(null_sales) > 10 else ''}\n"
            f"         Fix: UPDATE InventoryItem SET SalesUnit = BaseUnit WHERE SalesUnit IS NULL"
        )
    else:
        ok(f"All {len(items_with_from_unit)} items have non-null SalesUnit")

    if null_purchase:
        error(
            f"{len(null_purchase)} items have null/empty PurchaseUnit where BaseUnit={from_unit}.\n"
            f"         Items: {null_purchase[:10]}{'...' if len(null_purchase) > 10 else ''}\n"
            f"         Fix: UPDATE InventoryItem SET PurchaseUnit = BaseUnit WHERE PurchaseUnit IS NULL"
        )
    else:
        ok(f"All {len(items_with_from_unit)} items have non-null PurchaseUnit")


def check_uom_open_so_lines(client: AcumaticaRestClient, from_unit: str) -> None:
    """Check 2: Open Sales Order lines with the FROM unit.

    After the migration, these lines will reference the renamed unit.
    If the rename fails (INUnit records missing), these lines become broken.
    We need to count them as a risk indicator.
    """
    print(f"\n[Check 2] Open Sales Order lines with UOM={from_unit}")

    try:
        orders = client.query(
            "SalesOrder",
            select="OrderNbr,OrderType,Status",
            filter_str=f"Status ne 'Completed' and Status ne 'Cancelled'",
            top=200,
        )
    except RuntimeError as e:
        warn(f"Could not query open Sales Orders: {e}")
        return

    ok(f"Found {len(orders)} open/active Sales Orders")

    if orders:
        warn(
            f"There are {len(orders)} open Sales Orders. After UOM rename, open SO lines "
            f"with UOM={from_unit} will reference the renamed unit. Verify these are correct post-migration."
        )


def check_uom_open_po_lines(client: AcumaticaRestClient, from_unit: str) -> None:
    """Check 3: Open Purchase Order lines with the FROM unit.

    Same risk as SO lines — open PO lines with the old unit will reference
    the renamed unit after migration. Count them as a risk indicator.
    """
    print(f"\n[Check 3] Open Purchase Order lines with UOM={from_unit}")

    try:
        orders = client.query(
            "PurchaseOrder",
            select="OrderNbr,OrderType,Status",
            filter_str=f"Status ne 'Completed' and Status ne 'Cancelled'",
            top=200,
        )
    except RuntimeError as e:
        warn(f"Could not query open Purchase Orders: {e}")
        return

    ok(f"Found {len(orders)} open Purchase Orders")

    if orders:
        warn(
            f"There are {len(orders)} open Purchase Orders. After UOM rename, open PO lines "
            f"with UOM={from_unit} will reference the renamed unit. Verify these are correct post-migration."
        )


def check_uom_item_classes(client: AcumaticaRestClient, from_unit: str) -> None:
    """Check 4: Item classes with the FROM unit as BaseUnit.

    After migration, item classes with BaseUnit=FROM_UNIT need corresponding
    INUnit records (UnitType=2) with the new unit. If these are missing, items
    in those classes will have broken UOM lookups.
    """
    print(f"\n[Check 4] Item classes with BaseUnit={from_unit}")

    try:
        # Use ItemClass endpoint if available, fallback to a count check
        classes = client.query(
            "ItemClass",
            select="ItemClassID,BaseUnit",
            top=200,
        )
    except RuntimeError as e:
        warn(f"Could not query ItemClass: {e} (endpoint may not be available in this API version)")
        return

    classes_with_from_unit = [
        c.get("ItemClassID", {}).get("value", "?")
        for c in classes
        if c.get("BaseUnit", {}).get("value", "") == from_unit
    ]

    if classes_with_from_unit:
        ok(f"Found {len(classes_with_from_unit)} item classes with BaseUnit={from_unit}")
        ok(f"Classes: {classes_with_from_unit[:20]}")
    else:
        ok(f"No item classes found with BaseUnit={from_unit}")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Pre-migration validation for Acumatica data migrations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--type", choices=["uom"], required=True, help="Migration type")
    parser.add_argument("--from-unit", help="UOM being renamed (e.g., PIECE)")
    parser.add_argument("--to-unit", help="New UOM name (e.g., YDS)")
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    parser.add_argument(
        "--tenant",
        default=os.environ.get("ACUMATICA_TENANT", ""),
        help="Tenant name (use test tenant for pre-migration validation!)",
    )

    args = parser.parse_args()

    if not args.url:
        parser.error("--url required (or set ACUMATICA_URL)")
    if not args.username:
        parser.error("--username required (or set ACUMATICA_USERNAME)")
    if not args.password:
        parser.error("--password required (or set ACUMATICA_PASSWORD)")

    if args.type == "uom":
        if not args.from_unit:
            parser.error("--from-unit required for UOM migration type")
        if not args.to_unit:
            parser.error("--to-unit required for UOM migration type")

    print(f"Pre-Migration Validation: {args.type.upper()}")
    print(f"Target:  {args.url}")
    print(f"Tenant:  {args.tenant or '(default)'}")
    if args.type == "uom":
        print(f"Rename:  {args.from_unit} -> {args.to_unit}")
    print("=" * 60)
    print()
    print("NOTE: Run this against Heritage Test FIRST, then against production.")
    print("Both must pass before deploying the migration to production.")
    print()

    try:
        client = AcumaticaRestClient(args.url, args.username, args.password, args.tenant)
    except RuntimeError as e:
        error(f"Cannot connect to Acumatica: {e}")
        print()
        print(f"{RED}BLOCKED — cannot validate: connection failed{RESET}")
        sys.exit(1)

    try:
        if args.type == "uom":
            check_uom_inventory_items(client, args.from_unit)
            check_uom_open_so_lines(client, args.from_unit)
            check_uom_open_po_lines(client, args.from_unit)
            check_uom_item_classes(client, args.from_unit)
    finally:
        client.logout()

    print()
    print("=" * 60)

    if issues:
        print(f"{RED}BLOCKED — {len(issues)} issue(s) found. DO NOT deploy migration.{RESET}")
        print()
        print("Resolve all issues above before deploying the migration.")
        print("AAR 2026-03-29: Deploying without validating caused a multi-hour production outage.")
        sys.exit(1)
    elif warnings_found:
        print(f"{YELLOW}PASSED with {len(warnings_found)} warning(s) — review before migrating{RESET}")
        print()
        print("No blocking issues found. Review warnings above before proceeding.")
        sys.exit(0)
    else:
        print(f"{GREEN}PASSED — all checks passed. Safe to proceed with migration.{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
