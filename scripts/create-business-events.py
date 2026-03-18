#!/usr/bin/env python3
"""
Create Business Events in Acumatica via the SM302050 SOAP Screen API.
Run via GitHub Actions (uses ACUMATICA_PROD_* secrets) or locally with env vars.

Usage:
    ACUMATICA_URL=... ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... python3 create-business-events.py

Events created:
    SO-AUTOALLOC-NEW        - New SO entry (PC/CO)  -> trigger=entry
    SO-AUTOALLOC-HOLD       - Hold removed (PC/CO)  -> trigger=remove-hold
    SO-AUTOALLOC-BACKORDER  - Backorder cleared (PC/CO) -> trigger=remove-backorder

Webhook URL: https://webhook-router-production-e161.up.railway.app/webhook/acumatica/allocate-inventory
"""

import os
import sys
import re
import urllib.request
import urllib.error
import http.cookiejar
import json

BASE_URL     = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME     = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD     = os.environ.get("ACUMATICA_PASSWORD", "")
COMPANY      = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")
SCHEMA_ONLY  = os.environ.get("SCHEMA_ONLY", "false").lower() == "true"
DRY_RUN      = os.environ.get("DRY_RUN", "false").lower() == "true"

WEBHOOK_URL  = "https://webhook-router-production-e161.up.railway.app/webhook/acumatica/allocate-inventory"

# Build SOAP URL.
# Acumatica multi-tenant: company in URL path gives HTTP 401 (requires pre-auth).
# Root path /Soap/<ScreenID>.asmx accepts the SOAP Login operation directly;
# company is determined from the Login credentials server-side.
SOAP_URL = f"{BASE_URL}/Soap/SM302050.asmx"
print(f"SOAP URL: {SOAP_URL}")

# ── SOAP helpers ─────────────────────────────────────────────────────────────

NS = "http://www.acumatica.com/typed/"
ENVELOPE_OPEN  = f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body>'
ENVELOPE_CLOSE = "</soap:Body></soap:Envelope>"


def soap_request(cookie_jar, action, body, label=""):
    full_body = (ENVELOPE_OPEN + body + ENVELOPE_CLOSE).encode("utf-8")
    req = urllib.request.Request(
        SOAP_URL,
        data=full_body,
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{NS}{action}"',
        },
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    try:
        with opener.open(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label or action}] HTTP {e.code}: {raw[:500]}")
        sys.exit(1)
    return raw


def check_fault(xml, label):
    if "<soap:Fault>" in xml or "faultstring" in xml:
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1).strip() if m else xml[:400]
        print(f"[{label}] SOAP Fault: {msg}")
        sys.exit(1)


# ── Login / Logout ─────────────────────────────────────────────────────────

def login():
    jar = http.cookiejar.CookieJar()
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password></tns:Login>"
    xml = soap_request(jar, "Login", body, "Login")
    check_fault(xml, "Login")
    m = re.search(r"<Code>(.*?)</Code>", xml)
    code = m.group(1) if m else "?"
    if code != "OK":
        print(f"[Login] Failed — Code={code}")
        m2 = re.search(r"<Message>(.*?)</Message>", xml)
        print(f"         Message: {m2.group(1) if m2 else xml[:300]}")
        sys.exit(1)
    print(f"[Login] OK (company={COMPANY})")
    return jar


def logout(jar):
    body = "<tns:Logout/>"
    soap_request(jar, "Logout", body, "Logout")
    print("[Logout] Done")


# ── GetSchema — discover field/container names ────────────────────────────

def get_schema(jar):
    body = "<tns:GetSchema/>"
    xml = soap_request(jar, "GetSchema", body, "GetSchema")
    check_fault(xml, "GetSchema")
    return xml


def print_schema(xml):
    """Extract and print Container→Field hierarchy from schema XML."""
    # Parse containers and their fields using a simple state machine
    # The schema XML has nested <Container> elements with <Fields>/<Children>
    print("\n=== SM302050 Schema (Raw Container→Field Map) ===")

    # Find all Container blocks with their Name and nested Fields
    container_pattern = r"<Container>(.*?)</Container>"
    name_pattern = r"<Name>(.*?)</Name>"
    field_pattern = r"<Field>(.*?)</Field>"
    display_pattern = r"<DisplayName>(.*?)</DisplayName>"
    object_pattern = r"<ObjectName>(.*?)</ObjectName>"

    # Extract the GetSchemaResult content
    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", xml, re.DOTALL)
    if not schema_match:
        print("  Could not find GetSchemaResult in response")
        print(f"  Response length: {len(xml)}")
        print(f"  Response preview: {xml[:500]}")
        print("=== End Schema ===\n")
        return

    schema = schema_match.group(1)

    # Print all unique ObjectName values (these are the view names for Commands)
    objects = re.findall(object_pattern, schema)
    print(f"\nObjectName values (view names for SOAP Commands):")
    for o in sorted(set(objects)):
        print(f"  ObjectName: {o}")

    # Print all Field elements with their ObjectName context
    fields = re.findall(r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>", schema, re.DOTALL)
    if not fields:
        # Try without ObjectName
        fields_only = re.findall(r"<FieldName>(.*?)</FieldName>", schema)
        print(f"\nField names (no ObjectName context, first 80):")
        for f in fields_only[:80]:
            print(f"  Field: {f}")
    else:
        print(f"\nField→ObjectName pairs ({len(fields)} fields):")
        for fname, oname in fields[:80]:
            print(f"  {oname}.{fname}")

    # Also extract container names for reference
    containers = re.findall(r"<Container>.*?<Name>(.*?)</Name>", schema, re.DOTALL)
    if containers:
        print(f"\nContainer names:")
        for c in sorted(set(containers)):
            print(f"  Container: {c}")

    # Print DisplayName mappings for human-readable field labels
    displays = re.findall(r"<FieldName>(.*?)</FieldName>.*?<DisplayName>(.*?)</DisplayName>", schema, re.DOTALL)
    if displays:
        print(f"\nField→DisplayName (first 40):")
        for fname, dname in displays[:40]:
            print(f"  {fname} = \"{dname}\"")

    print("=== End Schema ===\n")


# ── Build SOAP commands ───────────────────────────────────────────────────

def cmd(field, value, obj=None, commit=False):
    """Build a <tns:Command> element."""
    parts = [f"<tns:FieldName>{field}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{obj}</tns:ObjectName>")
    if value is not None:
        parts.append(f"<tns:Value>{value}</tns:Value>")
    if commit:
        parts.append("<tns:Commit>true</tns:Commit>")
    return f"<tns:Command>{''.join(parts)}</tns:Command>"


def action_cmd(field, obj=None):
    """An action (button) command — no Value."""
    return cmd(field, None, obj)


def build_submit(commands):
    inner = "".join(commands)
    return f"<tns:Submit><tns:commands>{inner}</tns:commands></tns:Submit>"


# ── Event definitions ─────────────────────────────────────────────────────

EVENTS = [
    {
        "event_id":    "SO-AUTOALLOC-NEW",
        "description": "Auto-allocate inventory on new SO entry (PC/CO order types)",
        "screen_id":   "SO301000",
        # RaiseEventOn values: "Record Inserted", "Record Updated", "Record Deleted",
        #                      "Field Changed", "Condition Satisfied"
        "raise_on":    "Record Inserted",
        "trigger":     "entry",
        # Conditions: OrderType in [PC, CO]
        "conditions": [
            {"field": "OrderType", "condition": "Equal", "value": "PC"},
            {"field": "OrderType", "condition": "Equal", "value": "CO", "or": True},
        ],
    },
    {
        "event_id":    "SO-AUTOALLOC-HOLD",
        "description": "Auto-allocate inventory when Hold removed (PC/CO order types)",
        "screen_id":   "SO301000",
        "raise_on":    "Field Changed",
        "field_name":  "Hold",
        "field_val":   "False",
        "trigger":     "remove-hold",
        "conditions": [
            {"field": "OrderType", "condition": "Equal", "value": "PC"},
            {"field": "OrderType", "condition": "Equal", "value": "CO", "or": True},
        ],
    },
    {
        "event_id":    "SO-AUTOALLOC-BACKORDER",
        "description": "Auto-allocate inventory when backorder flag cleared (PC/CO order types)",
        "screen_id":   "SO301000",
        "raise_on":    "Field Changed",
        "field_name":  "IsBackOrder",
        "field_val":   "False",
        "trigger":     "remove-backorder",
        "conditions": [
            {"field": "OrderType", "condition": "Equal", "value": "PC"},
            {"field": "OrderType", "condition": "Equal", "value": "CO", "or": True},
        ],
    },
]


# ── Create a single event ─────────────────────────────────────────────────

def create_event(jar, ev, schema_xml=None):
    eid = ev["event_id"]
    print(f"[{eid}] Creating...")

    if DRY_RUN:
        print(f"[{eid}] DRY RUN — skipping SOAP Submit")
        return True

    commands = []

    # 1. New row on the Events grid / header
    commands.append(action_cmd("Insert", "Events"))

    # 2. Set header fields
    commands.append(cmd("EventID",          eid,              "Events"))
    commands.append(cmd("Description",      ev["description"], "Events"))
    commands.append(cmd("ScreenID",         ev["screen_id"],  "Events"))
    commands.append(cmd("RaiseEventOn",     ev["raise_on"],   "Events"))
    commands.append(cmd("IsActive",         "True",           "Events"))

    # 3. If Field Changed, set the field name + new value
    if ev.get("field_name"):
        commands.append(cmd("FieldName",    ev["field_name"], "Events"))
        commands.append(cmd("NewValue",     ev["field_val"],  "Events"))

    # 4. Add subscriber (Webhook)
    commands.append(action_cmd("Insert", "Subscribers"))
    commands.append(cmd("SubType",   "Webhook",   "Subscribers"))
    commands.append(cmd("Address",   WEBHOOK_URL, "Subscribers"))
    # Pass trigger as HTTP header in the body template
    payload = json.dumps({"OrderType": "={{OrderType}}", "OrderNbr": "={{OrderNbr}}", "Trigger": ev["trigger"]})
    commands.append(cmd("BodyTemplate",  payload,      "Subscribers", commit=True))
    commands.append(cmd("IsActive",      "True",       "Subscribers"))

    # 5. Add conditions
    for i, cond in enumerate(ev.get("conditions", [])):
        commands.append(action_cmd("Insert", "EventConditions"))
        commands.append(cmd("FieldName",  cond["field"],     "EventConditions"))
        commands.append(cmd("Condition",  cond["condition"], "EventConditions"))
        commands.append(cmd("Value",      cond["value"],     "EventConditions"))
        if cond.get("or"):
            commands.append(cmd("Operator", "Or", "EventConditions"))
        commands.append(cmd("IsActive", "True", "EventConditions", commit=(i == len(ev["conditions"]) - 1)))

    # 6. Save
    commands.append(action_cmd("Save"))

    body = build_submit(commands)
    xml = soap_request(jar, "Submit", body, eid)

    if "<soap:Fault>" in xml or "faultstring" in xml:
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1)[:500] if m else xml[:500]
        print(f"[{eid}] SOAP Fault: {msg}")
        # Don't exit — try remaining events, return failure
        return False

    if "errorMessage" in xml.lower() or "isError>true" in xml:
        m = re.search(r"<Message>(.*?)</Message>", xml, re.DOTALL)
        print(f"[{eid}] Error in response: {m.group(1)[:300] if m else xml[:300]}")
        return False

    print(f"[{eid}] Created OK")
    return True


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    if not USERNAME or not PASSWORD:
        print("Error: ACUMATICA_USERNAME and ACUMATICA_PASSWORD must be set")
        sys.exit(1)

    print(f"DRY_RUN: {DRY_RUN}, SCHEMA_ONLY: {SCHEMA_ONLY}")

    jar = login()
    schema_xml = None

    try:
        # Always fetch schema to discover field names (helps debug if Submit fails)
        print("[GetSchema] Fetching SM302050 field structure...")
        schema_xml = get_schema(jar)
        print_schema(schema_xml)

        if SCHEMA_ONLY:
            print("SCHEMA_ONLY=true — exiting after schema dump")
            return

        results = []
        for ev in EVENTS:
            ok = create_event(jar, ev, schema_xml)
            results.append((ev["event_id"], ok))

        print("\n=== Results ===")
        all_ok = True
        for eid, ok in results:
            status = "OK" if ok else "FAILED"
            print(f"  {eid}: {status}")
            if not ok:
                all_ok = False

        if not all_ok:
            sys.exit(1)

    finally:
        logout(jar)


if __name__ == "__main__":
    main()
