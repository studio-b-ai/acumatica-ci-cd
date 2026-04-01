#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Strategy (based on full SM207060 GetSchema analysis):
  1. Set filter to ContainerTracking endpoint (InterfaceName on Endpoint)
  2. Navigate EntityTree to each wrong-named entity (//Title field)
  3. Delete via DeleteRow on SelectedEntity
  4. Add correct entities via insertNew + CreateEntityView dialog
  5. Save and verify via REST

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

def check_response(resp, label):
    if resp.status_code != 200:
        try:
            root = ET.fromstring(resp.text)
            fault = get_fault(root)
        except:
            fault = resp.text[:200]
        print(f"  FAIL ({label}): HTTP {resp.status_code} — {fault[:300]}")
        return False
    return True

def extract_field_value(xml_text, field_name):
    """Extract a field value from SOAP response."""
    pattern = rf'<FieldName>{re.escape(field_name)}</FieldName>.*?<Value>(.*?)</Value>'
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
        print(f"Login failed: {resp.status_code}")
        sys.exit(1)
    print("OK: Logged in")

def logout(session):
    session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
    print("OK: Logged out")

def navigate_to_endpoint(session):
    """Set filter to ContainerTracking endpoint."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>InterfaceName</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Value>{ENDPOINT_NAME}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
    <tns:Command>
      <tns:FieldName>GateVersion</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Value>{ENDPOINT_VERSION}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, "navigate_to_endpoint"):
        return False
    print(f"  OK: Navigated to {ENDPOINT_NAME} {ENDPOINT_VERSION}")
    return True

def select_entity_in_tree(session, entity_name):
    """Navigate EntityTree to select an entity by title."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>//Title</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Value>{entity_name}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"select_entity {entity_name}"):
        return False
    # Check what was selected
    selected = extract_field_value(resp.text, "ObjectName")
    print(f"    Selected entity: {selected!r} (expected {entity_name!r})")
    return True

def delete_selected_entity(session, entity_name):
    """Delete the currently selected entity via SelectedEntity.DeleteRow."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>DeleteRow</tns:FieldName>
      <tns:ObjectName>SelectedEntity</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"delete_entity {entity_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        return False
    print(f"    Deleted: {entity_name}")
    return True

def add_entity(session, object_name):
    """Add entity via insertNew + CreateEntityView dialog flow."""
    print(f"\n  Adding entity: {object_name}")

    # Step 1: insertNew on Endpoint to open Create Entity dialog
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>insertNew</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"insertNew for {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        return False
    # Check if dialog opened
    dialog_check = extract_field_value(resp.text, "ObjectName")
    print(f"    insertNew response ObjectName: {dialog_check!r}")
    print(f"    insertNew response: {resp.text[100:300]}")

    # Step 2: Fill dialog fields
    body = f"""<tns:Submit>
  <tns:commands>
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
      <tns:FieldName>Save</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"fill+save {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:500]}")
        print(f"    Response: {resp.text[100:400]}")
        return False
    print(f"    Created and saved: {object_name}")
    return True

def save_endpoint(session):
    """Final save."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Save</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, "final save"):
        root = ET.fromstring(resp.text)
        print(f"  Fault: {get_fault(root)[:300]}")
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
            try:
                print(f"       {r.json().get('message', r.text[:200])}")
            except:
                print(f"       {r.text[:200]}")

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
        navigate_to_endpoint(session)

        # Phase 1: Delete wrong-named entities via EntityTree
        print("\n--- Phase 1: Delete wrong-named entities ---")
        for name in WRONG_NAMES:
            print(f"\n  Deleting: {name}")
            if select_entity_in_tree(session, name):
                delete_selected_entity(session, name)
            else:
                print(f"    Could not select {name} — may already be deleted or different name")
            time.sleep(1)

        # Phase 2: Add correct entities
        print("\n--- Phase 2: Add correct-named entities ---")
        # Re-navigate to ensure we're on ContainerTracking
        navigate_to_endpoint(session)
        for name in CORRECT_NAMES:
            add_entity(session, name)
            time.sleep(1)

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
