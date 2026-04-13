#!/usr/bin/env python3
"""
Unpublish all customization projects on Acumatica Sandbox via REST API.

This clears orphaned project metadata from the database cleanup state,
which can cause NullReferenceException in CstWorkflowEventHandlers.CleanUpDatabase.

After unpublishing, optionally re-publishes the listed projects.

SAFETY: Only connects to sandbox (URL must contain 'sandbox').
"""

import os
import sys
import urllib.request
import urllib.error
import http.cookiejar
import json
import time

# ── Configuration (sandbox ONLY) ─────────────────────────────────────────────

BASE_URL  = os.environ.get("ACUMATICA_SANDBOX_URL", "")
USERNAME  = os.environ.get("ACUMATICA_SANDBOX_USERNAME", "")
PASSWORD  = os.environ.get("ACUMATICA_SANDBOX_PASSWORD", "")
TENANT    = os.environ.get("ACUMATICA_SANDBOX_TENANT", "")
REPUBLISH = os.environ.get("REPUBLISH", "").strip()  # comma-separated project names
POLL_INTERVAL = 10
POLL_TIMEOUT  = 600

# Safety
if BASE_URL and "sandbox" not in BASE_URL.lower():
    print(f"SAFETY: URL does not contain 'sandbox': {BASE_URL}")
    print("This script ONLY targets sandbox. Aborting.")
    sys.exit(1)

# ── HTTP helpers ─────────────────────────────────────────────────────────────

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def api_request(method, path, body=None, label=""):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": "application/json",
    })
    try:
        with opener.open(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label}] HTTP {e.code}: {raw[:500]}")
        return e.code, raw


# ── Login / Logout ─────────────────────────────────────────────────────────

def login():
    body = {"name": USERNAME, "password": PASSWORD}
    if TENANT:
        body["tenant"] = TENANT
    code, raw = api_request("POST", "/entity/auth/login", body, "Login")
    if code not in (200, 204):
        print(f"[Login] Failed — HTTP {code}")
        sys.exit(1)
    print(f"[Login] OK (tenant={TENANT})")


def logout():
    api_request("POST", "/entity/auth/logout", label="Logout")
    print("[Logout] Done")


# ── Unpublish All ────────────────────────────────────────────────────────────

def get_published_projects():
    """Get list of currently published customization projects."""
    code, raw = api_request("GET", "/CustomizationApi/published", label="GetPublished")
    if code == 200:
        try:
            projects = json.loads(raw)
            print(f"[GetPublished] Currently published: {projects}")
            return projects
        except json.JSONDecodeError:
            print(f"[GetPublished] Could not parse: {raw[:300]}")
    else:
        print(f"[GetPublished] HTTP {code} — endpoint may not exist")
    return None


def unpublish_all():
    """
    Unpublish all customization projects.

    Strategy: publish with isMergeWithExistingPackages=false and a single
    dummy/known project. This replaces the published set, effectively
    unpublishing everything else. Then unpublish the dummy.

    Alternative: try publishBegin with isOnlyDbUpdates=true which may
    skip the CleanUpDatabase step.
    """
    # First, see what's published
    get_published_projects()

    # Try approach: publish with isOnlyDbUpdates=true
    # This should skip CleanUpDatabase and only run SQL scripts
    print("[Unpublish] Trying isOnlyDbUpdates=true publish (skips CleanUpDatabase)...")

    body = {
        "isMergeWithExistingPackages": False,
        "isOnlyValidation": False,
        "isOnlyDbUpdates": True,
        "projectNames": ["StudioBAcuOps"],
        "tenantMode": "Current"
    }

    code, raw = api_request("POST", "/CustomizationApi/publishBegin", body, "DbOnlyPublish")
    if code in (200, 204):
        print("[Unpublish] publishBegin (dbOnly) OK — polling...")
        result = poll_publish("DbOnly")
        if result:
            return True
        print("[Unpublish] dbOnly failed, trying normal approach...")

    # Fallback: try normal publish with merge=false to replace published set
    print("[Unpublish] Trying merge=false publish to replace published set...")

    body = {
        "isMergeWithExistingPackages": False,
        "isOnlyValidation": False,
        "isOnlyDbUpdates": False,
        "projectNames": ["StudioBAcuOps"],
        "tenantMode": "Current"
    }

    code, raw = api_request("POST", "/CustomizationApi/publishBegin", body, "ReplacePublish")
    if code not in (200, 204):
        print(f"[Unpublish] publishBegin failed — HTTP {code}")
        print(f"[Unpublish] Response: {raw[:500]}")
        return False

    print("[Unpublish] publishBegin OK — polling for completion...")
    return poll_publish("Replace")


def poll_publish(label):
    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        code, raw = api_request("POST", "/CustomizationApi/publishEnd", {}, f"{label}Poll")

        if code in (200, 400):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    if data.get("isFailed"):
                        log_entries = data.get("log", [])
                        print(f"[{label}] FAILED after {elapsed}s")
                        for entry in log_entries[-20:]:
                            ts = entry.get("timestamp", "")
                            msg = entry.get("message", "")
                            print(f"  {ts} {msg}")
                        return False
                    if data.get("isCompleted"):
                        print(f"[{label}] Completed successfully ({elapsed}s)")
                        return True
                elif raw.strip().lower() == "false":
                    print(f"  [{label}] Still processing... ({elapsed}s / {POLL_TIMEOUT}s)")
                    continue
            except json.JSONDecodeError:
                if raw.strip().lower() == "false":
                    print(f"  [{label}] Still processing... ({elapsed}s / {POLL_TIMEOUT}s)")
                    continue
                elif raw.strip().lower() == "true":
                    print(f"[{label}] Completed ({elapsed}s)")
                    return True

        print(f"  [{label}] HTTP {code}, still processing... ({elapsed}s)")

    print(f"[{label}] Timed out after {POLL_TIMEOUT}s")
    return False


# ── Republish ────────────────────────────────────────────────────────────────

def republish(project_names):
    print(f"\n[Republish] Publishing projects: {project_names}")

    body = {
        "isMergeWithExistingPackages": True,
        "isOnlyValidation": False,
        "isOnlyDbUpdates": False,
        "projectNames": project_names,
        "tenantMode": "Current"
    }

    code, raw = api_request("POST", "/CustomizationApi/publishBegin", body, "RepublishBegin")
    if code not in (200, 204):
        print(f"[Republish] publishBegin failed — HTTP {code}")
        print(f"[Republish] Response: {raw[:500]}")
        return False

    print("[Republish] publishBegin OK — polling...")
    return poll_publish("Republish")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BASE_URL or not USERNAME or not PASSWORD:
        print("Error: ACUMATICA_SANDBOX_URL, ACUMATICA_SANDBOX_USERNAME, ACUMATICA_SANDBOX_PASSWORD required")
        sys.exit(1)

    print(f"Target: {BASE_URL} (sandbox)")
    print(f"Tenant: {TENANT}")
    print(f"Republish after: {REPUBLISH or '(none)'}")

    login()

    try:
        # Step 1: Unpublish all
        ok = unpublish_all()
        if not ok:
            print("\nUnpublish failed. The orphaned metadata may be blocking even unpublish.")
            print("Fallback: try publishing with cleanup via the UI (SM204505 > Publish > With Cleanup)")
            sys.exit(1)

        # Step 2: Republish if requested
        if REPUBLISH:
            projects = [p.strip() for p in REPUBLISH.split(",") if p.strip()]
            if projects:
                # Give the app pool time to restart after unpublish
                print("\n[Wait] Giving app pool 15s to stabilize after unpublish...")
                time.sleep(15)

                # Re-login (app pool restart invalidates session)
                login()

                ok = republish(projects)
                if not ok:
                    print("\nRepublish failed. Projects may need manual publish via SM204505.")
                    sys.exit(1)

        print("\nDone!")

    finally:
        logout()


if __name__ == "__main__":
    main()
