#!/usr/bin/env python3
"""
Nightly Test Environment Sync — Acumatica Company Copy

Copies production company data to the test company on the same instance
using SOAP Screen API (SM203520 — Company Maintenance).

Runtime view names (from GetSchema — WSDL names differ!):
  Companies            Header (CompanyID key, CompanyCD = name)
  Snapshots            Snapshot grid
  CopyCompanyPanel     Copy Company dialog (CompanyID field)
  ExportSnapshotPanel  Create Snapshot dialog (Company, Description, ExportMode)
  ImportSnapshotPanel  Restore Snapshot dialog (Company, Name, Description)

Actions (all on ObjectName=Companies, camelCase FieldName):
  copyCompanyCommand, prepareAdbSnapshotCommand, importSnapshotCommand

Usage:
  python sync-test-env.py
  python sync-test-env.py --dry-run
  python sync-test-env.py --schema-only
"""

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def log(msg): print(f"{BLUE}[SYNC]{RESET} {msg}", flush=True)
def ok(msg): print(f"{GREEN}[  OK  ]{RESET} {msg}", flush=True)
def warn(msg): print(f"{YELLOW}[ WARN ]{RESET} {msg}", flush=True)
def err(msg): print(f"{RED}[ERROR ]{RESET} {msg}", file=sys.stderr, flush=True)

SCREEN_ID = "SM203520"
NS = "http://www.acumatica.com/typed/"


class SoapClient:
    def __init__(self, url, username, password):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.endpoint = f"{self.url}/Soap/{SCREEN_ID}.asmx"
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _soap_call(self, action, body, timeout=600):
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="{NS}">
  <soap:Body>{body}</soap:Body>
</soap:Envelope>"""
        req = urllib.request.Request(self.endpoint, data=envelope.encode("utf-8"), headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{NS}{action}"',
        })
        try:
            return self.opener.open(req, timeout=timeout).read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            fault = ""
            try:
                root = ET.fromstring(body_text)
                el = root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}faultstring")
                if el is not None and el.text:
                    fault = el.text[:500]
            except Exception:
                pass
            raise RuntimeError(f"SOAP {action} HTTP {e.code}: {fault or body_text[:500]}")

    def login(self, company):
        self._soap_call("Login", f"""<tns:Login>
      <tns:name>{self.username}</tns:name>
      <tns:password>{self.password}</tns:password>
      <tns:company>{company}</tns:company>
    </tns:Login>""")
        ok(f"Logged in to {SCREEN_ID} ({company})")

    def logout(self):
        try: self._soap_call("Logout", "<tns:Logout/>")
        except Exception: pass

    def get_schema(self):
        return self._soap_call("GetSchema", "<tns:GetSchema/>")

    def get_process_status(self):
        resp = self._soap_call("GetProcessStatus", "<tns:GetProcessStatus/>")
        root = ET.fromstring(resp)
        s = root.find(f".//{{{NS}}}Status")
        m = root.find(f".//{{{NS}}}Message")
        return (s.text if s is not None else "NotExists", (m.text or "") if m is not None else "")

    def submit(self, commands):
        xml = []
        for c in commands:
            parts = [f"<tns:FieldName>{c['FieldName']}</tns:FieldName>",
                     f"<tns:ObjectName>{c['ObjectName']}</tns:ObjectName>"]
            if "Value" in c: parts.append(f"<tns:Value>{c['Value']}</tns:Value>")
            if c.get("Commit"): parts.append("<tns:Commit>true</tns:Commit>")
            xml.append(f"<tns:Command>{''.join(parts)}</tns:Command>")
        return self._soap_call("Submit",
            f"<tns:Submit><tns:commands>{''.join(xml)}</tns:commands></tns:Submit>")

    def clear(self):
        self._soap_call("Clear", "<tns:Clear/>")

    def poll(self, operation, timeout_s=1800, interval=20):
        elapsed = 0
        while elapsed < timeout_s:
            time.sleep(interval)
            elapsed += interval
            status, msg = self.get_process_status()
            log(f"  {operation}: {status} ({elapsed}s) {msg[:100]}")
            if status == "Completed":
                ok(f"{operation} completed ({elapsed}s)")
                return True
            if status == "Aborted":
                err(f"{operation} aborted: {msg[:300]}")
                return False
            if status == "NotExists" and elapsed > 60:
                warn(f"{operation}: NotExists after {elapsed}s — may have completed instantly")
                return True
        err(f"{operation} timed out after {timeout_s}s")
        return False


def copy_company(client, target_company):
    """Copy current company to target using CopyCompanyCommand.

    Runtime views: CopyCompanyPanel.CompanyID, Actions on Companies.
    """
    log(f"Copying to '{target_company}'...")

    # Trigger CopyCompanyCommand action — this opens the CopyCompanyPanel dialog
    log("  Triggering copyCompanyCommand...")
    try:
        client.submit([
            {"FieldName": "copyCompanyCommand", "ObjectName": "Companies"},
        ])
        ok("  Copy dialog opened")
    except RuntimeError as e:
        # Action may return error while opening dialog — expected
        warn(f"  Action response: {str(e)[:200]}")

    # Set target company ID in the dialog and confirm
    log(f"  Setting target to '{target_company}' and confirming...")
    try:
        client.submit([
            {"FieldName": "CompanyID", "ObjectName": "CopyCompanyPanel", "Value": target_company, "Commit": True},
            {"FieldName": "DialogAnswer", "ObjectName": "CopyCompanyPanel", "Value": "Yes"},
        ])
        ok("  Copy command accepted")
    except RuntimeError as e:
        if "InProcess" in str(e):
            log("  Copy process started...")
        else:
            err(f"  Copy failed: {e}")
            return False

    return client.poll("CopyCompany", timeout_s=1800, interval=20)


def slack(url, text):
    if not url: return
    try:
        urllib.request.urlopen(urllib.request.Request(url,
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"}), timeout=10)
    except Exception: pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    p.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    p.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    p.add_argument("--source", default=os.environ.get("SOURCE_COMPANY", "Heritage Fabrics"))
    p.add_argument("--target", default=os.environ.get("TARGET_COMPANY", "Heritage Test"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--schema-only", action="store_true")
    args = p.parse_args()

    if not args.url or not args.username or not args.password:
        err("Missing ACUMATICA_URL, ACUMATICA_USERNAME, or ACUMATICA_PASSWORD")
        sys.exit(1)

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    client = SoapClient(args.url, args.username, args.password)

    try:
        client.login(args.source)

        if args.schema_only:
            log("SM203520 GetSchema:")
            resp = client.get_schema()
            log(f"Response: {len(resp)} bytes")
            # Print just the view/field pairs
            root = ET.fromstring(resp)
            for el in root.iter():
                fn = el.find(f"{{{NS}}}FieldName")
                on = el.find(f"{{{NS}}}ObjectName")
                if fn is not None and on is not None:
                    log(f"  {on.text}: {fn.text}")
            client.logout()
            return

        if args.dry_run:
            log("Dry run — connectivity OK")
            client.logout()
            return

        result = copy_company(client, args.target)
        if not result:
            err("Company copy failed")
            slack(slack_url, f":x: *Test Env Sync FAILED*\nCopy `{args.source}` → `{args.target}` failed")
            client.logout()
            sys.exit(1)

        ok(f"Synced: {args.source} → {args.target}")
        slack(slack_url, f":white_check_mark: *Test Env Sync Complete*\n`{args.source}` → `{args.target}`")

    except Exception as e:
        err(f"Sync failed: {e}")
        slack(slack_url, f":x: *Test Env Sync FAILED*\n{str(e)[:200]}")
        sys.exit(1)
    finally:
        try: client.logout()
        except Exception: pass


if __name__ == "__main__":
    main()
