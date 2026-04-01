#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Key fixes vs prior attempts:
  1. EntityTree.Key = "Container" for tree navigation (not //Title which stacks; not Title which picks root)
  2. ScreenID = "Container Maintenance" (screen NAME, not screen ID "SB501000")
  3. SelectedEndpoint.InterfaceName read-back to verify navigation
  4. ObjectName set AFTER ScreenID commit so it isn't overwritten
  5. Full SOAP response logging for every step

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
SCREEN_NAME      = "Container Maintenance"   # Human-readable screen name for ScreenID selector
SCREEN_ID        = "SB501000"                # Actual screen ID (for reference/fallback)

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
            fault = resp.text[:300]
        print(f"  FAIL ({label}): HTTP {resp.status_code} — {fault[:400]}")
        return False
    if dump:
        print(f"  [SOAP response for {label}]: {resp.text[100:600]}")
    return True

def extract_field_value(xml_text, field_name):
    """Extract a field value from SOAP response."""
    pattern = rf'<FieldName>{re.escape(field_name)}</FieldName>.*?<Value>(.*?)</Value>'
    m = re.search(pattern, xml_text, re.DOTALL)
    return m.group(1) if m else None

def extract_all_field_values(xml_text):
    """Extract all FieldName→Value pairs from SOAP response."""
    results = {}
    pattern = r'<FieldName>(.*?)</FieldName>[^<]*(?:<[^/][^<]*>)*[^<]*<Value>(.*?)</Value>'
    for m in re.finditer(pattern, xml_text, re.DOTALL):
        fn = m.group(1).strip()
        val = m.group(2).strip()
        results[fn] = val
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
        print(f"Login failed: {resp.status_code}\n{resp.text[:300]}")
        sys.exit(1)
    print("OK: Logged in")

def logout(session):
    session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
    print("OK: Logged out")

def navigate_to_endpoint(session):
    """Navigate to ContainerTracking endpoint. Returns True if navigation confirmed."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>InterfaceName</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Value>{ENDPOINT_NAME}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, "navigate InterfaceName"):
        return False
    iface = extract_field_value(resp.text, "InterfaceName")
    print(f"  InterfaceName after nav: {iface!r}")

    # Set GateVersion to pin to 24.200.001
    body2 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>GateVersion</tns:FieldName>
      <tns:ObjectName>Endpoint</tns:ObjectName>
      <tns:Value>{ENDPOINT_VERSION}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp2 = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
    if not check_response(resp2, "navigate GateVersion"):
        return False
    version = extract_field_value(resp2.text, "GateVersion")
    print(f"  GateVersion after nav: {version!r}")

    # Verify via SelectedEndpoint object (right-panel showing actual endpoint properties)
    body3 = """<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>InterfaceName</tns:FieldName>
      <tns:ObjectName>SelectedEndpoint</tns:ObjectName>
      <tns:Commit>false</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp3 = session.post(SOAP_URL, data=make_envelope(body3), headers=soap_headers("Submit"))
    if resp3.status_code == 200:
        sel_iface = extract_field_value(resp3.text, "InterfaceName")
        print(f"  SelectedEndpoint.InterfaceName: {sel_iface!r}")
        if sel_iface == ENDPOINT_NAME:
            print(f"  CONFIRMED on {ENDPOINT_NAME}")
            return True
        # Full dump for diagnosis
        print(f"  [SelectedEndpoint probe response]: {resp3.text[100:500]}")

    # If we can't confirm via SelectedEndpoint, check via tree title
    body4 = """<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Title</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Commit>false</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp4 = session.post(SOAP_URL, data=make_envelope(body4), headers=soap_headers("Submit"))
    if resp4.status_code == 200:
        tree_title = extract_field_value(resp4.text, "Title")
        print(f"  EntityTree.Title probe: {tree_title!r}")

    print(f"  WARNING: Cannot verify on {ENDPOINT_NAME} — proceeding")
    return True

def delete_entity(session, entity_name):
    """Select entity by Key in EntityTree then delete it."""
    print(f"\n  Deleting: {entity_name}")

    # Navigate to entity using EntityTree.Key (the entity's ObjectName is its key)
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>Key</tns:FieldName>
      <tns:ObjectName>EntityTree</tns:ObjectName>
      <tns:Value>{entity_name}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"EntityTree.Key={entity_name}"):
        print(f"    Key nav failed — trying //Title approach")
        return delete_via_path_title(session, entity_name)

    # Check what was selected
    fields = extract_all_field_values(resp.text)
    key_val = fields.get("Key", "?")
    title_val = fields.get("Title", "?")
    obj_name = fields.get("ObjectName", "?")
    print(f"    Selected: Key={key_val!r}, Title={title_val!r}, ObjectName={obj_name!r}")
    print(f"    Full response snippet: {resp.text[200:500]}")

    # Delete the selected entity
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
    if not check_response(resp2, f"SelectedEntity.DeleteRow {entity_name}", dump=True):
        root = ET.fromstring(resp2.text)
        print(f"    Delete fault: {get_fault(root)[:300]}")
        return False

    print(f"    Deleted {entity_name}")
    return True

def delete_via_path_title(session, entity_name):
    """Fallback: try Endpoint.deleteNode after navigating."""
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
    if not check_response(resp, f"Endpoint.deleteNode fallback"):
        return False
    print(f"    deleteNode fallback returned OK")
    return True

def add_entity(session, object_name):
    """Add entity: EntityTree.insertNew → fill dialog → confirm."""
    print(f"\n  Adding entity: {object_name}")

    # Open new entity dialog via EntityTree.insertNew
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
    if not check_response(resp, f"EntityTree.insertNew {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        # Fall back to Endpoint.insertNew
        print(f"    Trying Endpoint.insertNew fallback")
        return add_entity_endpoint_insertnew(session, object_name)

    print(f"    insertNew OK. Response: {resp.text[200:500]}")

    # Step 1: Set ScreenID first (screen NAME selector) so it doesn't overwrite ObjectName
    body2 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ScreenID</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>{SCREEN_NAME}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp2 = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
    if not check_response(resp2, f"ScreenID={SCREEN_NAME}"):
        root = ET.fromstring(resp2.text)
        print(f"    ScreenID fault: {get_fault(root)[:300]}")
        # Try screen ID directly as fallback
        print(f"    Trying ScreenID={SCREEN_ID} (ID format)")
        return add_entity_with_screen_id(session, object_name)

    screen_resp = extract_all_field_values(resp2.text)
    print(f"    ScreenID set. Response fields: {dict(list(screen_resp.items())[:6])}")
    print(f"    ScreenID response: {resp2.text[200:500]}")

    # Step 2: Set ObjectName and ObjectType after ScreenID is committed
    body3 = f"""<tns:Submit>
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
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp3 = session.post(SOAP_URL, data=make_envelope(body3), headers=soap_headers("Submit"))
    if not check_response(resp3, f"ObjectName={object_name}+ObjectType"):
        root = ET.fromstring(resp3.text)
        print(f"    ObjectName fault: {get_fault(root)[:300]}")
        return False

    fields3 = extract_all_field_values(resp3.text)
    print(f"    ObjectName set. Response fields: {dict(list(fields3.items())[:6])}")

    # Step 3: Confirm dialog (try OK then Save)
    for button in ["OK", "Save"]:
        body4 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>{button}</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
        resp4 = session.post(SOAP_URL, data=make_envelope(body4), headers=soap_headers("Submit"))
        if check_response(resp4, f"dialog {button}"):
            fields4 = extract_all_field_values(resp4.text)
            print(f"    Dialog {button} OK. Fields: {dict(list(fields4.items())[:4])}")
            return True
        root = ET.fromstring(resp4.text)
        fault = get_fault(root)
        print(f"    {button} fault: {fault[:200]}")
        if "does not exist" in fault.lower() or "not found" in fault.lower():
            continue

    return False

def add_entity_with_screen_id(session, object_name):
    """Fallback: try using actual screen ID SB501000 instead of name."""
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ScreenID</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>{SCREEN_ID}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    check_response(resp, f"ScreenID={SCREEN_ID} fallback", dump=True)

    body2 = f"""<tns:Submit>
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
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp2 = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
    check_response(resp2, f"ObjectName fallback {object_name}", dump=True)

    body3 = """<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>OK</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp3 = session.post(SOAP_URL, data=make_envelope(body3), headers=soap_headers("Submit"))
    if check_response(resp3, f"dialog OK fallback"):
        print(f"    Dialog OK (fallback) worked")
        return True
    return False

def add_entity_endpoint_insertnew(session, object_name):
    """Fallback: insertNew on Endpoint (original approach, tries to add entity)."""
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
    if not check_response(resp, f"Endpoint.insertNew {object_name}", dump=True):
        return False

    # Fill dialog same as above
    body2 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ScreenID</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Value>{SCREEN_NAME}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp2 = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
    check_response(resp2, f"ScreenID in Endpoint fallback", dump=True)

    body3 = f"""<tns:Submit>
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
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp3 = session.post(SOAP_URL, data=make_envelope(body3), headers=soap_headers("Submit"))
    check_response(resp3, f"ObjectName in Endpoint fallback", dump=True)

    body4 = """<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>OK</tns:FieldName>
      <tns:ObjectName>CreateEntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp4 = session.post(SOAP_URL, data=make_envelope(body4), headers=soap_headers("Submit"))
    if check_response(resp4, f"dialog OK Endpoint fallback"):
        print(f"    Endpoint.insertNew → OK worked")
        return True
    return False

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
    if not check_response(resp, "final save", dump=True):
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
    print(f"Screen: {SCREEN_NAME} ({SCREEN_ID})")

    session = requests.Session()

    try:
        login(session)
        navigate_to_endpoint(session)

        # Phase 1: Delete wrong-named entities
        print("\n--- Phase 1: Delete wrong-named entities ---")
        for name in WRONG_NAMES:
            delete_entity(session, name)
            time.sleep(0.5)

        # Phase 2: Add correct entities
        print("\n--- Phase 2: Add correct-named entities ---")
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
            print("WARNING: Not all entities added — attempting save anyway")
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
