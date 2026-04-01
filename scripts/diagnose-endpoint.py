#!/usr/bin/env python3
"""Diagnose ContainerTracking endpoint — check all possible entity names via REST."""
import os, sys, requests

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
TENANT   = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

ENDPOINT_NAME    = "ContainerTracking"
ENDPOINT_VERSION = "24.200.001"

CANDIDATES = [
    "Container",
    "ContainerEvent",
    "ContainerPOLink",
    "UsrContainer",
    "UsrContainerEvent",
    "UsrContainerPOLink",
]

session = requests.Session()
r = session.post(
    f"{BASE_URL}/entity/auth/login",
    json={"name": USERNAME, "password": PASSWORD, "company": TENANT}
)
if r.status_code != 204:
    print(f"REST login failed: {r.status_code} — {r.text[:200]}")
    sys.exit(1)
print(f"Logged in as {USERNAME}")

print(f"\n=== ContainerTracking {ENDPOINT_VERSION} entity probe ===")
for entity in CANDIDATES:
    url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/{entity}"
    resp = session.get(url, params={"$top": "1"})
    icon = "OK" if resp.status_code == 200 else f"HTTP {resp.status_code}"
    try:
        msg = resp.json().get("message", "") if resp.status_code != 200 else f"{len(resp.json())} records"
    except:
        msg = resp.text[:100]
    print(f"  {icon}: {entity} — {msg}")

session.post(f"{BASE_URL}/entity/auth/logout")
print("\nDone.")
