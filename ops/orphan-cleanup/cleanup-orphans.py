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

    def probe_project(self, project_name: str) -> dict:
        """Read-only probe: does a CustProject row exist for this name?

        Returns dict with:
          http_code: HTTP status from /CustomizationApi/getProject
          present: True if HTTP 200 (orphan row exists on instance)
          has_nre: True if response body contains "NullReferenceException"
                   — matches qualify.py check_orphan_scan() corruption heuristic.
          detail: short human-readable message

        Does not import, delete, or publish anything.
        """
        r = self.session.post(
            f"{self.base}/CustomizationApi/getProject",
            json={"projectName": project_name},
            timeout=30,
        )
        body = r.text or ""
        has_nre = "NullReferenceException" in body
        present = r.status_code == 200
        if has_nre:
            detail = "NRE — subsystem corrupted (see Rule #18)"
        elif present:
            detail = "present on instance"
        elif r.status_code == 400 and "not found" in body.lower():
            detail = "not found (clean)"
        else:
            detail = f"unexpected HTTP {r.status_code}: {body[:120]}"
        return {
            "name": project_name,
            "http_code": r.status_code,
            "present": present,
            "has_nre": has_nre,
            "detail": detail,
        }

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
    ap.add_argument("--probe-only", action="store_true",
                    help="Read-only diagnostic: check each ORPHAN name via "
                         "/CustomizationApi/getProject. No imports, deletes, or "
                         "publishes. Exits 0 if all clean, 1 if any NRE detected, "
                         "2 if any orphan row still present.")
    ap.add_argument("--extra", default="",
                    help="Comma-separated list of additional project names to "
                         "probe (only used with --probe-only).")
    args = ap.parse_args()

    # Load credentials from env (set by caller before invoking)
    base_url = os.environ.get("ACUMATICA_URL", "").rstrip("/")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    tenant = os.environ.get("ACUMATICA_TENANT", "")

    if not all([base_url, username, password, tenant]):
        print("ERROR: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT required")
        sys.exit(2)

    mode = "PROBE-ONLY" if args.probe_only else ("DRY-RUN" if args.dry_run else "LIVE")
    print(f"\n=== Orphan Cleanup — {args.env.upper()} ===")
    print(f"Instance: {base_url}")
    print(f"Tenant:   {tenant}")
    print(f"User:     {username}")
    print(f"Mode:     {mode}\n")

    # Probe-only: read-only diagnostic path, no prerequisites, no mutations.
    if args.probe_only:
        extra = [n.strip() for n in args.extra.split(",") if n.strip()]
        probe_names = [n for n, _ in ORPHANS] + extra
        print(f"Probing {len(probe_names)} name(s) via /CustomizationApi/getProject:")
        for name in probe_names:
            print(f"  • {name}")
        print()

        client = AcuClient(base_url, username, password, tenant)
        try:
            client.login()
            results = [client.probe_project(name) for name in probe_names]
        finally:
            client.logout()

        print(f"\n{'Name':55}  {'HTTP':>4}  {'Status':16}  Detail")
        print("-" * 110)
        for r in results:
            present_tag = "ORPHAN ROW" if r["present"] else "NRE" if r["has_nre"] else "clean"
            print(f"{r['name'][:55]:55}  {r['http_code']:>4}  {present_tag:16}  {r['detail']}")

        any_nre = any(r["has_nre"] for r in results)
        any_present = any(r["present"] for r in results)
        print()
        if any_nre:
            print("❌ One or more probes returned NullReferenceException. "
                  "Corruption confirmed — see docs/AAR-2026-04-17-custproject-nre-transient.md "
                  "for the Rule #18 diagnostic. Exiting 1.")
            return 1
        if any_present:
            print("⚠️  One or more orphan CustProject rows are present. "
                  "Run without --probe-only to clean them via import + "
                  "/CustomizationApi/delete. Exiting 2.")
            return 2
        print("✅ All probed names return 'not found' — no orphan CustProject rows on instance.")
        return 0

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
