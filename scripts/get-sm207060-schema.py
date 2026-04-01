#!/usr/bin/env python3
"""Diagnose SM207060 SOAP — verify insertNew creates entity in ContainerTracking vs new endpoint."""
import os, sys, requests, xml.etree.ElementTree as ET, re

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
TENANT   = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"
TNS      = "http://www.acumatica.com/typed/"
SOAP_NS  = "http://schemas.xmlsoap.org/soap/envelope/"

def make_envelope(body_xml):
    return (f'<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">'
            f'<soap:Body>{body_xml}</soap:Body></soap:Envelope>')

def soap_headers(action):
    return {"SOAPAction": f'"{TNS}{action}"', "Content-Type": "text/xml; charset=utf-8"}

def extract_value(xml_text, field_name):
    """Extract a field value from the SOAP response."""
    # Look for the field value
    pattern = rf'<FieldName>{field_name}</FieldName>.*?<Value>(.*?)</Value>'
    m = re.search(pattern, xml_text, re.DOTALL)
    return m.group(1) if m else None

session = requests.Session()

# Login
body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Login"))
print(f"Login: HTTP {resp.status_code}")

# Navigate to ContainerTracking
body = """<tns:Submit><tns:commands>
  <tns:Command><tns:FieldName>InterfaceName</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>ContainerTracking</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
  <tns:Command><tns:FieldName>GateVersion</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>24.200.001</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
</tns:commands></tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"Navigate to ContainerTracking: HTTP {resp.status_code}")
iface_val = extract_value(resp.text, "InterfaceName")
print(f"  InterfaceName after navigate = '{iface_val}'")

# Now call insertNew and check what endpoint we're on AFTER
print("\n--- Calling insertNew on Endpoint ---")
body = """<tns:Submit><tns:commands>
  <tns:Command><tns:FieldName>insertNew</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Commit>true</tns:Commit></tns:Command>
</tns:commands></tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"insertNew: HTTP {resp.status_code}")
iface_val = extract_value(resp.text, "InterfaceName")
ver_val = extract_value(resp.text, "GateVersion")
print(f"  InterfaceName AFTER insertNew = '{iface_val}'")
print(f"  GateVersion AFTER insertNew = '{ver_val}'")
# Check if a dialog opened
has_dialog = "CreateEntityView" in resp.text or "ObjectName" in resp.text
print(f"  Response has dialog/ObjectName = {has_dialog}")
print(f"  Response snippet: {resp.text[200:800]}")

# Cancel the dialog (if any)
body = """<tns:Submit><tns:commands>
  <tns:Command><tns:FieldName>Cancel</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Commit>true</tns:Commit></tns:Command>
</tns:commands></tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"\nCancel: HTTP {resp.status_code}")
iface_val = extract_value(resp.text, "InterfaceName")
print(f"  InterfaceName after Cancel = '{iface_val}'")

# Re-navigate and test deleteNode for Container
print("\n--- Re-navigating and testing deleteNode ---")
body = """<tns:Submit><tns:commands>
  <tns:Command><tns:FieldName>InterfaceName</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>ContainerTracking</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
  <tns:Command><tns:FieldName>GateVersion</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>24.200.001</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
</tns:commands></tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"Navigate: HTTP {resp.status_code}")

# Try deleteNode with Value=Container
body = """<tns:Submit><tns:commands>
  <tns:Command><tns:FieldName>deleteNode</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>Container</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
</tns:commands></tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"deleteNode Container: HTTP {resp.status_code}")
if resp.status_code != 200:
    root = ET.fromstring(resp.text)
    for el in root.iter():
        if el.tag.endswith("faultstring"):
            print(f"  Fault: {el.text[:300]}")
else:
    iface_val = extract_value(resp.text, "InterfaceName")
    print(f"  OK! InterfaceName = '{iface_val}'")
    print(f"  Response snippet: {resp.text[200:600]}")

session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
print("\nDone")
