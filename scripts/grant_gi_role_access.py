#!/usr/bin/env python3
"""
Grant role access to OData-exposed GIs whose <RolesInGraph> blocks
were skipped by Acumatica's "already applied" tracking.

DISCOVERY SCRIPT — documents the SOAP investigation that led to the
C# CustomizationPlugin SQL grant approach (the only path that works
for this case on Acumatica 24.200.001 cloud).

Symptom:
    GI shows in /OData/{Tenant}/ catalog listing but probe returns 403.
    Cause: <GenericInquiryScreen> block was tracked as "already applied"
    and the embedded <SiteMap>/<row>/<RolesInGraph> never attached to
    the GI's NodeID. No RoleAccess rows exist for the GI's screen ID.

Probe command (sandbox):
    curl -o /dev/null -w "%{http_code}" \\
        -H "Authorization: Basic $(printf 'api-bot:PASSWORD' | base64)" \\
        "https://heritagefabrics-sandbox.acumatica.com/OData/Heritage%20Fabrics/DRP_ItemWarehouseSettings?\$top=1"
    Expected before fix: 403
    Expected after fix:  200

WHAT DOES NOT WORK (verified on heritagefabrics-sandbox.acumatica.com,
2026-04-17, Acumatica 24.200.001):

1. SOAP SM208000 publishToUI dialog
   - WSDL exposes /Soap/SM208000.asmx
   - Login + GetSchema work fine (api-bot, ~0.5s)
   - Submit with xsi:type="tns:Key" + Cancel pattern is IGNORED — the
     "Designs" view returns the full paginated GI list (~681 records,
     323KB) regardless of the key value sent. Tested with both stuck
     GIs and known-working GIs (e.g. ARCustomerSummary).
   - publishToUI action returns SOAP fault:
     "PX.Data.PXActionDisabledException: Error: The Publish to the UI
     button is disabled."  (because no record is loaded into the
     screen state).
   - Schema response contains 34 ObjectNames but PublishToTheUIAccessRights
     view (per WSDL Content schema) never appears in runtime — only
     PublishToUIDialog and PublishToUIDialog: 1 are exposed, and only
     after the dialog opens (which never happens because of the disabled
     publishToUI button).
   - No "SetVisibleForAllRoles" or equivalent action exists on the
     Designs view actions enum (see schema dump for full action list).
   - Confirms 2026-03-29 spike doc finding (gi-api-spike.md):
     "SM208000 uses ASP.NET WebForms postbacks, not SOAP — Screen-Based
     SOAP API does not drive the GI designer."

2. SOAP SM201020 (Access Rights by Screen)
   - WSDL exposes EntitiesWithLeafs (tree) + EntityRoles (per-role grid)
   - Tree navigation requires ParameterNodeID/ParameterCacheName/
     ParameterMemberName service commands with values that are
     opaque to external callers (the cache name + node IDs are
     internal Acumatica state, not derivable from screen IDs).
   - Export on EntitiesWithLeafs returns 0 rows (tree views don't
     stream via Export), so even discovering the path is blocked.

3. SOAP SM206540 / SM206530 (was: Database Scripts)
   - On Acumatica 24.200.001 these screen IDs are now "Scanners" and
     "Scale" respectively (DeviceHub), not the SQL execution console
     that scripts/sandbox-exec-sql.py was originally written against.
   - SM205070 has Sql/SqlSummary views but it's the SQL trace/profiler,
     not an ad-hoc SQL executor.

4. REST entity catalog
   - GET /entity/Default/24.200.001/Role returns 404 ("Entity Role
     not found"). RoleAccess also 404. The default endpoint doesn't
     expose role-management entities.

WHAT DOES WORK:

5. C# CustomizationPlugin SQL via UpdateDatabase()
   - Direct INSERT into RoleAccess (one row per role × screen) inside
     the existing AesthetikContainersInstall plugin.
   - Idempotent (NOT EXISTS guard).
   - Allowed by validate-project.py (INSERT is not in the destructive
     SQL ban list — only DELETE/UPDATE/DROP/TRUNCATE require markers).
   - Side effect: requires a re-publish, which restarts the app pool.
     Per CLAUDE.md Rule #11, after-hours only on prod (5:30 PM -
     6:00 AM ET weekdays, anytime weekends).
   - Pattern: copy RoleAccess rows from a known-working sibling GI
     (e.g. SB401080 = DRP_VelocityHistory) to the broken target
     (SB401120 / SB401130). Same companies, same roles, same Rights=4.

USAGE:
    This script ONLY does pre-flight probes. The actual fix is in
    src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs
    method EnsureGIRoleAccess(). Run this script before AND after
    the deploy to confirm the 403 → 200 transition.

    SANDBOX (anytime):
        ACUMATICA_HOST=heritagefabrics-sandbox.acumatica.com \\
        ACUMATICA_USERNAME=api-bot \\
        ACUMATICA_PASSWORD='...' \\
        python3 scripts/grant_gi_role_access.py

    PROD (after-hours only, per Rule #11):
        ACUMATICA_HOST=heritagefabrics.acumatica.com \\
        ACUMATICA_USERNAME=api-bot \\
        ACUMATICA_PASSWORD='...' \\
        python3 scripts/grant_gi_role_access.py
"""

import base64
import os
import sys

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

# Stuck GIs from PR #462 (the 2 that landed in the OData catalog but
# returned 403 because <RolesInGraph> got skipped by Acumatica's
# "already applied" tracking on <GenericInquiryScreen> blocks).
STUCK_GIS = [
    ("DRP_ItemWarehouseSettings", "SB401120"),
    ("InventoryQuantityDetail",   "SB401130"),
]

HOST     = os.environ.get("ACUMATICA_HOST", "heritagefabrics-sandbox.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "api-bot")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
TENANT   = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

if not PASSWORD:
    print("ERROR: ACUMATICA_PASSWORD environment variable is required", file=sys.stderr)
    sys.exit(1)


def probe_odata(gi_name: str) -> int:
    """Probe an OData GI endpoint with HTTP Basic auth.

    Returns the HTTP status code. 200 = role access granted; 403 = no
    grant; 404 = GI not in catalog at all (different problem).
    """
    tenant_url = TENANT.replace(" ", "%20")
    url = f"https://{HOST}/OData/{tenant_url}/{gi_name}?$top=1"
    try:
        r = requests.get(url, auth=(USERNAME, PASSWORD), timeout=30)
        return r.status_code
    except Exception as e:
        print(f"  ERROR probing {gi_name}: {e}", file=sys.stderr)
        return -1


def main() -> int:
    print(f"Target: https://{HOST}/OData/{TENANT.replace(' ', '%20')}/")
    print(f"User:   {USERNAME}")
    print()

    any_403 = False
    for gi_name, screen_id in STUCK_GIS:
        code = probe_odata(gi_name)
        marker = "OK " if code == 200 else "FAIL"
        print(f"  [{marker}] {gi_name:35s} (screen {screen_id}): HTTP {code}")
        if code != 200:
            any_403 = True

    print()
    if any_403:
        print("STILL FAILING — re-deploy AesthetikContainers to apply EnsureGIRoleAccess")
        print("(see src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs)")
        return 1
    else:
        print("ALL PASS — role access granted.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
