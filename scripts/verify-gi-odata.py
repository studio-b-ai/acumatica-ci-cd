#!/usr/bin/env python3
"""Post-deploy GI OData verification.

Checks all expected Generic Inquiries are accessible via OData after
a customization publish. Acumatica's no-merge publish mode can silently
deregister GI OData endpoints — this script detects that and provides
specific remediation steps.

Usage:
    python3 scripts/verify-gi-odata.py

Environment variables:
    ACUMATICA_URL       - Instance URL (e.g. https://heritagefabrics.acumatica.com)
    ACUMATICA_USERNAME  - API user
    ACUMATICA_PASSWORD  - API password
    ACUMATICA_TENANT    - Tenant name (e.g. "Heritage Fabrics")
    SLACK_WEBHOOK_URL   - (optional) Slack incoming webhook for alerts

Exit codes:
    0 - All GIs healthy
    1 - One or more GIs failed (alerts sent)
"""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
import ssl

# ── GI Registry ──────────────────────────────────────────────────────────
# All GIs that MUST be accessible via OData after deploy.
# Format: (name, screen_id, description)
EXPECTED_GIS = [
    ("DRP_VelocityHistory",        "SB401080", "Shipment history for demand forecasting"),
    ("DRP_OpenSOCommitments",      "SB401090", "Open SO lines for net requirements"),
    ("DRP_InventoryBySite",        "SB401110", "Current inventory snapshot"),
    ("DRP_OpenPOLines",            "SB401100", "Open PO lines for supply pipeline"),
    ("DRP_ItemWarehouseSettings",  "SB401120", "Replenishment params (ROP, safety stock, lead time)"),
]


def check_gi(base_url: str, tenant: str, gi_name: str, auth_header: str) -> tuple[int, str]:
    """Check a single GI via OData. Returns (status_code, detail)."""
    tenant_path = f"/t/{urllib.parse.quote(tenant)}" if tenant else ""
    url = f"{base_url}{tenant_path}/api/odata/gi/{urllib.parse.quote(gi_name)}?$top=1"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={
        "Authorization": auth_header,
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            row_count = len(data.get("value", []))
            return resp.status, f"{row_count} rows"
    except urllib.error.HTTPError as e:
        return e.code, e.reason
    except Exception as e:
        return 0, str(e)[:200]


def post_slack(webhook_url: str, text: str) -> None:
    """Post alert to Slack."""
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Slack alert failed: {e}", file=sys.stderr)


def main():
    base_url = os.environ.get("ACUMATICA_URL", "").rstrip("/")
    username = os.environ.get("ACUMATICA_USERNAME", "")
    password = os.environ.get("ACUMATICA_PASSWORD", "")
    tenant = os.environ.get("ACUMATICA_TENANT", "")
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")

    if not base_url or not username or not password:
        print("ERROR: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD required")
        sys.exit(1)

    auth_header = f"Basic {base64.b64encode(f'{username}:{password}'.encode()).decode()}"

    print(f"Verifying {len(EXPECTED_GIS)} GIs via OData...")
    print(f"  Instance: {base_url}")
    print(f"  Tenant:   {tenant or '(default)'}")
    print()

    failures = []
    for gi_name, screen_id, description in EXPECTED_GIS:
        status, detail = check_gi(base_url, tenant, gi_name, auth_header)

        if status == 200:
            print(f"  ✅ {gi_name} ({screen_id}): {detail}")
        elif status == 404:
            print(f"  ❌ {gi_name} ({screen_id}): 404 — NOT REGISTERED in OData")
            failures.append((gi_name, screen_id, 404, "OData not registered"))
        elif status == 403:
            print(f"  ❌ {gi_name} ({screen_id}): 403 — api-bot lacks screen access")
            failures.append((gi_name, screen_id, 403, "Screen access missing"))
        else:
            print(f"  ⚠️  {gi_name} ({screen_id}): HTTP {status} — {detail}")
            failures.append((gi_name, screen_id, status, detail))

    print()

    if not failures:
        print("All GIs healthy ✅")
        return 0

    # Build remediation message
    lines_404 = [f for f in failures if f[2] == 404]
    lines_403 = [f for f in failures if f[2] == 403]
    lines_other = [f for f in failures if f[2] not in (403, 404)]

    msg_parts = [f"⚠️ *Post-Deploy GI OData Verification — {len(failures)} failure(s)*\n"]

    if lines_404:
        msg_parts.append("*404 — OData not registered* (fix: SM208000 → load GI → Unpublish → Publish to UI)")
        for name, sid, _, _ in lines_404:
            msg_parts.append(f"  • `{name}` (Screen ID: `{sid}`)")

    if lines_403:
        msg_parts.append("\n*403 — api-bot screen access missing* (fix: SM201010 → api-bot role → add Screen ID)")
        for name, sid, _, _ in lines_403:
            msg_parts.append(f"  • `{name}` (Screen ID: `{sid}`)")

    if lines_other:
        msg_parts.append("\n*Other errors:*")
        for name, sid, code, detail in lines_other:
            msg_parts.append(f"  • `{name}` ({sid}): HTTP {code} — {detail}")

    msg_parts.append(
        "\n_Root cause: `isMergeWithExistingPackages=false` doesn't re-register GI OData. "
        "Permanent fix: Acumatica support cleans orphan IIG metadata → switch to merge=true._"
    )

    alert_text = "\n".join(msg_parts)
    print(alert_text)

    # Set GitHub Actions annotation
    for name, sid, code, detail in failures:
        print(f"::warning::GI {name} ({sid}): HTTP {code} — {detail}")

    # Send Slack alert
    if slack_url:
        post_slack(slack_url, alert_text)
        print("\nSlack alert sent.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
