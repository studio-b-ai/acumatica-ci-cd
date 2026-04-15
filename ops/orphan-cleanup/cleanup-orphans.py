#!/usr/bin/env python3
"""Reconcile + remove orphan customization metadata via Acumatica's own API.

Strategy: Re-import each orphan project (creates matching CustProject row),
then call /CustomizationApi/delete to let Acumatica's own deletion logic
clean up CustProject + CustPublishedProject + child tables properly.

This avoids any direct system-table SQL.

Usage:
    python3 cleanup-orphans.py --env sandbox --dry-run
    python3 cleanup-orphans.py --env sandbox
    python3 cleanup-orphans.py --env production
"""
import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests  # type: ignore

# ── Config ──────────────────────────────────────────────────────────────

ZIP_DIR = Path("/tmp/orphan-cleanup")

ORPHANS = [
    ("IIGCONTAINERMGMT[24.204.0004][R19]1", "IIGCONTAINERMGMT.zip"),
    ("IIGHFContainerMods[24.204.0004][R04]", "IIGHFContainerMods.zip"),
    ("AesthetikContainerGIs",                "AesthetikContainerGIs.zip"),
]

# ── Acumatica client (minimal) ──────────────────────────────────────────

class AcuClient:
    def __init__(self, base_url: str, username: str, password: str, tenant: str):
        self.base = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.tenant = tenant
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"

    def login(self):
        r = self.session.post(
            f"{self.base}/entity/auth/login",
            json={"name": self.username, "password": self.password,
                  "company": self.tenant},
            timeout=180,
        )
        r.raise_for_status()
        log("Logged in.", "ok")

    def logout(self):
        try:
            self.session.post(f"{self.base}/entity/auth/logout", timeout=30)
        except Exception:
            pass

    def get_projects(self) -> list:
        """Returns currently-published project list (uses publishEnd query trick).
        Falls back to empty list on error."""
        # Acumatica doesn't expose a clean 'list projects' endpoint via the
        # CustomizationApi. We query it indirectly via publishBegin's pre-flight
        # (set isOnlyValidation=true) — but that's destructive. Skip listing,
        # rely on POST /delete idempotence (returns log even if not found).
        return []

    def import_package(self, project_name: str, zip_path: Path):
        b64 = base64.b64encode(zip_path.read_bytes()).decode("ascii")
        payload = {
            "projectName": project_name,
            "projectDescription": f"Orphan reconciliation reimport — will be deleted immediately",
            "projectLevel": 0,
            "isReplaceIfExists": True,
            "projectContentBase64": b64,
        }
        r = self.session.post(
            f"{self.base}/CustomizationApi/Import",
            json=payload,
            timeout=120,
        )
        if r.status_code not in (200, 204):
            raise RuntimeError(f"Import failed ({r.status_code}): {r.text[:300]}")
        log(f"Imported: {project_name}", "ok")

    def delete_project(self, project_name: str) -> dict:
        r = self.session.post(
            f"{self.base}/CustomizationApi/delete",
            json={"projectName": project_name},
            timeout=180,
        )
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        if r.status_code not in (200, 204):
            raise RuntimeError(
                f"Delete failed ({r.status_code}) for {project_name}: {data}"
            )
        return data

    def test_merge_publish(self, project_names=None) -> tuple[bool, str]:
        """Validate-only publishBegin with merge=true. Returns (success, message).

        With empty project_names, exercises Acumatica's merge-state enumeration
        (the code path that crashes on orphan rows) without needing any real
        project content. This is the most reliable orphan-presence test.
        """
        r = self.session.post(
            f"{self.base}/CustomizationApi/publishBegin",
            json={
                "isMergeWithExistingPackages": True,
                "isOnlyValidation": True,
                "isOnlyDbUpdates": False,
                "projectNames": project_names or [],
                "tenantMode": "Current",
            },
            timeout=180,
        )
        if r.status_code not in (200, 204):
            return False, f"publishBegin returned {r.status_code}: {r.text[:300]}"

        # Poll publishEnd briefly (validation-only completes fast)
        for _ in range(30):
            time.sleep(2)
            pe = self.session.post(
                f"{self.base}/CustomizationApi/publishEnd",
                json={},
                timeout=30,
            )
            try:
                d = pe.json()
                if isinstance(d, dict):
                    if d.get("isFailed"):
                        return False, f"Validation failed: {str(d.get('log',''))[:300]}"
                    if d.get("isCompleted"):
                        return True, "merge=true validation completed"
            except Exception:
                if pe.text.strip().lower() == "true":
                    return True, "merge=true validation completed"
        return False, "publishEnd timed out (60s)"


def log(msg: str, kind: str = "info"):
    icons = {"info": "•", "ok": "✅", "warn": "⚠️ ", "err": "❌"}
    print(f"  {icons.get(kind,'•')} {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["sandbox", "production"], required=True)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan, don't make changes")
    ap.add_argument("--skip-merge-test", action="store_true",
                    help="Skip the post-cleanup merge=true validation")
    args = ap.parse_args()

    # Load credentials from env (set by caller before invoking)
    base_url = os.environ.get("ACUMATICA_URL", "").rstrip("/")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    tenant = os.environ.get("ACUMATICA_TENANT", "")

    if not all([base_url, username, password, tenant]):
        print("ERROR: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT required")
        sys.exit(2)

    print(f"\n=== Orphan Cleanup — {args.env.upper()} ===")
    print(f"Instance: {base_url}")
    print(f"Tenant:   {tenant}")
    print(f"User:     {username}")
    print(f"Mode:     {'DRY-RUN' if args.dry_run else 'LIVE'}\n")

    print("Plan:")
    for name, zip_name in ORPHANS:
        zp = ZIP_DIR / zip_name
        exists = "✓" if zp.exists() else "✗ MISSING"
        print(f"  {exists}  {name} ← {zip_name}")
    print()

    if args.dry_run:
        print("DRY-RUN: no changes made.")
        return 0

    # Verify all zips exist before touching anything
    missing = [z for _, z in ORPHANS if not (ZIP_DIR / z).exists()]
    if missing:
        print(f"ERROR: missing zip(s): {missing}")
        return 2

    # Production safety: require explicit env var
    if args.env == "production":
        if os.environ.get("CONFIRM_PRODUCTION") != "YES":
            print("REFUSED: production runs require CONFIRM_PRODUCTION=YES")
            return 2

    client = AcuClient(base_url, username, password, tenant)
    try:
        client.login()

        for name, zip_name in ORPHANS:
            print(f"\n→ Processing: {name}")
            try:
                client.import_package(name, ZIP_DIR / zip_name)
            except Exception as e:
                log(f"Import failed (continuing): {e}", "warn")
                # Try delete anyway — orphan might still be deletable
            try:
                result = client.delete_project(name)
                log_lines = result.get("log", [])
                if log_lines:
                    for entry in log_lines[:3]:
                        log(f"  {entry.get('message','')}", "info")
                log(f"Deleted: {name}", "ok")
            except Exception as e:
                log(f"Delete failed: {e}", "err")

        if not args.skip_merge_test:
            print("\n→ Testing merge=true publishBegin (validation only, empty list)...")
            # Empty list exercises orphan enumeration without needing real content
            ok, msg = client.test_merge_publish()
            if ok:
                log(msg, "ok")
                print("\n✅ ORPHAN CLEANUP SUCCESSFUL — merge=true is now safe to use.")
            else:
                log(msg, "err")
                print("\n⚠️  Cleanup ran but merge=true still fails. May need investigation.")
                return 1

    finally:
        client.logout()

    return 0


if __name__ == "__main__":
    sys.exit(main())
