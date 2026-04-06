#!/usr/bin/env python3
"""
ASPX Import Overwrite Reproduction Test

Tests whether Acumatica's CustomizationApi/Import with isReplaceIfExists=true
actually overwrites existing ASPX files. Tests three scenarios:

1. CDATA change only (project.xml modified, no physical file change)
2. Physical file change only (standalone .aspx modified, CDATA unchanged)
3. Both changed (CDATA + physical file both modified)

Runs against the Heritage Fabrics sandbox instance.
"""

import argparse
import base64
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

SANDBOX_URL = "https://heritagefabrics-sandbox.acumatica.com"
TENANT = "Heritage Fabrics"
PROJECT_NAME = "AesthetikContainers"

# Path to local customization project (relative to repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_PROJECT_DIR = REPO_ROOT / "Customization" / PROJECT_NAME

# Marker we inject into ASPX to detect overwrites
MARKER_CDATA = "<!-- OVERWRITE-TEST-CDATA-{ts} -->"
MARKER_FILE = "<!-- OVERWRITE-TEST-FILE-{ts} -->"
MARKER_BOTH = "<!-- OVERWRITE-TEST-BOTH-{ts} -->"

# Target ASPX — use SB302000 (low-risk screen) not SB501000 (active screen)
TARGET_ASPX_PATH = "Pages/SB/SB302000.aspx"


def log(msg, style="info"):
    prefix = {"info": "  ", "ok": "OK", "warn": "!!", "fail": "XX"}
    print(f"[{prefix.get(style, '  ')}] {msg}")


class AcumaticaClient:
    def __init__(self, url, username, password, tenant):
        self.base_url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.username = username
        self.password = password
        self.tenant = tenant

    def login(self, retries=5):
        for attempt in range(retries):
            try:
                log(f"Logging in to {self.base_url} as {self.username}...")
                resp = self.session.post(
                    f"{self.base_url}/entity/auth/login",
                    json={
                        "name": self.username,
                        "password": self.password,
                        "tenant": self.tenant,
                    },
                    timeout=60,
                )
                if resp.status_code == 204:
                    log("Authenticated", style="ok")
                    return
                if resp.status_code in (500, 502, 503, 504) and attempt < retries - 1:
                    log(f"Login got HTTP {resp.status_code}, retrying in 15s... ({attempt+1}/{retries})", style="warn")
                    time.sleep(15)
                    continue
                raise RuntimeError(f"Login failed (HTTP {resp.status_code}): {resp.text[:300]}")
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as e:
                if attempt < retries - 1:
                    log(f"Login connection error, retrying in 15s... ({attempt+1}/{retries})", style="warn")
                    time.sleep(15)
                    continue
                raise

    def logout(self):
        try:
            self.session.post(f"{self.base_url}/entity/auth/logout", timeout=10)
        except Exception:
            pass

    def export_project(self, project_name):
        """Download existing customization package as bytes."""
        log(f"Exporting current '{project_name}' package...")
        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/getProject",
            json={"projectName": project_name},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Export failed (HTTP {resp.status_code}): {resp.text[:300]}")
        b64 = resp.text.strip().strip('"')
        data = base64.b64decode(b64)
        log(f"Exported {len(data)} bytes", style="ok")
        return data

    def import_package(self, project_name, zip_bytes, description=""):
        """Import a customization zip package."""
        content_b64 = base64.b64encode(zip_bytes).decode("ascii")
        if not description:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            description = f"ASPX overwrite test at {ts}"
        log(f"Importing package ({len(zip_bytes)} bytes)...")
        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/Import",
            json={
                "projectName": project_name,
                "projectDescription": description,
                "projectLevel": 0,
                "isReplaceIfExists": True,
                "projectContentBase64": content_b64,
            },
            timeout=120,
        )
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"Import failed (HTTP {resp.status_code}): {resp.text[:500]}")
        log("Package imported", style="ok")

    def publish(self, project_names, timeout_s=600):
        """Publish and wait for completion."""
        log(f"Publishing: {', '.join(project_names)}...")
        resp = self.session.post(
            f"{self.base_url}/CustomizationApi/publishBegin",
            json={
                "isMergeWithExistingPackages": False,
                "isOnlyValidation": False,
                "isOnlyDbUpdates": False,
                "projectNames": project_names,
                "tenantMode": "Current",
            },
            timeout=60,
        )
        if resp.status_code not in (200, 204):
            raise RuntimeError(f"Publish begin failed (HTTP {resp.status_code}): {resp.text[:300]}")

        elapsed = 0
        poll = 10
        conn_errors = 0
        while elapsed < timeout_s:
            time.sleep(poll)
            elapsed += poll
            try:
                resp = self.session.post(
                    f"{self.base_url}/CustomizationApi/publishEnd",
                    json={},
                    timeout=60,
                )
            except Exception:
                conn_errors += 1
                log(f"  Connection lost ({conn_errors}/6) — app pool restarting ({elapsed}s)", style="warn")
                if conn_errors >= 6:
                    raise TimeoutError("App pool did not recover")
                continue

            conn_errors = 0
            if resp.status_code in (500, 502, 503, 504):
                log(f"  HTTP {resp.status_code} — app pool restarting ({elapsed}s)", style="warn")
                continue

            body = resp.text.strip()
            try:
                data = json.loads(body)
                if isinstance(data, dict):
                    if data.get("isFailed"):
                        full_log = json.dumps(data.get('log', ''), indent=2)
                        # Print full log for diagnosis
                        print(f"\n--- PUBLISH FAILURE LOG ---")
                        # Find error entries
                        for entry in (data.get('log') or []):
                            if entry.get('logType') in ('error', 'warning'):
                                print(f"  [{entry['logType']}] {entry['message']}")
                        print(f"--- END PUBLISH LOG ---\n")
                        raise RuntimeError(f"Publish failed (see log above)")
                    if data.get("isCompleted"):
                        log(f"Publish completed ({elapsed}s)", style="ok")
                        return
            except json.JSONDecodeError:
                pass

            if body.lower() == "true":
                log(f"Publish completed ({elapsed}s)", style="ok")
                return
            log(f"  Publishing... ({elapsed}s)")

        raise TimeoutError(f"Publish timed out after {timeout_s}s")


def build_zip_from_local(project_dir):
    """Build a customization zip from the local project directory."""
    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise RuntimeError(f"Local project dir not found: {project_dir}")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(project_dir.rglob("*")):
            if file_path.is_file():
                arc_name = str(file_path.relative_to(project_dir))
                zf.write(file_path, arc_name)
    data = out.getvalue()
    log(f"Built zip from local dir: {len(data)} bytes, {project_dir}", style="ok")
    return data


def extract_aspx_from_zip(zip_bytes, aspx_path):
    """Extract an ASPX file's content from a zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if name.replace("\\", "/") == aspx_path.replace("\\", "/"):
                return zf.read(name).decode("utf-8")
    return None


def extract_aspx_from_cdata(zip_bytes, aspx_path):
    """Extract the CDATA content for an ASPX from project.xml in a zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_content = zf.read("project.xml").decode("utf-8")

    pattern = (
        r'<File\s+AppRelativePath="'
        + re.escape(aspx_path.replace("/", "\\"))
        + r'"[^>]*Source="#CDATA"[^>]*>.*?<CDATA\s+name="Source"><!\[CDATA\[(.*?)\]\]></CDATA>'
    )
    match = re.search(pattern, xml_content, re.DOTALL)
    if match:
        return match.group(1)
    return None


def inject_marker_in_cdata(zip_bytes, aspx_path, marker):
    """Return new zip bytes with marker injected into CDATA for target ASPX."""
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf_in:
        xml_content = zf_in.read("project.xml").decode("utf-8")
        all_files = {name: zf_in.read(name) for name in zf_in.namelist()}

    # Inject marker after the first <asp:Content...> tag within CDATA
    pattern = (
        r'(<File\s+AppRelativePath="'
        + re.escape(aspx_path.replace("/", "\\"))
        + r'"[^>]*Source="#CDATA"[^>]*>.*?<CDATA\s+name="Source"><!\[CDATA\[)'
        r'(.*?)(<asp:Content[^>]*>)'
    )
    replacement = r'\1\2\3\n' + marker
    new_xml = re.sub(pattern, replacement, xml_content, count=1, flags=re.DOTALL)

    if new_xml == xml_content:
        raise RuntimeError(f"Failed to inject CDATA marker for {aspx_path}")

    all_files["project.xml"] = new_xml.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf_out:
        for name, data in all_files.items():
            zf_out.writestr(name, data)
    return out.getvalue()


def inject_marker_in_file(zip_bytes, aspx_path, marker):
    """Return new zip bytes with marker injected into the standalone ASPX file.

    Injects after the first <asp:Content> opening tag to avoid ASPX parsing errors
    (content pages only allow Content controls at the top level).
    """
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf_in:
        all_files = {name: zf_in.read(name) for name in zf_in.namelist()}

    target_key = None
    for name in all_files:
        if name.replace("\\", "/") == aspx_path.replace("\\", "/"):
            target_key = name
            break

    if not target_key:
        raise RuntimeError(f"File {aspx_path} not found in zip")

    content = all_files[target_key].decode("utf-8")
    # Inject after the first <asp:Content ...> tag (inside a Content control)
    asp_content_match = re.search(r'(<asp:Content[^>]*>)', content, re.IGNORECASE)
    if asp_content_match:
        insert_pos = asp_content_match.end()
        content = content[:insert_pos] + "\n" + marker + content[insert_pos:]
    else:
        # Fallback: inject after first line (Page directive)
        lines = content.split("\n")
        content = lines[0] + "\n" + marker + "\n" + "\n".join(lines[1:])
    all_files[target_key] = content.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf_out:
        for name, data in all_files.items():
            zf_out.writestr(name, data)
    return out.getvalue()


def run_test(client, scenario, modify_fn, marker, baseline_zip):
    """Run a single overwrite test scenario."""
    print(f"\n{'='*60}")
    log(f"SCENARIO: {scenario}")
    print(f"{'='*60}")

    modified_zip = modify_fn(baseline_zip, TARGET_ASPX_PATH, marker)
    log(f"Injected marker: {marker}")

    client.import_package(PROJECT_NAME, modified_zip, description=f"Test: {scenario}")
    client.publish([PROJECT_NAME])

    log("Waiting 15s for app pool to stabilize...")
    time.sleep(15)

    client.login()

    result_zip = client.export_project(PROJECT_NAME)

    cdata_content = extract_aspx_from_cdata(result_zip, TARGET_ASPX_PATH)
    cdata_has_marker = marker in (cdata_content or "")

    file_content = extract_aspx_from_zip(result_zip, TARGET_ASPX_PATH)
    file_has_marker = marker in (file_content or "")

    log(f"CDATA contains marker: {cdata_has_marker}", style="ok" if cdata_has_marker else "fail")
    log(f"Physical file contains marker: {file_has_marker}", style="ok" if file_has_marker else "fail")

    return {
        "scenario": scenario,
        "cdata_has_marker": cdata_has_marker,
        "file_has_marker": file_has_marker,
        "cdata_content_snippet": (cdata_content or "")[:200],
        "file_content_snippet": (file_content or "")[:200],
    }


def main():
    parser = argparse.ArgumentParser(description="ASPX Import Overwrite Test")
    parser.add_argument("--url", default=SANDBOX_URL)
    parser.add_argument("--username", default="api-bot")
    parser.add_argument("--password", required=True)
    parser.add_argument("--tenant", default=TENANT)
    parser.add_argument("--scenario", choices=["cdata", "file", "both", "all"], default="all")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    client = AcumaticaClient(args.url, args.username, args.password, args.tenant)

    try:
        client.login()

        # Try to export existing project; if not found, seed from local repo
        try:
            baseline_zip = client.export_project(PROJECT_NAME)
            log(f"Baseline exported ({len(baseline_zip)} bytes)")
        except RuntimeError as e:
            if "not found" in str(e).lower():
                log(f"Project '{PROJECT_NAME}' not found on instance — seeding from local repo", style="warn")
                seed_zip = build_zip_from_local(LOCAL_PROJECT_DIR)
                client.import_package(PROJECT_NAME, seed_zip, description="Seed for overwrite test")
                log("Seed import done. Exporting as baseline...")
                baseline_zip = client.export_project(PROJECT_NAME)
                log(f"Baseline exported ({len(baseline_zip)} bytes)")
            else:
                raise

        # Also build a local-format zip (has CDATA in project.xml)
        local_zip = build_zip_from_local(LOCAL_PROJECT_DIR)

        # Analyze both formats
        exp_cdata = extract_aspx_from_cdata(baseline_zip, TARGET_ASPX_PATH)
        exp_phys = extract_aspx_from_zip(baseline_zip, TARGET_ASPX_PATH)
        loc_cdata = extract_aspx_from_cdata(local_zip, TARGET_ASPX_PATH)
        loc_phys = extract_aspx_from_zip(local_zip, TARGET_ASPX_PATH)
        log(f"Exported zip — CDATA present: {exp_cdata is not None}, Physical file present: {exp_phys is not None}")
        log(f"Local zip   — CDATA present: {loc_cdata is not None}, Physical file present: {loc_phys is not None}")

        if not exp_phys and not loc_cdata:
            log("Target ASPX not found in either format — cannot test", style="fail")
            sys.exit(1)

        results = []
        run_scenarios = [args.scenario] if args.scenario != "all" else ["cdata", "file", "both"]

        for s_key in run_scenarios:
            marker = {
                "cdata": MARKER_CDATA,
                "file": MARKER_FILE,
                "both": MARKER_BOTH,
            }[s_key].format(ts=ts)

            if s_key == "cdata":
                # Use local zip (which has CDATA) and inject marker into CDATA only
                modified = inject_marker_in_cdata(local_zip, TARGET_ASPX_PATH, marker)
                result = run_test(client, "CDATA only (local format)", lambda z, p, m: modified, marker, local_zip)
            elif s_key == "file":
                # Use local zip and inject marker into physical file only (leave CDATA unchanged)
                modified = inject_marker_in_file(local_zip, TARGET_ASPX_PATH, marker)
                result = run_test(client, "Physical file only (local format)", lambda z, p, m: modified, marker, local_zip)
            elif s_key == "both":
                # Use local zip, inject marker into both CDATA and physical file
                step1 = inject_marker_in_cdata(local_zip, TARGET_ASPX_PATH, marker)
                step2 = inject_marker_in_file(step1, TARGET_ASPX_PATH, marker)
                result = run_test(client, "Both CDATA + file (local format)", lambda z, p, m: step2, marker, local_zip)

            results.append(result)

            # Restore baseline before next test (use local zip — Acumatica export zip
            # may have compression quirks that fail on re-import)
            if s_key != run_scenarios[-1]:
                log("Restoring baseline for next test...")
                client.import_package(PROJECT_NAME, local_zip, description="Restore baseline")
                client.publish([PROJECT_NAME])
                time.sleep(15)
                client.login()

        # Restore baseline after all tests
        log("\nRestoring baseline package (local format)...")
        client.import_package(PROJECT_NAME, local_zip, description="Restore after overwrite test")
        client.publish([PROJECT_NAME])

        # Print summary
        print(f"\n{'='*60}")
        print("RESULTS SUMMARY")
        print(f"{'='*60}")
        for r in results:
            print(f"\n  {r['scenario']}:")
            print(f"    CDATA overwritten: {r['cdata_has_marker']}")
            print(f"    Physical file overwritten: {r['file_has_marker']}")

        # Determine root cause
        print(f"\n{'='*60}")
        print("ANALYSIS")
        print(f"{'='*60}")
        cdata_result = next((r for r in results if r["scenario"] == "CDATA only"), None)
        file_result = next((r for r in results if r["scenario"] == "Physical file only"), None)

        if cdata_result and not cdata_result["cdata_has_marker"]:
            print("  FINDING: CDATA changes in project.xml are NOT applied to the instance ASPX.")
            print("  The import API ignores CDATA content for files that already exist.")
        if file_result and file_result["file_has_marker"]:
            print("  FINDING: Physical file changes DO overwrite the instance ASPX.")
            print("  The standalone file in the zip is the effective source of truth.")
        if cdata_result and cdata_result["cdata_has_marker"]:
            print("  FINDING: CDATA changes ARE applied. The original incident may have been")
            print("  caused by a different issue (e.g., wrong CDATA content, caching).")

    finally:
        client.logout()


if __name__ == "__main__":
    main()
