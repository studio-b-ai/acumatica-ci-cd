#!/usr/bin/env python3
"""
Create the ContainerTracking Web Service Endpoint in Acumatica via SM208030 SOAP Screen API.

This script creates a custom REST endpoint at /entity/ContainerTracking/24.200.001/
with three entities: UsrContainer, UsrContainerEvent, UsrContainerPOLink.

The webhook-router container tracking worker requires this endpoint to CRUD container data.

Usage:
    # Schema discovery (safe — read-only):
    ACUMATICA_URL=... ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... \
        python3 create-container-endpoint.py --schema

    # Create endpoint (writes to Acumatica):
    ACUMATICA_URL=... ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... \
        python3 create-container-endpoint.py --create

    # Dry run (prints SOAP XML without sending):
    python3 create-container-endpoint.py --dry-run
"""

import os
import sys
import re
import urllib.request
import urllib.error
import http.cookiejar

BASE_URL    = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME    = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD    = os.environ.get("ACUMATICA_PASSWORD", "")
COMPANY     = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

SOAP_URL = f"{BASE_URL}/Soap/SM208030.asmx"

# ── SOAP helpers ─────────────────────────────────────────────────────────────

NS = "http://www.acumatica.com/typed/"
ENVELOPE_OPEN  = f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body>'
ENVELOPE_CLOSE = "</soap:Body></soap:Envelope>"


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
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password></tns:Login>"
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


# ── GetSchema ─────────────────────────────────────────────────────────────

def get_schema(jar):
    body = "<tns:GetSchema/>"
    xml = soap_request(jar, "GetSchema", body, "GetSchema")
    check_fault(xml, "GetSchema")
    return xml


def print_schema(xml):
    """Extract and print Container->Field hierarchy from SM208030 schema."""
    print(f"\n=== SM208030 Schema (Web Service Endpoints) ===")
    print(f"SOAP URL: {SOAP_URL}")

    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", xml, re.DOTALL)
    if not schema_match:
        print("  Could not find GetSchemaResult in response")
        print(f"  Response length: {len(xml)}")
        print(f"  Response preview: {xml[:500]}")
        return

    schema = schema_match.group(1)

    # Print ObjectName values (view names)
    objects = re.findall(r"<ObjectName>(.*?)</ObjectName>", schema)
    print(f"\nObjectName values ({len(set(objects))} unique):")
    for o in sorted(set(objects)):
        print(f"  {o}")

    # Print Field->ObjectName pairs
    fields = re.findall(
        r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>",
        schema, re.DOTALL
    )
    if fields:
        print(f"\nField->ObjectName pairs ({len(fields)} fields):")
        for fname, oname in fields[:120]:
            print(f"  {oname}.{fname}")
    else:
        field_names = re.findall(r"<FieldName>(.*?)</FieldName>", schema)
        print(f"\nField names ({len(field_names)}):")
        for f in field_names[:120]:
            print(f"  {f}")

    # Container names
    containers = re.findall(r"<Container>.*?<Name>(.*?)</Name>", schema, re.DOTALL)
    if containers:
        print(f"\nContainer names:")
        for c in sorted(set(containers)):
            print(f"  {c}")

    # Raw dump for debugging
    print(f"\n--- Raw Schema XML (first 12000 chars) ---")
    print(schema[:12000])
    print("--- End Raw ---")
    print("=== End Schema ===\n")


# ── SOAP Commands ─────────────────────────────────────────────────────────

def cmd(field, value, obj=None, commit=False):
    """Build a <tns:Command> element."""
    parts = [f"<tns:FieldName>{field}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{obj}</tns:ObjectName>")
    if value is not None:
        parts.append(f"<tns:Value>{value}</tns:Value>")
    if commit:
        parts.append("<tns:Commit>true</tns:Commit>")
    return f"<tns:Command>{''.join(parts)}</tns:Command>"


def action_cmd(field, obj=None):
    return cmd(field, None, obj)


def build_submit(commands):
    inner = "".join(commands)
    return f"<tns:Submit><tns:commands>{inner}</tns:commands></tns:Submit>"


# ── Endpoint Definition ──────────────────────────────────────────────────
# NOTE: The exact field/object names depend on GetSchema output from SM208030.
# This section will be populated after running --schema to discover the field map.
#
# Expected endpoint structure:
#   Endpoint Name:    ContainerTracking
#   Endpoint Version: 24.200.001
#   System Endpoint:  Default (extend from)
#
# Entities to create:
#   1. UsrContainer (top-level)
#      - Graph: StudioB.Containers.ContainerMaint
#      - View: Container
#      - Fields: ContainerCD, CarrierCode, BookingRef, BillOfLading, VesselName,
#                VesselIMO, VoyageNbr, PortOfLoading, PortOfDischarge, ETD, ATD,
#                ETA, ATA, Status, ContainerType, SealNbr, LastEventCode,
#                LastEventDate, LastSyncDate
#      - Sub-entities: Events, POLinks
#
#   2. UsrContainerEvent (sub-entity of UsrContainer, or top-level)
#      - View: Events
#      - Fields: CarrierEventCode, NormalizedEventCode, EventDateTime,
#                EventClassifier, LocationName, LocationCode, VesselName,
#                Description
#
#   3. UsrContainerPOLink (sub-entity of UsrContainer, or top-level)
#      - View: POLinks
#      - Fields: OrderType, OrderNbr, LineNbr


def create_endpoint(jar, schema_xml):
    """
    Create the ContainerTracking endpoint.

    This function must be updated after running --schema to discover
    the exact field names used by SM208030's SOAP interface.

    The SM208030 screen has a header (endpoint name/version) and detail grids
    for entities and their field mappings. The SOAP commands need to:
    1. Set endpoint name = "ContainerTracking"
    2. Set version = "24.200.001"
    3. Add each entity mapping
    4. Save
    """
    # First, parse the schema to discover field names
    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", schema_xml, re.DOTALL)
    if not schema_match:
        print("[ERROR] Cannot parse schema — run --schema first to inspect field names")
        return False

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

    print(f"\n[Schema] Found {len(field_map)} views with fields:")
    for view, flds in sorted(field_map.items()):
        print(f"  {view}: {', '.join(flds[:10])}{'...' if len(flds) > 10 else ''}")

    # Look for the header view (endpoint name/version fields)
    # Common patterns: "Endpoint", "EndpointSummary", "ServiceEndpoint"
    header_candidates = [v for v in field_map.keys()
                        if any(k in v.lower() for k in ["endpoint", "header", "summary"])]

    if not header_candidates:
        print("\n[WARN] Could not auto-detect header view. Available views:")
        for v in sorted(field_map.keys()):
            print(f"  {v}: {field_map[v]}")
        print("\n[ACTION] Review the schema output above and update this script's")
        print("         create_endpoint() function with the correct field names.")
        print("         Then re-run with --create.")
        return False

    print(f"\n[Auto-detect] Header view candidates: {header_candidates}")
    print("[ACTION] Review schema output and run --create after confirming field names.")
    return False


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("--schema", "--create", "--dry-run"):
        print("Usage: python3 create-container-endpoint.py [--schema|--create|--dry-run]")
        print()
        print("  --schema    Discover SM208030 field map (read-only, safe)")
        print("  --create    Create the ContainerTracking endpoint")
        print("  --dry-run   Print what would be done without executing")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "--dry-run":
        print("[DRY RUN] Would create ContainerTracking endpoint at:")
        print(f"  {BASE_URL}/entity/ContainerTracking/24.200.001/")
        print()
        print("Entities:")
        print("  UsrContainer      — 19 fields, header entity")
        print("  UsrContainerEvent — 8 fields, sub-entity (Events)")
        print("  UsrContainerPOLink — 3 fields, sub-entity (POLinks)")
        print()
        print("Graph: StudioB.Containers.ContainerMaint")
        print()
        print("Run --schema first to discover SM208030 field names,")
        print("then --create to execute.")
        return

    if not USERNAME or not PASSWORD:
        print("[ERROR] Set ACUMATICA_USERNAME and ACUMATICA_PASSWORD env vars")
        sys.exit(1)

    jar = login()
    try:
        if mode == "--schema":
            schema_xml = get_schema(jar)
            print_schema(schema_xml)
            # Save raw schema for offline analysis
            with open("sm208030-schema.xml", "w") as f:
                f.write(schema_xml)
            print(f"\n[Saved] Raw schema written to sm208030-schema.xml")

        elif mode == "--create":
            schema_xml = get_schema(jar)
            success = create_endpoint(jar, schema_xml)
            if success:
                print("\n[SUCCESS] ContainerTracking endpoint created.")
                print(f"  Verify: GET {BASE_URL}/entity/ContainerTracking/24.200.001/UsrContainer")
            else:
                print("\n[INFO] Endpoint creation requires schema analysis first.")
                print("  Run --schema, review output, update script, then --create.")
    finally:
        logout(jar)


if __name__ == "__main__":
    main()
