#!/usr/bin/env python3
"""
Add custom DAC fields to the AesthetikWMS endpoint's SalesOrder entity via SM207060 SOAP API.

The AesthetikWMS endpoint (extending Default 24.200.001) was created via the UI.
This script navigates to SalesOrder in the entity tree and adds the Usr* fields.

Usage:
    ACUMATICA_URL=https://heritagefabrics.acumatica.com \
    ACUMATICA_USERNAME=api-bot \
    ACUMATICA_PASSWORD='pedhek-hugpid-4Gokge' \
    ACUMATICA_TENANT='Heritage Fabrics' \
    python3 scripts/heritage/add-so-custom-fields.py
"""

import os
import sys
import re
import urllib.request
import urllib.error
import http.cookiejar
import xml.sax.saxutils as saxutils

BASE_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME = os.environ.get("ACUMATICA_USERNAME", "api-bot")
PASSWORD = os.environ.get("ACUMATICA_PASSWORD", "")
COMPANY  = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")

SOAP_URL = f"{BASE_URL}/Soap/SM207060.asmx"
NS = "http://www.acumatica.com/typed/"
ENVELOPE = (
    f'<?xml version="1.0" encoding="utf-8"?>'
    f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
    f'xmlns:tns="{NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    f'<soap:Body>{{body}}</soap:Body></soap:Envelope>'
)

# Fields to add to SalesOrder entity
FIELDS = [
    {"name": "UsrWMSStatus",            "object": "Order Summary", "field": "UsrWMSStatus",            "type": "StringValue"},
    {"name": "UsrHubSpotDealId",        "object": "Order Summary", "field": "UsrHubSpotDealId",        "type": "StringValue"},
    {"name": "UsrComplianceHold",       "object": "Order Summary", "field": "UsrComplianceHold",       "type": "BooleanValue"},
    {"name": "UsrComplianceHoldReason", "object": "Order Summary", "field": "UsrComplianceHoldReason", "type": "StringValue"},
]


def soap_request(jar, action, body, label=""):
    full = ENVELOPE.format(body=body)
    req = urllib.request.Request(
        SOAP_URL, data=full.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}{action}"'},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    try:
        with opener.open(req, timeout=120) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label or action}] HTTP {e.code}: {raw[:500]}")
        raise


def check_fault(xml, label):
    if "<soap:Fault>" in xml or "faultstring" in xml:
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1).strip() if m else xml[:400]
        print(f"[{label}] SOAP Fault: {msg}")
        sys.exit(1)


def cmd(field, value=None, obj=None, commit=False):
    parts = [f"<tns:FieldName>{saxutils.escape(field)}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{saxutils.escape(obj)}</tns:ObjectName>")
    if value is not None:
        parts.append(f"<tns:Value>{saxutils.escape(str(value))}</tns:Value>")
    if commit:
        parts.append("<tns:Commit>true</tns:Commit>")
    return f"<tns:Command>{''.join(parts)}</tns:Command>"


def action(field, obj=None):
    parts = [f"<tns:FieldName>{saxutils.escape(field)}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{saxutils.escape(obj)}</tns:ObjectName>")
    return f'<tns:Command xsi:type="tns:Action">{"".join(parts)}</tns:Command>'


def key(field, value, obj=None):
    parts = [f"<tns:FieldName>{saxutils.escape(field)}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{saxutils.escape(obj)}</tns:ObjectName>")
    parts.append(f"<tns:Value>{saxutils.escape(str(value))}</tns:Value>")
    return f'<tns:Command xsi:type="tns:Key">{"".join(parts)}</tns:Command>'


def new_row(obj):
    return f'<tns:Command xsi:type="tns:NewRow"><tns:ObjectName>{saxutils.escape(obj)}</tns:ObjectName></tns:Command>'


def submit(commands):
    inner = "".join(commands)
    return f"<tns:Submit><tns:commands>{inner}</tns:commands></tns:Submit>"


def login():
    jar = http.cookiejar.CookieJar()
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password><tns:company>{saxutils.escape(COMPANY)}</tns:company></tns:Login>"
    xml = soap_request(jar, "Login", body, "Login")
    check_fault(xml, "Login")
    if "OK" not in xml:
        print(f"[Login] Unexpected response: {xml[:300]}")
        sys.exit(1)
    print("[Login] OK")
    return jar


def logout(jar):
    try:
        soap_request(jar, "Logout", "<tns:Logout/>", "Logout")
    except Exception:
        pass
    print("[Logout] Done")


def main():
    if not PASSWORD:
        print("[ERROR] Set ACUMATICA_PASSWORD env var")
        sys.exit(1)

    jar = login()
    try:
        # Step 1: Navigate to AesthetikWMS endpoint
        print("[1/4] Navigating to AesthetikWMS endpoint...")
        cmds = [
            # Set endpoint keys
            key("InterfaceName", "AesthetikWMS", "Endpoint"),
            key("GateVersion", "24.200.001", "Endpoint"),
            action("Cancel", "Endpoint"),
        ]
        xml = soap_request(jar, "Submit", submit(cmds), "Navigate")
        check_fault(xml, "Navigate")
        print("  Endpoint selected")

        # Step 2: Navigate to SalesOrder in the entity tree
        # Use Export to read the tree and find SalesOrder's key
        print("[2/4] Finding SalesOrder in entity tree...")
        export_body = (
            "<tns:Export>"
            "<tns:commands>"
            + cmd("Title", obj="EntityTree")
            + cmd("Key", obj="EntityTree")
            + "</tns:commands>"
            "<tns:topCount>200</tns:topCount>"
            "<tns:includeHeaders>true</tns:includeHeaders>"
            "</tns:Export>"
        )
        xml = soap_request(jar, "Export", export_body, "TreeExport")
        check_fault(xml, "TreeExport")

        # Parse tree nodes — find SalesOrder key
        rows = re.findall(r"<Row>(.*?)</Row>", xml, re.DOTALL)
        so_key = None
        for row in rows:
            values = re.findall(r"<Value>(.*?)</Value>", row)
            if len(values) >= 2:
                title, key_val = values[0], values[1]
                if title == "SalesOrder":
                    so_key = key_val
                    print(f"  Found SalesOrder: key={so_key}")
                    break

        if not so_key:
            print(f"  [WARN] SalesOrder not found. Got {len(rows)} rows from Export.")
            print(f"  Raw response (first 2000 chars): {xml[:2000]}")
            # Try alternate approach: just add fields directly without tree navigation
            # The endpoint was created extending Default — SalesOrder entity is inherited.
            # We may need to use "Extend Entity" action first, or add fields using
            # a Parameter key that references SalesOrder.
            print()
            print("  Trying alternate: skip tree nav, add fields with entity key parameter...")

        # Navigate to SalesOrder using its key
        cmds = [
            key("Key", so_key, "EntityTree"),
            cmd("Title", obj="EntityTree", commit=True),
        ]
        xml = soap_request(jar, "Submit", submit(cmds), "TreeNav")
        check_fault(xml, "TreeNav")
        print("  SalesOrder selected")

        # Step 3: Add each custom field
        print("[3/4] Adding custom fields...")
        for f in FIELDS:
            print(f"  + {f['name']} → {f['object']}.{f['field']} ({f['type']})")
            cmds = [
                # Add new row in Fields grid
                new_row("Fields"),
                # Set field name
                cmd("FieldName", f["name"], "Fields", commit=True),
                # Set mapped object (the Acumatica view/DAC)
                cmd("MappedObject", f["object"], "Fields", commit=True),
                # Set mapped field (the DAC field name)
                cmd("MappedField", f["field"], "Fields", commit=True),
                # Set field type
                cmd("FieldType", f["type"], "Fields", commit=True),
            ]
            xml = soap_request(jar, "Submit", submit(cmds), f"AddField:{f['name']}")
            check_fault(xml, f"AddField:{f['name']}")

        # Step 4: Save
        print("[4/4] Saving...")
        cmds = [action("Save", "Endpoint")]
        xml = soap_request(jar, "Submit", submit(cmds), "Save")
        check_fault(xml, "Save")
        print("  Saved!")

        print("\n[SUCCESS] Custom fields added to AesthetikWMS endpoint SalesOrder entity")
        print(f"  Verify: GET {BASE_URL}/entity/AesthetikWMS/24.200.001/SalesOrder/$adHocSchema")
        print("  Then update heritage-wms to use /entity/AesthetikWMS/24.200.001/ instead of /entity/default/24.200.001/")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
    finally:
        logout(jar)


if __name__ == "__main__":
    main()
