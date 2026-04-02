#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Strategy: Use SOAP Import action with ImportHeaderCommands to navigate to ContainerTracking.
The Import action uses header commands for record lookup (different from Submit which starts at Default).

Fallback: SOAP Export to find ContainerTracking's canonical key, then use it for navigation.

Usage:
    python3 fix-container-entity-names.py

Requires env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import os, sys, requests, xml.etree.ElementTree as ET, time, re

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", os.environ.get("ACUMATICA_PROD_USERNAME", ""))
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", os.environ.get("ACUMATICA_PROD_PASSWORD", ""))
TENANT   = os.environ.get("ACUMATICA_TENANT",   os.environ.get("ACUMATICA_PROD_TENANT", "Heritage Fabrics"))

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"
TNS      = "http://www.acumatica.com/typed/"
SOAP_NS  = "http://schemas.xmlsoap.org/soap/envelope/"

ENDPOINT_NAME    = "ContainerTracking"
ENDPOINT_VERSION = "24.200.001"
SCREEN_ID        = "SB501000"

WRONG_NAMES   = ["Container", "ContainerEvent", "ContainerPOLink"]
CORRECT_NAMES = ["UsrContainer", "UsrContainerEvent", "UsrContainerPOLink"]

def make_envelope(body_xml):
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">'
        f'<soap:Body>{body_xml}</soap:Body>'
        f'</soap:Envelope>'
    )

def soap_headers(action):
    return {
        "SOAPAction": f'"{TNS}{action}"',
        "Content-Type": "text/xml; charset=utf-8",
    }

def get_fault(root):
    for el in root.iter():
        if el.tag.endswith("faultstring"):
            return el.text or ""
    return ""

def login(session):
    body = (
        f"<tns:Login>"
        f"<tns:name>{USERNAME}</tns:name>"
        f"<tns:password>{PASSWORD}</tns:password>"
        f"<tns:company>{TENANT}</tns:company>"
        f"</tns:Login>"
    )
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Login"))
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code}\n{resp.text[:300]}")
        sys.exit(1)
    print("OK: Logged in")

def logout(session):
    session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
    print("OK: Logged out")

def export_all_endpoints(session):
    """Use SOAP Export to list all endpoints and find ContainerTracking."""
    print("\n--- SOAP Export: listing all endpoints ---")
    body = """<tns:Export>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>InterfaceName</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
    </tns:Command>
    <tns:Command>
      <tns:FieldName>GateVersion</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
    </tns:Command>
  </tns:commands>
  <tns:topCount>100</tns:topCount>
  <tns:includeHeaders>true</tns:includeHeaders>
</tns:Export>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Export"))
    print(f"  Export status: {resp.status_code}")
    print(f"  Export response: {resp.text[:2000]}")
    return resp

def import_delete_entity(session, entity_name):
    """Use SOAP Import with header commands to navigate to ContainerTracking and delete entity."""
    print(f"\n  Import-Delete: {entity_name}")
    body = f"""<tns:Import>
  <tns:requests>
    <tns:Request>
      <tns:Action>Update</tns:Action>
      <tns:ImportHeaderCommands>
        <tns:Command>
          <tns:FieldName>InterfaceName</tns:FieldName>
          <tns:ObjectName>Endpoint</tns:ObjectName>
          <tns:Value>{ENDPOINT_NAME}</tns:Value>
          <tns:Commit>false</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>GateVersion</tns:FieldName>
          <tns:ObjectName>Endpoint</tns:ObjectName>
          <tns:Value>{ENDPOINT_VERSION}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
      </tns:ImportHeaderCommands>
      <tns:Commands>
        <tns:Command>
          <tns:FieldName>Key</tns:FieldName>
          <tns:ObjectName>EntityTree</tns:ObjectName>
          <tns:Value>{ENDPOINT_NAME}#{entity_name}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>DeleteRow</tns:FieldName>
          <tns:ObjectName>SelectedEntity</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
      </tns:Commands>
    </tns:Request>
  </tns:requests>
  <tns:breakOnError>false</tns:breakOnError>
</tns:Import>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Import"))
    print(f"  Import-Delete {entity_name}: HTTP {resp.status_code}")
    print(f"  Response: {resp.text[:800]}")
    return resp.status_code == 200

def import_add_entity(session, object_name):
    """Use SOAP Import with header commands to navigate to ContainerTracking and add entity."""
    print(f"\n  Import-Add: {object_name}")
    body = f"""<tns:Import>
  <tns:requests>
    <tns:Request>
      <tns:Action>Insert</tns:Action>
      <tns:ImportHeaderCommands>
        <tns:Command>
          <tns:FieldName>InterfaceName</tns:FieldName>
          <tns:ObjectName>Endpoint</tns:ObjectName>
          <tns:Value>{ENDPOINT_NAME}</tns:Value>
          <tns:Commit>false</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>GateVersion</tns:FieldName>
          <tns:ObjectName>Endpoint</tns:ObjectName>
          <tns:Value>{ENDPOINT_VERSION}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
      </tns:ImportHeaderCommands>
      <tns:Commands>
        <tns:Command>
          <tns:FieldName>insertNew</tns:FieldName>
          <tns:ObjectName>EntityTree</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>ObjectName</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Value>{object_name}</tns:Value>
          <tns:Commit>false</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>ObjectType</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Value>Top-Level</tns:Value>
          <tns:Commit>false</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>ScreenID</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Value>{SCREEN_ID}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>OK</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
        <tns:Command>
          <tns:FieldName>Save</tns:FieldName>
          <tns:ObjectName>Endpoint</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>
      </tns:Commands>
    </tns:Request>
  </tns:requests>
  <tns:breakOnError>false</tns:breakOnError>
</tns:Import>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Import"))
    print(f"  Import-Add {object_name}: HTTP {resp.status_code}")
    print(f"  Response: {resp.text[:800]}")
    return resp.status_code == 200

def try_submit_navigation_variants(session):
    """Try different Submit navigation approaches and log what happens to diagnose."""
    print("\n--- Navigation diagnostics ---")

    variants = [
        # (FieldName, ObjectName, Value)
        ("InterfaceName", "Endpoint", ENDPOINT_NAME),
        ("InterfaceName", "SelectedEndpoint", ENDPOINT_NAME),
        ("EndpointName", "Endpoint", ENDPOINT_NAME),
        ("Name", "Endpoint", ENDPOINT_NAME),
    ]

    for field, obj, val in variants:
        cmd_xml = f"""<tns:Command>
          <tns:FieldName>{field}</tns:FieldName>
          <tns:ObjectName>{obj}</tns:ObjectName>
          <tns:Value>{val}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>"""
        body = f"<tns:Submit><tns:commands>{cmd_xml}</tns:commands></tns:Submit>"
        resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
        key_m = re.search(r'<Value>ROOT#([^<]+)</Value>', resp.text)
        iface_m = re.search(r'<FieldName>InterfaceName</FieldName>.*?<Value>(.*?)</Value>', resp.text, re.DOTALL)
        print(f"  {obj}.{field}={val}: HTTP {resp.status_code}, ROOT#key={key_m.group(1) if key_m else '?'}, InterfaceName={iface_m.group(1) if iface_m else '?'}")

def verify_rest():
    """Verify REST endpoint entities respond."""
    session = requests.Session()
    r = session.post(
        f"{BASE_URL}/entity/auth/login",
        json={"name": USERNAME, "password": PASSWORD, "company": TENANT}
    )
    if r.status_code != 204:
        print(f"  REST login failed: {r.status_code}")
        return False

    all_ok = True
    for entity in CORRECT_NAMES:
        url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/{entity}"
        r = session.get(url, params={"$top": "1"})
        icon = "OK" if r.status_code == 200 else "FAIL"
        print(f"  {icon}: {entity} → HTTP {r.status_code}")
        if r.status_code != 200:
            all_ok = False

    print("\n  Wrong-named entities check:")
    for entity in WRONG_NAMES:
        url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/{entity}"
        r = session.get(url, params={"$top": "1"})
        icon = "OK (gone)" if r.status_code != 200 else "STILL PRESENT"
        print(f"  {icon}: {entity} → HTTP {r.status_code}")

    session.post(f"{BASE_URL}/entity/auth/logout")
    return all_ok

def main():
    if not USERNAME or not PASSWORD:
        print("ERROR: ACUMATICA_USERNAME and ACUMATICA_PASSWORD required")
        sys.exit(1)

    print(f"=== Fix ContainerTracking Entity Names ===")
    print(f"User: {USERNAME} | Tenant: {TENANT}")
    print(f"Endpoint: {ENDPOINT_NAME} {ENDPOINT_VERSION}")

    session = requests.Session()

    try:
        login(session)

        # First: Export to understand what endpoints exist and diagnose navigation
        export_all_endpoints(session)

        # Try different navigation approaches
        try_submit_navigation_variants(session)

        # Attempt Import-based delete + add
        print("\n--- Phase 1: Import-Delete wrong-named entities ---")
        for name in WRONG_NAMES:
            import_delete_entity(session, name)
            time.sleep(0.5)

        print("\n--- Phase 2: Import-Add correct-named entities ---")
        for name in CORRECT_NAMES:
            import_add_entity(session, name)
            time.sleep(0.5)

        logout(session)

        print("\n=== Verifying REST endpoint ===")
        ok = verify_rest()
        if ok:
            print("\nSUCCESS: All entities accessible!")
        else:
            print("\nFAILED: Some entities not accessible.")
            sys.exit(1)

    except Exception as e:
        import traceback
        print(f"ERROR: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
