#!/usr/bin/env python3
"""
Fix ContainerTracking REST endpoint entity names.
Changes: Container→UsrContainer, ContainerEvent→UsrContainerEvent, ContainerPOLink→UsrContainerPOLink.

Strategy:
  1. Delete the 3 wrong-named entities (Container, ContainerEvent, ContainerPOLink)
  2. Re-add them with correct names (UsrContainer, UsrContainerEvent, UsrContainerPOLink)
  3. Save and verify

Usage:
    python3 fix-container-entity-names.py

Requires env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import os, sys, requests, xml.etree.ElementTree as ET, time

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

# Wrong names → correct names mapping
RENAME_MAP = [
    ("Container",      "UsrContainer"),
    ("ContainerEvent", "UsrContainerEvent"),
    ("ContainerPOLink","UsrContainerPOLink"),
]

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
        root = ET.fromstring(resp.text)
        fault = get_fault(root)
        print(f"  FAIL ({label}): HTTP {resp.status_code} — {fault[:300]}")
        return False
    return True

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
    """Navigate to ContainerTracking endpoint."""
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

def export_entities(session):
    """Export current entity list to see what's there."""
    body = f"""<tns:Export>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ObjectName</tns:FieldName>
      <tns:ObjectName>EntityView</tns:ObjectName>
    </tns:Command>
    <tns:Command>
      <tns:FieldName>ObjectType</tns:FieldName>
      <tns:ObjectName>EntityView</tns:ObjectName>
    </tns:Command>
  </tns:commands>
  <tns:topCount>50</tns:topCount>
  <tns:includeHeaders>true</tns:includeHeaders>
</tns:Export>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Export"))
    if resp.status_code != 200:
        print(f"  Export failed: {resp.status_code} - {resp.text[:300]}")
        return []

    root = ET.fromstring(resp.text)
    entities = []
    for result in root.iter():
        if result.tag.endswith("ExportResult"):
            for row in result:
                vals = [v.text or "" for v in row]
                if vals and vals[0] and vals[0] != "ObjectName":
                    entities.append(vals[0])
    return entities

def delete_entity(session, object_name):
    """Delete an entity by selecting it and calling deleteRow."""
    print(f"\n  Deleting entity: {object_name}")

    # Step 1: Navigate/select the entity in the tree view
    # In SM207060, the EntityView grid key is ObjectName
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ObjectName</tns:FieldName>
      <tns:ObjectName>EntityView</tns:ObjectName>
      <tns:Value>{object_name}</tns:Value>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"select entity {object_name}"):
        print(f"    Trying alternative select...")
        # Try without Commit
        body2 = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>ObjectName</tns:FieldName>
      <tns:ObjectName>EntityView</tns:ObjectName>
      <tns:Value>{object_name}</tns:Value>
      <tns:Commit>false</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
        resp = session.post(SOAP_URL, data=make_envelope(body2), headers=soap_headers("Submit"))
        if not check_response(resp, f"select entity {object_name} (no commit)"):
            return False

    print(f"    Selected: {object_name}")

    # Step 2: Delete the selected row
    body = f"""<tns:Submit>
  <tns:commands>
    <tns:Command>
      <tns:FieldName>deleteRow</tns:FieldName>
      <tns:ObjectName>EntityView</tns:ObjectName>
      <tns:Commit>true</tns:Commit>
    </tns:Command>
  </tns:commands>
</tns:Submit>"""
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    if not check_response(resp, f"deleteRow {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:300]}")
        return False

    print(f"    Deleted: {object_name}")
    return True

def add_entity(session, object_name, object_type):
    """Add entity via SM207060 SOAP — two-step dialog flow."""
    print(f"\n  Adding entity: {object_name} ({object_type})")

    # Step 1: Open Create Entity dialog
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
    print(f"    Dialog opened")

    # Step 2: Fill dialog fields + Save
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
      <tns:Value>{object_type}</tns:Value>
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
    if not check_response(resp, f"fill+save dialog for {object_name}"):
        root = ET.fromstring(resp.text)
        print(f"    Fault: {get_fault(root)[:500]}")
        print(f"    Response: {resp.text[100:400]}")
        return False

    print(f"    Created: {object_name}")
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

    entities = ["UsrContainer", "UsrContainerEvent", "UsrContainerPOLink"]
    all_ok = True
    for entity in entities:
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

        # Check current entities
        print("\n--- Current entities ---")
        current = export_entities(session)
        print(f"  Found: {current}")

        # Delete wrong-named entities
        wrong_names = [old for old, new in RENAME_MAP]
        to_delete = [name for name in wrong_names if name in current]
        to_add = [(new, "Top-Level") for old, new in RENAME_MAP if old in current]

        if not to_delete:
            print("\nNo wrong-named entities found — may already be fixed or different names.")
            # Check if correct names already exist
            correct_names = [new for _, new in RENAME_MAP]
            already_correct = [name for name in correct_names if name in current]
            if already_correct:
                print(f"  Already correct: {already_correct}")
            else:
                print(f"  Current entities: {current}")
                print("  WARNING: Neither wrong nor correct names found!")
        else:
            print(f"\n--- Deleting wrong-named entities: {to_delete} ---")
            for name in to_delete:
                delete_entity(session, name)
                time.sleep(1)

            print(f"\n--- Adding correct-named entities ---")
            for obj_name, obj_type in to_add:
                add_entity(session, obj_name, obj_type)
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
