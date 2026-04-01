#!/usr/bin/env python3
"""Call GetSchema on SM207060 to find all SOAP ObjectNames."""
import os, sys, requests, xml.etree.ElementTree as ET

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
TENANT   = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"
TNS      = "http://www.acumatica.com/typed/"
SOAP_NS  = "http://schemas.xmlsoap.org/soap/envelope/"

def make_envelope(body_xml):
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_NS}" xmlns:tns="{TNS}">'
        f'<soap:Body>{body_xml}</soap:Body>'
        f'</soap:Envelope>'
    )

def soap_headers(action):
    return {"SOAPAction": f'"{TNS}{action}"', "Content-Type": "text/xml; charset=utf-8"}

session = requests.Session()

# Login
body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Login"))
if resp.status_code != 200:
    print(f"Login failed: {resp.status_code}")
    sys.exit(1)
print("Logged in")

# Navigate to ContainerTracking endpoint first
body = """<tns:Submit>
  <tns:commands>
    <tns:Command><tns:FieldName>InterfaceName</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>ContainerTracking</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
    <tns:Command><tns:FieldName>GateVersion</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>24.200.001</tns:Value><tns:Commit>true</tns:Commit></tns:Command>
  </tns:commands>
</tns:Submit>"""
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
print(f"Navigate: HTTP {resp.status_code}")

# GetSchema — empty objectName to get all objects
body = "<tns:GetSchema><tns:objectName></tns:objectName></tns:GetSchema>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("GetSchema"))
print(f"GetSchema: HTTP {resp.status_code}")

if resp.status_code == 200:
    # Parse and print all Object names
    root = ET.fromstring(resp.text)
    for el in root.iter():
        if el.tag.endswith("Schema"):
            for obj in el:
                obj_name = obj.get("ObjectName") or obj.get("name") or obj.tag
                print(f"  Object: {obj_name}")
                for field in obj:
                    fname = field.get("FieldName") or field.get("name") or field.tag
                    print(f"    Field: {fname}")
else:
    print(f"  Error: {resp.text[:500]}")

# Also try with "Endpoint" as the object name
print("\n--- GetSchema for 'Endpoint' ---")
body = "<tns:GetSchema><tns:objectName>Endpoint</tns:objectName></tns:GetSchema>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("GetSchema"))
print(f"HTTP {resp.status_code}")
if resp.status_code == 200:
    root = ET.fromstring(resp.text)
    print(resp.text[:2000])
else:
    print(resp.text[:500])

# Logout
session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
print("Done")
