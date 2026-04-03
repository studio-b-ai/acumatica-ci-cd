#!/usr/bin/env python3
"""
Create Non-Stock Kit items and Kit Specifications in Acumatica.

Uses REST API to create NonStockItem (IsKit=true), then SOAP Screen API
(IN209500) to define stock components for each kit.

Usage:
    # 1. Discover IN209500 field names (run once)
    SCHEMA_ONLY=true ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... python3 create-sample-kits.py

    # 2. Dry run (default) — logs actions without calling APIs
    ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... python3 create-sample-kits.py kits.json

    # 3. Live run
    DRY_RUN=false ACUMATICA_USERNAME=... ACUMATICA_PASSWORD=... python3 create-sample-kits.py kits.json

Input JSON format:
    {
      "kits": [
        {
          "id": "SAMPKIT-ACE",
          "description": "Ace Collection Sample Kit",
          "components": ["ACE2", "ADELE1"]
        }
      ]
    }
"""

import os
import sys
import re
import json
import ssl
import time
import urllib.request

# Force unbuffered output so progress is visible in background runs
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)
import urllib.error
import http.cookiejar

# macOS Python often lacks system CA certs — use certifi if available, else unverified
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()
    SSL_CONTEXT.check_hostname = False
    SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# ── Config ───────────────────────────────────────────────────────────────

BASE_URL     = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")
USERNAME     = os.environ.get("ACUMATICA_USERNAME", "")
PASSWORD     = os.environ.get("ACUMATICA_PASSWORD", "")
COMPANY      = os.environ.get("ACUMATICA_TENANT", "Heritage Fabrics")
SCHEMA_ONLY  = os.environ.get("SCHEMA_ONLY", "false").lower() == "true"
DRY_RUN      = os.environ.get("DRY_RUN", "true").lower() == "true"  # default TRUE for safety

SOAP_URL = f"{BASE_URL}/Soap/IN209500.asmx"
REST_URL = f"{BASE_URL}/entity/default/24.200.001"

# Kit item defaults
KIT_DEFAULTS = {
    "PostingClass": "SALES",
    "TaxCategory": "TAXABLE",
    "BaseUnit": "EA",
    "SalesUnit": "EA",
    "PurchaseUnit": "EA",
    "DefaultPrice": 0,
}

# ── SOAP helpers (from create-business-events.py) ────────────────────────

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
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar),
        urllib.request.HTTPSHandler(context=SSL_CONTEXT),
    )
    try:
        with opener.open(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        print(f"  [{label or action}] HTTP {e.code}: {raw[:500]}")
        return None
    return raw


def check_fault(xml, label):
    if xml and ("<soap:Fault>" in xml or "faultstring" in xml):
        m = re.search(r"<faultstring>(.*?)</faultstring>", xml, re.DOTALL)
        msg = m.group(1).strip() if m else xml[:400]
        print(f"  [{label}] SOAP Fault: {msg}")
        return True
    return False


def cmd(field, value, obj=None, commit=False):
    parts = [f"<tns:FieldName>{field}</tns:FieldName>"]
    if obj:
        parts.append(f"<tns:ObjectName>{obj}</tns:ObjectName>")
    if value is not None:
        parts.append(f"<tns:Value>{value}</tns:Value>")
    if commit:
        parts.append("<tns:Commit>true</tns:Commit>")
    return f"<tns:Command>{''.join(parts)}</tns:Command>"


def action_cmd(field, obj=None):
    return cmd(field, None, obj)


def build_submit(commands):
    inner = "".join(commands)
    return f"<tns:Submit><tns:commands>{inner}</tns:commands></tns:Submit>"


# ── SOAP session ─────────────────────────────────────────────────────────

def soap_login():
    jar = http.cookiejar.CookieJar()
    body = f"<tns:Login><tns:name>{USERNAME}</tns:name><tns:password>{PASSWORD}</tns:password></tns:Login>"
    xml = soap_request(jar, "Login", body, "SOAP Login")
    if xml is None or check_fault(xml, "SOAP Login"):
        print("SOAP login failed")
        sys.exit(1)
    m = re.search(r"<Code>(.*?)</Code>", xml)
    code = m.group(1) if m else "?"
    if code != "OK":
        print(f"SOAP login failed — Code={code}")
        sys.exit(1)
    print(f"[SOAP] Logged in (company={COMPANY})")
    return jar


def soap_logout(jar):
    body = "<tns:Logout/>"
    soap_request(jar, "Logout", body, "SOAP Logout")
    print("[SOAP] Logged out")


# ── Schema discovery ─────────────────────────────────────────────────────

def get_schema(jar):
    body = "<tns:GetSchema/>"
    xml = soap_request(jar, "GetSchema", body, "GetSchema")
    if xml is None or check_fault(xml, "GetSchema"):
        print("GetSchema failed")
        sys.exit(1)
    return xml


def print_schema(xml):
    print("\n=== IN209500 Schema (Kit Specifications) ===")

    schema_match = re.search(r"<GetSchemaResult>(.*)</GetSchemaResult>", xml, re.DOTALL)
    if not schema_match:
        print("  Could not find GetSchemaResult in response")
        print(f"  Response length: {len(xml)}")
        print(f"  Response preview: {xml[:500]}")
        print("=== End Schema ===\n")
        return

    schema = schema_match.group(1)

    # Print ObjectName values (view names)
    objects = re.findall(r"<ObjectName>(.*?)</ObjectName>", schema)
    print(f"\nObjectName values (view names for SOAP Commands):")
    for o in sorted(set(objects)):
        print(f"  {o}")

    # Print Field→ObjectName pairs
    fields = re.findall(
        r"<Field>.*?<FieldName>(.*?)</FieldName>.*?<ObjectName>(.*?)</ObjectName>.*?</Field>",
        schema, re.DOTALL,
    )
    if fields:
        print(f"\nField→ObjectName pairs ({len(fields)} fields):")
        for fname, oname in fields:
            print(f"  {oname}.{fname}")
    else:
        fields_only = re.findall(r"<FieldName>(.*?)</FieldName>", schema)
        print(f"\nField names (first 80):")
        for f in fields_only[:80]:
            print(f"  {f}")

    # Container names
    containers = re.findall(r"<Container>.*?<Name>(.*?)</Name>", schema, re.DOTALL)
    if containers:
        print(f"\nContainer names:")
        for c in sorted(set(containers)):
            print(f"  {c}")

    print(f"\n--- Raw Schema XML (first 8000 chars) ---")
    print(schema[:8000])
    print("--- End Raw ---")
    print("=== End Schema ===\n")


# ── REST API session ─────────────────────────────────────────────────────

class RestSession:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=SSL_CONTEXT),
        )

    def login(self):
        payload = json.dumps({
            "name": USERNAME,
            "password": PASSWORD,
            "tenant": COMPANY,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/entity/auth/login",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            print(f"  [REST Login] HTTP {e.code}: {raw[:300]}")
            sys.exit(1)
        print("[REST] Logged in")

    def logout(self):
        req = urllib.request.Request(
            f"{BASE_URL}/entity/auth/logout",
            method="POST",
        )
        try:
            self.opener.open(req, timeout=15)
        except Exception:
            pass
        print("[REST] Logged out")

    def get(self, entity, key):
        url = f"{REST_URL}/{entity}/{key}"
        req = urllib.request.Request(url, method="GET")
        try:
            with self.opener.open(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raw = e.read().decode("utf-8", errors="replace")
            print(f"  [REST GET] HTTP {e.code}: {raw[:300]}")
            return None

    def put(self, entity, data, retries=3):
        for attempt in range(retries):
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                f"{REST_URL}/{entity}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            try:
                with self.opener.open(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", errors="replace")
                print(f"  [REST PUT] HTTP {e.code}: {raw[:500]}")
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                print(f"  [REST PUT] Timeout/network error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(10)
                else:
                    return None


# ── Kit creation logic ───────────────────────────────────────────────────

def create_kit_item(rest, kit):
    """Create a NonStockItem with IsKit=true via REST API."""
    kit_id = kit["id"]

    # Check if it already exists
    existing = rest.get("NonStockItem", kit_id)
    if existing and existing.get("InventoryID"):
        print(f"  [REST] {kit_id} already exists — skipping item creation")
        return True

    data = {
        "InventoryID":  {"value": kit_id},
        "Description":  {"value": kit["description"]},
        "IsKit":        {"value": True},
        "PostingClass": {"value": KIT_DEFAULTS["PostingClass"]},
        "TaxCategory":  {"value": KIT_DEFAULTS["TaxCategory"]},
        "BaseUnit":     {"value": KIT_DEFAULTS["BaseUnit"]},
        "SalesUnit":    {"value": KIT_DEFAULTS["SalesUnit"]},
        "PurchaseUnit": {"value": KIT_DEFAULTS["PurchaseUnit"]},
        "DefaultPrice": {"value": KIT_DEFAULTS["DefaultPrice"]},
    }

    result = rest.put("NonStockItem", data)
    if result is None:
        print(f"  [REST] Failed to create {kit_id}")
        return False

    print(f"  [REST] Created {kit_id}")
    return True


def add_kit_spec(soap_jar, kit, field_map):
    """Add stock components to a kit via SOAP Screen API (IN209500).

    field_map contains the ObjectName/FieldName pairs discovered from GetSchema.
    These are filled in after the first SCHEMA_ONLY run.
    """
    kit_id = kit["id"]
    components = kit["components"]

    # Build SOAP commands
    # 1. Navigate to the kit (set Kit Inventory ID)
    commands = []
    commands.append(cmd(
        field_map["kit_inventory_id_field"],
        kit_id,
        field_map["header_view"],
        commit=True,
    ))

    # 2. Set Revision
    commands.append(cmd(
        field_map["revision_field"],
        "01",
        field_map["header_view"],
        commit=True,
    ))

    # 3. Add each component
    # Schema shows CompInventoryID has LinkedCommand=NewRow, so setting it
    # auto-inserts a new row — no separate Insert action needed.
    for comp_id in components:
        # Set Component ID (auto-inserts new row via LinkedCommand)
        commands.append(cmd(
            field_map["component_id_field"],
            comp_id,
            field_map["components_view"],
            commit=True,
        ))
        # Set Qty
        commands.append(cmd(
            field_map["component_qty_field"],
            "1",
            field_map["components_view"],
            commit=True,
        ))

    # 4. Save
    commands.append(action_cmd("Save", field_map["header_view"]))

    body = build_submit(commands)
    xml = soap_request(soap_jar, "Submit", body, f"KitSpec-{kit_id}")

    if xml is None:
        print(f"  [SOAP] Failed to submit kit spec for {kit_id}")
        return False

    if check_fault(xml, f"KitSpec-{kit_id}"):
        return False

    if "errorMessage" in xml.lower() or "isError>true" in xml:
        m = re.search(r"<Message>(.*?)</Message>", xml, re.DOTALL)
        print(f"  [SOAP] Error: {m.group(1)[:300] if m else xml[:300]}")
        return False

    print(f"  [SOAP] Kit spec saved for {kit_id} ({len(components)} components)")
    return True


# ── Input loading ────────────────────────────────────────────────────────

def load_kits(path):
    with open(path, "r") as f:
        data = json.load(f)
    kits = data.get("kits", [])
    print(f"Loaded {len(kits)} kit definitions from {path}")
    return kits


# ── Field map ────────────────────────────────────────────────────────────
# These field/view names come from running SCHEMA_ONLY=true once.
# Update after running schema discovery if they differ from these defaults.

DEFAULT_FIELD_MAP = {
    # Header fields (Kit Inventory ID, Revision)
    "header_view":           "Hdr",
    "kit_inventory_id_field": "KitInventoryID",
    "revision_field":        "RevisionID",
    # Stock Components grid
    "components_view":       "StockDet",
    "component_id_field":    "CompInventoryID",
    "component_qty_field":   "DfltCompQty",
}


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    if not USERNAME or not PASSWORD:
        print("Error: ACUMATICA_USERNAME and ACUMATICA_PASSWORD must be set")
        sys.exit(1)

    print(f"Mode: DRY_RUN={DRY_RUN}, SCHEMA_ONLY={SCHEMA_ONLY}")
    print(f"SOAP URL: {SOAP_URL}")
    print(f"REST URL: {REST_URL}")

    # --- Schema discovery mode ---
    if SCHEMA_ONLY:
        jar = soap_login()
        try:
            schema_xml = get_schema(jar)
            print_schema(schema_xml)
        finally:
            soap_logout(jar)
        return

    # --- Bulk creation mode ---
    if len(sys.argv) < 2:
        print("Usage: python3 create-sample-kits.py <kits.json>")
        print("       SCHEMA_ONLY=true python3 create-sample-kits.py")
        sys.exit(1)

    kits = load_kits(sys.argv[1])
    if not kits:
        print("No kits to create")
        return

    field_map = DEFAULT_FIELD_MAP
    print(f"\nField map: {json.dumps(field_map, indent=2)}")

    if DRY_RUN:
        print("\n=== DRY RUN — no API calls ===")
        for kit in kits:
            print(f"\n  Kit: {kit['id']}")
            print(f"    Description: {kit['description']}")
            print(f"    Components: {', '.join(kit['components'])}")
            print(f"    -> Would create NonStockItem (IsKit=true, EA, $0, SALES)")
            print(f"    -> Would add {len(kit['components'])} stock components to IN209500")
        print(f"\n=== {len(kits)} kits would be created ===")
        return

    # Live mode — create items and kit specs
    rest = RestSession()
    rest.login()
    soap_jar = soap_login()

    results = []
    try:
        for i, kit in enumerate(kits):
            kit_id = kit["id"]
            print(f"\n--- [{i+1}/{len(kits)}] {kit_id}: {kit['description']} ---")

            try:
                # Step 1: Create the Non-Stock Kit item
                item_ok = create_kit_item(rest, kit)
                if not item_ok:
                    results.append((kit_id, "FAILED (item creation)"))
                    time.sleep(2)
                    continue

                # Step 2: Add kit specification with components
                spec_ok = add_kit_spec(soap_jar, kit, field_map)
                if not spec_ok:
                    # SOAP session may have died — try re-login once
                    print(f"  [SOAP] Retrying after re-login...")
                    soap_logout(soap_jar)
                    soap_jar = soap_login()
                    spec_ok = add_kit_spec(soap_jar, kit, field_map)
                    if not spec_ok:
                        results.append((kit_id, "FAILED (kit spec)"))
                        time.sleep(2)
                        continue

                results.append((kit_id, "OK"))

            except Exception as e:
                print(f"  [ERROR] {kit_id}: {e}")
                results.append((kit_id, f"FAILED ({e})"))
                # Wait and continue — do NOT re-login (risks lockout)
                time.sleep(10)

            # Throttle to avoid overloading the server
            time.sleep(2)

    finally:
        soap_logout(soap_jar)
        rest.logout()

    # Summary
    print("\n=== Results ===")
    ok_count = 0
    fail_count = 0
    for kit_id, status in results:
        print(f"  {kit_id}: {status}")
        if status == "OK":
            ok_count += 1
        else:
            fail_count += 1
    print(f"\n  Total: {ok_count} OK, {fail_count} FAILED")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
