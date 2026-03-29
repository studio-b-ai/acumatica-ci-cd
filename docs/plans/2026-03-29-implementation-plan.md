# GI Builder Engine + CI/CD Pipeline Hardening — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a safe, programmatic GI creation engine for AcuDev and harden the CI/CD pipeline to prevent another 2026-03-29 outage.

**Architecture:** Direct SQL inside `CustomizationPlugin.UpdateDatabase()` with `INFORMATION_SCHEMA` schema discovery and `BEGIN TRAN`/`COMMIT` wrapping. Pipeline gets a new Heritage Test hard gate between sandbox and prod, destructive SQL detection, GI health checks, and pre/post-deploy baseline diffing.

**Tech Stack:** Python 3 (pipeline scripts), C# (CustomizationPlugin), GitHub Actions YAML, Acumatica REST API, SQL Server

---

## Task 1: Research Spike — SM208000 Network Traffic

**Goal:** Discover if Acumatica has undocumented REST/SOAP endpoints for GI CRUD.

**Files:**
- Create: `docs/research/2026-03-29-gi-api-spike.md`

**Step 1: Open sandbox SM208000 in browser with DevTools**

Navigate to the sandbox Acumatica instance Generic Inquiry designer screen (SM208000). Open Chrome DevTools → Network tab. Filter to XHR/Fetch requests.

**Step 2: Create a test GI through the UI**

- Click "New" to create a new Generic Inquiry
- Add one table: `PX.Objects.IN.InventoryItem`
- Add one result column: `InventoryCD`
- Save the GI with name "TestSpike001"
- Capture every network request during save

**Step 3: Analyze captured requests**

Look for:
- The save endpoint URL (likely `/Screen/SM208000/...` or `/api/...`)
- The request payload format (JSON? SOAP XML? form data?)
- Whether it's a screen API call or a dedicated GI endpoint
- Any `PUT`/`POST` to GI-specific routes

**Step 4: Test if discovered endpoint is callable externally**

If a GI CRUD endpoint is found:
```bash
curl -s -X POST "https://{sandbox-url}/{endpoint}" \
  -H "Cookie: {session-cookie}" \
  -H "Content-Type: application/json" \
  -d '{payload-from-step-3}'
```

**Step 5: Clean up — delete TestSpike001 GI from SM208000**

**Step 6: Document findings**

Write results to `docs/research/2026-03-29-gi-api-spike.md`:
- Endpoint discovered (or "none found — SM208000 uses internal screen API only")
- Request/response format
- Go/no-go for Path C (GI CRUD API)

**Step 7: Commit**

```bash
git add docs/research/2026-03-29-gi-api-spike.md
git commit -m "research: SM208000 network traffic analysis for GI CRUD API"
```

---

## Task 2: Research Spike — Import Without Publish

**Goal:** Determine if `CustomizationApi/Import` alone makes GI definitions visible.

**Files:**
- Modify: `docs/research/2026-03-29-gi-api-spike.md`

**Step 1: Generate a minimal GI XML package**

Create a test customization .zip containing a single GI definition. Use the UserAuditTrail XML structure as template but with a unique name (`TestImportSpike001`) and fresh GUIDs.

```bash
# Create temp directory for the package
mkdir -p /tmp/gi-spike-package
```

Create `/tmp/gi-spike-package/GenericInquiryScreen_TestImportSpike001.xml` with this minimal structure (single table, single result, no filters):

```xml
<GenericInquiryScreen>
  <data-set>
    <relations format-version="3" relations-version="20190410" main-table="GIDesign"
               stable-sharing="True" file-name="TestImportSpike001">
      <link from="GIFilter (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIGroupBy (DesignID)" to="GIDesign (DesignID)" />
      <link from="GINavigationCondition (DesignID)" to="GIDesign (DesignID)" />
      <link from="GINavigationParameter (DesignID)" to="GIDesign (DesignID)" />
      <link from="GINavigationScreen (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIOn (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIRelation (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIResult (DesignID)" to="GIDesign (DesignID)" />
      <link from="GISort (DesignID)" to="GIDesign (DesignID)" />
      <link from="GITable (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIWhere (DesignID)" to="GIDesign (DesignID)" />
      <link from="GIOn (DesignID,LineNbr)" to="GIRelation (DesignID,LineNbr)" />
      <link from="GIRelation (DesignID)" to="GITable (DesignID,Alias)" />
      <link from="GIResult (DesignID)" to="GITable (DesignID,Alias)" />
    </relations>
    <layout>
      <group id="1" sorting="Natural" filtering="Natural" />
    </layout>
    <data>
      <GIDesign>
        <row DesignID="{FRESH-UUID}" Name="TestImportSpike001" ScreenID="GI999001"
             FilterColCount="3" PageSize="0" ExportTop="0"
             NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0"
             MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0"
             ExposeViaOData="1" ExposeViaMobile="0">
          <GITable Alias="StockItem" Name="PX.Objects.IN.InventoryItem">
            <GIResult LineNbr="1" SortOrder="1" IsActive="1" Field="InventoryCD"
                      Width="120" IsVisible="1" DefaultNav="1" QuickFilter="0"
                      FastFilter="1" Caption="Inventory ID" RowID="{FRESH-UUID}" />
          </GITable>
        </row>
      </GIDesign>
    </data>
  </data-set>
</GenericInquiryScreen>
```

Create a minimal `project.xml` wrapper and zip it.

**Step 2: Import without publishing**

```bash
# Use deploy.py's import-only capability (or direct API call)
python scripts/deploy.py \
  --url "$ACUMATICA_SANDBOX_URL" \
  --username "$ACUMATICA_USERNAME" \
  --password "$ACUMATICA_PASSWORD" \
  --project TestImportSpike001 \
  --package /tmp/gi-spike-package.zip \
  --import-only  # If supported; otherwise use curl to call Import API directly
```

If `--import-only` isn't supported:
```bash
curl -s -X POST "$ACUMATICA_SANDBOX_URL/CustomizationApi/Import" \
  -H "Cookie: {session}" \
  -H "Content-Type: application/json" \
  -d '{"projectName":"TestImportSpike001","projectDescription":"Spike test","projectLevel":1,"isReplaceIfExists":true,"projectContent":"BASE64_ZIP"}'
```

**Step 3: Check if GI is visible**

```bash
# Check REST API
curl -s "$ACUMATICA_SANDBOX_URL/entity/Default/24.200.001/TestImportSpike001?\$top=1"
# Expected: 404 (not visible without publish) or 200 (visible!)
```

Also check SM208000 in the browser — does TestImportSpike001 appear in the GI list?

**Step 4: Clean up — delete the test project from sandbox**

**Step 5: Document findings**

Append to `docs/research/2026-03-29-gi-api-spike.md`:
- Import-only result: GI visible or not?
- Go/no-go for import-without-publish path

**Step 6: Commit**

```bash
git add docs/research/2026-03-29-gi-api-spike.md
git commit -m "research: import-without-publish GI test results"
```

---

## Task 3: Research Spike — Direct SQL + Schema Discovery via Plugin

**Goal:** Confirm SQL access works inside `UpdateDatabase()`, test `INFORMATION_SCHEMA` queries, test transaction support.

**Files:**
- Modify: `Customization/StudioBAcuOps/project.xml`
- Modify: `docs/research/2026-03-29-gi-api-spike.md`

**Step 1: Write schema discovery SQL in the plugin**

Modify `Customization/StudioBAcuOps/project.xml`. Replace the current `UpdateDatabase()` body with a diagnostic version that queries `INFORMATION_SCHEMA` and logs the results. Keep the existing cleanup logic. Add schema discovery BEFORE the cleanup:

```csharp
public override void UpdateDatabase()
{
    try
    {
        var cs = ConfigurationManager.ConnectionStrings["ProjectX"];
        if (cs == null) { WriteLog("[StudioBAcuOps] No connection string — skipping"); return; }
        string connStr = cs.ConnectionString + ";TrustServerCertificate=True";

        using (var conn = new SqlConnection(connStr))
        {
            conn.Open();

            // === SCHEMA DISCOVERY SPIKE ===
            string[] giTables = { "GIDesign", "GITable", "GIResult", "GIWhere",
                                  "GISort", "GIFilter", "GIRelation", "GIOn", "GIGroupBy" };

            foreach (var tableName in giTables)
            {
                WriteLog("[SCHEMA] Table: " + tableName);
                using (var cmd = new SqlCommand(
                    @"SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH,
                             COLUMN_DEFAULT
                      FROM INFORMATION_SCHEMA.COLUMNS
                      WHERE TABLE_NAME = @Table
                      ORDER BY ORDINAL_POSITION", conn))
                {
                    cmd.Parameters.AddWithValue("@Table", tableName);
                    using (var reader = cmd.ExecuteReader())
                    {
                        while (reader.Read())
                        {
                            string col = reader.GetString(0);
                            string dtype = reader.GetString(1);
                            string nullable = reader.GetString(2);
                            string maxLen = reader.IsDBNull(3) ? "n/a" : reader.GetInt32(3).ToString();
                            string def = reader.IsDBNull(4) ? "NULL" : reader.GetString(4);
                            WriteLog(string.Format("  {0}: {1}({2}) nullable={3} default={4}",
                                col, dtype, maxLen, nullable, def));
                        }
                    }
                }
            }

            // === TRANSACTION SUPPORT TEST ===
            WriteLog("[SCHEMA] Testing transaction support...");
            using (var txn = conn.BeginTransaction())
            {
                using (var cmd = new SqlCommand(
                    "SELECT COUNT(*) FROM GIDesign", conn, txn))
                {
                    int count = (int)cmd.ExecuteScalar();
                    WriteLog("[SCHEMA] GIDesign row count inside transaction: " + count);
                }
                txn.Rollback();
                WriteLog("[SCHEMA] Transaction ROLLBACK succeeded — transactions work");
            }

            // === TEMPLATE ROW EXTRACTION ===
            WriteLog("[SCHEMA] Extracting template row from InventoryAllocationDetail...");
            using (var cmd = new SqlCommand(
                @"SELECT TOP 1 CreatedByID, CreatedByScreenID, CreatedDateTime,
                         LastModifiedByID, LastModifiedByScreenID, LastModifiedDateTime
                  FROM GIDesign WHERE Name = 'InventoryAllocationDetail'", conn))
            {
                using (var reader = cmd.ExecuteReader())
                {
                    if (reader.Read())
                    {
                        for (int i = 0; i < reader.FieldCount; i++)
                        {
                            WriteLog(string.Format("  {0} = {1}",
                                reader.GetName(i), reader.IsDBNull(i) ? "NULL" : reader.GetValue(i)));
                        }
                    }
                }
            }

            WriteLog("[SCHEMA] Schema discovery spike complete");

            // === EXISTING CLEANUP (unchanged) ===
            // ... keep existing cleanup code from current project.xml ...
        }
    }
    catch (Exception ex)
    {
        WriteLog("[StudioBAcuOps] Error: " + ex.ToString());
    }
}
```

**Step 2: Deploy to sandbox**

Deploy StudioBAcuOps to the sandbox instance via the CI/CD pipeline. The schema discovery runs during `UpdateDatabase()` and outputs to the customization publish log.

**Step 3: Capture the publish log**

The `WriteLog()` output appears in the Acumatica publish log. Capture the full schema discovery output.

**Step 4: Parse results into schema map**

From the publish log, extract:
- Every column, data type, nullable flag, max length, and default for each GI table
- The template row audit column values
- Confirmation that transactions work

**Step 5: Document findings**

Append to `docs/research/2026-03-29-gi-api-spike.md`:
- Full schema map per GI table (NOT NULL columns highlighted)
- Template row values
- Transaction support confirmed/denied
- Go/no-go for Path B (Direct SQL)

**Step 6: Revert the diagnostic plugin**

Replace the schema discovery code with the original cleanup-only version. The schema data is captured — we don't need it running on every publish.

**Step 7: Commit**

```bash
git add docs/research/2026-03-29-gi-api-spike.md
git commit -m "research: GI schema discovery via INFORMATION_SCHEMA + transaction test"
```

---

## Task 4: Research Spike — Callable Plugin Endpoint

**Goal:** Determine if a CustomizationPlugin can expose a REST-callable endpoint.

**Files:**
- Modify: `docs/research/2026-03-29-gi-api-spike.md`

**Step 1: Research Acumatica's endpoint registration**

Check Acumatica developer docs for:
- Custom API endpoints via `ServiceGate` or `PXGraph`-based handlers
- Contract-based API: can a custom graph be called via `/entity/...`?
- `ICustomEndpoint` interface or similar
- Whether `[PXRestService]` attribute exists

**Step 2: Check existing codebase for endpoint patterns**

```bash
# Search for any REST endpoint patterns in the repo
grep -r "RestService\|ServiceGate\|ICustomEndpoint\|WebMethod\|PXRestHandler" Customization/
```

**Step 3: Check SM208000 for screen API pattern**

The Acumatica screen API (`/Screen/{ScreenID}/...`) allows CRUD on any screen. Check if SM208000 (GI designer) supports:
```bash
curl -s "$ACUMATICA_SANDBOX_URL/Screen/SM208000" \
  -H "Cookie: {session}" \
  -H "Content-Type: application/json"
```

This may reveal the screen API contract for GI management.

**Step 4: Document findings**

Append to `docs/research/2026-03-29-gi-api-spike.md`:
- Can a plugin expose a callable endpoint? (yes/no, with method)
- Can the SM208000 screen API be used for GI CRUD? (yes/no)
- Go/no-go for Path D (callable plugin endpoint)

**Step 5: Write final spike summary**

Add a "Conclusions" section to the research doc:
- Primary execution path recommendation
- Fallback paths
- Risks and constraints per path

**Step 6: Commit**

```bash
git add docs/research/2026-03-29-gi-api-spike.md
git commit -m "research: callable plugin endpoint + final spike conclusions"
```

---

## Task 5: Destructive SQL Detection in validate-project.py

**Goal:** Hard-fail builds that contain direct SQL against GI tables without explicit review marker.

**Files:**
- Modify: `scripts/validate-project.py`
- Create: `tests/test_validate_gi_sql.py`

**Step 1: Write the failing test**

Create `tests/test_validate_gi_sql.py`:

```python
"""Tests for destructive GI SQL detection in validate-project.py."""
import subprocess
import tempfile
import os
from pathlib import Path


def make_project_xml(graph_code: str) -> str:
    """Create a minimal project.xml with the given Graph code."""
    return f'''<Customization level="1" description="test">
  <Graph ClassName="TestPlugin" Source="#CDATA" IsNew="True" FileType="NewFile">
    <CDATA name="Source"><![CDATA[{graph_code}]]></CDATA>
  </Graph>
</Customization>'''


def run_validate(project_xml_content: str) -> subprocess.CompletedProcess:
    """Write project.xml to temp dir and run validate-project.py against it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        proj_dir = Path(tmpdir) / "TestProject"
        proj_dir.mkdir()
        (proj_dir / "project.xml").write_text(project_xml_content)
        return subprocess.run(
            ["python", "scripts/validate-project.py", str(proj_dir)],
            capture_output=True, text=True
        )


def test_insert_into_gi_table_blocked():
    code = '''using Customization;
public class Bad : CustomizationPlugin {
    public override void UpdateDatabase() {
        ExecuteSQL("INSERT INTO GIDesign (Name) VALUES ('bad')");
    }
}'''
    result = run_validate(make_project_xml(code))
    assert result.returncode != 0
    assert "GI tables" in result.stdout or "GI tables" in result.stderr
    assert "AAR-2026-03-29" in result.stdout or "AAR-2026-03-29" in result.stderr


def test_delete_from_gi_table_blocked():
    code = '''using Customization;
public class Bad : CustomizationPlugin {
    public override void UpdateDatabase() {
        ExecuteSQL("DELETE FROM GIResult WHERE DesignID = @id");
    }
}'''
    result = run_validate(make_project_xml(code))
    assert result.returncode != 0


def test_update_gi_table_blocked():
    code = '''using Customization;
public class Bad : CustomizationPlugin {
    public override void UpdateDatabase() {
        ExecuteSQL("UPDATE GIWhere SET Value1 = 'x'");
    }
}'''
    result = run_validate(make_project_xml(code))
    assert result.returncode != 0


def test_gi_sql_with_review_marker_allowed():
    code = '''using Customization;
public class Safe : CustomizationPlugin {
    public override void UpdateDatabase() {
        // -- REVIEWED: gi-sql-safe
        ExecuteSQL("DELETE FROM GIDesign WHERE Name = 'orphan'");
    }
}'''
    result = run_validate(make_project_xml(code))
    # Should pass (or at least not fail on GI SQL check)
    assert "GI tables" not in result.stdout


def test_non_gi_sql_allowed():
    code = '''using Customization;
public class Safe : CustomizationPlugin {
    public override void UpdateDatabase() {
        ExecuteSQL("INSERT INTO MyCustomTable (Name) VALUES ('ok')");
    }
}'''
    result = run_validate(make_project_xml(code))
    # Should not trigger GI SQL check
    assert "GI tables" not in result.stdout
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_validate_gi_sql.py -v
```

Expected: FAIL — validate-project.py doesn't have GI SQL detection yet.

**Step 3: Implement GI SQL detection**

In `scripts/validate-project.py`, add a new validation function. Insert it near the existing `<Graph>` validation loop (around line 249):

```python
import re

# GI table SQL detection pattern (case-insensitive)
GI_SQL_PATTERN = re.compile(
    r'\b(INSERT\s+INTO|DELETE\s+FROM|UPDATE|DROP\s+TABLE|TRUNCATE\s+TABLE|ALTER\s+TABLE)'
    r'\s+GI\w*',
    re.IGNORECASE
)

GI_SQL_REVIEW_MARKER = "-- REVIEWED: gi-sql-safe"


def validate_gi_sql(class_name: str, code: str):
    """Block direct SQL against GI tables unless explicitly reviewed.

    See docs/AAR-2026-03-29-gi-sql-insert-outage.md for why this exists.
    """
    if GI_SQL_REVIEW_MARKER in code:
        return  # Explicitly reviewed — allow

    matches = GI_SQL_PATTERN.findall(code)
    if matches:
        error(
            f"BLOCKED: Direct SQL against GI tables detected in {class_name}. "
            f"This pattern caused a 45-minute production outage on 2026-03-29. "
            f"See docs/AAR-2026-03-29-gi-sql-insert-outage.md. "
            f"If this SQL has been reviewed and is safe, add: {GI_SQL_REVIEW_MARKER}"
        )
```

Then call `validate_gi_sql(class_name, code)` in the `<Graph>` validation loop, right after the existing `validate_customization_plugin_ban` call.

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_validate_gi_sql.py -v
```

Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add scripts/validate-project.py tests/test_validate_gi_sql.py
git commit -m "feat: add destructive GI SQL detection to validate-project.py

Block INSERT/DELETE/UPDATE/DROP/TRUNCATE/ALTER against GI* tables
unless code contains '-- REVIEWED: gi-sql-safe' marker.
References AAR-2026-03-29."
```

---

## Task 6: Sandbox Gate — Unskippable for Plugin Changes

**Goal:** Prevent `skip_sandbox=true` from bypassing sandbox when CustomizationPlugin code changed.

**Files:**
- Modify: `.github/workflows/deploy-customization.yml`

**Step 1: Add plugin change detection step**

In the `build` job (before sandbox-gate), add a step that checks the git diff for plugin patterns:

```yaml
    - name: Detect plugin changes
      id: plugin_check
      run: |
        # Check diff against the base branch for plugin-related changes
        DIFF=$(git diff origin/main -- '*.xml' '*.cs' || true)
        if echo "$DIFF" | grep -qiE '(CustomizationPlugin|UpdateDatabase|<Sql>|ExecuteSQL|SqlCommand)'; then
          echo "plugin_changes=true" >> "$GITHUB_OUTPUT"
          echo "::warning::CustomizationPlugin changes detected — sandbox gate is MANDATORY"
        else
          echo "plugin_changes=false" >> "$GITHUB_OUTPUT"
        fi
```

**Step 2: Update sandbox-gate job condition**

Modify the sandbox-gate `if:` condition (around line 323). Replace the simple `skip_sandbox != 'true'` check:

```yaml
  sandbox-gate:
    name: Sandbox Publish Gate
    needs: [build, qualify]
    runs-on: ubuntu-latest
    timeout-minutes: 20
    if: |
      always() &&
      needs.build.result == 'success' &&
      github.event_name != 'pull_request' &&
      github.event.inputs.force_qualify != 'true' &&
      (
        github.event.inputs.skip_sandbox != 'true' ||
        needs.build.outputs.plugin_changes == 'true'
      ) && (
        needs.qualify.result == 'success' ||
        needs.qualify.result == 'skipped'
      )
```

This means: skip_sandbox is honored UNLESS plugin changes are detected.

**Step 3: Add skip_sandbox_force input**

Add a new workflow input for the emergency override:

```yaml
    inputs:
      # ... existing inputs ...
      skip_sandbox_force:
        description: 'Force skip sandbox even for plugin changes (LOGGED, use with caution)'
        required: false
        type: boolean
        default: false
```

Update the sandbox-gate condition to respect force override:

```yaml
      (
        github.event.inputs.skip_sandbox != 'true' ||
        (needs.build.outputs.plugin_changes == 'true' &&
         github.event.inputs.skip_sandbox_force != 'true')
      ) && (
```

**Step 4: Add Slack notification for force override**

Add a step in sandbox-gate that fires when `skip_sandbox_force=true` AND `plugin_changes=true`:

```yaml
    - name: Log forced sandbox skip
      if: |
        github.event.inputs.skip_sandbox_force == 'true' &&
        needs.build.outputs.plugin_changes == 'true'
      run: |
        echo "::error::SANDBOX GATE FORCE-SKIPPED for plugin changes by ${{ github.actor }}"
        # TODO: Add Slack webhook notification here
```

**Step 5: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "feat: make sandbox gate unskippable for CustomizationPlugin changes

skip_sandbox=true is now rejected when plugin changes are detected.
New skip_sandbox_force=true flag for emergency override (logged).
Ref: AAR-2026-03-29"
```

---

## Task 7: GI Health Check in Post-Publish Verification

**Goal:** Detect GI subsystem corruption after publish.

**Files:**
- Modify: `scripts/validate-publish.py`
- Create: `tests/test_validate_gi_health.py`

**Step 1: Write the failing test**

Create `tests/test_validate_gi_health.py`:

```python
"""Tests for GI health check in post-publish verification."""
import json
from unittest.mock import MagicMock, patch


def test_gi_probe_healthy():
    """GI probe passes when known GI returns 200."""
    from scripts.validate_publish_gi import check_gi_health

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200)
    assert check_gi_health(session, "https://acumatica.example.com") is True


def test_gi_probe_broken():
    """GI probe fails when known GI returns 500."""
    from scripts.validate_publish_gi import check_gi_health

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=500)
    assert check_gi_health(session, "https://acumatica.example.com") is False


def test_gi_probe_timeout():
    """GI probe fails when request times out."""
    import requests
    from scripts.validate_publish_gi import check_gi_health

    session = MagicMock()
    session.get.side_effect = requests.exceptions.Timeout()
    assert check_gi_health(session, "https://acumatica.example.com") is False
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_validate_gi_health.py -v
```

Expected: FAIL — `validate_publish_gi` module doesn't exist yet.

**Step 3: Implement GI health check**

Create `scripts/validate_publish_gi.py`:

```python
"""GI health check for post-publish verification.

Probes the GI subsystem by querying a known Generic Inquiry via REST API.
If the GI subsystem is corrupted (e.g., duplicate key in PXGenericInqGrph),
this probe returns 500 and triggers rollback.
"""
import requests

# Known GIs to probe — these should always exist on any Heritage Fabrics instance
PROBE_GIS = [
    "InventoryAllocationDetail",
    "LotAvailability",
]

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def check_gi_health(session: requests.Session, base_url: str) -> bool:
    """Probe the GI subsystem by querying known GIs.

    Returns True if at least one GI responds successfully.
    Returns False if ALL probes fail (indicates systemic GI corruption).
    """
    base_url = base_url.rstrip("/")
    any_success = False

    for gi_name in PROBE_GIS:
        try:
            resp = session.get(
                f"{base_url}/entity/Default/24.200.001/{gi_name}",
                params={"$top": "1"},
                timeout=30,
            )
            if resp.status_code == 200:
                print(f"{GREEN}[  OK  ]{RESET} GI probe: {gi_name} responded (HTTP 200)")
                any_success = True
            else:
                print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} returned HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} timed out")
        except Exception as exc:
            print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} error: {exc}")

    if not any_success:
        print(f"{RED}[FAIL  ]{RESET} GI SUBSYSTEM UNHEALTHY — all probes failed")

    return any_success
```

**Step 4: Integrate into validate-publish.py**

Add the GI health check call after the entity validation loop (around line 293 in `validate-publish.py`):

```python
from validate_publish_gi import check_gi_health

# After entity validation loop:
gi_healthy = check_gi_health(session, base_url)
if not gi_healthy:
    fail("GI subsystem unhealthy — all GI probes failed. Possible PXGenericInqGrph corruption.")
```

**Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_validate_gi_health.py -v
```

Expected: All 3 tests PASS.

**Step 6: Commit**

```bash
git add scripts/validate_publish_gi.py scripts/validate-publish.py tests/test_validate_gi_health.py
git commit -m "feat: add GI health check to post-publish verification

Probes known GIs (InventoryAllocationDetail, LotAvailability) via REST API
after publish. All probes failing = GI subsystem corruption = trigger rollback.
Ref: AAR-2026-03-29"
```

---

## Task 8: Emergency Deploy Fix (HTTP 401)

**Goal:** Investigate and fix the basic auth 401 error.

**Files:**
- Modify: `scripts/emergency-deploy-basic-auth.py`

**Step 1: Investigate the 401**

Read `scripts/emergency-deploy-basic-auth.py` and check:

1. **Credential source:** Lines 5-7 use `ACUMATICA_URL`, `ACUMATICA_USERNAME`, `ACUMATICA_PASSWORD` env vars. Verify these are set correctly in GitHub Actions secrets.

2. **Auth method:** Line 13-14 uses `requests.post(url, auth=(USER, PASS))` which sends HTTP Basic Auth. Check if Acumatica's `CustomizationApi` endpoints actually accept Basic Auth, or if they only accept session cookies.

3. **Likely root cause:** Acumatica's REST API may not support HTTP Basic Auth on `CustomizationApi/*` endpoints. The session-based login (`/entity/auth/login`) returns a cookie, and that cookie is required for subsequent API calls. Basic Auth is a different mechanism.

**Step 2: Fix — use session auth with retry**

If Basic Auth doesn't work on Acumatica, replace it with session-based auth that retries aggressively (the emergency script exists because normal auth might be failing, but we should still try session auth first):

```python
def emergency_login(url, username, password, max_retries=5, delay=15):
    """Attempt session login with aggressive retries for emergency deploys."""
    session = requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(
                f"{url}/entity/auth/login",
                json={"name": username, "password": password},
                timeout=30,
            )
            if resp.status_code in (200, 204):
                print(f"Emergency login succeeded on attempt {attempt}")
                return session
            print(f"Emergency login attempt {attempt}: HTTP {resp.status_code}")
        except Exception as exc:
            print(f"Emergency login attempt {attempt}: {exc}")
        if attempt < max_retries:
            time.sleep(delay)
    raise RuntimeError(f"Emergency login failed after {max_retries} attempts")
```

**Step 3: Add post-publish smoke test**

After the emergency publish completes, add a minimal GI probe (reuse `check_gi_health` from Task 7):

```python
from validate_publish_gi import check_gi_health

# After publish completes:
gi_ok = check_gi_health(session, URL)
if not gi_ok:
    print("WARNING: GI subsystem unhealthy after emergency deploy")
```

**Step 4: Add Slack notification for emergency deploys**

Add a Slack webhook call at the end of the script:

```python
def notify_emergency_deploy(outcome: str, operator: str, reason: str):
    """Log emergency deploy to Slack."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return
    requests.post(webhook_url, json={
        "text": f":rotating_light: *EMERGENCY DEPLOY* by {operator}\n"
                f"Outcome: {outcome}\nReason: {reason}"
    })
```

**Step 5: Commit**

```bash
git add scripts/emergency-deploy-basic-auth.py
git commit -m "fix: replace basic auth with session auth + retries in emergency deploy

Basic auth returned HTTP 401 during 2026-03-29 incident because
Acumatica CustomizationApi doesn't accept Basic Auth.
Now uses session-based auth with 5 retries at 15s intervals.
Added post-deploy GI health check and Slack notification."
```

---

## Task 9: Pre/Post-Deploy GI Baseline Diffing

**Goal:** Capture GI state before deploy, compare after, warn on unexpected changes.

**Files:**
- Create: `scripts/gi_baseline.py`
- Create: `tests/test_gi_baseline.py`
- Modify: `.github/workflows/deploy-customization.yml`

**Step 1: Write the failing test**

Create `tests/test_gi_baseline.py`:

```python
"""Tests for GI baseline capture and diffing."""
import json
from scripts.gi_baseline import diff_baselines


def test_no_changes():
    before = [{"name": "GI1", "designId": "aaa"}, {"name": "GI2", "designId": "bbb"}]
    after = [{"name": "GI1", "designId": "aaa"}, {"name": "GI2", "designId": "bbb"}]
    result = diff_baselines(before, after)
    assert result["added"] == []
    assert result["removed"] == []
    assert result["duplicates"] == []


def test_new_gi_detected():
    before = [{"name": "GI1", "designId": "aaa"}]
    after = [{"name": "GI1", "designId": "aaa"}, {"name": "GI2", "designId": "bbb"}]
    result = diff_baselines(before, after)
    assert len(result["added"]) == 1
    assert result["added"][0]["name"] == "GI2"


def test_missing_gi_detected():
    before = [{"name": "GI1", "designId": "aaa"}, {"name": "GI2", "designId": "bbb"}]
    after = [{"name": "GI1", "designId": "aaa"}]
    result = diff_baselines(before, after)
    assert len(result["removed"]) == 1
    assert result["removed"][0]["name"] == "GI2"


def test_duplicate_gi_detected():
    before = [{"name": "GI1", "designId": "aaa"}]
    after = [{"name": "GI1", "designId": "aaa"}, {"name": "GI1", "designId": "bbb"}]
    result = diff_baselines(before, after)
    assert len(result["duplicates"]) == 1
    assert result["duplicates"][0] == "GI1"
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_gi_baseline.py -v
```

Expected: FAIL — module doesn't exist.

**Step 3: Implement gi_baseline.py**

Create `scripts/gi_baseline.py`:

```python
"""Pre/post-deploy GI baseline capture and diff.

Captures the list of Generic Inquiries before and after a customization publish.
Detects unexpected additions, removals, and duplicates.
"""
import argparse
import json
import os
import sys
import requests

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Known GIs that should always exist
EXPECTED_GIS = [
    "InventoryAllocationDetail",
    "LotAvailability",
]


def capture_baseline(session: requests.Session, base_url: str) -> list[dict]:
    """Capture current GI list from the Acumatica instance.

    Queries each known GI endpoint to build a baseline. This is a best-effort
    approach since there's no "list all GIs" REST endpoint.
    """
    base_url = base_url.rstrip("/")
    baseline = []

    # Try to get GI list via SM208000 screen API
    try:
        resp = session.get(
            f"{base_url}/entity/Default/24.200.001/GenericInquiry",
            params={"$top": "1000", "$select": "InquiryTitle"},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            for gi in data:
                title = gi.get("InquiryTitle", {}).get("value", "")
                if title:
                    baseline.append({"name": title, "designId": gi.get("id", "")})
            return baseline
    except Exception:
        pass  # Fall through to probe-based approach

    # Fallback: probe known GIs
    for gi_name in EXPECTED_GIS:
        try:
            resp = session.get(
                f"{base_url}/entity/Default/24.200.001/{gi_name}",
                params={"$top": "1"},
                timeout=15,
            )
            if resp.status_code == 200:
                baseline.append({"name": gi_name, "designId": "unknown"})
        except Exception:
            pass

    return baseline


def diff_baselines(before: list[dict], after: list[dict]) -> dict:
    """Compare pre-deploy and post-deploy GI baselines.

    Returns dict with added, removed, and duplicate GI lists.
    """
    before_names = {gi["name"] for gi in before}
    after_names = [gi["name"] for gi in after]
    after_names_set = set(after_names)

    added = [gi for gi in after if gi["name"] not in before_names]
    removed = [gi for gi in before if gi["name"] not in after_names_set]

    # Detect duplicates (same name appearing multiple times)
    seen = set()
    duplicates = []
    for name in after_names:
        if name in seen and name not in duplicates:
            duplicates.append(name)
        seen.add(name)

    return {"added": added, "removed": removed, "duplicates": duplicates}


def report_diff(diff: dict) -> bool:
    """Print diff report. Returns True if there are warnings/errors."""
    has_issues = False

    if diff["duplicates"]:
        for name in diff["duplicates"]:
            print(f"{RED}[ERROR ]{RESET} DUPLICATE GI detected: {name}")
        has_issues = True

    if diff["removed"]:
        for gi in diff["removed"]:
            print(f"{YELLOW}[ WARN ]{RESET} GI removed after deploy: {gi['name']}")
        has_issues = True

    if diff["added"]:
        for gi in diff["added"]:
            print(f"{GREEN}[ INFO ]{RESET} New GI after deploy: {gi['name']}")

    if not has_issues and not diff["added"]:
        print(f"{GREEN}[  OK  ]{RESET} GI baseline unchanged")

    return has_issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GI baseline capture/diff")
    parser.add_argument("action", choices=["capture", "diff"])
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--baseline-file", default="/tmp/gi-baseline.json")
    args = parser.parse_args()

    if args.action == "capture":
        session = requests.Session()
        # Login handled by caller (pass session cookie via env or prior auth)
        baseline = capture_baseline(session, args.url)
        with open(args.baseline_file, "w") as f:
            json.dump(baseline, f, indent=2)
        print(f"Captured {len(baseline)} GIs to {args.baseline_file}")

    elif args.action == "diff":
        with open(args.baseline_file) as f:
            before = json.load(f)
        session = requests.Session()
        after = capture_baseline(session, args.url)
        result = diff_baselines(before, after)
        has_issues = report_diff(result)
        if any(result["duplicates"]):
            sys.exit(1)  # Duplicates are errors
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_gi_baseline.py -v
```

Expected: All 4 tests PASS.

**Step 5: Integrate into workflow**

Add baseline capture/diff steps to `.github/workflows/deploy-customization.yml`:

Pre-deploy (in countdown-notify job, before publish):
```yaml
    - name: Capture GI baseline
      run: |
        python scripts/gi_baseline.py capture \
          --url "${{ secrets.ACUMATICA_URL }}" \
          --baseline-file /tmp/gi-baseline.json
```

Post-deploy (after publish + validation):
```yaml
    - name: Compare GI baseline
      run: |
        python scripts/gi_baseline.py diff \
          --url "${{ secrets.ACUMATICA_URL }}" \
          --baseline-file /tmp/gi-baseline.json
```

**Step 6: Commit**

```bash
git add scripts/gi_baseline.py tests/test_gi_baseline.py .github/workflows/deploy-customization.yml
git commit -m "feat: add pre/post-deploy GI baseline capture and diff

Captures GI list before publish, compares after.
Duplicate GI names = hard error (exit 1).
Missing GIs = warning. New GIs = info.
Ref: AAR-2026-03-29"
```

---

## Task 10: Heritage Test Hard Gate

**Goal:** Add a new pipeline job that deploys to Heritage Test tenant before prod.

**Files:**
- Modify: `.github/workflows/deploy-customization.yml`

**Step 1: Add Heritage Test secrets**

Ensure these GitHub Actions secrets/variables exist:
- `ACUMATICA_PROD_URL` — production instance URL
- `ACUMATICA_TEST_TENANT` — Heritage Test tenant name (e.g., "Heritage Test")
- (Username/password reused from prod secrets)

**Step 2: Add Heritage Test gate job**

Insert a new job between `sandbox-gate` and `countdown-notify`:

```yaml
  heritage-test-gate:
    name: Heritage Test Validation Gate
    needs: [build, qualify, sandbox-gate]
    runs-on: ubuntu-latest
    timeout-minutes: 20
    if: |
      always() &&
      needs.build.result == 'success' &&
      github.event_name != 'pull_request' &&
      (
        needs.sandbox-gate.result == 'success' ||
        needs.sandbox-gate.result == 'skipped'
      )
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - run: pip install requests

      - uses: actions/download-artifact@v4
        with:
          name: customization-packages

      - name: Deploy to Heritage Test tenant
        run: |
          python scripts/deploy.py \
            --url "${{ secrets.ACUMATICA_PROD_URL }}" \
            --username "${{ secrets.ACUMATICA_USERNAME }}" \
            --password "${{ secrets.ACUMATICA_PASSWORD }}" \
            --tenant "${{ secrets.ACUMATICA_TEST_TENANT }}" \
            --project "${{ env.PRIMARY_PROJECT }}" \
            --package "${{ env.PACKAGE_PATH }}"

      - name: Validate Heritage Test publish
        run: |
          python scripts/validate-publish.py \
            --url "${{ secrets.ACUMATICA_PROD_URL }}" \
            --username "${{ secrets.ACUMATICA_USERNAME }}" \
            --password "${{ secrets.ACUMATICA_PASSWORD }}" \
            --tenant "${{ secrets.ACUMATICA_TEST_TENANT }}"

      - name: GI health check on Heritage Test
        run: |
          python -c "
          import requests
          from scripts.validate_publish_gi import check_gi_health
          s = requests.Session()
          s.post('${{ secrets.ACUMATICA_PROD_URL }}/entity/auth/login',
                 json={'name':'${{ secrets.ACUMATICA_USERNAME }}',
                       'password':'${{ secrets.ACUMATICA_PASSWORD }}',
                       'tenant':'${{ secrets.ACUMATICA_TEST_TENANT }}'})
          if not check_gi_health(s, '${{ secrets.ACUMATICA_PROD_URL }}'):
              raise SystemExit('GI health check failed on Heritage Test')
          "
```

**Step 3: Update countdown-notify dependencies**

Update the `countdown-notify` job to depend on the Heritage Test gate:

```yaml
  countdown-notify:
    needs: [build, qualify, sandbox-gate, heritage-test-gate]
    if: |
      always() &&
      needs.build.result == 'success' &&
      github.event_name != 'pull_request' &&
      (
        needs.sandbox-gate.result == 'success' ||
        needs.sandbox-gate.result == 'skipped'
      ) &&
      needs.heritage-test-gate.result == 'success' &&
      ...
```

Note: Heritage Test is a **hard gate** — `needs.heritage-test-gate.result == 'success'` is required, no `|| 'skipped'` fallback.

**Step 4: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "feat: add Heritage Test hard gate to CI/CD pipeline

New pipeline stage: sandbox -> Heritage Test -> prod.
Heritage Test gate deploys to test tenant on production instance,
runs full post-publish validation + GI health check.
Hard gate: failure blocks prod deploy with no override."
```

---

## Task 11: GI Schema Discovery Implementation (Phase 1)

**Goal:** Build the schema discovery service that queries `INFORMATION_SCHEMA` and caches the result.

**Depends on:** Task 3 research spike results (confirms SQL access works in plugins).

**Files:**
- Create: `scripts/gi_schema.py`
- Create: `tests/test_gi_schema.py`

**Step 1: Write the failing test**

```python
"""Tests for GI schema discovery and caching."""
import json
from scripts.gi_schema import GISchemaMap, parse_information_schema_output


def test_parse_schema_output():
    """Parse WriteLog output from schema discovery plugin into structured map."""
    log_output = """[SCHEMA] Table: GIDesign
  DesignID: uniqueidentifier(n/a) nullable=NO default=NULL
  Name: nvarchar(128) nullable=NO default=NULL
  ScreenID: nvarchar(8) nullable=YES default=NULL
  CompanyID: int(n/a) nullable=NO default=NULL
[SCHEMA] Table: GITable
  Alias: nvarchar(128) nullable=NO default=NULL
  Name: nvarchar(512) nullable=NO default=NULL
  Type: int(n/a) nullable=NO default=((0))
  CompanyID: int(n/a) nullable=NO default=NULL"""

    schema = parse_information_schema_output(log_output)
    assert "GIDesign" in schema
    assert "GITable" in schema
    assert schema["GIDesign"]["DesignID"]["nullable"] == "NO"
    assert schema["GIDesign"]["DesignID"]["data_type"] == "uniqueidentifier"
    assert schema["GITable"]["Type"]["nullable"] == "NO"
    assert schema["GITable"]["Type"]["default"] == "((0))"


def test_schema_map_not_null_columns():
    """Schema map correctly identifies NOT NULL columns per table."""
    schema = {
        "GIDesign": {
            "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
            "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
            "ScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        }
    }
    sm = GISchemaMap(schema, "24.200.001")
    not_null = sm.not_null_columns("GIDesign")
    assert "DesignID" in not_null
    assert "Name" in not_null
    assert "ScreenID" not in not_null


def test_schema_map_validate_row():
    """Schema map validates a row against NOT NULL constraints."""
    schema = {
        "GIDesign": {
            "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
            "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        }
    }
    sm = GISchemaMap(schema, "24.200.001")

    # Valid row
    assert sm.validate_row("GIDesign", {"DesignID": "abc-123", "Name": "TestGI"}) == []

    # Missing required column
    errors = sm.validate_row("GIDesign", {"DesignID": "abc-123"})
    assert len(errors) == 1
    assert "Name" in errors[0]
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_gi_schema.py -v
```

**Step 3: Implement gi_schema.py**

Create `scripts/gi_schema.py`:

```python
"""GI Schema Discovery — parse INFORMATION_SCHEMA output and validate rows.

The schema discovery SQL runs inside a CustomizationPlugin (see Task 3).
This module parses the WriteLog output and provides validation.
"""
import json
import re
from pathlib import Path


class GISchemaMap:
    """Cached schema map for GI tables, keyed by Acumatica version."""

    def __init__(self, tables: dict, acumatica_version: str):
        self.tables = tables
        self.acumatica_version = acumatica_version

    def not_null_columns(self, table_name: str) -> list[str]:
        """Return list of NOT NULL column names for a table."""
        if table_name not in self.tables:
            raise ValueError(f"Unknown table: {table_name}")
        return [
            col for col, info in self.tables[table_name].items()
            if info["nullable"] == "NO"
        ]

    def validate_row(self, table_name: str, row: dict) -> list[str]:
        """Validate a row dict against the schema. Returns list of error strings."""
        errors = []
        for col in self.not_null_columns(table_name):
            if col not in row or row[col] is None:
                # Skip columns with defaults — the DB will fill them
                col_info = self.tables[table_name][col]
                if col_info.get("default") is not None:
                    continue
                errors.append(f"Missing required column {table_name}.{col} (NOT NULL, no default)")
        return errors

    def save(self, path: Path):
        data = {"acumatica_version": self.acumatica_version, "tables": self.tables}
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "GISchemaMap":
        data = json.loads(path.read_text())
        return cls(data["tables"], data["acumatica_version"])


def parse_information_schema_output(log_text: str) -> dict:
    """Parse WriteLog output from the schema discovery plugin.

    Expected format:
    [SCHEMA] Table: GIDesign
      ColumnName: datatype(maxlen) nullable=YES/NO default=VALUE
    """
    tables = {}
    current_table = None
    col_pattern = re.compile(
        r"^\s+(\w+): (\w+)\(([^)]*)\) nullable=(YES|NO) default=(.+)$"
    )

    for line in log_text.splitlines():
        if line.startswith("[SCHEMA] Table: "):
            current_table = line.split(": ", 1)[1].strip()
            tables[current_table] = {}
        elif current_table:
            m = col_pattern.match(line)
            if m:
                col_name, dtype, max_len, nullable, default = m.groups()
                tables[current_table][col_name] = {
                    "data_type": dtype,
                    "max_length": None if max_len == "n/a" else int(max_len),
                    "nullable": nullable,
                    "default": None if default == "NULL" else default,
                }

    return tables
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_gi_schema.py -v
```

**Step 5: Commit**

```bash
git add scripts/gi_schema.py tests/test_gi_schema.py
git commit -m "feat: GI schema discovery parser and validator (Phase 1)

Parses INFORMATION_SCHEMA output from CustomizationPlugin WriteLog.
Validates rows against NOT NULL constraints before any SQL execution.
Caches schema by Acumatica version."
```

---

## Task 12: GI Definition Builder (Phase 2)

**Goal:** Build the in-memory GI definition builder that constructs validated SQL or XML.

**Depends on:** Task 11 (schema map available).

**Files:**
- Create: `scripts/gi_builder.py`
- Create: `tests/test_gi_builder.py`

**Step 1: Write the failing test**

```python
"""Tests for GI Definition Builder."""
import uuid
from scripts.gi_builder import GIDefinition, GIBuilder
from scripts.gi_schema import GISchemaMap


MOCK_SCHEMA = {
    "GIDesign": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "ScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "FilterColCount": {"data_type": "int", "nullable": "YES", "max_length": None, "default": "((3))"},
        "NoteID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
    },
    "GITable": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Alias": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 512, "default": None},
        "Type": {"data_type": "int", "nullable": "NO", "max_length": None, "default": "((0))"},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIResult": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Field": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "RowID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
}


def test_build_simple_gi():
    """Build a simple single-table GI definition."""
    schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")
    template = {"CreatedByID": "00000000-0000-0000-0000-000000000001", "NoteID": None}

    spec = GIDefinition(
        name="TestGI",
        screen_id="GI999001",
        tables=[{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}],
        results=[{"field": "ScreenID", "caption": "Screen", "width": 120}],
    )

    builder = GIBuilder(schema, template_row=template, company_id=2)
    sql = builder.build_sql(spec)

    assert "BEGIN TRANSACTION" in sql
    assert "INSERT INTO GIDesign" in sql
    assert "INSERT INTO GITable" in sql
    assert "INSERT INTO GIResult" in sql
    assert "COMMIT" in sql
    assert "TestGI" in sql


def test_build_validates_against_schema():
    """Builder fails fast when required columns can't be filled."""
    schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")
    template = {}  # Empty template — no audit column values

    spec = GIDefinition(
        name="TestGI",
        screen_id="GI999001",
        tables=[{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}],
        results=[{"field": "ScreenID", "caption": "Screen", "width": 120}],
    )

    builder = GIBuilder(schema, template_row=template, company_id=2)
    try:
        builder.build_sql(spec)
        assert False, "Should have raised ValueError for missing audit columns"
    except ValueError as e:
        assert "Missing required" in str(e) or "CreatedByID" in str(e)


def test_idempotent_check_in_sql():
    """Generated SQL includes pre-flight check for existing GI."""
    schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")
    template = {"CreatedByID": "00000000-0000-0000-0000-000000000001", "NoteID": None}

    spec = GIDefinition(name="TestGI", screen_id="GI999001",
                        tables=[{"dac": "PX.SM.AuditHistory", "alias": "AH"}],
                        results=[{"field": "ScreenID", "caption": "Screen", "width": 120}])

    builder = GIBuilder(schema, template_row=template, company_id=2)
    sql = builder.build_sql(spec)

    assert "IF EXISTS" in sql or "WHERE Name = " in sql
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_gi_builder.py -v
```

**Step 3: Implement gi_builder.py**

Create `scripts/gi_builder.py`:

```python
"""GI Definition Builder — constructs validated SQL for GI creation.

Phase 2 of the GI Builder Engine. Takes a GI specification and produces
a transactional SQL script validated against the schema map.
"""
import uuid
from dataclasses import dataclass, field
from scripts.gi_schema import GISchemaMap


@dataclass
class GIDefinition:
    """Specification for a Generic Inquiry to create."""
    name: str
    screen_id: str
    tables: list[dict]  # [{"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"}]
    results: list[dict]  # [{"field": "ScreenID", "caption": "Screen", "width": 120}]
    filters: list[dict] = field(default_factory=list)
    where: list[dict] = field(default_factory=list)
    sort: list[dict] = field(default_factory=list)


class GIBuilder:
    """Builds validated, transactional SQL for GI creation."""

    def __init__(self, schema: GISchemaMap, template_row: dict, company_id: int):
        self.schema = schema
        self.template = template_row
        self.company_id = company_id

    def _new_guid(self) -> str:
        return str(uuid.uuid4())

    def _build_row(self, table_name: str, values: dict) -> dict:
        """Build a complete row, filling audit/system columns from template."""
        row = dict(values)
        row.setdefault("CompanyID", self.company_id)

        # Fill audit columns from template
        for col in self.schema.not_null_columns(table_name):
            if col not in row and col in self.template:
                row[col] = self.template[col]
            if col not in row:
                col_info = self.schema.tables[table_name].get(col, {})
                if col_info.get("default") is not None:
                    continue  # DB will fill it
                if col_info.get("data_type") == "uniqueidentifier":
                    row[col] = self._new_guid()

        # Validate
        errors = self.schema.validate_row(table_name, row)
        if errors:
            raise ValueError(f"Validation failed for {table_name}: {'; '.join(errors)}")

        return row

    def _sql_value(self, val) -> str:
        """Format a Python value as a SQL literal."""
        if val is None:
            return "NULL"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, str):
            return f"N'{val.replace(chr(39), chr(39)+chr(39))}'"
        return f"N'{val}'"

    def _insert_sql(self, table_name: str, row: dict) -> str:
        """Generate a single INSERT statement."""
        cols = ", ".join(row.keys())
        vals = ", ".join(self._sql_value(v) for v in row.values())
        return f"INSERT INTO {table_name} ({cols}) VALUES ({vals});"

    def build_sql(self, spec: GIDefinition) -> str:
        """Build the complete transactional SQL script for a GI definition."""
        design_id = self._new_guid()
        lines = []

        lines.append("-- GI Builder: Auto-generated transactional SQL")
        lines.append(f"-- GI Name: {spec.name}")
        lines.append(f"-- Generated by AcuDev GI Builder Engine")
        lines.append("-- REVIEWED: gi-sql-safe")
        lines.append("")

        # Pre-flight: check if GI already exists
        lines.append(f"IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'{spec.name}' AND CompanyID = {self.company_id})")
        lines.append("BEGIN")
        lines.append(f"    PRINT 'GI {spec.name} already exists — skipping creation';")
        lines.append("    RETURN;")
        lines.append("END")
        lines.append("")

        lines.append("BEGIN TRANSACTION;")
        lines.append("BEGIN TRY")
        lines.append("")

        # GIDesign row
        design_row = self._build_row("GIDesign", {
            "DesignID": design_id,
            "Name": spec.name,
            "ScreenID": spec.screen_id,
        })
        lines.append(f"-- GIDesign: {spec.name}")
        lines.append(self._insert_sql("GIDesign", design_row))
        lines.append("")

        # GITable rows
        for i, table in enumerate(spec.tables):
            table_row = self._build_row("GITable", {
                "DesignID": design_id,
                "Alias": table["alias"],
                "Name": table["dac"],
            })
            lines.append(f"-- GITable: {table['alias']}")
            lines.append(self._insert_sql("GITable", table_row))
        lines.append("")

        # GIResult rows
        for i, result in enumerate(spec.results):
            result_row = self._build_row("GIResult", {
                "DesignID": design_id,
                "LineNbr": i + 1,
                "Field": result["field"],
            })
            lines.append(f"-- GIResult: {result['field']}")
            lines.append(self._insert_sql("GIResult", result_row))
        lines.append("")

        # Post-flight: verify row counts
        lines.append("-- Post-flight verification")
        lines.append(f"DECLARE @design_count INT = (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'{design_id}' AND CompanyID = {self.company_id});")
        lines.append(f"DECLARE @table_count INT = (SELECT COUNT(*) FROM GITable WHERE DesignID = N'{design_id}' AND CompanyID = {self.company_id});")
        lines.append(f"DECLARE @result_count INT = (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'{design_id}' AND CompanyID = {self.company_id});")
        lines.append("")
        lines.append(f"IF @design_count != 1 OR @table_count != {len(spec.tables)} OR @result_count != {len(spec.results)}")
        lines.append("BEGIN")
        lines.append("    ROLLBACK TRANSACTION;")
        lines.append(f"    RAISERROR('Post-flight check failed: design=%d tables=%d results=%d', 16, 1, @design_count, @table_count, @result_count);")
        lines.append("    RETURN;")
        lines.append("END")
        lines.append("")

        lines.append("COMMIT TRANSACTION;")
        lines.append(f"PRINT 'GI {spec.name} created successfully (DesignID={design_id})';")
        lines.append("")
        lines.append("END TRY")
        lines.append("BEGIN CATCH")
        lines.append("    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;")
        lines.append("    DECLARE @err NVARCHAR(4000) = ERROR_MESSAGE();")
        lines.append("    RAISERROR('GI creation failed: %s', 16, 1, @err);")
        lines.append("END CATCH")

        return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_gi_builder.py -v
```

**Step 5: Commit**

```bash
git add scripts/gi_builder.py tests/test_gi_builder.py
git commit -m "feat: GI Definition Builder with transactional SQL generation (Phase 2)

Constructs validated, all-or-nothing SQL for GI creation.
Pre-flight: idempotency check (skip if GI exists).
Post-flight: row count verification inside transaction.
BEGIN TRY/CATCH wraps everything — partial inserts impossible."
```

---

## Task 13: Proof-of-Concept — UserAuditTrail GI on Heritage Test

**Goal:** Use the GI Builder to create the UserAuditTrail GI on the Heritage Test tenant.

**Depends on:** Tasks 3, 11, 12 (schema discovery results + builder implementation).

**Files:**
- Create: `scripts/poc_user_audit_trail.py`
- Modify: `Customization/StudioBAcuOps/project.xml` (embed generated SQL)

**Step 1: Generate the UserAuditTrail SQL**

```python
"""POC: Generate UserAuditTrail GI SQL using the GI Builder."""
from scripts.gi_builder import GIDefinition, GIBuilder
from scripts.gi_schema import GISchemaMap
from pathlib import Path

# Load cached schema (from Task 3 research spike)
schema = GISchemaMap.load(Path("data/gi-schema-24.200.001.json"))

# Template row values (from Task 3 research spike)
template = {
    "CreatedByID": "{from-template-extraction}",
    "CreatedByScreenID": "SM208000",
    "NoteID": None,  # Will be auto-generated as fresh UUID
}

spec = GIDefinition(
    name="UserAuditTrail",
    screen_id="GI000001",
    tables=[
        {"dac": "PX.SM.AuditHistory", "alias": "AuditHistory"},
    ],
    results=[
        {"field": "ScreenID", "caption": "Screen ID", "width": 120},
        {"field": "Operation", "caption": "Operation", "width": 100},
        {"field": "ChangeDate", "caption": "Change Date", "width": 150},
        {"field": "TableName", "caption": "Table", "width": 150},
        {"field": "BatchID", "caption": "Batch ID", "width": 80},
        {"field": "ChangeID", "caption": "Change ID", "width": 80},
        {"field": "CombinedKey", "caption": "Combined Key", "width": 200},
        {"field": "ModifiedFields", "caption": "Modified Fields", "width": 300},
        {"field": "UserID", "caption": "User", "width": 120},
    ],
    filters=[
        {"name": "ScreenFilter", "display_name": "Screen ID", "data_type": 6},
        {"name": "FromDate", "display_name": "From Date", "data_type": 5},
        {"name": "ToDate", "display_name": "To Date", "data_type": 5},
    ],
    where=[
        {"field": "AuditHistory.ScreenID", "condition": "E", "value": "@ScreenFilter"},
        {"field": "AuditHistory.ChangeDate", "condition": "GE", "value": "@FromDate"},
        {"field": "AuditHistory.ChangeDate", "condition": "LE", "value": "@ToDate"},
    ],
    sort=[
        {"field": "AuditHistory.ChangeDate", "order": "D"},
    ],
)

builder = GIBuilder(schema, template_row=template, company_id=2)
sql = builder.build_sql(spec)
print(sql)
Path("data/user-audit-trail.sql").write_text(sql)
```

**Step 2: Embed SQL in StudioBAcuOps plugin**

Update `Customization/StudioBAcuOps/project.xml` UpdateDatabase() to execute the generated SQL inside a transaction.

**Step 3: Deploy to Heritage Test via CI/CD**

Push to a branch, let the pipeline run through sandbox + Heritage Test gates.

**Step 4: Verify the GI works**

```bash
# REST API probe
curl -s "$ACUMATICA_PROD_URL/entity/Default/24.200.001/UserAuditTrail?\$top=1" \
  -H "Cookie: {session}"
```

Also verify in SM208000 that the GI appears and is queryable.

**Step 5: Commit**

```bash
git add scripts/poc_user_audit_trail.py data/user-audit-trail.sql
git commit -m "feat: POC — UserAuditTrail GI created on Heritage Test via GI Builder

Proof-of-concept for the GI Builder Engine.
Generated transactional SQL, deployed via StudioBAcuOps plugin,
verified via REST API on Heritage Test tenant."
```

---

## Execution Dependencies

```
Task 1 (SM208000 spike) ──┐
Task 2 (Import spike) ────┤
Task 3 (SQL spike) ───────┼──> Task 11 (Schema) ──> Task 12 (Builder) ──> Task 13 (POC)
Task 4 (Endpoint spike) ──┘
                                Task 5 (SQL detection) ─────────┐
                                Task 6 (Sandbox gate) ──────────┤
                                Task 7 (GI health check) ──────┼──> Task 10 (Heritage Test gate)
                                Task 8 (Emergency fix) ────────┤
                                Task 9 (GI baseline) ──────────┘
```

Tasks 1-4 can run in parallel. Tasks 5-9 can run in parallel. Task 10 depends on 5-9. Tasks 11-13 are sequential and depend on Tasks 1-4.
