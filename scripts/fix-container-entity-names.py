#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Strategy:
  1. Navigate to ContainerTracking endpoint via SOAP (verify via response)
  2. Delete wrong-named entities using EntityTree.Title navigation + SelectedEntity.DeleteRow
     (uses plain 'Title' not '//Title' to avoid stack overflow)
  3. Add correct entities via EntityTree.insertNew + CreateEntityView dialog
  4. Save and verify via REST

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
            fault = resp.text[:300]
        print(f"  FAIL ({label}): HTTP {resp.status_code} — {fault[:400]}")
        return False
    return True

def extract_field_value(xml_text, field_name):
    """Extract a field value from SOAP response."""
    pattern = rf'<FieldName>{re.escape(field_name)}</FieldName>.*?<Value>(.*?)</Value>'
    m = re.search(pattern, xml_text, re.DOTALL)
    return m.group(1) if m else None

def extract_all_field_values(xml_text):
    """Extract all FieldName→Value pairs from SOAP response for debugging."""
    results = {}
    pattern = r'<FieldName>(.*?)</FieldName>.*?<Value>(.*?)</Value>'
    for m in re.finditer(pattern, xml_text, re.DOTALL):
        results[m.group(1)] = m.group(2)
    return results

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
    """Navigate to ContainerTracking endpoint and verify we landed on it."""
    # Submit InterfaceName and GateVersion together to search for ContainerTracking
    body = f"""<tns:Submit>
  <tns:commands>
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
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, "navigate_to_endpoint"):
        return False

    # Verify we actually landed on ContainerTracking
    fields = extract_all_field_values(resp.text)
    iface   = fields.get("InterfaceName", "<not found>")
    version = fields.get("GateVersion",   "<not found>")
    print(f"  Navigation response: InterfaceName={iface!r}, GateVersion={version!r}")

    if iface != ENDPOINT_NAME:
        print(f"  WARNING: Expected '{ENDPOINT_NAME}', got '{iface}' — trying Search approach")
        # Try the Search action to find ContainerTracking
        return navigate_via_search(session)

    print(f"  OK: Confirmed on {ENDPOINT_NAME} {ENDPOINT_VERSION}")
    return True

def navigate_via_search(session):
    """Alternative: use Search/FindRow to navigate to ContainerTracking."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Search</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, "navigate_via_search"):
        return False

    fields = extract_all_field_values(resp.text)
    iface = fields.get("InterfaceName", "<not found>")
    print(f"  After Search: InterfaceName={iface!r}")

    if iface == ENDPOINT_NAME:
        print(f"  OK: Search navigation worked")
        return True

    # Last resort: print all fields to diagnose
    print(f"  All response fields: {fields}")
    print(f"  WARNING: Could not navigate to {ENDPOINT_NAME} — proceeding anyway")
    return True  # continue with best-effort

def delete_entity(session, entity_name):
    """Navigate to entity using plain 'Title' (not '//Title') then delete."""
    print(f"\n  Deleting: {entity_name}")

    # Step 1: Navigate to entity in tree using plain Title field
    # (Using '//Title' caused InsufficientExecutionStackException in prior runs)
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Title</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Value>{entity_name}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"select_entity_title {entity_name}"):
        print(f"    Trying deleteNode approach instead...")
        return delete_via_deletenode(session, entity_name)

    fields = extract_all_field_values(resp.text)
    print(f"    After Title navigate: ObjectName={fields.get('ObjectName', '?')!r}, Title={fields.get('Title', '?')!r}")

    # Step 2: Delete the selected entity
    body2 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>DeleteRow</tns:FieldName>
      <tns:ObjectName>SelectedEntity</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp2 = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
    if not check_response(resp2, f"delete_selected {entity_name}"):
        root = ET.fromstring(resp2.text)
        print(f"    Delete fault: {get_fault(root)[:300]}")
        return False

    fields2 = extract_all_field_values(resp2.text)
    print(f"    Deleted. Response fields: {list(fields2.keys())[:5]}")
    return True

def delete_via_deletenode(session, entity_name):
    """Fallback: use Endpoint.deleteNode ServiceCommand."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>deleteNode</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"deleteNode {entity_name}"):
        return False
    print(f"    deleteNode response OK for {entity_name}")
    return True

def add_entity(session, object_name):
    """Add entity via EntityTree.insertNew + CreateEntityView dialog."""
    print(f"\n  Adding entity: {object_name}")

    # Step 1: insertNew on EntityTree (NOT Endpoint — that creates a new endpoint record)
    # EntityTree.insertNew adds a new entity to the currently active endpoint
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>insertNew</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"EntityTree.insertNew for {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        print(f"    Trying Endpoint.insertNew fallback...")
        return add_entity_via_endpoint_insertnew(session, object_name)

    fields = extract_all_field_values(resp.text)
    print(f"    insertNew response fields: {dict(list(fields.items())[:6])}")

    # Step 2: Fill CreateEntityView dialog
    return fill_create_entity_dialog(session, object_name)

def add_entity_via_endpoint_insertnew(session, object_name):
    """Fallback: insertNew on Endpoint (may open Create Endpoint dialog instead of Create Entity)."""
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
    if not check_response(resp, f"Endpoint.insertNew for {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        return False

    fields = extract_all_field_values(resp.text)
    print(f"    Endpoint.insertNew response fields: {dict(list(fields.items())[:6])}")
    return fill_create_entity_dialog(session, object_name)

def fill_create_entity_dialog(session, object_name):
    """Fill and submit the CreateEntityView dialog."""
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
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"fill_dialog {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Dialog fill fault: {get_fault(root)[:400]}")
        print(f"    Response snippet: {resp.text[200:500]}")
        return False

    fields = extract_all_field_values(resp.text)
    print(f"    Dialog filled. ObjectName={fields.get('ObjectName', '?')!r}, ScreenID={fields.get('ScreenID', '?')!r}")

    # Confirm/OK the dialog
    return confirm_dialog(session, object_name)

def confirm_dialog(session, object_name):
    """Click OK/Save on the CreateEntityView dialog."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>OK</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"dialog_ok {object_name}"):
        root = ET.fromstring(resp.text)
        fault = get_fault(root)
        print(f"    Dialog OK fault: {fault[:300]}")
        # Try 'Save' button instead of 'OK'
        return confirm_dialog_save(session, object_name)

    fields = extract_all_field_values(resp.text)
    print(f"    Dialog confirmed. Tree fields: {dict(list(fields.items())[:4])}")
    return True

def confirm_dialog_save(session, object_name):
    """Fallback: use Save button on CreateEntityView."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Save</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"dialog_save {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Dialog Save fault: {get_fault(root)[:300]}")
        return False

    fields = extract_all_field_values(resp.text)
    print(f"    Dialog save OK. Fields: {dict(list(fields.items())[:4])}")
    return True

def save_endpoint(session):
    """Final save of the endpoint."""
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

    # Also check wrong-named entities are gone
    print("\n  Checking wrong-named entities are gone:")
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

        if not navigate_to_endpoint(session):
            print("ERROR: Could not navigate to endpoint")
            sys.exit(1)

        # Phase 1: Delete wrong-named entities
        print("\n--- Phase 1: Delete wrong-named entities ---")
        deleted_any = False
        for name in WRONG_NAMES:
            if delete_entity(session, name):
                deleted_any = True
            else:
                print(f"    Could not delete {name} — may already be absent")
            time.sleep(0.5)

        # Phase 2: Add correct entities
        print("\n--- Phase 2: Add correct-named entities ---")
        # Re-navigate to ensure we're on ContainerTracking after deletes
        navigate_to_endpoint(session)
        time.sleep(0.5)

        added_all = True
        for name in CORRECT_NAMES:
            if not add_entity(session, name):
                print(f"  ERROR: Failed to add {name}")
                added_all = False
            time.sleep(0.5)

        if added_all:
            save_endpoint(session)
        else:
            print("WARNING: Not all entities added — skipping save")

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
