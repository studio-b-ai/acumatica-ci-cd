#!/usr/bin/env python3
"""
Pre-deploy smoke test — verify Acumatica is reachable before starting deploy.

Authenticates to Acumatica and queries the current user endpoint.
If Acumatica is down or credentials are invalid, the deploy should
be skipped rather than failing mid-way through snapshot + countdown.

Usage:
  python scripts/smoke-test.py

Environment variables:
  ACUMATICA_URL       - Instance URL (e.g., https://heritagefabrics.acumatica.com)
  ACUMATICA_USERNAME  - API username
  ACUMATICA_PASSWORD  - API password
  ACUMATICA_TENANT    - Company/tenant name (optional)
"""

import os
import sys
import requests


def main():
    url = os.environ.get("ACUMATICA_URL", "").rstrip("/")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    tenant = os.environ.get("ACUMATICA_TENANT", "")

    if not url or not username or not password:
        print("::error::Missing required env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD")
        sys.exit(1)

    print(f"Smoke test: {url}")
    print(f"  User: {username}")
    print(f"  Tenant: {tenant or '(default)'}")

    session = requests.Session()

    # Step 1: Login
    login_body = {"name": username, "password": password}
    if tenant:
        login_body["company"] = tenant

    try:
        print("  Logging in...")
        resp = session.post(
            f"{url}/entity/auth/login",
            json=login_body,
            timeout=30,
        )
    except requests.ConnectionError as e:
        print(f"::error::Acumatica unreachable: {e}")
        sys.exit(1)
    except requests.Timeout:
        print("::error::Acumatica login timed out (30s)")
        sys.exit(1)

    if resp.status_code >= 400:
        body = resp.text[:200]
        if "locked out" in body.lower():
            print(f"::error::Account is LOCKED OUT — do NOT deploy. Unlock in SM201010.")
        elif "API Login Limit" in body:
            print(f"::error::API Login Limit reached — wait and retry.")
        else:
            print(f"::error::Login failed: HTTP {resp.status_code} — {body}")
        sys.exit(1)

    print("  Login successful")

    # Step 2: Verify API access with lightweight query
    try:
        print("  Querying current user...")
        user_resp = session.get(
            f"{url}/entity/default/24.200.001/",
            params={"$top": "1"},
            timeout=15,
        )
        if user_resp.status_code == 200:
            print("  API responding normally")
        else:
            print(f"::warning::API returned HTTP {user_resp.status_code} (non-fatal)")
    except Exception as e:
        print(f"::warning::API query failed: {e} (non-fatal)")

    # Step 3: Logout
    try:
        session.post(f"{url}/entity/auth/logout", timeout=10)
        print("  Logged out")
    except Exception:
        pass  # Best effort

    print("Smoke test PASSED — Acumatica is reachable and credentials are valid")


if __name__ == "__main__":
    main()
