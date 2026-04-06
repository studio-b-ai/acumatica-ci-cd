# ASPX Import Overwrite Investigation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Determine why Acumatica customization import doesn't overwrite existing ASPX files, fix the source-of-truth divergence in project.xml, and add ASPX verification to the pipeline.

**Architecture:** Three-phase approach: (1) empirical reproduction test against sandbox to establish ground truth, (2) fix the project.xml CDATA divergence in acumatica-ci-cd, (3) add post-deploy ASPX verification to acuops-pipeline. Findings documented as a root cause analysis.

**Tech Stack:** Python (requests), Acumatica REST API, Acumatica Customization API, GitHub Actions YAML

---

## Context

### The Incident (2026-04-05)

SB501000.aspx on production had `TabView.master` (from an unmerged branch) while the pipeline's project.xml CDATA had the correct `FormDetail.master`. Three deploys didn't fix it. PR #221 updated the standalone ASPX file, and that's when it resolved — but it's unclear whether the CDATA or the physical file fixed it.

### Current State of the Codebase

The zip package sent to Acumatica contains BOTH sources for SB501000.aspx:
- **project.xml CDATA** (line ~169): Old "Container Maintenance" simple form view with `PrimaryView="Container"`
- **Pages/SB/SB501000.aspx** standalone file: Current "Procurement Command Center" dashboard with `PrimaryView="Filter"`, KPI cards, split container

These are **completely different screens**. The other 4 ASPX files (SB302000, SB302010, SB302020, SB302030) are identical between CDATA and standalone — SB501000 is the only divergent one.

### Key Files

| File | Repo | Purpose |
|------|------|---------|
| `Customization/AesthetikContainers/project.xml` | acumatica-ci-cd | CDATA ASPX definitions (stale for SB501000) |
| `Customization/AesthetikContainers/Pages/SB/SB501000.aspx` | acumatica-ci-cd | Standalone ASPX (current/correct) |
| `.github/workflows/acuops-deploy.yml` | acumatica-ci-cd | Zip packaging (lines 380-404) |
| `scripts/deploy.py` | acuops-pipeline | Import + publish logic |
| `scripts/validate-publish.py` | acuops-pipeline | Post-deploy validation (no ASPX checks) |

### Sandbox Credentials

- URL: `https://heritagefabrics-sandbox.acumatica.com`
- Tenant: `Heritage Fabrics`
- Username: `api-bot`
- Password: in 1Password item `acumatica-api-bot` (Studio B Infrastructure vault)

---

## Task 1: Reproduction Test — Does Import Overwrite ASPX?

**Goal:** Definitively answer: when a zip with `isReplaceIfExists: true` is imported, does it replace an existing ASPX file on the instance?

**Files:**
- Create: `scripts/test-aspx-overwrite.py`

### Step 1: Write the reproduction test script

This script will:
1. Authenticate to sandbox
2. Export the current customization package (baseline)
3. Import a modified package with a known ASPX change (add an HTML comment marker)
4. Publish
5. Export again and compare — did the ASPX change take effect?
6. Test both scenarios: CDATA-only change and physical-file-only change

```python
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

# Marker we inject into ASPX to detect overwrites
MARKER_CDATA = "<!-- OVERWRITE-TEST-CDATA-{ts} -->"
MARKER_FILE = "<!-- OVERWRITE-TEST-FILE-{ts} -->"
MARKER_BOTH = "<!-- OVERWRITE-TEST-BOTH-{ts} -->"

# Target ASPX — use SB302000 (low-risk screen) not SB501000 (active screen)
TARGET_ASPX_PATH = "Pages/SB/SB302000.aspx"
TARGET_ASPX_XPATH = r'AppRelativePath="Pages\\SB\\SB302000.aspx"'


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

    def login(self):
        log(f"Logging in to {self.base_url} as {self.username}...")
        resp = self.session.post(
            f"{self.base_url}/entity/auth/login",
            json={
                "name": self.username,
                "password": self.password,
                "tenant": self.tenant,
            },
            timeout=30,
        )
        if resp.status_code != 204:
            raise RuntimeError(f"Login failed (HTTP {resp.status_code}): {resp.text[:300]}")
        log("Authenticated", style="ok")

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
                        raise RuntimeError(f"Publish failed: {json.dumps(data.get('log', ''))[:1000]}")
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


def extract_aspx_from_zip(zip_bytes, aspx_path):
    """Extract an ASPX file's content from a zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Try both forward and back slashes
        for name in zf.namelist():
            if name.replace("\\", "/") == aspx_path.replace("\\", "/"):
                return zf.read(name).decode("utf-8")
    return None


def extract_aspx_from_cdata(zip_bytes, aspx_path):
    """Extract the CDATA content for an ASPX from project.xml in a zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_content = zf.read("project.xml").decode("utf-8")

    # Find the File element for our target ASPX
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

    # Inject marker after the <%@ Page directive line in CDATA
    escaped_path = aspx_path.replace("/", "\\\\")
    pattern = (
        r'(<File\s+AppRelativePath="'
        + re.escape(aspx_path.replace("/", "\\"))
        + r'"[^>]*Source="#CDATA"[^>]*>.*?<CDATA\s+name="Source"><!\[CDATA\[)'
        r'(<%@[^\n]*\n)'
    )
    replacement = r'\1\2' + marker + r'\n'
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
    """Return new zip bytes with marker injected into the standalone ASPX file."""
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf_in:
        all_files = {name: zf_in.read(name) for name in zf_in.namelist()}

    # Find the ASPX file in the zip
    target_key = None
    for name in all_files:
        if name.replace("\\", "/") == aspx_path.replace("\\", "/"):
            target_key = name
            break

    if not target_key:
        raise RuntimeError(f"File {aspx_path} not found in zip")

    content = all_files[target_key].decode("utf-8")
    # Inject after the Page directive
    lines = content.split("\n")
    new_lines = [lines[0], marker] + lines[1:]
    all_files[target_key] = "\n".join(new_lines).encode("utf-8")

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

    # Step 1: Inject marker
    modified_zip = modify_fn(baseline_zip, TARGET_ASPX_PATH, marker)
    log(f"Injected marker: {marker}")

    # Step 2: Import modified package
    client.import_package(PROJECT_NAME, modified_zip, description=f"Test: {scenario}")

    # Step 3: Publish
    client.publish([PROJECT_NAME])

    # Step 4: Wait for app pool restart
    log("Waiting 15s for app pool to stabilize...")
    time.sleep(15)

    # Step 5: Re-authenticate (session killed by app pool restart)
    client.login()

    # Step 6: Export and check
    result_zip = client.export_project(PROJECT_NAME)

    # Check CDATA
    cdata_content = extract_aspx_from_cdata(result_zip, TARGET_ASPX_PATH)
    cdata_has_marker = marker in (cdata_content or "")

    # Check physical file
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

        # Export baseline
        baseline_zip = client.export_project(PROJECT_NAME)
        log(f"Baseline exported ({len(baseline_zip)} bytes)")

        # Verify SB302000.aspx exists in both forms
        cdata = extract_aspx_from_cdata(baseline_zip, TARGET_ASPX_PATH)
        phys = extract_aspx_from_zip(baseline_zip, TARGET_ASPX_PATH)
        log(f"Baseline CDATA present: {cdata is not None}")
        log(f"Baseline physical file present: {phys is not None}")

        if not cdata and not phys:
            log("Target ASPX not found in baseline — cannot test", style="fail")
            sys.exit(1)

        results = []

        scenarios = {
            "cdata": ("CDATA only", inject_marker_in_cdata, MARKER_CDATA.format(ts=ts)),
            "file": ("Physical file only", inject_marker_in_file, MARKER_FILE.format(ts=ts)),
            "both": ("Both CDATA + file", None, MARKER_BOTH.format(ts=ts)),  # special handling
        }

        run_scenarios = [args.scenario] if args.scenario != "all" else ["cdata", "file", "both"]

        for s_key in run_scenarios:
            s_name, modify_fn, marker = scenarios[s_key]

            if s_key == "both":
                # Inject into both CDATA and physical file
                step1 = inject_marker_in_cdata(baseline_zip, TARGET_ASPX_PATH, marker)
                step2 = inject_marker_in_file(step1, TARGET_ASPX_PATH, marker)
                result = run_test(client, s_name, lambda z, p, m: step2, marker, baseline_zip)
            else:
                result = run_test(client, s_name, modify_fn, marker, baseline_zip)

            results.append(result)

            # Restore baseline before next test
            if s_key != run_scenarios[-1]:
                log("Restoring baseline for next test...")
                client.import_package(PROJECT_NAME, baseline_zip, description="Restore baseline")
                client.publish([PROJECT_NAME])
                time.sleep(15)
                client.login()

        # Restore baseline after all tests
        log("\nRestoring baseline package...")
        client.import_package(PROJECT_NAME, baseline_zip, description="Restore after overwrite test")
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
```

### Step 2: Run the reproduction test

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python3 scripts/test-aspx-overwrite.py \
  --password "$(op item get acumatica-api-bot --vault 'Studio B Infrastructure' --fields password)" \
  --scenario all
```

**Expected output:** One of three outcomes:
- CDATA ignored, physical file wins → explains the incident directly
- Both applied → incident was caused by something else (caching? publish timing?)
- Neither applied → import truly doesn't overwrite

### Step 3: Save results to investigation doc

Record findings in `docs/investigations/2026-04-06-aspx-import-overwrite-results.md` with:
- Raw test output
- Which scenario(s) succeeded/failed
- Root cause determination

### Step 4: Commit

```bash
git add scripts/test-aspx-overwrite.py docs/investigations/
git commit -m "test: ASPX import overwrite reproduction test against sandbox"
```

---

## Task 2: Sync project.xml CDATA with Standalone ASPX

**Goal:** Eliminate the source-of-truth divergence by updating the SB501000.aspx CDATA in project.xml to match the current standalone file.

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml:169-247`

### Step 1: Read the current standalone SB501000.aspx

Read `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Pages/SB/SB501000.aspx` — this is the source of truth (Procurement Command Center with Filter primary view, KPIs, split container).

### Step 2: Replace the CDATA block in project.xml

Replace the entire CDATA content for `AppRelativePath="Pages\SB\SB501000.aspx"` (lines ~170-247) with the content from the standalone file.

The CDATA block structure stays the same:
```xml
<File AppRelativePath="Pages\SB\SB501000.aspx" Source="#CDATA">
    <CDATA name="Source"><![CDATA[
    {paste full content of standalone SB501000.aspx here}
    ]]></CDATA>
</File>
```

### Step 3: Verify no other ASPX files are divergent

Compare CDATA vs standalone for SB302000, SB302010, SB302020, SB302030. These should already be identical (confirmed during investigation). If any differ, sync them too.

### Step 4: Commit

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: sync SB501000 project.xml CDATA with standalone ASPX

The CDATA in project.xml was the old Container Maintenance form view
while the standalone file had the current Procurement Command Center
dashboard. This divergence may have contributed to the 2026-04-05
incident where deploys didn't update the screen.

Refs: docs/prompts/aspx-import-overwrite-investigation.md"
```

---

## Task 3: Add ASPX Verification to Pipeline (acuops-pipeline)

**Goal:** Add a post-deploy check that verifies ASPX files on the instance match what was deployed.

**Files:**
- Modify: `/Users/kevin/dev/acuops-pipeline/scripts/validate-publish.py`

### Step 1: Read the current validate-publish.py

Understand the existing validation structure (entity reachability + custom field checks).

### Step 2: Add ASPX content verification function

Add a new function that:
1. Exports the published customization project via `getProject` API
2. Extracts ASPX files from the exported zip
3. Compares them against the ASPX files in the deployed package
4. Reports any mismatches

Add to `validate-publish.py`:

```python
def validate_aspx_files(session, project_name, package_path):
    """Verify ASPX files on the instance match the deployed package.

    Exports the published project and compares ASPX file content against
    the original package. Catches silent failures where import doesn't
    overwrite existing files.
    """
    if not package_path or not Path(package_path).exists():
        warn("No package path provided — skipping ASPX verification")
        return True

    log("Verifying ASPX files match deployed package...")

    # Export current state from instance
    resp = session.session.post(
        f"{session.base_url}/CustomizationApi/getProject",
        json={"projectName": project_name},
        timeout=60,
    )
    if resp.status_code != 200:
        warn(f"Could not export project for ASPX verification (HTTP {resp.status_code})")
        return True  # Don't fail the pipeline on export failure

    instance_zip = base64.b64decode(resp.text.strip().strip('"'))

    # Load the deployed package
    deployed_zip = Path(package_path).read_bytes()

    # Extract and compare ASPX files
    mismatches = []
    with zipfile.ZipFile(io.BytesIO(deployed_zip)) as zf_deployed:
        aspx_files = [n for n in zf_deployed.namelist()
                      if n.lower().endswith(".aspx") and not n.startswith("__")]

        with zipfile.ZipFile(io.BytesIO(instance_zip)) as zf_instance:
            instance_names = {n.replace("\\", "/"): n for n in zf_instance.namelist()}

            for aspx in aspx_files:
                normalized = aspx.replace("\\", "/")
                deployed_content = zf_deployed.read(aspx).decode("utf-8").strip()

                instance_key = instance_names.get(normalized)
                if not instance_key:
                    warn(f"ASPX file {normalized} not found in exported project")
                    mismatches.append(normalized)
                    continue

                instance_content = zf_instance.read(instance_key).decode("utf-8").strip()

                if deployed_content != instance_content:
                    # Show first difference for debugging
                    deployed_lines = deployed_content.splitlines()
                    instance_lines = instance_content.splitlines()
                    for i, (d, inst) in enumerate(zip(deployed_lines, instance_lines)):
                        if d != inst:
                            warn(f"ASPX mismatch in {normalized} at line {i+1}:")
                            warn(f"  Deployed: {d[:100]}")
                            warn(f"  Instance: {inst[:100]}")
                            break
                    mismatches.append(normalized)
                else:
                    ok(f"ASPX verified: {normalized}")

    if mismatches:
        fail(f"ASPX files NOT overwritten by import: {', '.join(mismatches)}")
        fail("Manual fix: delete stale files via SM204505 and redeploy")
        return False

    ok("All ASPX files match deployed package")
    return True
```

### Step 3: Wire it into the main validation flow

In the `main()` function of validate-publish.py, add a call to `validate_aspx_files` after the entity/field checks. Accept `--package` and `--project` CLI args to pass the deployed zip path and project name.

### Step 4: Update the workflow to pass the package path

In `acumatica-ci-cd/.github/workflows/acuops-deploy.yml`, update the validate-publish step to pass `--package` pointing to the deployed zip.

### Step 5: Commit (acuops-pipeline)

```bash
cd /Users/kevin/dev/acuops-pipeline
git add scripts/validate-publish.py
git commit -m "feat: add ASPX file verification to post-deploy validation

Exports the published project and compares ASPX files against the
deployed package. Catches silent failures where customization import
doesn't overwrite existing ASPX files.

Refs: studio-b-ai/acumatica-ci-cd docs/prompts/aspx-import-overwrite-investigation.md"
```

### Step 6: Commit (acumatica-ci-cd workflow)

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add .github/workflows/acuops-deploy.yml
git commit -m "fix: pass package path to validate-publish for ASPX verification"
```

---

## Task 4: Write Root Cause Analysis Document

**Goal:** Document findings from the reproduction test, the fix, and recommendations.

**Files:**
- Create: `docs/investigations/2026-04-06-aspx-import-overwrite-results.md`

### Step 1: Write the RCA document

Template:

```markdown
# ASPX Import Overwrite — Root Cause Analysis

**Date:** 2026-04-06
**Incident:** 2026-04-05 — SB501000.aspx stuck on TabView.master across 3 deploys
**Investigated by:** Claude (automated reproduction test)

## Root Cause

{Filled in based on Task 1 results}

## Reproduction Test Results

| Scenario | CDATA Overwritten | Physical File Overwritten |
|----------|------------------|--------------------------|
| CDATA only | {yes/no} | {yes/no} |
| Physical file only | {yes/no} | {yes/no} |
| Both | {yes/no} | {yes/no} |

## Contributing Factors

1. **Source-of-truth divergence**: project.xml CDATA had old Container Maintenance
   view while standalone file had Procurement Command Center. Fixed in Task 2.
2. **No ASPX verification**: Pipeline only validated DAC fields, not ASPX files.
   Fixed in Task 3.
3. {Additional findings from test}

## Recommendations

1. {Based on test results — e.g., always use physical files, not CDATA}
2. ASPX verification now runs as part of post-deploy validation
3. Keep project.xml CDATA in sync with standalone files (or remove CDATA entirely)

## Files Changed

- `Customization/AesthetikContainers/project.xml` — synced CDATA
- `acuops-pipeline: scripts/validate-publish.py` — ASPX verification
- `.github/workflows/acuops-deploy.yml` — passes package path to validation
```

### Step 2: Commit

```bash
git add docs/investigations/
git commit -m "docs: ASPX import overwrite root cause analysis"
```

---

## Task 5: Create PRs

### Step 1: PR for acumatica-ci-cd

```bash
cd /Users/kevin/dev/acumatica-ci-cd
gh pr create --title "fix: ASPX import overwrite investigation + CDATA sync" --body "$(cat <<'EOF'
## Summary
- Reproduction test confirming whether Acumatica import API overwrites ASPX files
- Synced SB501000 project.xml CDATA with standalone ASPX (eliminates dual-source divergence)
- Updated workflow to pass package path for ASPX verification
- Root cause analysis document

## Context
On 2026-04-05, SB501000.aspx on production was stuck with TabView.master despite 3 deploys.
Investigation found project.xml CDATA and standalone ASPX were completely different screens.

## Test plan
- [ ] Run `scripts/test-aspx-overwrite.py` against sandbox
- [ ] Verify project.xml CDATA matches standalone SB501000.aspx
- [ ] Deploy to sandbox and verify screen loads correctly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Step 2: PR for acuops-pipeline (if changes made there)

```bash
cd /Users/kevin/dev/acuops-pipeline
gh pr create --title "feat: ASPX file verification in post-deploy validation" --body "$(cat <<'EOF'
## Summary
- Added ASPX content verification to validate-publish.py
- Exports published project and compares ASPX files against deployed package
- Catches silent failures where import doesn't overwrite existing files

## Context
Cross-repo dependency: studio-b-ai/acumatica-ci-cd passes --package to validation step.

## Test plan
- [ ] Run validate-publish with --package pointing to a known package
- [ ] Verify mismatch detection works when files differ

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
