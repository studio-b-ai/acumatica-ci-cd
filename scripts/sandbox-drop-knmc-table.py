#!/usr/bin/env python3
"""
Drop KNMCSalesPriceSyncData from sandbox via Customization API.

Strategy:
1. Import drop-table-package.zip as a customization project
2. Publish with isOnlyDbUpdates=true (skips CleanUpDatabase — avoids NullRef)
3. SQL in the package runs DROP TABLE

SAFETY: Only connects to sandbox (URL must contain 'sandbox').
"""

import os
import sys
import urllib.request
import urllib.error
import http.cookiejar
import json
import time
import base64

BASE_URL  = os.environ.get("ACUMATICA_SANDBOX_URL", "")
USERNAME  = os.environ.get("ACUMATICA_SANDBOX_USERNAME", "")
PASSWORD  = os.environ.get("ACUMATICA_SANDBOX_PASSWORD", "")
TENANT    = os.environ.get("ACUMATICA_SANDBOX_TENANT", "")
PACKAGE   = os.environ.get("PACKAGE_PATH", "drop-table-package.zip")
PROJECT   = "StudioBAcuOps"
POLL_INTERVAL = 10
POLL_TIMEOUT  = 600

if BASE_URL and "sandbox" not in BASE_URL.lower():
    print(f"SAFETY: URL does not contain 'sandbox': {BASE_URL}")
    sys.exit(1)

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def api_request(method, path, body=None, label="", content_type="application/json"):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body and isinstance(body, (dict, list)) else body
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Content-Type": content_type,
    })
    try:
        with opener.open(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label}] HTTP {e.code}: {raw[:500]}")
        return e.code, raw


def login():
    body = {"name": USERNAME, "password": PASSWORD}
    if TENANT:
        body["tenant"] = TENANT
    code, raw = api_request("POST", "/entity/auth/login", body, "Login")
    if code not in (200, 204):
        print(f"[Login] Failed — HTTP {code}")
        sys.exit(1)
    print(f"[Login] OK")


def logout():
    api_request("POST", "/entity/auth/logout", label="Logout")
    print("[Logout] Done")


def import_package():
    """Import the .zip package via Customization API, replacing StudioBAcuOps."""
    if not os.path.exists(PACKAGE):
        print(f"[Import] Package not found: {PACKAGE}")
        sys.exit(1)

    with open(PACKAGE, "rb") as f:
        pkg_bytes = f.read()

    pkg_b64 = base64.b64encode(pkg_bytes).decode("ascii")
    print(f"[Import] Uploading {PACKAGE} ({len(pkg_bytes)} bytes) as {PROJECT}")

    body = {
        "projectName": PROJECT,
        "projectDescription": "StudioBAcuOps + DROP KNMCSalesPriceSyncData",
        "projectLevel": 1,
        "isReplaceIfExists": True,
        "projectContent": pkg_b64
    }

    code, raw = api_request("POST", "/CustomizationApi/import", body, "Import")
    if code in (200, 204):
        print(f"[Import] Success")
        return True
    else:
        print(f"[Import] Failed — HTTP {code}")
        print(f"[Import] Response: {raw[:500]}")
        return False


def publish_db_only():
    """Publish with isOnlyDbUpdates=true to run SQL without CleanUpDatabase."""
    print(f"[Publish] Starting dbOnly publish for {PROJECT}...")

    body = {
        "isMergeWithExistingPackages": True,
        "isOnlyValidation": False,
        "isOnlyDbUpdates": True,
        "projectNames": [PROJECT],
        "tenantMode": "Current"
    }

    code, raw = api_request("POST", "/CustomizationApi/publishBegin", body, "PublishBegin")
    if code not in (200, 204):
        print(f"[Publish] publishBegin failed — HTTP {code}")
        print(f"[Publish] Response: {raw[:500]}")
        return False

    print("[Publish] publishBegin OK — polling...")

    elapsed = 0
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        code, raw = api_request("POST", "/CustomizationApi/publishEnd", {}, "PublishPoll")

        if code in (200, 400):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    if data.get("isFailed"):
                        log_entries = data.get("log", [])
                        print(f"[Publish] FAILED after {elapsed}s")
                        for entry in log_entries[-20:]:
                            ts = entry.get("timestamp", "")
                            msg = entry.get("message", "")
                            print(f"  {ts} {msg}")
                        return False
                    if data.get("isCompleted"):
                        log_entries = data.get("log", [])
                        print(f"[Publish] Completed successfully ({elapsed}s)")
                        for entry in log_entries:
                            ts = entry.get("timestamp", "")
                            msg = entry.get("message", "")
                            if "sql" in msg.lower() or "drop" in msg.lower() or "knmc" in msg.lower():
                                print(f"  {ts} {msg}")
                        return True
            except json.JSONDecodeError:
                if raw.strip().lower() == "false":
                    print(f"  Still publishing... ({elapsed}s)")
                    continue
                elif raw.strip().lower() == "true":
                    print(f"[Publish] Completed ({elapsed}s)")
                    return True

        print(f"  Still processing... ({elapsed}s)")

    print(f"[Publish] Timed out after {POLL_TIMEOUT}s")
    return False


def main():
    if not BASE_URL or not USERNAME or not PASSWORD:
        print("Error: ACUMATICA_SANDBOX_* env vars required")
        sys.exit(1)

    print(f"Target: {BASE_URL}")
    print(f"Package: {PACKAGE}")
    print(f"Project: {PROJECT}")

    login()

    try:
        # Step 1: Import the drop-table package
        if not import_package():
            sys.exit(1)

        # Step 2: Publish with dbOnly
        if not publish_db_only():
            sys.exit(1)

        print("\nKNMCSalesPriceSyncData should now be dropped from sandbox.")
        print("You can now try a normal publish of your customization projects.")

    finally:
        logout()


if __name__ == "__main__":
    main()
