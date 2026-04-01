#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Key insight from diagnostic runs:
  - EntityTree uses Key format: ROOT#<EndpointName> for roots, <EndpointName>#<EntityName> for entities
  - Navigate via EntityTree.Key = ROOT#ContainerTracking (NOT via Endpoint.InterfaceName)
  - Delete via EntityTree.Key = ContainerTracking#Container + SelectedEntity.DeleteRow
  - Add via EntityTree.insertNew after navigating to ROOT#ContainerTracking
  - ScreenID selector: try several screen name variants until one works

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

# Screen name variants to try in the ScreenID selector
SCREEN_NAME_CANDIDATES = [
    "Container Maintenance",
    "Container Tracking",
    "Containers",
    "SB501000",
]

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

def check_response(resp, label, dump=False):
    if resp.status_code != 200:
        try:
            root = ET.fromstring(resp.text)
            fault = get_fault(root)
        except:
            fault = resp.text[:400]
        print(f"  FAIL ({label}): HTTP {resp.status_code} — {fault[:400]}")
        return False
    if dump:
        print(f"  [SOAP {label}]: {resp.text[100:700]}")
    return True

def soap_submit(session, commands_xml, label, dump=False):
    """Submit SOAP commands, return response or None on failure."""
    body = f"<tns:Submit><tns:commands>{commands_xml}</tns:commands></tns:Submit>"
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, label, dump):
        return None
    return resp

def extract_key_value(xml_text):
    """Extract EntityTree Key value from SOAP response."""
    m = re.search(r'<FieldName>Key</FieldName><ObjectName>EntityTree</ObjectName><Value>(.*?)</Value>', xml_text)
    return m.group(1) if m else None

def extract_field(xml_text, field_name, object_name=""):
    """Extract a field value by FieldName (and optionally ObjectName) from SOAP response."""
    if object_name:
        pattern = rf'<FieldName>{re.escape(field_name)}</FieldName><ObjectName>{re.escape(object_name)}</ObjectName><Value>(.*?)</Value>'
    else:
        pattern = rf'<FieldName>{re.escape(field_name)}</FieldName>[^<]*(?:<[^/][^<]*>)*?<Value>(.*?)</Value>'
    m = re.search(pattern, xml_text, re.DOTALL)
    return m.group(1) if m else None

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

def navigate_to_endpoint(session):
    """Navigate to ContainerTracking using EntityTree.Key = ROOT#ContainerTracking."""
    root_key = f"ROOT#{ENDPOINT_NAME}"
    print(f"  Navigating via EntityTree.Key = {root_key!r}")

    cmd = f"""<tns:Command>
      <tns:FieldName>Key</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Value>{root_key}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp = soap_submit(session, cmd, f"EntityTree.Key={root_key}", dump=False)
    if resp is None:
        print(f"  ERROR: Navigation failed")
        return False

    key_val = extract_key_value(resp.text)
    print(f"  EntityTree.Key after nav: {key_val!r}")
    print(f"  Full response: {resp.text[100:700]}")

    if key_val == root_key:
        print(f"  CONFIRMED: On {ENDPOINT_NAME} root")
        return True
    else:
        print(f"  WARNING: Expected {root_key!r}, got {key_val!r}")
        return False

def delete_entity(session, entity_name):
    """Navigate to entity using key format <EndpointName>#<EntityName>, then delete."""
    entity_key = f"{ENDPOINT_NAME}#{entity_name}"
    print(f"\n  Deleting {entity_name} (key={entity_key!r})")

    # Navigate to the entity node
    cmd = f"""<tns:Command>
      <tns:FieldName>Key</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Value>{entity_key}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp = soap_submit(session, cmd, f"EntityTree.Key={entity_key}")
    if resp is None:
        print(f"    Navigation to {entity_name} failed")
        return False

    key_val = extract_key_value(resp.text)
    print(f"    EntityTree.Key after nav: {key_val!r}")
    print(f"    Response: {resp.text[100:600]}")

    if key_val != entity_key:
        print(f"    WARNING: Expected {entity_key!r}, got {key_val!r} — trying delete anyway")

    # Delete the selected entity
    cmd2 = """<tns:Command>
      <tns:FieldName>DeleteRow</tns:FieldName>
      <tns:ObjectName>SelectedEntity</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp2 = soap_submit(session, cmd2, f"DeleteRow {entity_name}", dump=True)
    if resp2 is None:
        return False

    print(f"    Deleted {entity_name}")
    return True

def find_working_screen_name(session):
    """Try different screen name candidates to find one the ScreenID selector accepts."""
    print(f"  Finding valid screen name for SB501000...")

    for candidate in SCREEN_NAME_CANDIDATES:
        cmd = f"""<tns:Command>
          <tns:FieldName>ScreenID</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Value>{candidate}</tns:Value>
          <tns:Commit>true</tns:Commit>
        </tns:Command>"""
        resp = soap_submit(session, cmd, f"ScreenID={candidate!r}")
        if resp is None:
            continue

        # Check if the ScreenID field accepted the value (non-empty Value in response)
        # Look for ScreenID in CreateEntityView response
        snippet = resp.text[200:800]
        print(f"    ScreenID={candidate!r} response: {snippet}")

        # Check if Value is non-empty for ScreenID field
        m = re.search(r'<FieldName>ScreenID</FieldName><ObjectName>CreateEntityView</ObjectName><Value>(.*?)</Value>', resp.text)
        if m and m.group(1).strip():
            print(f"    FOUND working screen name: {candidate!r} → value={m.group(1)!r}")
            return candidate

        # Also check ScreenIDValue (the read-only display of screen ID)
        m2 = re.search(r'ScreenIDValue.*?<Value>(.*?)</Value>', resp.text, re.DOTALL)
        if m2 and m2.group(1).strip():
            print(f"    ScreenIDValue populated with {m2.group(1)!r} for {candidate!r}")
            return candidate

    print(f"  WARNING: No screen name candidate worked, using {SCREEN_NAME_CANDIDATES[0]!r}")
    return SCREEN_NAME_CANDIDATES[0]

def add_entity(session, object_name, screen_name):
    """Add entity: navigate to endpoint root, insertNew, fill dialog."""
    print(f"\n  Adding entity: {object_name}")

    # Make sure we're on the ContainerTracking root
    navigate_to_endpoint(session)
    time.sleep(0.3)

    # Open new entity dialog
    cmd = """<tns:Command>
      <tns:FieldName>insertNew</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp = soap_submit(session, cmd, f"EntityTree.insertNew {object_name}", dump=True)
    if resp is None:
        print(f"  EntityTree.insertNew failed")
        return False

    # Step 1: Set ScreenID (use the working screen name found earlier)
    cmd2 = f"""<tns:Command>
      <tns:FieldName>ScreenID</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>{screen_name}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp2 = soap_submit(session, cmd2, f"ScreenID={screen_name!r}", dump=True)
    if resp2 is None:
        return False

    # Step 2: Set ObjectName (after ScreenID is committed so it won't be overwritten)
    cmd3 = f"""<tns:Command>
      <tns:FieldName>ObjectName</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>{object_name}</tns:Value>
      <tns:Commit>false</tns:Commit>
    </tns:Command>
    <tns:Command>
      <tns:FieldName>ObjectType</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>Top-Level</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp3 = soap_submit(session, cmd3, f"ObjectName={object_name}", dump=True)
    if resp3 is None:
        return False

    # Step 3: Confirm dialog
    for button in ["OK", "Save"]:
        cmd4 = f"""<tns:Command>
          <tns:FieldName>{button}</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>"""
        resp4 = soap_submit(session, cmd4, f"dialog {button}", dump=True)
        if resp4 is not None:
            print(f"    Dialog {button} OK for {object_name}")
            return True

    print(f"  All dialog confirm attempts failed for {object_name}")
    return False

def save_endpoint(session):
    """Final save."""
    cmd = """<tns:Command>
      <tns:FieldName>Save</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>"""
    resp = soap_submit(session, cmd, "final save", dump=True)
    if resp is None:
        return False
    print("OK: Final save complete")
    return True

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

        # Navigate to ContainerTracking using tree key
        print("\n--- Navigating to ContainerTracking ---")
        nav_ok = navigate_to_endpoint(session)
        if not nav_ok:
            print("ERROR: Could not navigate to ContainerTracking via EntityTree.Key")
            print("Check log above for full SOAP response to diagnose key format")
            sys.exit(1)

        # Phase 1: Delete wrong-named entities
        print("\n--- Phase 1: Delete wrong-named entities ---")
        for name in WRONG_NAMES:
            delete_entity(session, name)
            time.sleep(0.5)

        # Phase 2: Find working screen name
        print("\n--- Finding valid screen name ---")
        navigate_to_endpoint(session)
        time.sleep(0.3)
        # Open a dummy insertNew to access CreateEntityView dialog for screen name probing
        cmd = """<tns:Command>
          <tns:FieldName>insertNew</tns:FieldName>
          <tns:ObjectName>EntityTree</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>"""
        soap_submit(session, cmd, "insertNew for screen probe")
        screen_name = find_working_screen_name(session)
        # Cancel the dialog (try pressing Cancel or just navigate away)
        cancel_cmd = """<tns:Command>
          <tns:FieldName>Cancel</tns:FieldName>
          <tns:ObjectName>CreateEntityView</tns:ObjectName>
          <tns:Commit>true</tns:Commit>
        </tns:Command>"""
        soap_submit(session, cancel_cmd, "cancel dialog probe")

        # Phase 3: Add correct entities
        print("\n--- Phase 3: Add correct-named entities ---")
        navigate_to_endpoint(session)
        time.sleep(0.3)

        for name in CORRECT_NAMES:
            ok = add_entity(session, name, screen_name)
            if not ok:
                print(f"  ERROR: Failed to add {name}")
            time.sleep(0.5)

        save_endpoint(session)
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
