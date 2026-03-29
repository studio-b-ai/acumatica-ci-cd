#!/usr/bin/env python3
"""
Configure ContainerTracking REST endpoint via SOAP Screen API.

Modes:
    --schema-only   Discover SM207060 fields
    --verify        Check endpoint exists and responds
    --schema        Discover SM201025/SM201030 access rights schemas
    --grant         Grant API role access to SB501000 via SM201025

Requires env vars: ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import os, sys, requests, xml.etree.ElementTree as ET

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
TARGET_ROLES = ["Administrator"]

def make_envelope(body_xml):
    return f'<?xml version="1.0" encoding="utf-8"?>\n<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">\n  <soap:Body>\n    {body_xml}\n  </soap:Body>\n</soap:Envelope>'

def soap_headers(action):
    return {"SOAPAction": f'"{TNS}{action}"', "Content-Type": "text/xml; charset=utf-8"}

def login_rest(session):
    resp = session.post(REST_LOGIN_URL, json={"name": USERNAME, "password": PASSWORD, "company": TENANT})
    if resp.status_code != 204:
        print(f"REST Login failed: {resp.status_code}"); print(resp.text[:500]); sys.exit(1)
    print("OK: REST Logged in")

def logout_rest(session):
    session.post(REST_LOGOUT_URL); print("OK: REST Logged out")

def login_soap(session, soap_url):
    body = f'<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>'
    resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("Login"))
    if resp.status_code != 200:
        print(f"SOAP Login failed: {resp.status_code}"); print(resp.text[:500]); sys.exit(1)
    print("OK: SOAP Logged in")

def logout_soap(session, soap_url):
    session.post(soap_url, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
    print("OK: SOAP Logged out")

def verify_endpoint(session):
    entities = ["UsrContainer", "UsrContainerEvent", "UsrContainerPOLink"]
    all_ok = True
    for entity in entities:
        url = f"{BASE_URL}/entity/{ENDPOINT_NAME}/{ENDPOINT_VERSION}/{entity}"
        resp = session.get(url, params={"$top": "1"})
        icon = "OK" if resp.status_code == 200 else "FAIL"
        print(f"  {icon}: {entity} -> {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"       Records: {len(data)}")
            if data: print(f"       Fields: {list(data[0].keys())[:8]}...")
        else:
            try: print(f"       {resp.json().get('message', resp.text[:200])}")
            except: print(f"       {resp.text[:200]}")
            all_ok = False
    return all_ok

def grant_access_sm201025(session):
    """Grant access to SB501000 using SM201025 (Access Rights by Role)."""
    soap_url = f"{BASE_URL}/Soap/SM201025.asmx"
    print(f"\n=== Grant SB501000 Access via SM201025 (Access Rights by Role) ===")
    login_soap(session, soap_url)

    for role in TARGET_ROLES:
        print(f"\n--- Processing role: {role} ---")
        
        # Step 1: Export current screen access for this role to find SB501000 NodeID
        print(f"  Step 1: Exporting current entity tree for role '{role}'...")
        export_body = f"""<tns:Export>
    <tns:commands>
      <tns:Command><tns:FieldName>Rolename</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>{role}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>Text</tns:FieldName><tns:ObjectName>Entities</tns:ObjectName></tns:Command>
      <tns:Command><tns:FieldName>Path</tns:FieldName><tns:ObjectName>Entities</tns:ObjectName></tns:Command>
      <tns:Command><tns:FieldName>NodeID</tns:FieldName><tns:ObjectName>Entities</tns:ObjectName></tns:Command>
    </tns:commands>
    <tns:topCount>500</tns:topCount>
    <tns:includeHeaders>true</tns:includeHeaders>
  </tns:Export>"""
        
        resp = session.post(soap_url, data=make_envelope(export_body), headers=soap_headers("Export"))
        print(f"  Export status: {resp.status_code}")
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            sb501_node = None
            for elem in root.iter():
                if elem.tag.endswith("ExportResult"):
                    row_count = 0
                    for row in elem:
                        values = [v.text or "" for v in row]
                        row_count += 1
                        # Look for SB501000
                        for v in values:
                            if v and "SB501000" in v:
                                print(f"  FOUND: {' | '.join(values)}")
                                # Get the NodeID (typically last column)
                                sb501_node = values[-1] if values[-1] else values[0]
                        # Print first few and any container-related
                        if row_count <= 3 or any("Container" in (v or "") or "SB5" in (v or "") for v in values):
                            print(f"  Row {row_count}: {' | '.join(values)}")
                    print(f"  Total: {row_count} rows")
                    break
            
            if sb501_node:
                print(f"\n  Step 2: Setting access for NodeID={sb501_node}...")
                # Navigate to the node and set Delete access
                submit_body = f"""<tns:Submit>
    <tns:commands>
      <tns:Command><tns:FieldName>Rolename</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>{role}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>NodeID</tns:FieldName><tns:ObjectName>Entities</tns:ObjectName><tns:Value>{sb501_node}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>RoleRight</tns:FieldName><tns:ObjectName>RoleEntities</tns:ObjectName><tns:Value>Delete</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>Save</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName></tns:Command>
    </tns:commands>
  </tns:Submit>"""
                resp = session.post(soap_url, data=make_envelope(submit_body), headers=soap_headers("Submit"))
                if resp.status_code == 200:
                    print(f"  OK: Access granted for '{role}' on SB501000")
                else:
                    print(f"  FAIL: Submit returned {resp.status_code}")
                    try:
                        fault_root = ET.fromstring(resp.text)
                        for elem in fault_root.iter():
                            if elem.tag.endswith("faultstring"):
                                print(f"  Fault: {elem.text[:300]}")
                                break
                    except: pass
            else:
                print(f"  WARNING: SB501000 not found in entity tree. It may not exist in SiteMap yet.")
                print(f"  Trying direct submit without NodeID...")
                
                # Alternative: try Submit with path-based selection
                # The RoleEntities view might accept direct screen ID references
                submit_body = f"""<tns:Submit>
    <tns:commands>
      <tns:Command><tns:FieldName>Rolename</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>{role}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>MemberName</tns:FieldName><tns:ObjectName>Entities</tns:ObjectName><tns:Value>SB501000</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>RoleRight</tns:FieldName><tns:ObjectName>RoleEntities</tns:ObjectName><tns:Value>Delete</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>Save</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName></tns:Command>
    </tns:commands>
  </tns:Submit>"""
                resp = session.post(soap_url, data=make_envelope(submit_body), headers=soap_headers("Submit"))
                if resp.status_code == 200:
                    print(f"  OK: Access granted via MemberName")
                else:
                    print(f"  FAIL: {resp.status_code}")
                    try:
                        fault_root = ET.fromstring(resp.text)
                        for elem in fault_root.iter():
                            if elem.tag.endswith("faultstring"):
                                print(f"  Fault: {elem.text[:300]}")
                                break
                    except: pass
        else:
            print(f"  Export failed: {resp.status_code}")
            try:
                fault_root = ET.fromstring(resp.text)
                for elem in fault_root.iter():
                    if elem.tag.endswith("faultstring"):
                        print(f"  Fault: {elem.text[:300]}")
                        break
            except: pass

    logout_soap(session, soap_url)

def main():
    if not USERNAME or not PASSWORD:
        print("ERROR: ACUMATICA_USERNAME and ACUMATICA_PASSWORD required"); sys.exit(1)

    mode = sys.argv[1] if len(sys.argv) > 1 else "--schema-only"
    session = requests.Session()

    try:
        if mode == "--schema-only":
            soap_url = f"{BASE_URL}/Soap/SM207060.asmx"
            print(f"=== SM207060 Schema Discovery ===")
            login_soap(session, soap_url)
            body = "<tns:GetSchema/>"
            resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("GetSchema"))
            if resp.status_code == 200:
                with open("/tmp/sm207060-schema.xml", "w") as f: f.write(resp.text)
                print("Schema saved to /tmp/sm207060-schema.xml")
            logout_soap(session, soap_url)

        elif mode == "--schema":
            # Discover access rights screens
            for sid in ["SM201030", "SM201025"]:
                soap_url = f"{BASE_URL}/Soap/{sid}.asmx"
                print(f"\n{'='*60}\nTrying {sid}\n{'='*60}")
                login_soap(session, soap_url)
                body = "<tns:GetSchema/>"
                resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("GetSchema"))
                if resp.status_code == 200:
                    with open(f"/tmp/{sid}-schema.xml", "w") as f: f.write(resp.text)
                    root = ET.fromstring(resp.text)
                    for elem in root.iter():
                        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                        if tag == "FieldName":
                            text = (elem.text or "").strip()
                            parent = None
                            for p in root.iter():
                                if elem in list(p): parent = p; break
                            obj = ""
                            if parent:
                                for sib in parent:
                                    stag = sib.tag.split("}")[-1] if "}" in sib.tag else sib.tag
                                    if stag == "ObjectName": obj = (sib.text or "").strip(); break
                            if text and obj: print(f"  {obj}.{text}")
                logout_soap(session, soap_url)

        elif mode == "--verify":
            print(f"=== Verify ContainerTracking Endpoint ===")
            login_rest(session)
            ok = verify_endpoint(session)
            logout_rest(session)
            if not ok: print("\nFAILED"); sys.exit(1)
            else: print("\nAll entities accessible!")

        elif mode == "--grant":
            grant_access_sm201025(session)
            print("\n=== Verifying endpoint after access grant ===")
            login_rest(session)
            ok = verify_endpoint(session)
            logout_rest(session)
            if ok: print("\nSUCCESS: All entities accessible!")
            else: print("\nWARNING: Some entities still not accessible.")

        else:
            print(f"Unknown mode: {mode}")
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
