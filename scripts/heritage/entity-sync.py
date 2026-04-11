#!/usr/bin/env python3
"""
Acumatica Entity Sync: Production → Test Company

Copies key business entities from the production tenant to the test tenant
on the same Acumatica instance using the REST API upsert (PUT) pattern.

Entities synced:
  1. Customer   — key: CustomerID, expand: MainContact
  2. StockItem  — key: InventoryID, expand: Attributes
  3. Vendor     — key: VendorID
  4. Employee   — key: EmployeeID
  5. SalesOrder — read-only count comparison (no write)

Safety:
  - Never deletes records in test — only creates/updates
  - Logs every write operation
  - Continues to next entity on failure (no abort)
  - Rate-limited writes to avoid session timeout

Usage:
  python scripts/entity-sync.py

Environment variables (all required):
  ACUMATICA_URL          — Instance URL (e.g. https://heritagefabrics.acumatica.com)
  ACUMATICA_USERNAME     — API user
  ACUMATICA_PASSWORD     — API password
  PROD_TENANT            — Production tenant name (e.g. "Heritage Fabrics")
  TEST_TENANT            — Test tenant name (e.g. "Heritage Test")
  SLACK_WEBHOOK_URL      — Incoming webhook for summary notification (optional)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Force unbuffered output — critical for GitHub Actions log visibility
os.environ["PYTHONUNBUFFERED"] = "1"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_VERSION = "24.200.001"
WRITE_DELAY_SECONDS = 0.3  # Delay between PUT calls to avoid session pressure
PAGE_SIZE = 100  # Records per API page
MAX_PAGES = 50  # Safety cap: 5,000 records per entity

# Entities to sync — order matters (customers before orders, etc.)
ENTITY_CONFIG = [
    {
        "name": "Customer",
        "key_field": "CustomerID",
        "expand": "MainContact",
        "select": None,  # Fetch all default fields
        "write": True,
    },
    {
        "name": "StockItem",
        "key_field": "InventoryID",
        "expand": "Attributes",
        "select": None,
        "write": True,
    },
    {
        "name": "Vendor",
        "key_field": "VendorID",
        "expand": None,
        "select": None,
        "write": True,
    },
    {
        "name": "Employee",
        "key_field": "EmployeeID",
        "expand": None,
        "select": None,
        "write": True,
    },
    {
        "name": "SalesOrder",
        "key_field": "OrderNbr",
        "expand": None,
        "select": "OrderNbr,OrderType,Status,OrderTotal",
        "write": False,  # Read-only — count comparison
    },
    {
        "name": "PurchaseOrder",
        "key_field": "OrderNbr",
        "expand": None,
        "select": None,
        "write": True,
    },
    {
        "name": "Shipment",
        "key_field": "ShipmentNbr",
        "expand": None,
        "select": None,
        "write": True,
    },
]


# ---------------------------------------------------------------------------
# Logging helpers (match deploy.py style)
# ---------------------------------------------------------------------------

COLORS = {
    "ok": "\033[92m",      # green
    "warn": "\033[93m",    # yellow
    "err": "\033[91m",     # red
    "info": "\033[96m",    # cyan
    "bold": "\033[1m",     # bold
    "reset": "\033[0m",
}


def _log(message: str, style: str = "info") -> None:
    """Print a timestamped, colorized log line."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    color = COLORS.get(style, "")
    reset = COLORS["reset"]
    print(f"{color}[{ts}] {message}{reset}", flush=True)


# ---------------------------------------------------------------------------
# Acumatica REST client
# ---------------------------------------------------------------------------

class AcumaticaEntityClient:
    """Lightweight REST client for Acumatica entity API."""

    def __init__(self, url: str, username: str, password: str, tenant: str, timeout: int = 60):
        self.base_url = url.rstrip("/")
        self.entity_base = f"{self.base_url}/entity/default/{API_VERSION}"
        self.username = username
        self.password = password
        self.tenant = tenant
        self.timeout = timeout
        self.session = self._create_session()
        self._authenticated = False

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({"Content-Type": "application/json"})
        return session

    def login(self) -> None:
        payload: dict[str, str] = {"name": self.username, "password": self.password}
        if self.tenant:
            payload["tenant"] = self.tenant

        resp = self.session.post(
            f"{self.base_url}/entity/auth/login",
            json=payload,
            timeout=self.timeout,
        )
        if resp.status_code != 204:
            raise RuntimeError(
                f"Login failed for tenant '{self.tenant}' "
                f"(HTTP {resp.status_code}): {resp.text[:500]}"
            )
        self._authenticated = True
        _log(f"Authenticated to tenant: {self.tenant}", style="ok")

    def logout(self) -> None:
        if not self._authenticated:
            return
        try:
            self.session.post(f"{self.base_url}/entity/auth/logout", timeout=15)
        except Exception:
            pass
        self._authenticated = False

    def fetch_all(
        self,
        entity: str,
        expand: Optional[str] = None,
        select: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetch all records for an entity type, handling pagination."""
        records: list[dict[str, Any]] = []
        skip = 0

        for page in range(MAX_PAGES):
            params: dict[str, str] = {
                "$top": str(PAGE_SIZE),
                "$skip": str(skip),
            }
            if expand:
                params["$expand"] = expand
            if select:
                params["$select"] = select

            resp = self.session.get(
                f"{self.entity_base}/{entity}",
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Fetch {entity} failed at page {page} "
                    f"(HTTP {resp.status_code}): {resp.text[:300]}"
                )

            batch = resp.json()
            if not batch:
                break

            records.extend(batch)
            _log(f"  Fetched page {page + 1}: {len(batch)} records (total: {len(records)})")

            if len(batch) < PAGE_SIZE:
                break
            skip += PAGE_SIZE

        return records

    def put_record(self, entity: str, payload: dict[str, Any]) -> requests.Response:
        """PUT (upsert) a single record."""
        resp = self.session.put(
            f"{self.entity_base}/{entity}",
            json=payload,
            timeout=self.timeout,
        )
        return resp


# ---------------------------------------------------------------------------
# Record cleaning — strip read-only / server-generated fields before PUT
# ---------------------------------------------------------------------------

# Fields that Acumatica returns but rejects on PUT (read-only or computed)
STRIP_FIELDS = {
    "id", "rowNumber", "note", "custom",
    "LastModifiedDateTime", "CreatedDateTime",
    "_links",
}

# Sub-entity collections that should not be sent back on PUT
# (they have their own lifecycle or are read-only)
STRIP_SUB_ENTITIES: dict[str, set[str]] = {
    "Customer": {"Salespersons", "BillingContact", "ShippingContact",
                 "CreditVerificationRules", "PaymentInstructions",
                 "StatementAddressOverride", "Attributes"},
    "StockItem": {"WarehouseDetails", "CrossReferences", "VendorDetails",
                  "ReplenishmentParameters", "SubItems", "BoxesByArticle"},
    "Employee": {"EmployeeCost", "EmploymentHistory"},
}


def _unwrap_value(v: Any) -> Any:
    """Acumatica wraps scalars in {value: X} — unwrap for comparison, keep for PUT."""
    if isinstance(v, dict) and "value" in v and len(v) == 1:
        return v["value"]
    return v


def clean_record(entity_name: str, record: dict[str, Any]) -> dict[str, Any]:
    """Strip read-only fields from a record so it can be PUT to another tenant."""
    cleaned: dict[str, Any] = {}
    strip_subs = STRIP_SUB_ENTITIES.get(entity_name, set())

    for key, val in record.items():
        if key in STRIP_FIELDS:
            continue
        if key in strip_subs:
            continue
        # Keep the value as-is (Acumatica expects {value: X} wrappers on PUT)
        cleaned[key] = val

    return cleaned


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

class SyncResult:
    """Tracks results for one entity type."""

    def __init__(self, entity_name: str):
        self.entity_name = entity_name
        self.prod_count = 0
        self.test_count_before = 0
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors: list[str] = []
        self.write_enabled = True

    @property
    def total_written(self) -> int:
        return self.created + self.updated

    def summary_line(self) -> str:
        if not self.write_enabled:
            return (
                f"{self.entity_name}: prod={self.prod_count}, "
                f"test={self.test_count_before} (read-only comparison)"
            )
        status = "OK" if not self.errors else f"ERRORS({len(self.errors)})"
        return (
            f"{self.entity_name}: prod={self.prod_count}, "
            f"written={self.total_written} "
            f"(created={self.created}, updated={self.updated}, "
            f"skipped={self.skipped}, errors={len(self.errors)}) [{status}]"
        )


# ---------------------------------------------------------------------------
# Slack notification
# ---------------------------------------------------------------------------

def post_slack_summary(webhook_url: str, results: list[SyncResult], target: str = "test") -> None:
    """Post a summary to Slack via incoming webhook."""
    total_errors = sum(len(r.errors) for r in results)
    icon = ":white_check_mark:" if total_errors == 0 else ":warning:"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    target_label = "Sandbox" if target == "sandbox" else "Test"

    lines = [f"{icon} *Entity Sync: Prod → {target_label}* ({ts})", ""]
    for r in results:
        lines.append(f"  {r.summary_line()}")

    if total_errors > 0:
        lines.append("")
        lines.append(f":x: {total_errors} total errors — check workflow logs")

    payload = {
        "text": "\n".join(lines),
        "unfurl_links": False,
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            _log("Slack notification sent", style="ok")
        else:
            _log(f"Slack notification failed: HTTP {resp.status_code}", style="warn")
    except Exception as e:
        _log(f"Slack notification error: {e}", style="warn")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Sync entities from prod to target instance")
    parser.add_argument(
        "--target", choices=["test", "sandbox"], default="test",
        help="Target instance: 'test' (Heritage Test tenant on prod) or 'sandbox' (separate sandbox instance)",
    )
    args = parser.parse_args()

    target_label = "Sandbox" if args.target == "sandbox" else "Test"
    _log(f"=== Acumatica Entity Sync: Production → {target_label} ===", style="bold")

    # Read config from environment
    url = os.environ.get("ACUMATICA_URL", "").rstrip("/")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    prod_tenant = os.environ.get("PROD_TENANT", "Heritage Fabrics")
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not all([url, username, password]):
        _log("Missing required env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD", style="err")
        return 1

    # Target config: test uses same instance, sandbox uses separate instance
    if args.target == "sandbox":
        target_url = os.environ.get("SANDBOX_URL", "").rstrip("/")
        target_username = os.environ.get("SANDBOX_USERNAME", "")
        target_password = os.environ.get("SANDBOX_PASSWORD", "")
        target_tenant = os.environ.get("SANDBOX_TENANT", "")
        if not all([target_url, target_username, target_password]):
            _log(
                "Missing required env vars for sandbox target: "
                "SANDBOX_URL, SANDBOX_USERNAME, SANDBOX_PASSWORD",
                style="err",
            )
            return 1
    else:
        target_url = url
        target_username = username
        target_password = password
        target_tenant = os.environ.get("TEST_TENANT", "Heritage Test")

    _log(f"Source instance: {url}")
    _log(f"Production tenant: {prod_tenant}")
    _log(f"Target ({args.target}): {target_url} / {target_tenant or '(default)'}")

    # Create clients
    prod = AcumaticaEntityClient(url, username, password, prod_tenant)
    test = AcumaticaEntityClient(target_url, target_username, target_password, target_tenant)

    results: list[SyncResult] = []

    # Phase 1: Read all data from production (single session)
    prod_data: dict[str, list[dict[str, Any]]] = {}
    _log("=== Phase 1: Reading from production ===", style="bold")
    try:
        prod.login()
        for config in ENTITY_CONFIG:
            name = config["name"]
            try:
                _log(f"--- Fetching {name} from production ---", style="bold")
                records = prod.fetch_all(
                    name,
                    expand=config.get("expand"),
                    select=config.get("select"),
                )
                prod_data[name] = records
                _log(f"  {name}: {len(records)} records fetched", style="ok")
            except Exception as e:
                _log(f"  {name}: fetch failed — {e}", style="err")
                prod_data[name] = []
    finally:
        prod.logout()

    # Phase 2: Write to target (separate session — avoids session gate conflict)
    _log("")
    _log(f"=== Phase 2: Writing to {target_label} ===", style="bold")
    try:
        test.login()
        for config in ENTITY_CONFIG:
            name = config["name"]
            try:
                result = SyncResult(name)
                result.write_enabled = config["write"]
                result.prod_count = len(prod_data.get(name, []))

                if not config["write"]:
                    # Read-only: just count test records
                    test_records = test.fetch_all(name, select=config.get("select"))
                    result.test_count_before = len(test_records)
                    _log(
                        f"  {name}: prod={result.prod_count}, test={result.test_count_before} "
                        f"(delta: {result.prod_count - result.test_count_before})",
                        style="info",
                    )
                    results.append(result)
                    continue

                # Fetch existing test keys
                key_field = config["key_field"]
                test_records = test.fetch_all(name, select=key_field)
                result.test_count_before = len(test_records)
                test_keys = set()
                for r in test_records:
                    key_val = r.get(key_field)
                    if isinstance(key_val, dict):
                        key_val = key_val.get("value")
                    if key_val:
                        test_keys.add(str(key_val).strip())
                _log(f"  {name}: {result.test_count_before} existing test records")

                # Upsert each prod record to test
                prod_records = prod_data.get(name, [])
                for i, record in enumerate(prod_records):
                    key_val = record.get(key_field)
                    if isinstance(key_val, dict):
                        key_val = key_val.get("value")
                    key_str = str(key_val).strip() if key_val else f"unknown-{i}"

                    try:
                        payload = clean_record(name, record)
                        resp = test.put_record(name, payload)

                        if resp.status_code in (200, 201):
                            is_new = key_str not in test_keys
                            if is_new:
                                result.created += 1
                                _log(f"  [{i+1}/{len(prod_records)}] Created {name} {key_str}", style="ok")
                            else:
                                result.updated += 1
                                if (i + 1) % 25 == 0:
                                    _log(f"  [{i+1}/{len(prod_records)}] Updated {name} (batch progress)")
                        elif resp.status_code == 500 and "PXLockViolation" in resp.text:
                            result.skipped += 1
                            _log(f"  [{i+1}] Skipped {name} {key_str} (record locked)", style="warn")
                        else:
                            msg = f"{name} {key_str}: PUT HTTP {resp.status_code} — {resp.text[:200]}"
                            _log(f"  [{i+1}] {msg}", style="err")
                            result.errors.append(msg)
                    except Exception as e:
                        msg = f"{name} {key_str}: {e}"
                        _log(f"  [{i+1}] Error: {msg}", style="err")
                        result.errors.append(msg)

                    time.sleep(WRITE_DELAY_SECONDS)

                _log(
                    f"  {name} complete: {result.total_written} written, "
                    f"{result.skipped} skipped, {len(result.errors)} errors",
                    style="ok" if not result.errors else "warn",
                )
                results.append(result)

            except Exception as e:
                _log(f"Entity {name} sync failed: {e}", style="err")
                r = SyncResult(name)
                r.errors.append(str(e))
                results.append(r)
    finally:
        test.logout()

    # Print summary
    _log("")
    _log("=== SYNC SUMMARY ===", style="bold")
    total_errors = 0
    for r in results:
        style = "ok" if not r.errors else "err"
        _log(f"  {r.summary_line()}", style=style)
        total_errors += len(r.errors)

    # Slack notification
    if slack_webhook:
        post_slack_summary(slack_webhook, results, target=args.target)
    else:
        _log("No SLACK_WEBHOOK_URL set — skipping notification", style="warn")

    if total_errors > 0:
        _log(f"\n{total_errors} total errors across all entities", style="err")
        return 1

    _log("\nAll entities synced successfully", style="ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
