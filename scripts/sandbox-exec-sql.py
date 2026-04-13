#!/usr/bin/env python3
"""
Execute arbitrary SQL on Acumatica Sandbox via the SOAP Screen API.
Targets SM206540 (Database Scripts) which allows direct SQL execution.

SAFETY: This script ONLY connects to the sandbox instance.
        Production and test credentials are not accepted.

Usage:
    ACUMATICA_SANDBOX_URL=... ACUMATICA_SANDBOX_USERNAME=... \
    ACUMATICA_SANDBOX_PASSWORD=... ACUMATICA_SANDBOX_TENANT=... \
    python3 scripts/sandbox-exec-sql.py

Set SCHEMA_ONLY=true to dump the screen field layout without executing SQL.
"""

import os
import sys
import re
import urllib.request
import urllib.error
import http.cookiejar

# ── Configuration (sandbox ONLY) ─────────────────────────────────────────────

BASE_URL  = os.environ.get("ACUMATICA_SANDBOX_URL", "")
USERNAME  = os.environ.get("ACUMATICA_SANDBOX_USERNAME", "")
PASSWORD  = os.environ.get("ACUMATICA_SANDBOX_PASSWORD", "")
COMPANY   = os.environ.get("ACUMATICA_SANDBOX_TENANT", "")
SCHEMA_ONLY = os.environ.get("SCHEMA_ONLY", "false").lower() == "true"

# The SQL to execute — set via env var or use default
SQL_SCRIPT = os.environ.get("SQL_SCRIPT", """
IF OBJECT_ID('dbo.KNMCSalesPriceSyncData', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.KNMCSalesPriceSyncData;
    PRINT 'Dropped table KNMCSalesPriceSyncData';
END
ELSE
BEGIN
    PRINT 'Table KNMCSalesPriceSyncData does not exist — no action taken';
END
""").strip()

# Safety: reject anything that looks like production
if BASE_URL and "sandbox" not in BASE_URL.lower():
    print(f"SAFETY: URL does not contain 'sandbox': {BASE_URL}")
    print("This script ONLY targets sandbox. Aborting.")
    sys.exit(1)

# Try multiple screen IDs — Acumatica versions vary
SCREEN_IDS = ["SM206540", "SM206530"]

# ── SOAP helpers ─────────────────────────────────────────────────────────────

NS = "http://www.acumatica.com/typed/"
ENVELOPE_OPEN  = f'<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="{NS}"><soap:Body>'
ENVELOPE_CLOSE = "</soap:Body></soap:Envelope>"

SOAP_URL = ""  # Set after screen discovery


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
        with opener.open(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"[{label or action}] HTTP {e.code}: {raw[:800]}")
        return None
    return raw


def check_fault(xml, label):
    if xml and ("<soap:Fault>" in xml or "faultstring" in xml):
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1).strip() if m else xml[:400]
        print(f"[{label}] SOAP Fault: {msg}")
        return True
    return False


# ── Login / Logout ─────────────────────────────────────────────────────────

def login(jar):
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password></tns:Login>"
    xml = soap_request(jar, "Login", body, "Login")
    if xml is None:
        print("[Login] No response")
        sys.exit(1)
    if check_fault(xml, "Login"):
        sys.exit(1)
    m = re.search(r"<Code>(.*?)</Code>", xml)
    code = m.group(1) if m else "?"
    if code != "OK":
        print(f"[Login] Failed — Code={code}")
        m2 = re.search(r"<Message>(.*?)</Message>", xml)
        print(f"         Message: {m2.group(1) if m2 else xml[:300]}")
        sys.exit(1)
    print(f"[Login] OK (company={COMPANY})")


def logout(jar):
    body = "<tns:Logout/>"
    soap_request(jar, "Logout", body, "Logout")
    print("[Logout] Done")


# ── Schema discovery ─────────────────────────────────────────────────────────

def get_schema(jar):
    body = "<tns:GetSchema/>"
    xml = soap_request(jar, "GetSchema", body, "GetSchema")
    if xml is None:
        return None
    if check_fault(xml, "GetSchema"):
        return None
    return xml


def print_schema(xml, screen_id):
    print(f"\n=== {screen_id} Schema ===")
    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", xml, re.DOTALL)
    if not schema_match:
        print("  Could not find GetSchemaResult")
        print(f"  Response preview: {xml[:500]}")
        return

    schema = schema_match.group(1)

    # ObjectName values
    objects = re.findall(r"<ObjectName>(.*?)</ObjectName>", schema)
    print(f"\nObjectName values:")
    for o in sorted(set(objects)):
        print(f"  {o}")

    # Field→Object pairs
    fields = re.findall(
        r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>",
        schema, re.DOTALL
    )
    if fields:
        print(f"\nFields ({len(fields)}):")
        for fname, oname in fields:
            print(f"  {oname}.{fname}")
    else:
        field_names = re.findall(r"<FieldName>(.*?)</FieldName>", schema)
        print(f"\nField names ({len(field_names)}):")
        for f in field_names:
            print(f"  {f}")

    # Actions
    actions = re.findall(r"<Action>.*?<FieldName>(.*?)</FieldName>.*?</Action>", schema, re.DOTALL)
    if actions:
        print(f"\nActions:")
        for a in actions:
            print(f"  {a}")

    # Raw first 6000 chars
    print(f"\n--- Raw ({len(schema)} chars, first 6000) ---")
    print(schema[:6000])
    print("--- End Raw ---")
    print(f"=== End {screen_id} Schema ===\n")


# ── SOAP command builders ────────────────────────────────────────────────────

def cmd(field, value, obj=None, commit=False):
    parts = [f"<tns:FieldName>{field}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{obj}</tns:ObjectName>")
    if value is not None:
        # XML-escape the value
        escaped = (value
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))
        parts.append(f"<tns:Value>{escaped}</tns:Value>")
    if commit:
        parts.append("<tns:Commit>true</tns:Commit>")
    return f"<tns:Command>{''.join(parts)}</tns:Command>"


def action_cmd(field, obj=None):
    return cmd(field, None, obj)


def build_submit(commands):
    inner = "".join(commands)
    return f"<tns:Submit><tns:commands>{inner}</tns:commands></tns:Submit>"


# ── Execute SQL ──────────────────────────────────────────────────────────────

def execute_sql(jar, schema_xml):
    """
    Try to fill in the SQL script field and click Execute/Save.
    The exact field names depend on the screen schema — we discover them dynamically.
    """
    print(f"[SQL] Script to execute:\n{SQL_SCRIPT}\n")

    # Try common field name patterns for the SQL text area
    # SM206540 typically has: Script (text area), ScriptName, etc.
    schema = schema_xml or ""

    # Extract all field→object pairs from schema
    fields = re.findall(
        r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>",
        schema, re.DOTALL
    )
    field_map = {fname: oname for fname, oname in fields}

    # Look for SQL-related fields
    sql_fields = [(f, o) for f, o in fields if any(
        kw in f.lower() for kw in ["script", "sql", "query", "command", "text"]
    )]
    print(f"[SQL] Candidate SQL fields: {sql_fields}")

    if not sql_fields:
        print("[SQL] ERROR: Could not find any SQL-related field in schema.")
        print("[SQL] Run with SCHEMA_ONLY=true to inspect the field layout.")
        return False

    # Try the first matching field
    sql_field, sql_obj = sql_fields[0]
    print(f"[SQL] Using field: {sql_obj}.{sql_field}")

    # Look for an Execute/Run action
    actions = re.findall(r"<Action>.*?<FieldName>(.*?)</FieldName>.*?</Action>", schema, re.DOTALL)
    exec_actions = [a for a in actions if any(
        kw in a.lower() for kw in ["execute", "run", "process", "save"]
    )]
    print(f"[SQL] Candidate actions: {exec_actions}")

    commands = [
        cmd(sql_field, SQL_SCRIPT, sql_obj, commit=True),
    ]

    # Add execute action if found, otherwise try Save
    if exec_actions:
        commands.append(action_cmd(exec_actions[0]))
    else:
        commands.append(action_cmd("Save"))

    body = build_submit(commands)
    xml = soap_request(jar, "Submit", body, "ExecuteSQL")

    if xml is None:
        print("[SQL] No response from Submit")
        return False

    if check_fault(xml, "ExecuteSQL"):
        return False

    if "errorMessage" in xml.lower() or "isError>true" in xml.lower():
        m = re.search(r"<Message>(.*?)</Message>", xml, re.DOTALL)
        print(f"[SQL] Error: {m.group(1)[:500] if m else xml[:500]}")
        return False

    print(f"[SQL] Submit response (first 1000 chars): {xml[:1000]}")
    print("[SQL] Executed successfully")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global SOAP_URL

    if not BASE_URL:
        print("Error: ACUMATICA_SANDBOX_URL must be set")
        sys.exit(1)
    if not USERNAME or not PASSWORD:
        print("Error: ACUMATICA_SANDBOX_USERNAME and ACUMATICA_SANDBOX_PASSWORD must be set")
        sys.exit(1)

    print(f"Target: {BASE_URL} (sandbox)")
    print(f"Tenant: {COMPANY}")
    print(f"SCHEMA_ONLY: {SCHEMA_ONLY}")

    # Try each screen ID until one works
    working_screen = None
    jar = None

    for screen_id in SCREEN_IDS:
        SOAP_URL = f"{BASE_URL}/Soap/{screen_id}.asmx"
        print(f"\n[Probe] Trying {screen_id} at {SOAP_URL}...")

        jar = http.cookiejar.CookieJar()
        login(jar)

        schema_xml = get_schema(jar)
        if schema_xml:
            print(f"[Probe] {screen_id} — schema retrieved OK")
            print_schema(schema_xml, screen_id)
            working_screen = screen_id
            break
        else:
            print(f"[Probe] {screen_id} — not available, trying next...")
            logout(jar)
            jar = None

    if not working_screen:
        print("\nERROR: Neither SM206540 nor SM206530 are accessible on this instance.")
        print("The sandbox may not have a Direct SQL screen available.")
        print("Alternative: Ask Acumatica support to drop the table, or restore from snapshot.")
        sys.exit(1)

    print(f"\nUsing screen: {working_screen}")

    try:
        if SCHEMA_ONLY:
            print("SCHEMA_ONLY=true — exiting after schema dump")
            return

        ok = execute_sql(jar, schema_xml)
        if not ok:
            sys.exit(1)

    finally:
        if jar:
            logout(jar)


if __name__ == "__main__":
    main()
