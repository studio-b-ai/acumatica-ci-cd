#!/usr/bin/env python3
"""
Configure ContainerTracking REST endpoint fields via SOAP Screen API (SM207060).

After the SiteMap GraphType is set (by CustomizationPlugin during publish),
this script uses SOAP to navigate SM207060 and add field mappings for
UsrContainer, UsrContainerEvent, and UsrContainerPOLink entities.

Usage:
    python configure-container-endpoint.py --schema-only   # Discover SM207060 fields
    python configure-container-endpoint.py --configure      # Add field mappings
    python configure-container-endpoint.py --verify         # Check endpoint exists

Requires env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import os
import sys
import json
import requests
import xml.etree.ElementTree as ET

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", os.environ.get("ACUMATICA_PROD_USERNAME", ""))
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", os.environ.get("ACUMATICA_PROD_PASSWORD", ""))
TENANT = os.environ.get("ACUMATICA_TENANT", os.environ.get("ACUMATICA_PROD_TENANT", "Heritage Fabrics"))

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"
REST_LOGIN_URL = f"{BASE_URL}/entity/auth/login"
REST_LOGOUT_URL = f"{BASE_URL}/entity/auth/logout"

TNS = "http://www.acumatica.com/typed/"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

# Endpoint configuration
ENDPOINT_NAME = "ContainerTracking"
ENDPOINT_VERSION = "24.200.001"

# UsrContainer fields to map (field name -> display name)
USR_CONTAINER_FIELDS = [
    "ContainerCD", "CarrierCode", "BookingRef", "BillOfLading",
    "VesselName", "VesselIMO", "VoyageNbr",
    "PortOfLoading", "PortOfDischarge",
    "ETD", "ATD", "ETA", "ATA",
    "Status", "ContainerType", "SealNbr",
    "LastEventCode", "LastEventDate", "LastSyncDate",
    "NoteID", "CreatedDateTime", "LastModifiedDateTime",
]

USR_CONTAINER_EVENT_FIELDS = [
    "EventID", "ContainerID", "CarrierEventCode", "NormalizedEventCode",
    "EventDateTime", "EventClassifier", "LocationName", "LocationCode",
    "VesselName", "Description", "CreatedDateTime",
]

USR_CONTAINER_PO_LINK_FIELDS = [
    "LinkID", "ContainerID", "OrderType", "OrderNbr", "LineNbr",
]


def make_envelope(body_xml):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">
  <soap:Body>
    {body_xml}
  </soap:Body>
</soap:Envelope>"""


def soap_headers(action):
    return {
        "SOAPAction": f'"{TNS}{action}"',
        "Content-Type": "text/xml; charset=utf-8",
    }


def login_rest(session):
    """Login via REST API to get session cookie (shared with SOAP)."""
    resp = session.post(REST_LOGIN_URL, json={
        "name": USERNAME,
        "password": PASSWORD,
        "company": TENANT,
    })
    if resp.status_code != 204:
        print(f"REST Login failed: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)
    print(f"✓ Logged in as {USERNAME} to {TENANT}")


def logout_rest(session):
    """Logout via REST API."""
    session.post(REST_LOGOUT_URL)
    print("✓ Logged out")


def login_soap(session):
    """Login via SOAP API."""
    body = f"""<tns:Login>
      <tns:name>{USERNAME}</tns:name>
      <tns:password>{PASSWORD}</tns:password>
      <tns:company>{TENANT}</tns:company>
    </tns:Login>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Login"))
    if resp.status_code != 200:
        print(f"SOAP Login failed: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)
    print(f"✓ SOAP Logged in as {USERNAME}")


def logout_soap(session):
    """Logout via SOAP API."""
    body = "<tns:Logout/>"
    session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Logout"))
    print("✓ SOAP Logged out")


def get_schema(session):
    """Get SM207060 screen schema to discover field names."""
    body = "<tns:GetSchema/>"
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("GetSchema"))
    if resp.status_code != 200:
        print(f"GetSchema failed: {resp.status_code}")
        print(resp.text[:1000])
        return None
    return resp.text


def parse_and_print_schema(schema_xml):
    """Parse SOAP GetSchema response and print container/field hierarchy."""
    root = ET.fromstring(schema_xml)

    # Find GetSchemaResult element
    result = None
    for elem in root.iter():
        if elem.tag.endswith("GetSchemaResult"):
            result = elem
            break

    if result is None:
        print("Could not find GetSchemaResult in response")
        # Print raw XML for debugging
        print("\n--- Raw Response (first 3000 chars) ---")
        print(schema_xml[:3000])
        return

    def print_element(elem, indent=0):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        attrs = " ".join(f'{k}="{v}"' for k, v in elem.attrib.items())
        text = (elem.text or "").strip()
        prefix = "  " * indent
        line = f"{prefix}<{tag}"
        if attrs:
            line += f" {attrs}"
        if text:
            line += f"> {text}"
        else:
            line += ">"
        print(line)
        for child in elem:
            print_element(child, indent + 1)

    print("\n=== SM207060 Schema ===")
    print_element(result)


def verify_endpoint(session):
    """Check if ContainerTracking endpoint exists via REST API."""
    url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/UsrContainer"
    resp = session.get(url, params={""$top": "1"})
    print(f"\nEndpoint check: GET {url}")
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"✓ Endpoint working! Returned {len(data)} record(s)")
        if data:
            print(f"  Fields: {list(data[0].keys())[:10]}...")
    elif resp.status_code == 500:
        try:
            err = resp.json()
            print(f"✗ Error: {err.get('message', resp.text[:200])}")
        except Exception:
            print(f"✗ Error: {resp.text[:200]}")
    else:
        print(f"✗ Unexpected: {resp.text[:200]}")


def submit_commands(session, commands):
    """Submit SOAP commands to SM207060."""
    cmd_xml = ""
    for cmd in commands:
        cmd_xml += "      <tns:Command>\n"
        for key, val in cmd.items():
            cmd_xml += f"        <tns:{key}>{val}</tns:{key}>\n"
        cmd_xml += "      </tns:Command>\n"

    body = f"""<tns:Submit>
    <tns:commands>
{cmd_xml}    </tns:commands>
  </tns:Submit>"""

    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if resp.status_code != 200:
        print(f"Submit failed: {resp.status_code}")
        # Extract fault string
        try:
            fault_root = ET.fromstring(resp.text)
            for elem in fault_root.iter():
                if elem.tag.endswith("faultstring"):
                    print(f"  Fault: {elem.text}")
                    break
        except Exception:
            pass
        print(resp.text[:1000])
        return False
    return True


def main():
    if not USERNAME or not PASSWORD:
        print("ERROR: ACUMATICA_USERNAME and ACUMATICA_PASSWORD required")
        sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "--schema-only"

    session = requests.Session()

    try:
        if mode == "--schema-only":
            print(f"=== SM207060 Schema Discovery ===")
            print(f"URL: {SOAP_URL}")
            login_soap(session)
            schema = get_schema(session)
            if schema:
                parse_and_print_schema(schema)
                # Save raw schema for analysis
                with open("/tmp/sm207060-schema.xml", "w") as f:
                    f.write(schema)
                print(f"\nRaw schema saved to /tmp/sm207060-schema.xml")
            logout_soap(session)

        elif mode == "--verify":
            print(f"=== Verify ContainerTracking Endpoint ===")
            login_rest(session)
            verify_endpoint(session)
            logout_rest(session)

        elif mode == "--configure":
            print(f"=== Configure ContainerTracking Endpoint Fields ===")
            print(f"This will add field mappings to SM207060 via SOAP.")
            print(f"Endpoint: {ENDPOINT_NAME} {ENDPOINT_VERSION}")
            login_soap(session)

            # Step 1: Get schema to understand field names
            print("\nStep 1: Getting SM207060 schema...")
            schema = get_schema(session)
            if schema:
                with open("/tmp/sm207060-schema.xml", "w") as f:
                    f.write(schema)
                print("Schema saved. Proceeding with configuration...")

            # Step 2: Navigate to the endpoint
            # The exact commands depend on the schema field names.
            # This will be populated after schema discovery.
            print("\nStep 2: Navigate to ContainerTracking endpoint...")
            print("NOTE: Field names must be populated from schema discovery.")
            print("Run with --schema-only first, then update this script.")

            logout_soap(session)

        else:
            print(f"Unknown mode: {mode}")
            print("Usage: configure-container-endpoint.py [--schema-only|--configure|--verify]")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}")
        try:
            if mode.startswith("--schema") or mode == "--configure":
                logout_soap(session)
            else:
                logout_rest(session)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
