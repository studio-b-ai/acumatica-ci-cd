"""
OData fetcher for StudioBAuditTrail GI.

Uses HTTP Basic Auth (not session cookies) — Acumatica cloud OData requires it.
No external dependencies — uses urllib from stdlib.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional

from .models import AuditRecord
from .parser import parse_odata_response


# ── Configuration ────────────────────────────────────────────────────────────

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _basic_auth_header(username: str, password: str) -> str:
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {creds}"


# ── Fetcher ──────────────────────────────────────────────────────────────────

class AuditFetcher:
    """Fetches audit trail data from Acumatica OData endpoint."""

    GI_NAME = "StudioBAuditTrail"

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tenant: Optional[str] = None,
    ):
        self.base_url = (base_url or _env("ACUMATICA_URL")).rstrip("/")
        self.username = username or _env("ACUMATICA_USERNAME")
        self.password = password or _env("ACUMATICA_PASSWORD")
        self.tenant = tenant or _env("ACUMATICA_TENANT", "Heritage Fabrics")

        if not self.base_url:
            raise ValueError("ACUMATICA_URL is required")
        if not self.username or not self.password:
            raise ValueError("ACUMATICA_USERNAME and ACUMATICA_PASSWORD are required")

    def _build_url(self, top: int = 1000, skip: int = 0,
                   since: Optional[datetime] = None,
                   until: Optional[datetime] = None,
                   screen_id: Optional[str] = None) -> str:
        """Build OData URL with filters."""
        tenant_encoded = urllib.parse.quote(self.tenant, safe="")
        url = f"{self.base_url}/odata/{tenant_encoded}/{self.GI_NAME}"

        params = {
            "$format": "json",
            "$top": str(top),
            "$orderby": "ChangeDate asc",
        }
        if skip > 0:
            params["$skip"] = str(skip)

        filters = []
        if since:
            filters.append(f"ChangeDate ge datetime'{since.strftime('%Y-%m-%dT%H:%M:%S')}'")
        if until:
            filters.append(f"ChangeDate le datetime'{until.strftime('%Y-%m-%dT%H:%M:%S')}'")
        if screen_id:
            filters.append(f"ScreenID eq '{screen_id}'")
        if filters:
            params["$filter"] = " and ".join(filters)

        query = urllib.parse.urlencode(params)
        return f"{url}?{query}"

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """SSL context that works on macOS (where system Python lacks certs)."""
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
        ctx = ssl.create_default_context()
        try:
            # Test if default context works
            ctx.load_default_certs()
            return ctx
        except Exception:
            # macOS Python without certs installed — fall back
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

    def _fetch_page(self, url: str) -> list[dict]:
        """Fetch a single page of OData results."""
        auth = _basic_auth_header(self.username, self.password)
        req = urllib.request.Request(url, headers={
            "Authorization": auth,
            "Accept": "application/json",
        })
        ctx = self._ssl_context()
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                data = json.loads(resp.read().decode())
                return data.get("value", [])
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OData request failed: HTTP {e.code} — {e.read().decode()[:500]}")

    def fetch(
        self,
        top: int = 1000,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        screen_id: Optional[str] = None,
        max_pages: int = 10,
    ) -> list[AuditRecord]:
        """Fetch audit records with pagination.

        Args:
            top: Records per page (max 1000)
            since: Only records after this date
            until: Only records before this date
            screen_id: Filter to a specific screen
            max_pages: Safety limit on pagination

        Returns:
            Parsed AuditRecords sorted by ChangeDate ascending
        """
        all_records: list[AuditRecord] = []
        skip = 0
        page_size = min(top, 1000)

        for page in range(max_pages):
            url = self._build_url(
                top=page_size, skip=skip,
                since=since, until=until, screen_id=screen_id,
            )
            rows = self._fetch_page(url)
            if not rows:
                break

            records = parse_odata_response(rows)
            all_records.extend(records)

            if len(rows) < page_size:
                break  # last page
            skip += page_size

        return all_records

    def fetch_since(self, since: datetime, **kwargs) -> list[AuditRecord]:
        """Convenience: fetch all records since a given date."""
        return self.fetch(since=since, **kwargs)

    def fetch_days(self, days: int = 30, **kwargs) -> list[AuditRecord]:
        """Convenience: fetch records from the last N days."""
        since = datetime.now() - timedelta(days=days)
        return self.fetch(since=since, **kwargs)


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Acumatica audit trail data")
    parser.add_argument("--top", type=int, default=100, help="Max records to fetch")
    parser.add_argument("--days", type=int, default=30, help="Fetch last N days")
    parser.add_argument("--screen", type=str, help="Filter by screen ID")
    args = parser.parse_args()

    fetcher = AuditFetcher()
    records = fetcher.fetch_days(days=args.days, top=args.top, screen_id=args.screen)

    print(f"Fetched {len(records)} records")
    for r in records[:5]:
        print(f"  [{r.batch_id}] {r.screen_id} {r.operation} {r.table_name} "
              f"key={r.combined_key} fields={len(r.modified_fields)}")
    if len(records) > 5:
        print(f"  ... and {len(records) - 5} more")
