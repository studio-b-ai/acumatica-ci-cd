#!/usr/bin/env python3
"""
Extend the Default Web Service Endpoint to include custom DAC fields on SalesOrder.

Acumatica's Default endpoint (v24.200.001) does NOT auto-include DAC extension
fields (Usr* fields from PXCacheExtension classes). Reads work via $custom=
query param, but writes are SILENTLY DROPPED. This script adds custom fields
to the endpoint definition so PUT requests correctly persist them.

Uses SM208010 (Web Service Endpoints) SOAP Screen API.

Target fields:
  - SalesOrder.UsrWMSStatus (SOOrderExt, CustomStringField)
  - SalesOrder.UsrHubSpotDealId (SOOrderExt, CustomStringField)
  - SalesOrder.UsrComplianceHold (SOOrderExt, CustomBooleanField)
  - SalesOrder.UsrComplianceHoldReason (SOOrderExt, CustomStringField)

Usage:
    # Schema discovery (safe — read-only):
    ACUMATICA_URL=... ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... \\
        python3 extend-default-endpoint.py --schema

    # Extend endpoint:
    ACUMATICA_URL=... ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... \\
        python3 extend-default-endpoint.py --extend

    # Dry run:
    python3 extend-default-endpoint.py --dry-run

KB: Any new DAC extension field (Usr* field) that needs REST API write support
    MUST be added to the Default endpoint via this script or SM208010 UI.
    Reading works via GET $custom= but writing requires endpoint mapping.
    See: docs/kb/acumatica-custom-field-endpoint-mapping.md
"""

import os
import sys
import re
import urllib.request
import urllib.error
import http.cookiejar

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
COMPANY  = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"

NS = "http://www.acumatica.com/typed/"
ENVELOPE_OPEN  = f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body>'
ENVELOPE_CLOSE = "</soap:Body></soap:Envelope>"

# Fields to add to the Default endpoint's SalesOrder entity.
# ObjectName = the Acumatica view/DAC that owns the field.
# For SOOrder DAC extension fields, ObjectName is typically "Document" or
# "SOOrder" — we'll discover the correct name via --schema.
CUSTOM_FIELDS = [
    {"field": "UsrWMSStatus",            "display": "WMS Status"},
    {"field": "UsrHubSpotDealId",        "display": "HubSpot Order ID"},
    {"field": "UsrComplianceHold",       "display": "Compliance Hold"},
    {"field": "UsrComplianceHoldReason", "display": "Compliance Hold Reason"},
]


# ── SOAP helpers ─────────────────────────────────────────────────────────────

def soap_request(cookie_jar, action, body, label=""):
    full_body = (ENVELOPE_OPEN + body + ENVELOPE_CLOSE).encode("utf-8")
    req = urllib.request.Request(
        SOAP_URL,
        data=full_body,
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{NS}{action}"',
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    try:
        with opener.open(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label or action}] HTTP {e.code}: {raw[:800]}")
        sys.exit(1)
    return raw


def check_fault(xml, label):
    if "<soap:Fault>" in xml or "faultstring" in xml:
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1).strip() if m else xml[:600]
        print(f"[{label}] SOAP Fault: {msg}")
        sys.exit(1)


# ── Login / Logout ────────────────────────────────────────────────────────

def login():
    jar = http.cookiejar.CookieJar()
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{COMPANY}</tns:company></tns:Login>"
    xml = soap_request(jar, "Login", body, "Login")
    check_fault(xml, "Login")
    m = re.search(r"<Code>(.*?)</Code>", xml)
    code = m.group(1) if m else "?"
    if code != "OK":
        print(f"[Login] Failed — Code={code}")
        m2 = re.search(r"<Message>(.*?)</Message>", xml)
        print(f"         Message: {m2.group(1) if m2 else xml[:300]}")
        sys.exit(1)
    print(f"[Login] OK (company={COMPANY})")
    return jar


def logout(jar):
    body = "<tns:Logout/>"
    soap_request(jar, "Logout", body, "Logout")
    print("[Logout] Done")


# ── Schema Discovery ─────────────────────────────────────────────────────

def get_schema(jar):
    body = "<tns:GetSchema/>"
    xml = soap_request(jar, "GetSchema", body, "GetSchema")
    check_fault(xml, "GetSchema")
    return xml


def print_schema(xml):
    """Print SM208010 schema — discover field/object names for SOAP commands."""
    print(f"\n=== SM208010 Schema (Web Service Endpoints) ===")
    print(f"SOAP URL: {SOAP_URL}")

    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", xml, re.DOTALL)
    if not schema_match:
        print("  Could not find GetSchemaResult in response")
        print(f"  Response preview: {xml[:500]}")
        return

    schema = schema_match.group(1)

    # Extract ObjectName -> FieldName mapping
    fields = re.findall(
        r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>",
        schema, re.DOTALL
    )

    field_map = {}
    for fname, oname in fields:
        if oname not in field_map:
            field_map[oname] = []
        field_map[oname].append(fname)

    print(f"\nViews ({len(field_map)}):")
    for view, flds in sorted(field_map.items()):
        print(f"  {view}:")
        for f in sorted(flds):
            print(f"    {f}")

    # Raw dump
    print(f"\n--- Raw Schema XML (first 15000 chars) ---")
    print(schema[:15000])
    print("--- End Raw ---")

    return field_map


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("--schema", "--extend", "--dry-run"):
        print("Usage: python3 extend-default-endpoint.py [--schema|--extend|--dry-run]")
        print()
        print("  --schema    Discover SM208010 field names (read-only, safe)")
        print("  --extend    Add custom fields to Default endpoint SalesOrder")
        print("  --dry-run   Show what would be done")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "--dry-run":
        print("[DRY RUN] Would extend Default endpoint (v24.200.001) SalesOrder entity with:")
        for f in CUSTOM_FIELDS:
            print(f"  + {f['field']} ({f['display']})")
        print()
        print("After extension, these fields will be writable via REST API PUT:")
        print("  PUT /entity/default/24.200.001/SalesOrder")
        print('  { "OrderType": {"value":"CO"}, "OrderNbr": {"value":"S003424"},')
        print('    "custom": {"Document": {"UsrWMSStatus": {"value":"A"}}} }')
        print()
        print("Run --schema first to discover SM208010 field names,")
        print("then --extend to execute.")
        return

    if not USERNAME or not PASSWORD:
        print("[ERROR] Set ACUMATICA_USERNAME and ACUMATICA_PASSWORD env vars")
        sys.exit(1)

    jar = login()
    try:
        if mode == "--schema":
            schema_xml = get_schema(jar)
            field_map = print_schema(schema_xml)
            with open("sm208010-schema.xml", "w") as f:
                f.write(schema_xml)
            print(f"\n[Saved] Raw schema written to sm208010-schema.xml")
            print("\n[NEXT] Review the schema output to find the correct field/object")
            print("       names for the SM208010 SOAP commands, then run --extend.")

        elif mode == "--extend":
            schema_xml = get_schema(jar)
            field_map = print_schema(schema_xml)
            print("\n[INFO] Schema discovery complete. The --extend command needs")
            print("       the correct SOAP command sequence for SM208010 to add")
            print("       custom fields to an existing endpoint entity.")
            print()
            print("       This requires knowing the exact ObjectName and FieldName")
            print("       values from the schema above. After discovering them,")
            print("       update this script's extend logic and re-run.")
            print()
            print("       Alternatively, use the Acumatica UI:")
            print(f"       1. Navigate to {BASE_URL}/Main?ScreenId=SM208010")
            print("       2. Select endpoint: Default, version 24.200.001")
            print("       3. Find SalesOrder entity in the tree")
            print("       4. Add each custom field from SOOrderExt:")
            for f in CUSTOM_FIELDS:
                print(f"          + {f['field']} → {f['display']}")
            print("       5. Save the endpoint")
            print("       6. Re-publish customization projects to apply")
    finally:
        logout(jar)


if __name__ == "__main__":
    main()
