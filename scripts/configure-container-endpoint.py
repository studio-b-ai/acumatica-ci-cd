#!/usr/bin/env python3
"""
Configure ContainerTracking REST endpoint via SOAP Screen API.

Modes:
    --schema-only   Discover SM207060 fields
    --configure     Add field mappings (placeholder — fields auto-resolve from GraphType)
    --verify        Check endpoint exists and responds
    --grant-access  Grant API role access to SB501000 via SM201010

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

REST_LOGIN_URL = f"{BASE_URL}/entity/auth/login"
REST_LOGOUT_URL = f"{BASE_URL}/entity/auth/logout"

TNS = "http://www.acumatica.com/typed/"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

ENDPOINT_NAME = "ContainerTracking"
ENDPOINT_VERSION = "24.200.001"

# Roles that need access to SB501000 for REST API
TARGET_ROLES = ["Administrator", "API User"]


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
    resp = session.post(REST_LOGIN_URL, json={
        "name": USERNAME, "password": PASSWORD, "company": TENANT,
    })
    if resp.status_code != 204:
        print(f"REST Login failed: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)
    print(f"OK: REST Logged in")


def logout_rest(session):
    session.post(REST_LOGOUT_URL)
    print("OK: REST Logged out")


def login_soap(session, soap_url):
    body = f'<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>'
    resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("Login"))
    if resp.status_code != 200:
        print(f"SOAP Login failed: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)
    print(f"OK: SOAP Logged in")


def logout_soap(session, soap_url):
    body = "<tns:Logout/>"
    session.post(soap_url, data=make_envelope(body), headers=soap_headers("Logout"))
    print("OK: SOAP Logged out")


def get_schema(session, soap_url):
    body = "<tns:GetSchema/>"
    resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("GetSchema"))
    if resp.status_code != 200:
        print(f"GetSchema failed: {resp.status_code}")
        print(resp.text[:1000])
        return None
    return resp.text


def parse_and_print_schema(schema_xml):
    root = ET.fromstring(schema_xml)
    result = None
    for elem in root.iter():
        if elem.tag.endswith("GetSchemaResult"):
            result = elem
            break
    if result is None:
        print("Could not find GetSchemaResult")
        print(schema_xml[:3000])
        return

    def print_element(elem, indent=0):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        attrs = " ".join(f'{k}="{v}"' for k, v in elem.attrib.items())
        text = (elem.text or "").strip()
        prefix = "  " * indent
        line = f"{prefix}<{tag}"
        if attrs: line += f" {attrs}"
        if text: line += f"> {text}"
        else: line += ">"
        print(line)
        for child in elem:
            print_element(child, indent + 1)

    print("\n=== SM207060 Schema ===")
    print_element(result)


def verify_endpoint(session):
    entities = ["UsrContainer", "UsrContainerEvent", "UsrContainerPOLink"]
    all_ok = True
    for entity in entities:
        url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/{entity}"
        resp = session.get(url, params={"$top": "1"})
        status_icon = "OK" if resp.status_code == 200 else "FAIL"
        print(f"  {status_icon}: {entity} -> {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"       Records: {len(data)}")
            if data:
                print(f"       Fields: {list(data[0].keys())[:8]}...")
        elif resp.status_code == 403:
            try:
                err = resp.json()
                print(f"       {err.get('message', '')}")
            except Exception:
                print(f"       {resp.text[:200]}")
            all_ok = False
        else:
            print(f"       {resp.text[:200]}")
            all_ok = False
    return all_ok


def grant_screen_access_via_soap(session):
    """Grant access to SB501000 using SM201010 (Access Rights by Screen) SOAP API."""
    soap_url = f"{BASE_URL}/Soap/SM201010.asmx"
    print(f"\n=== Grant Access to SB501000 via SM201010 ===")
    login_soap(session, soap_url)

    # Step 1: Get schema to understand field names
    print("\nStep 1: Getting SM201010 schema...")
    schema = get_schema(session, soap_url)
    if schema:
        with open("/tmp/sm201010-schema.xml", "w") as f:
            f.write(schema)
        print("  Schema saved to /tmp/sm201010-schema.xml")

        # Parse to find field names
        root = ET.fromstring(schema)
        result = None
        for elem in root.iter():
            if elem.tag.endswith("GetSchemaResult"):
                result = elem
                break

        if result is not None:
            # Print a condensed view of field names and object names
            print("\n  Schema fields:")
            for elem in result.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag in ("FieldName", "ObjectName", "Value"):
                    text = (elem.text or "").strip()
                    if text:
                        print(f"    {tag}: {text}")

    # Step 2: Export current roles for SB501000
    print("\nStep 2: Checking current access rights for SB501000...")
    export_body = """<tns:Export>
    <tns:commands>
      <tns:Command><tns:FieldName>ScreenID</tns:FieldName><tns:ObjectName>Screen</tns:ObjectName><tns:Value>SB501000</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>RoleName</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName></tns:Command>
      <tns:Command><tns:FieldName>AccessRights</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName></tns:Command>
    </tns:commands>
    <tns:topCount>50</tns:topCount>
    <tns:includeHeaders>true</tns:includeHeaders>
  </tns:Export>"""

    resp = session.post(soap_url, data=make_envelope(export_body), headers=soap_headers("Export"))
    print(f"  Export status: {resp.status_code}")
    if resp.status_code == 200:
        exp_root = ET.fromstring(resp.text)
        for elem in exp_root.iter():
            if elem.tag.endswith("ExportResult"):
                for row in elem:
                    values = [v.text or "" for v in row]
                    print(f"    {' | '.join(values)}")
                break
    else:
        # Try to extract fault
        try:
            fault_root = ET.fromstring(resp.text)
            for elem in fault_root.iter():
                if elem.tag.endswith("faultstring"):
                    print(f"  Fault: {elem.text}")
                    break
        except Exception:
            pass
        print(f"  Response: {resp.text[:1000]}")

    # Step 3: Try to grant "Delete" (full) access for each target role
    print(f"\nStep 3: Granting access for roles: {TARGET_ROLES}")
    for role in TARGET_ROLES:
        print(f"\n  Granting Delete access for role '{role}' on SB501000...")
        submit_body = f"""<tns:Submit>
    <tns:commands>
      <tns:Command><tns:FieldName>ScreenID</tns:FieldName><tns:ObjectName>Screen</tns:ObjectName><tns:Value>SB501000</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>RoleName</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>{role}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>AccessRights</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>Delete</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>Save</tns:FieldName><tns:ObjectName>Screen</tns:ObjectName></tns:Command>
    </tns:commands>
  </tns:Submit>"""

        resp = session.post(soap_url, data=make_envelope(submit_body), headers=soap_headers("Submit"))
        if resp.status_code == 200:
            print(f"    OK: Access granted for '{role}'")
        else:
            print(f"    FAIL: {resp.status_code}")
            try:
                fault_root = ET.fromstring(resp.text)
                for elem in fault_root.iter():
                    if elem.tag.endswith("faultstring"):
                        print(f"    Fault: {elem.text}")
                        break
            except Exception:
                pass
            print(f"    Response: {resp.text[:500]}")

    logout_soap(session, soap_url)


def main():
    if not USERNAME or not PASSWORD:
        print("ERROR: ACUMATICA_USERNAME and ACUMATICA_PASSWORD required")
        sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "--schema-only"
    session = requests.Session()

    try:
        if mode == "--schema-only":
            soap_url = f"{BASE_URL}/Soap/SM207060.asmx"
            print(f"=== SM207060 Schema Discovery ===")
            print(f"URL: {soap_url}")
            login_soap(session, soap_url)
            schema = get_schema(session, soap_url)
            if schema:
                parse_and_print_schema(schema)
                with open("/tmp/sm207060-schema.xml", "w") as f:
                    f.write(schema)
                print(f"\nRaw schema saved to /tmp/sm207060-schema.xml")
            logout_soap(session, soap_url)

        elif mode == "--verify":
            print(f"=== Verify ContainerTracking Endpoint ===")
            login_rest(session)
            ok = verify_endpoint(session)
            logout_rest(session)
            if not ok:
                print("\nEndpoint verification FAILED — some entities not accessible")
                sys.exit(1)
            else:
                print("\nAll entities accessible!")

        elif mode == "--grant-access":
            grant_screen_access_via_soap(session)
            # After granting, verify via REST
            print("\n=== Verifying endpoint after access grant ===")
            login_rest(session)
            ok = verify_endpoint(session)
            logout_rest(session)
            if ok:
                print("\nSUCCESS: All entities accessible!")
            else:
                print("\nWARNING: Some entities still not accessible. May need different role name.")

        elif mode == "--configure":
            print(f"=== Configure ContainerTracking Endpoint Fields ===")
            print(f"NOTE: Fields auto-resolve from GraphType. Use --grant-access instead.")
            print(f"If fields need explicit mapping, use SM207060 Populate Fields via SOAP.")

        else:
            print(f"Unknown mode: {mode}")
            print("Usage: configure-container-endpoint.py [--schema-only|--configure|--verify|--grant-access]")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
