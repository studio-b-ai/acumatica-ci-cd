#!/usr/bin/env python3
"""Save full SM207060 GetSchema to file artifact + try alternate navigation field names."""
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
def extract_values(xml_text):
    """Extract all FieldName/Value pairs from response."""
    pairs = {}
    root = ET.fromstring(xml_text)
    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag == "Field":
            fname = None; fval = None
            for child in el:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag == "FieldName": fname = child.text
                if ctag == "Value": fval = child.text
            if fname:
                pairs[fname] = fval
    return pairs

session = requests.Session()

# Login
body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{TENANT}</tns:company></tns:Login>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Login"))
print(f"Login: HTTP {resp.status_code}")

# GetSchema — save FULL response to file
body = "<tns:GetSchema/>"
resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("GetSchema"))
print(f"GetSchema: HTTP {resp.status_code} / {len(resp.text)} bytes")
with open("/tmp/sm207060-schema.xml", "w") as f:
    f.write(resp.text)
print("Schema saved to /tmp/sm207060-schema.xml")

# Print all FieldName/ObjectName from Fields section
root = ET.fromstring(resp.text)
print("\n=== All Fields (ObjectName.FieldName) ===")
for el in root.iter():
    tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
    if tag == "Field":
        fname = None; oname = None; vtype = None
        for child in el:
            ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if ctag == "FieldName": fname = child.text
            if ctag == "ObjectName": oname = child.text
            if ctag == "ViewTypeName": vtype = child.text
        if fname and oname:
            print(f"  {oname}.{fname}")

# Try multiple navigation approaches
print("\n=== Testing navigation alternatives ===")
nav_attempts = [
    ("Name + Version", [("Name", "ContainerTracking"), ("Version", "24.200.001")]),
    ("InterfaceName alone", [("InterfaceName", "ContainerTracking")]),
    ("Name alone", [("Name", "ContainerTracking")]),
]

for label, fields in nav_attempts:
    cmds = ""
    for fname, val in fields:
        cmds += f"""<tns:Command><tns:FieldName>{fname}</tns:FieldName><tns:ObjectName>Endpoint</tns:ObjectName><tns:Value>{val}</tns:Value><tns:Commit>true</tns:Commit></tns:Command>"""
    body = f"<tns:Submit><tns:commands>{cmds}</tns:commands></tns:Submit>"
    resp = session.post(SOAP_URL, data=make_envelope(body), headers=soap_headers("Submit"))
    pairs = extract_values(resp.text)
    print(f"\n  [{label}]: HTTP {resp.status_code}")
    for k, v in sorted(pairs.items())[:8]:
        print(f"    {k} = {v!r}")

session.post(SOAP_URL, data=make_envelope("<tns:Logout/>"), headers=soap_headers("Logout"))
print("\nDone")
