# Sandbox Reliability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all three sandbox-gate blockers — PO3010PL SiteMap shadow, --no-merge verify noise, and stale sandbox data — so the pipeline flows without force_deploy overrides.

**Architecture:** Three independent workstreams executed in order. WS1 fixes the customization XML and reverts test workarounds. WS2 adds a `--no-merge-expected` flag to verify.py and documents the IIG orphan cleanup SQL. WS3 extends entity-sync.py to target the sandbox instance.

**Tech Stack:** Python (verify.py, entity-sync.py), XML (project.xml), YAML (acuops.yaml, GH Actions workflows)

**Design doc:** `docs/plans/2026-04-11-sandbox-reliability-design.md`

---

## Workstream 1: Fix PO3010PL SiteMap Shadow

### Task 1.1: Change ScreenID in AesthetikWMS project.xml

**Files:**
- Modify: `Customization/AesthetikWMS/project.xml:417`

**Step 1: Make the change**

In `Customization/AesthetikWMS/project.xml`, line 417, change:
```xml
<row Position="0" Title="Purchase Orders" Url="~/Pages/PO/PO301000.aspx" ScreenID="PO3010PL" NodeID="5FC65FCB-7860-40B1-A897-8526F240D9E0" ParentID="12167736-AE7E-46AB-8A8C-DD4B86217519" SelectedUI="E">
```
to:
```xml
<row Position="0" Title="Purchase Orders" Url="~/Pages/PO/PO301000.aspx" ScreenID="PO301000" NodeID="5FC65FCB-7860-40B1-A897-8526F240D9E0" ParentID="12167736-AE7E-46AB-8A8C-DD4B86217519" SelectedUI="E">
```

**Step 2: Verify no other PO3010PL references exist**

Run: `grep -r "PO3010PL" Customization/`
Expected: No matches (the only occurrence was line 417).

**Step 3: Commit**

```bash
git add Customization/AesthetikWMS/project.xml
git commit -m "fix: change PO3010PL SiteMap shadow back to PO301000

The custom ScreenID was added to restore access after a corrupt publish.
It shadows stock PO301000, breaking SiteMap navigation. The RolesInGraph
entries are stock defaults — no custom overrides lost."
```

### Task 1.2: Revert test workarounds for PO3010PL

**Files:**
- Modify: `tests/ui/test_container_tracking.py:145-197`

**Step 1: Rewrite test_container_tracking_button_exists to use acumatica_screen fixture**

Replace lines 145-170 with:
```python
    def test_container_tracking_button_exists(self, acumatica_screen):
        """CONTAINER TRACKING toolbar button should be present on PO301000."""
        screen = acumatica_screen("PO301000")
        screen.page.wait_for_timeout(3_000)

        btn = screen.page.locator("text=CONTAINER TRACKING")
        assert btn.count() > 0, "CONTAINER TRACKING button not found on PO301000"
```

Note: Change fixture from `acumatica_page` to `acumatica_screen`. The `acumatica_screen("PO301000")` fixture handles login + SiteMap navigation. The 3s wait is still needed for toolbar render (PXAction buttons injected by JS after domcontentloaded).

**Step 2: Rewrite test_container_tracking_navigates_to_sb501000 to use acumatica_screen fixture**

Replace lines 172-197 (including the `@pytest.mark.skipif` added in PR #353) with:
```python
    def test_container_tracking_navigates_to_sb501000(self, acumatica_screen):
        """Clicking CONTAINER TRACKING should navigate to SB501000 without error."""
        screen = acumatica_screen("PO301000")
        screen.page.wait_for_timeout(3_000)

        btn = screen.page.locator("text=CONTAINER TRACKING").first
        if btn.is_visible(timeout=3000):
            btn.click()
            screen.page.wait_for_load_state("domcontentloaded")
            screen.page.wait_for_timeout(3000)

        assert "ScreenId=ERROR" not in screen.page.url, \
            f"CONTAINER TRACKING button caused error. URL: {screen.page.url}"
```

Note: Removes `skipif(sandbox)` decorator AND the direct-ASPX pattern. Both are no longer needed once PO3010PL → PO301000 fix is deployed.

**Step 3: Update docstrings referencing PO3010PL**

Search for remaining PO3010PL references in test files:
```bash
grep -n "PO3010PL" tests/ui/test_container_tracking.py
```
Remove or update any remaining docstring references to PO3010PL shadow workaround.

**Step 4: Commit**

```bash
git add tests/ui/test_container_tracking.py
git commit -m "fix(tests): revert PO3010PL direct-ASPX workarounds

PO3010PL→PO301000 fix in project.xml means SiteMap navigation works
again. Tests can use the standard acumatica_screen fixture instead of
direct ASPX URLs. Removes skipif(sandbox) from navigation test."
```

### Task 1.3: Verify access rights for Melanie, Steve, Lauren, and Sarah

**Files:**
- Modify: `Customization/AesthetikWMS/project.xml` (if access rights need adding)

**Step 1: Check current access rights in project.xml**

Search for RolesInGraph entries related to container tracking screens:
```bash
grep -A2 "ScreenID=\"SB501000\|ScreenID=\"PO302000\|ScreenID=\"SB401" Customization/AesthetikWMS/project.xml Customization/AesthetikContainers/project.xml
```

Document which roles have access to:
- SB501000 (Container Maintenance) — Melanie, Steve, Lauren need access
- PO302000 — Sarah needs access

**Step 2: Verify users have appropriate roles**

Check the Roles section of each project.xml for the roles that grant access. If the `*` wildcard role has `Accessrights="4"` on these screens, all users already have access. If specific roles are needed, add `RolesInGraph` entries.

**Step 3: Commit if changes needed**

```bash
git add Customization/*/project.xml
git commit -m "fix: ensure Melanie/Steve/Lauren access to SB501000, Sarah to PO302000"
```

---

## Workstream 2: --no-merge Verify Failure Suppression

### Task 2.1: Add no_merge_expected config to acuops.yaml

**Files:**
- Modify: `acuops.yaml`

**Step 1: Add the expected failures section**

Add after the `pipeline:` section (after line 73):
```yaml
# ─── --no-merge Expected Failures ──────────────────────────────────────────
# ASPX mismatches caused by --no-merge (isMergeWithExistingPackages=false).
# --no-merge only extracts ASPX for the primary project; co-published
# projects' ASPX files are silently skipped. These are downgraded to WARN
# in verify.py until the IIG orphan rows are cleaned (September 2026 DB access).
no_merge_expected:
  - "aspx:Pages/SB/SB501000.aspx"
```

Note: The exact ASPX paths must match what verify.py reports in the `aspx:{normalized}` check name. Run a verify to capture the exact 3 failure names if the above isn't exhaustive.

**Step 2: Verify the YAML is valid**

Run: `python3 -c "import yaml; yaml.safe_load(open('acuops.yaml'))"`
Expected: No errors.

**Step 3: Commit**

```bash
git add acuops.yaml
git commit -m "chore: add no_merge_expected ASPX failure list to acuops.yaml

Known ASPX mismatches from --no-merge mode. Will be removed when IIG
orphan rows are cleaned after DB access in September 2026."
```

### Task 2.2: Add --no-merge-expected flag to verify.py

**Files:**
- Modify: `scripts/verify.py:636-689` (argparser), `scripts/verify.py:535-540` (ASPX check result)

**Step 1: Add CLI argument**

After line 688 (`args = parser.parse_args()` — but before it), add:
```python
    parser.add_argument(
        "--no-merge-expected",
        default=None,
        help="Path to YAML file with no_merge_expected list of ASPX check names to downgrade FAIL→WARN",
    )
```

**Step 2: Load expected failures in main()**

After `args = parser.parse_args()` (line 689), add:
```python
    # Load --no-merge expected ASPX failures
    no_merge_expected = set()
    if args.no_merge_expected:
        import yaml
        with open(args.no_merge_expected) as f:
            config = yaml.safe_load(f)
        no_merge_expected = set(config.get("no_merge_expected", []))
```

**Step 3: Downgrade matching ASPX failures**

Find the section where `all_checks` is assembled (around line 740-755). After all checks are collected but before the overall status is computed, add:
```python
    # Downgrade known --no-merge ASPX failures to WARN
    if no_merge_expected:
        for check in all_checks:
            if (check.status == CheckStatus.FAIL
                    and check.name in no_merge_expected
                    and "not overwritten by import" in check.detail):
                check.status = CheckStatus.WARN
                check.detail += " [expected: --no-merge]"
```

**Step 4: Verify with a dry run**

Run verify.py locally with the flag to confirm the expected failures downgrade:
```bash
python scripts/verify.py --manifest publish-manifest.json --environment sandbox \
  --no-merge-expected acuops.yaml --json-output /tmp/verify-test.json 2>&1 | head -20
```
Expected: ASPX checks matching the list show `WARN` instead of `FAIL`.

**Step 5: Commit**

```bash
git add scripts/verify.py
git commit -m "feat(verify): --no-merge-expected flag downgrades known ASPX failures to WARN

Reads no_merge_expected list from acuops.yaml. Matching ASPX mismatch
checks are downgraded FAIL→WARN so they don't block the gate while
still reporting for visibility. Temporary until IIG orphan cleanup."
```

### Task 2.3: Wire --no-merge-expected into sandbox-gate workflow

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml:997-1000`

**Step 1: Update verify invocation in sandbox-gate**

Find the sandbox verify step (around line 997). Change:
```bash
python scripts/verify.py \
  --manifest publish-manifest.json \
  --environment sandbox \
  --json-output verify-result.json
```
to:
```bash
python scripts/verify.py \
  --manifest publish-manifest.json \
  --environment sandbox \
  --no-merge-expected acuops.yaml \
  --json-output verify-result.json
```

**Step 2: Also update production verify step**

Find the production verify step (around line 1656). Add `--no-merge-expected acuops.yaml` to the command there too.

**Step 3: Commit**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "fix(pipeline): pass --no-merge-expected to verify.py in sandbox + prod

Downgrades known ASPX mismatches from --no-merge mode so they don't
block the sandbox gate or trigger false prod alerts."
```

### Task 2.4: Document IIG orphan cleanup SQL for September

**Files:**
- Create: `docs/reference/iig-orphan-cleanup.md`

**Step 1: Write the cleanup reference doc**

```markdown
# IIG Orphan Row Cleanup — September 2026

## Context

Three ISV/internal packages were removed from Heritage Fabrics production
but left orphaned metadata in the Acumatica publish registry. This forces
`--no-merge` mode (`isMergeWithExistingPackages=false`) for all publishes,
which skips ASPX extraction for co-published projects.

Acumatica quoted an SOW for cleanup. Heritage Fabrics gets DB access in
September 2026.

## Orphaned Projects

| Project Name | Origin |
|---|---|
| `IIGCONTAINERMGMT[24.204.0004][R19]1` | IIG Container Management ISV |
| `IIGHFContainerMods[24.204.0004][R04]` | IIG HF Container Modifications |
| `AesthetikContainerGIs` | Internal — duplicated AesthetikContainers GIs |

## Cleanup SQL

Run against the Heritage Fabrics production database after obtaining access.

**IMPORTANT:** Take a database backup before running. Test on sandbox first.

```sql
-- Step 1: Identify orphan rows
SELECT CompanyID, Name, Level, IsPublished
FROM CustProject
WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

-- Step 2: Delete orphan project metadata (cascade to related tables)
DELETE FROM CustProjectMeta WHERE ProjectID IN (
    SELECT ProjectID FROM CustProject WHERE Name IN (
        'IIGCONTAINERMGMT[24.204.0004][R19]1',
        'IIGHFContainerMods[24.204.0004][R04]',
        'AesthetikContainerGIs'
    )
);

DELETE FROM CustPublishedProject WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

DELETE FROM CustProject WHERE Name IN (
    'IIGCONTAINERMGMT[24.204.0004][R19]1',
    'IIGHFContainerMods[24.204.0004][R04]',
    'AesthetikContainerGIs'
);

-- Step 3: Verify cleanup
SELECT COUNT(*) AS remaining FROM CustProject
WHERE Name LIKE 'IIG%' OR Name = 'AesthetikContainerGIs';
-- Expected: 0
```

## After Cleanup

1. Remove `--no-merge` from deploy.py invocations in `acuops-deploy.yml`
2. Remove `no_merge_expected` section from `acuops.yaml`
3. Remove `--no-merge-expected` flag from verify.py invocations in workflow
4. Test a publish with `isMergeWithExistingPackages=true` on sandbox first
```

**Step 2: Commit**

```bash
git add docs/reference/iig-orphan-cleanup.md
git commit -m "docs: IIG orphan cleanup SQL for September DB access

Ready-to-run SQL DELETE statements for the three orphaned CustProject
rows that force --no-merge mode. Test on sandbox before running on prod."
```

---

## Workstream 3: Sandbox Entity Sync

### Task 3.1: Make entity-sync.py accept target instance via CLI args

**Files:**
- Modify: `scripts/heritage/entity-sync.py`

**Step 1: Add argparse CLI**

Currently the script takes no arguments and reads env vars only. Add argparse so it can be invoked as:
```bash
python scripts/heritage/entity-sync.py --target sandbox
```

Add at the top of `main()`:
```python
    parser = argparse.ArgumentParser(description="Sync entities from prod to target instance")
    parser.add_argument(
        "--target", choices=["test", "sandbox"], default="test",
        help="Target instance: 'test' (Heritage Test tenant on prod) or 'sandbox' (separate sandbox instance)",
    )
    args = parser.parse_args()
```

For `--target sandbox`, read target credentials from:
- `SANDBOX_URL` (env var, maps to `ACUMATICA_SANDBOX_URL` in GH Actions)
- `SANDBOX_USERNAME` / `SANDBOX_PASSWORD` / `SANDBOX_TENANT`

For `--target test` (existing default), keep current behavior: same prod URL, different tenant.

**Step 2: Add PurchaseOrder and Shipment to ENTITY_CONFIG**

Add after the existing SalesOrder entry:
```python
    {
        "name": "PurchaseOrder",
        "key_field": "OrderNbr",
        "expand": None,
        "select": None,
        "write": True,
    },
    {
        "name": "Shipment",
        "key_field": "ShipmentNbr",
        "expand": None,
        "select": None,
        "write": True,
    },
```

**Step 3: Commit**

```bash
git add scripts/heritage/entity-sync.py
git commit -m "feat(entity-sync): add --target sandbox + PurchaseOrder/Shipment entities

Allows syncing prod data to sandbox instance for fresh CRUD/GI testing.
Adds PO and Shipment entities for container tracking test coverage."
```

### Task 3.2: Create sandbox sync workflow

**Files:**
- Create: `.github/workflows/sync-sandbox.yml`

**Step 1: Write the workflow**

```yaml
name: Sync Sandbox Data

on:
  schedule:
    - cron: "23 8 * * *"  # 3:23am ET (after prod→test sync at 2:07am)
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Dry run (read only, no writes)"
        type: boolean
        default: false

jobs:
  sync:
    name: Entity Sync — Prod → Sandbox
    runs-on: ubuntu-latest
    timeout-minutes: 45

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install requests pyyaml

      - name: Run entity sync to sandbox
        env:
          PYTHONUNBUFFERED: "1"
          ACUMATICA_URL: ${{ secrets.ACUMATICA_PROD_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          PROD_TENANT: "Heritage Fabrics"
          SANDBOX_URL: ${{ secrets.ACUMATICA_SANDBOX_URL }}
          SANDBOX_USERNAME: ${{ secrets.ACUMATICA_SANDBOX_USERNAME }}
          SANDBOX_PASSWORD: ${{ secrets.ACUMATICA_SANDBOX_PASSWORD }}
          SANDBOX_TENANT: ${{ secrets.ACUMATICA_SANDBOX_TENANT }}
          SLACK_WEBHOOK_URL: ${{ secrets.STUDIOB_SLACK_WEBHOOK_URL }}
        run: python scripts/heritage/entity-sync.py --target sandbox
```

**Step 2: Commit**

```bash
git add .github/workflows/sync-sandbox.yml
git commit -m "feat: nightly sandbox entity sync workflow

Runs prod→sandbox entity sync at 3:23am ET (after prod→test at 2:07am).
Also available via manual workflow_dispatch."
```

### Task 3.3: Remove skip_on_sandbox from CRUD tests

**Files:**
- Modify: `tests/ui/test_container_tracking.py`

**Step 1: Remove @skip_on_sandbox decorators**

This task should be done AFTER entity sync has run at least once and sandbox has fresh data. Until then, keep the decorators.

Search for all `@skip_on_sandbox` usages:
```bash
grep -n "skip_on_sandbox" tests/ui/test_container_tracking.py
```

Remove the decorator from:
- `TestContainerMaintenanceCRUD` (line 512)
- `TestFreightForwardersCRUD` (line 587)
- `TestContainerTypesSeedData` (line 608)
- `TestPortsSeedData` (line 643)
- `TestContainerPreferencesE2E` (line 672)

**Step 2: Commit**

```bash
git add tests/ui/test_container_tracking.py
git commit -m "feat(tests): enable CRUD tests on sandbox (entity sync provides data)"
```

**NOTE:** Only execute this task after confirming sandbox entity sync has run successfully and sandbox has production-like data.

---

## Execution Order

Tasks can be executed in workstream order (1→2→3). Within each workstream, tasks are sequential.

WS1 and WS2 are independent and could run in parallel. WS3 depends on WS1 being deployed (so PO301000 tests work on sandbox).

Task 3.3 (remove skip_on_sandbox) should be deferred until after the first successful sandbox sync run.
