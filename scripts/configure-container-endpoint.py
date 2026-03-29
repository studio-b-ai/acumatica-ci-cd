#!/usr/bin/env python3
"""Grant SB501000 access via SM201030 (Access Rights by Screen) SOAP API."""
import os, sys, requests, xml.etree.ElementTree as ET

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", os.environ.get("ACUMATICA_PROD_USERNAME", ""))
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", os.environ.get("ACUMATICA_PROD_PASSWORD", ""))
TENANT = os.environ.get("ACUMATICA_TENANT", os.environ.get("ACUMATICA_PROD_TENANT", "Heritage Fabrics"))

TNS = "http://www.acumatica.com/typed/"
SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"

def make_envelope(body_xml):
    return f'<?xml version="1.0" encoding="utf-8"?>\n<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">\n  <soap:Body>\n    {body_xml}\n  </soap:Body>\n</soap:Envelope>'

def soap_headers(action):
    return {"SOAPAction": f'"{TNS}{action}"', "Content-Type": "text/xml; charset=utf-8"}

mode = sys.argv[1] if len(sys.argv) > 1 else "--schema"
session = requests.Session()

# Try multiple screen IDs for Access Rights
SCREENS_TO_TRY = ["SM201030", "SM201025"]

for screen_id in SCREENS_TO_TRY:
    soap_url = f"{BASE_URL}/Soap/{screen_id}.asmx"
    print(f"\n{'='*60}")
    print(f"Trying {screen_id} at {soap_url}")
    print(f"{'='*60}")
    
    # Login
    body = f'<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>'
    resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("Login"))
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} — screen may not exist")
        continue
    print("OK: Logged in")
    
    if mode == "--schema":
        # Get schema
        body = "<tns:GetSchema/>"
        resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("GetSchema"))
        if resp.status_code == 200:
            with open(f"/tmp/{screen_id}-schema.xml", "w") as f:
                f.write(resp.text)
            print(f"Schema saved to /tmp/{screen_id}-schema.xml")
            
            root = ET.fromstring(resp.text)
            result = None
            for elem in root.iter():
                if elem.tag.endswith("GetSchemaResult"):
                    result = elem
                    break
            
            if result is not None:
                # Print condensed field/object pairs
                print("\nKey fields:")
                for elem in result.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "FieldName":
                        text = (elem.text or "").strip()
                        if text:
                            # Find sibling ObjectName
                            parent = None
                            for p in result.iter():
                                if elem in list(p):
                                    parent = p
                                    break
                            obj = ""
                            if parent is not None:
                                for sib in parent:
                                    stag = sib.tag.split("}")[-1] if "}" in sib.tag else sib.tag
                                    if stag == "ObjectName":
                                        obj = (sib.text or "").strip()
                                        break
                            print(f"  {obj}.{text}")
        else:
            print(f"GetSchema failed: {resp.status_code}")
    
    elif mode == "--grant":
        # First get schema to understand field names
        body = "<tns:GetSchema/>"
        resp = session.post(soap_url, data=make_envelope(body), headers=soap_headers("GetSchema"))
        if resp.status_code != 200:
            print(f"GetSchema failed: {resp.status_code}")
            body = "<tns:Logout/>"
            session.post(soap_url, data=make_envelope(body), headers=soap_headers("Logout"))
            continue
        
        with open(f"/tmp/{screen_id}-schema.xml", "w") as f:
            f.write(resp.text)
        print("Schema saved")
        
        # Parse the schema to find all ObjectNames and FieldNames
        root = ET.fromstring(resp.text)
        result = None
        for elem in root.iter():
            if elem.tag.endswith("GetSchemaResult"):
                result = elem
                break
        
        if result is not None:
            # Collect all unique ObjectName.FieldName pairs
            pairs = set()
            for elem in result.iter():
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                if tag == "FieldName":
                    text = (elem.text or "").strip()
                    parent = None
                    for p in result.iter():
                        if elem in list(p):
                            parent = p
                            break
                    obj = ""
                    if parent is not None:
                        for sib in parent:
                            stag = sib.tag.split("}")[-1] if "}" in sib.tag else sib.tag
                            if stag == "ObjectName":
                                obj = (sib.text or "").strip()
                                break
                    if text and obj:
                        pairs.add(f"{obj}.{text}")
            
            print(f"\nAll {len(pairs)} field references:")
            for p in sorted(pairs):
                print(f"  {p}")
        
        # Try Export to see current state
        print(f"\nExporting current roles for SB501000...")
        # The exact command names depend on the schema — try common patterns
        # SM201030 typically has: ScreenID on header, Roles grid with RoleName + Access
        # SM201025 typically has: RoleName on header, Screens grid with ScreenID + Access
        
        if screen_id == "SM201030":
            # Access Rights by Screen: header=ScreenID, grid=roles
            export_body = """<tns:Export>
    <tns:commands>
      <tns:Command><tns:FieldName>ScreenID</tns:FieldName><tns:ObjectName>ScreenRoles</tns:ObjectName><tns:Value>SB501000</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>Rolename</tns:FieldName><tns:ObjectName>ScreenRoles</tns:ObjectName></tns:Command>
      <tns:Command><tns:FieldName>AccessRights</tns:FieldName><tns:ObjectName>ScreenRoles</tns:ObjectName></tns:Command>
    </tns:commands>
    <tns:topCount>50</tns:topCount>
    <tns:includeHeaders>true</tns:includeHeaders>
  </tns:Export>"""
        else:
            export_body = """<tns:Export>
    <tns:commands>
      <tns:Command><tns:FieldName>Rolename</tns:FieldName><tns:ObjectName>Roles</tns:ObjectName><tns:Value>Administrator</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
      <tns:Command><tns:FieldName>ScreenID</tns:FieldName><tns:ObjectName>RoleScreenAccess</tns:ObjectName></tns:Command>
      <tns:Command><tns:FieldName>AccessRights</tns:FieldName><tns:ObjectName>RoleScreenAccess</tns:ObjectName></tns:Command>
    </tns:commands>
    <tns:topCount>50</tns:topCount>
    <tns:includeHeaders>true</tns:includeHeaders>
  </tns:Export>"""
        
        resp = session.post(soap_url, data=make_envelope(export_body), headers=soap_headers("Export"))
        print(f"Export status: {resp.status_code}")
        if resp.status_code == 200:
            exp_root = ET.fromstring(resp.text)
            for elem in exp_root.iter():
                if elem.tag.endswith("ExportResult"):
                    row_count = 0
                    for row in elem:
                        values = [v.text or "" for v in row]
                        print(f"  {' | '.join(values)}")
                        row_count += 1
                    print(f"  ({row_count} rows)")
                    break
        else:
            try:
                fault_root = ET.fromstring(resp.text)
                for elem in fault_root.iter():
                    if elem.tag.endswith("faultstring"):
                        print(f"  Fault: {elem.text[:300]}")
                        break
            except Exception:
                print(f"  {resp.text[:500]}")
    
    # Logout
    body = "<tns:Logout/>"
    session.post(soap_url, data=make_envelope(body), headers=soap_headers("Logout"))
    print("OK: Logged out")

