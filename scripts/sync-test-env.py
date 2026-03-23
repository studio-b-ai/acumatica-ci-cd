#!/usr/bin/env python3
"""
Nightly Test Environment Sync — Acumatica Company Snapshot + Restore

Creates a snapshot of the production company and restores it to the test
company on the same instance, keeping test in sync with production data.

Uses the SOAP Screen API (SM203520 — Company Maintenance) which exposes
CreateSnapshot and RestoreSnapshot dialogs.

SOAP Submit sequence:
  1. Login to SM203520
  2. Navigate to production company (TenantID)
  3. Open CreateSnapshot dialog → set Description → trigger PrepareAdbSnapshotCommand
  4. Poll GetProcessStatus until snapshot completes
  5. Select the new snapshot → open RestoreSnapshot dialog
  6. Set target Company to test → trigger restore
  7. Poll GetProcessStatus until restore completes
  8. Logout

Environment variables (or --flag equivalents):
  ACUMATICA_URL         Instance URL
  ACUMATICA_USERNAME    API user (same creds for both companies)
  ACUMATICA_PASSWORD    API password
  SOURCE_COMPANY        Production company name (default: "Heritage Fabrics")
  TARGET_COMPANY        Test company name (default: "Heritage Test")

Usage:
  python sync-test-env.py
  python sync-test-env.py --dry-run          # Schema discovery + login only
  python sync-test-env.py --schema-only      # Print SM203520 field map
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

# ─── Colors ─────────────────────────────────────────────────────────────────

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def log(msg: str) -> None:
    print(f"{BLUE}[SYNC]{RESET} {msg}", flush=True)

def ok(msg: str) -> None:
    print(f"{GREEN}[  OK  ]{RESET} {msg}", flush=True)

def warn(msg: str) -> None:
    print(f"{YELLOW}[ WARN ]{RESET} {msg}", flush=True)

def err(msg: str) -> None:
    print(f"{RED}[ERROR ]{RESET} {msg}", file=sys.stderr, flush=True)

# ─── SOAP Client ────────────────────────────────────────────────────────────

SCREEN_ID = "SM203520"
NS = "http://www.acumatica.com/typed/"

class SoapClient:
    """Minimal SOAP client for Acumatica Screen API."""

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.endpoint = f"{self.url}/Soap/{SCREEN_ID}.asmx"
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )

    def _soap_call(self, action: str, body: str, timeout: int = 120) -> str:
        """Execute a SOAP call and return the response body."""
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:tns="{NS}">
  <soap:Body>
    {body}
  </soap:Body>
</soap:Envelope>"""

        req = urllib.request.Request(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": f'"{NS}{action}"',
            },
        )
        try:
            resp = self.opener.open(req, timeout=timeout)
            return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            # Extract faultstring from SOAP fault for cleaner error messages
            fault_msg = ""
            try:
                fault_root = ET.fromstring(body_text)
                fault_el = fault_root.find(".//{http://schemas.xmlsoap.org/soap/envelope/}faultstring")
                if fault_el is not None and fault_el.text:
                    fault_msg = f"\nFault: {fault_el.text[:500]}"
            except Exception:
                pass
            raise RuntimeError(
                f"SOAP {action} failed: HTTP {e.code}{fault_msg}\n{body_text[:2000]}"
            )

    def login(self, company: str) -> None:
        """Authenticate to SM203520 in the context of a specific company."""
        body = f"""<tns:Login>
      <tns:name>{self.username}</tns:name>
      <tns:password>{self.password}</tns:password>
      <tns:company>{company}</tns:company>
    </tns:Login>"""
        self._soap_call("Login", body)
        ok(f"Logged in to {SCREEN_ID} as {self.username} (company: {company})")

    def logout(self) -> None:
        """Release session."""
        try:
            self._soap_call("Logout", "<tns:Logout/>")
        except Exception:
            pass

    def get_schema(self) -> str:
        """Get SM203520 field schema."""
        resp = self._soap_call("GetSchema", "<tns:GetSchema/>")
        return resp

    def get_process_status(self) -> tuple[str, str]:
        """Poll process status. Returns (status, message)."""
        resp = self._soap_call("GetProcessStatus", "<tns:GetProcessStatus/>")
        root = ET.fromstring(resp)
        status_el = root.find(f".//{{{NS}}}Status")
        message_el = root.find(f".//{{{NS}}}Message")
        status = status_el.text if status_el is not None else "NotExists"
        message = message_el.text if message_el is not None else ""
        return status, message or ""

    def submit(self, commands: list[dict]) -> str:
        """Submit commands to SM203520.

        Each command is a dict with keys: FieldName, ObjectName, Value (optional), Commit (optional).
        """
        cmd_xml = []
        for cmd in commands:
            parts = [
                f"<tns:FieldName>{cmd['FieldName']}</tns:FieldName>",
                f"<tns:ObjectName>{cmd['ObjectName']}</tns:ObjectName>",
            ]
            if "Value" in cmd:
                parts.append(f"<tns:Value>{cmd['Value']}</tns:Value>")
            if cmd.get("Commit"):
                parts.append("<tns:Commit>true</tns:Commit>")
            cmd_xml.append(f"<tns:Command>{''.join(parts)}</tns:Command>")

        body = f"""<tns:Submit>
      <tns:commands>
        {''.join(cmd_xml)}
      </tns:commands>
    </tns:Submit>"""
        return self._soap_call("Submit", body, timeout=300)

    def clear(self) -> None:
        """Clear screen state."""
        self._soap_call("Clear", "<tns:Clear/>")

    def poll_process(self, operation: str, timeout_seconds: int = 1200, poll_interval: int = 15) -> bool:
        """Poll GetProcessStatus until completed or timeout."""
        elapsed = 0
        while elapsed < timeout_seconds:
            time.sleep(poll_interval)
            elapsed += poll_interval
            status, message = self.get_process_status()
            log(f"  {operation}: {status} ({elapsed}s) {message[:100] if message else ''}")
            if status == "Completed":
                ok(f"{operation} completed ({elapsed}s)")
                return True
            if status == "Aborted":
                err(f"{operation} aborted: {message[:500]}")
                return False
            if status == "NotExists":
                # Process hasn't started yet or already finished
                if elapsed > 30:
                    warn(f"{operation}: NotExists after {elapsed}s — may have completed instantly")
                    return True
        err(f"{operation} timed out after {timeout_seconds}s")
        return False

# ─── Sync Logic ─────────────────────────────────────────────────────────────

def print_schema(client: SoapClient) -> None:
    """Print SM203520 schema for debugging."""
    resp = client.get_schema()
    root = ET.fromstring(resp)
    for cmd in root.iter(f"{{{NS}}}Command"):
        obj = cmd.find(f"{{{NS}}}ObjectName")
        field = cmd.find(f"{{{NS}}}FieldName")
        if obj is not None and field is not None:
            print(f"  {obj.text}: {field.text}")


def create_snapshot(client: SoapClient, source_company: str, description: str) -> bool:
    """Create a snapshot of the source company.

    SM203520 dialog flow:
    1. Set snapshot description in CreateSnapshot dialog
    2. Trigger PrepareAdbSnapshotCommand action
    3. Poll GetProcessStatus until complete
    """
    log(f"Step 1: Creating snapshot of '{source_company}'...")
    log(f"  Description: {description}")

    # Set snapshot parameters and trigger creation in one Submit.
    # The CreateSnapshot view is a dialog — set fields then trigger the action.
    try:
        client.submit([
            {"FieldName": "Description", "ObjectName": "CreateSnapshot", "Value": description},
            {"FieldName": "PrepareAdbSnapshotCommand", "ObjectName": "Actions"},
        ])
    except RuntimeError as e:
        # Some SOAP screens return 500 on long-running process initiation
        # but the process actually starts. Check GetProcessStatus.
        if "InProcess" in str(e) or "process" in str(e).lower():
            log("  Submit returned error but process may have started — polling...")
        else:
            err(f"  Submit failed: {e}")
            # Try alternative: use dialog answer pattern
            log("  Retrying with dialog answer pattern...")
            try:
                client.submit([
                    {"FieldName": "Description", "ObjectName": "CreateSnapshot", "Value": description},
                    {"FieldName": "ExportMode", "ObjectName": "CreateSnapshot", "Value": "All"},
                    {"FieldName": "DialogAnswer", "ObjectName": "CreateSnapshot", "Value": "OK"},
                ])
            except RuntimeError as e2:
                err(f"  Retry also failed: {e2}")
                return False

    # Poll until snapshot completes
    return client.poll_process("CreateSnapshot", timeout_seconds=1200, poll_interval=15)


def restore_snapshot(client: SoapClient, target_company: str, snapshot_name: str) -> bool:
    """Restore a snapshot to the target company.

    SM203520 restore flow:
    1. Select snapshot row in Snapshots grid
    2. Trigger ImportSnapshotCommand action (opens RestoreSnapshot dialog)
    3. Set Company on RestoreSnapshot dialog
    4. Confirm with DialogAnswer
    """
    log(f"Step 2: Restoring snapshot '{snapshot_name}' to '{target_company}'...")

    # Step 2a: Select the snapshot row by name
    log("  Selecting snapshot row...")
    try:
        client.submit([
            {"FieldName": "Name", "ObjectName": "Snapshots", "Value": snapshot_name, "Commit": True},
        ])
        ok("  Snapshot row selected")
    except RuntimeError as e:
        err(f"  Failed to select snapshot: {e}")
        return False

    # Step 2b: Trigger ImportSnapshotCommand to open the restore dialog
    log("  Triggering ImportSnapshotCommand (restore dialog)...")
    try:
        client.submit([
            {"FieldName": "ImportSnapshotCommand", "ObjectName": "Actions"},
        ])
        ok("  Restore dialog opened")
    except RuntimeError as e:
        # The action may open a dialog that expects fields — this error is expected
        warn(f"  ImportSnapshotCommand response: {str(e)[:200]}")

    # Step 2c: Set target company and confirm
    log(f"  Setting restore target to '{target_company}' and confirming...")
    try:
        client.submit([
            {"FieldName": "Company", "ObjectName": "RestoreSnapshot", "Value": target_company, "Commit": True},
            {"FieldName": "DialogAnswer", "ObjectName": "RestoreSnapshot", "Value": "OK"},
        ])
    except RuntimeError as e:
        if "InProcess" in str(e) or "process" in str(e).lower():
            log("  Restore process started — polling...")
        else:
            # Try alternative: just the dialog answer without setting Company
            # (Company may auto-populate from current company context)
            warn(f"  First attempt failed: {str(e)[:200]}")
            log("  Retrying with just DialogAnswer...")
            try:
                client.submit([
                    {"FieldName": "DialogAnswer", "ObjectName": "RestoreSnapshot", "Value": "OK"},
                ])
            except RuntimeError as e2:
                if "InProcess" in str(e2):
                    log("  Restore process started — polling...")
                else:
                    err(f"  Restore failed: {e2}")
                    return False

    # Poll until restore completes
    return client.poll_process("RestoreSnapshot", timeout_seconds=1200, poll_interval=15)


def send_slack(webhook_url: str, text: str) -> None:
    """Post a Slack notification (best effort)."""
    if not webhook_url:
        return
    try:
        data = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ─── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync test environment from production via snapshot")
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    parser.add_argument("--source", default=os.environ.get("SOURCE_COMPANY", "Heritage Fabrics"),
                        help="Production company name")
    parser.add_argument("--target", default=os.environ.get("TARGET_COMPANY", "Heritage Test"),
                        help="Test company name")
    parser.add_argument("--dry-run", action="store_true", help="Login + schema only, no snapshot")
    parser.add_argument("--schema-only", action="store_true", help="Print field schema and exit")
    args = parser.parse_args()

    if not args.url or not args.username or not args.password:
        err("Missing ACUMATICA_URL, ACUMATICA_USERNAME, or ACUMATICA_PASSWORD")
        sys.exit(1)

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    client = SoapClient(args.url, args.username, args.password)

    try:
        # Login to source company for schema/dry-run
        client.login(args.source)

        if args.schema_only:
            log("SM203520 schema:")
            print_schema(client)
            client.logout()
            return

        if args.dry_run:
            log("Dry run — checking connectivity and schema")
            status, msg = client.get_process_status()
            log(f"Process status: {status} — {msg}")
            ok("Dry run passed — SOAP connectivity confirmed")
            client.logout()
            return

        # Step 1: Create snapshot (logged into source company)
        timestamp = time.strftime("%Y-%m-%d")
        description = f"prod-mirror-{timestamp}"

        snapshot_ok = create_snapshot(client, args.source, description)
        if not snapshot_ok:
            err("Snapshot creation failed — aborting")
            send_slack(slack_url,
                       f":x: *Test Env Sync FAILED*\nSnapshot creation failed for `{args.source}`\nManual intervention required")
            client.logout()
            sys.exit(1)

        # Logout source session
        client.logout()
        log("Source session closed")

        # Step 2: Login to target company for restore
        target_client = SoapClient(args.url, args.username, args.password)
        try:
            target_client.login(args.target)

            restore_ok = restore_snapshot(target_client, args.target, description)
            if not restore_ok:
                err("Snapshot restore failed")
                send_slack(slack_url,
                           f":x: *Test Env Sync FAILED*\nSnapshot `{description}` created but restore to `{args.target}` failed\nSnapshot available for manual restore in SM203520")
                target_client.logout()
                sys.exit(1)

            ok(f"Test environment synced: {args.source} → {args.target}")
            send_slack(slack_url,
                       f":white_check_mark: *Test Env Sync Complete*\n`{args.source}` → `{args.target}`\nSnapshot: `{description}`")
        finally:
            target_client.logout()

    except Exception as e:
        err(f"Sync failed: {e}")
        send_slack(slack_url,
                   f":x: *Test Env Sync FAILED*\n{str(e)[:200]}")
        try:
            client.logout()
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
