# E2E View-Level Smoke Test — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `$select`-based e2e probes that force SQL column resolution on custom DAC extension fields, catching view/table mismatches before production.

**Architecture:** New `e2e_probes` section in `publish-manifest.json` drives a new `scripts/smoke-e2e.py` script that reuses `AcumaticaSession` from `validate-publish.py`. Wired into the pipeline after each existing `validate-publish.py` step (sandbox, Heritage Test, production).

**Tech Stack:** Python 3.12, urllib (no new dependencies), GitHub Actions

**Design doc:** `docs/plans/2026-03-30-e2e-smoke-test-design.md`

---

### Task 1: Populate `publish-manifest.json`

**Files:**
- Modify: `publish-manifest.json`

**Step 1: Add custom_fields and e2e_probes**

Replace the full contents of `publish-manifest.json` with:

```json
{
  "_comment": "Post-publish validation manifest. Defines expected custom fields per entity after a successful Acumatica customization publish. Used by validate-publish.py to verify fields exist in live API responses.",
  "entities": {
    "PurchaseOrder": {
      "screen": "PO301000",
      "custom_fields": ["custom.Document.UsrExpArrivalDate", "custom.Document.UsrActArrivalDate", "custom.Document.UsrContainerRef"]
    },
    "SalesOrder": {
      "screen": "SO301000",
      "custom_fields": ["custom.Document.UsrHubSpotDealId"]
    },
    "Customer": {
      "screen": "AR303000",
      "custom_fields": []
    },
    "Vendor": {
      "screen": "AP303000",
      "custom_fields": []
    },
    "Invoice": {
      "screen": "AR301000",
      "custom_fields": []
    },
    "StockItem": {
      "screen": "IN202500",
      "custom_fields": ["custom.ItemSettings.UsrHTSCode", "custom.ItemSettings.UsrDutyRate", "custom.ItemSettings.UsrCountryOfOrigin", "custom.ItemSettings.UsrFiberContent", "custom.ItemSettings.UsrPreferentialTariff", "custom.ItemSettings.UsrFreightClass"]
    }
  },
  "e2e_probes": [
    {
      "entity": "Vendor",
      "select_fields": ["VendorID", "UsrDefaultInTransitSiteID", "UsrDefaultCarrierCode"],
      "note": "BAccount extension — forces Vendor_Vendor view resolution"
    },
    {
      "entity": "PurchaseOrder",
      "select_fields": ["OrderNbr", "UsrExpArrivalDate", "UsrActArrivalDate", "UsrContainerRef"]
    },
    {
      "entity": "StockItem",
      "select_fields": ["InventoryID", "UsrHTSCode", "UsrDutyRate", "UsrCountryOfOrigin"]
    },
    {
      "entity": "SalesOrder",
      "select_fields": ["OrderNbr", "UsrHubSpotDealId"]
    },
    {
      "entity": "Shipment",
      "select_fields": ["ShipmentNbr", "UsrIncludeInContainer", "UsrContainerID"]
    }
  ],
  "sql_columns": [
    {"table": "POOrder", "columns": ["UsrExpArrivalDate", "UsrActArrivalDate", "UsrContainerRef"]},
    {"table": "POLine", "columns": ["UsrExpArrivalDate", "UsrActArrivalDate"]},
    {"table": "SOOrder", "columns": ["UsrHubSpotDealId"]},
    {"table": "BAccount", "columns": ["UsrDisablePayLink", "UsrDefaultInTransitSiteID", "UsrDefaultCarrierCode"]},
    {"table": "InventoryItem", "columns": ["UsrHTSCode", "UsrDutyRate", "UsrCountryOfOrigin", "UsrFiberContent", "UsrPreferentialTariff", "UsrFreightClass"]},
    {"table": "POReceiptLine", "columns": ["UsrActualDutyAmt", "UsrActualFreightAmt", "UsrBrokerageAmt", "UsrHTSCode", "UsrCountryOfOrigin"]},
    {"table": "SOShipment", "columns": ["UsrIncludeInContainer", "UsrContainerID"]},
    {"table": "UsrContainer", "columns": ["ContainerCD", "CarrierCode", "Status", "ETA", "ATA"]},
    {"table": "UsrContainerEvent", "columns": ["ContainerID", "NormalizedEventCode", "EventDateTime"]},
    {"table": "UsrContainerPOLink", "columns": ["ContainerID", "OrderType", "OrderNbr"]}
  ],
  "_notes": {
    "UsrDisablePayLink": "CustomerExt : PXCacheExtension<Customer> field. Works on AR303000 screen and in C# (ARInvoiceEntry_PayLink_Extension), but NOT exposed via REST API $adHocSchema for Customer entity. SQL column on BAccount table. Cannot validate via REST API schema check — only via sql_columns.",
    "UsrHubSpotDealId": "SOOrderExt in AesthetikWMS package. DAC field requires ALTER TABLE on SOOrder — created via CustomizationPlugin in AesthetikWMS.",
    "UsrDefaultInTransitSiteID": "BAccountContainerExt : PXCacheExtension<BAccount>. Column on BAccount table. NOT exposed via $adHocSchema — validated via e2e_probes on Vendor entity (forces Vendor_Vendor view resolution). See: 2026-03-30 outage.",
    "UsrDefaultCarrierCode": "Same as UsrDefaultInTransitSiteID — BAccount extension, e2e_probes only.",
    "container_tables": "UsrContainer, UsrContainerEvent, UsrContainerPOLink are standalone tables created by AesthetikContainers CustomizationPlugin.UpdateDatabase(). Validated via sql_columns, not entity custom_fields."
  }
}
```

**Step 2: Verify JSON is valid**

Run: `python -m json.tool publish-manifest.json > /dev/null && echo "Valid JSON"`
Expected: `Valid JSON`

**Step 3: Commit**

```bash
git add publish-manifest.json
git commit -m "feat: populate publish-manifest with custom_fields and e2e_probes

Add custom_fields for PurchaseOrder, SalesOrder, StockItem entities.
Add e2e_probes section for $select-based view resolution testing.
Add Vendor entity — forces Vendor_Vendor view validation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Create `scripts/smoke-e2e.py`

**Files:**
- Create: `scripts/smoke-e2e.py`
- Reference: `scripts/validate-publish.py` (reuse `AcumaticaSession` class)

**Step 1: Write the script**

Create `scripts/smoke-e2e.py`:

```python
#!/usr/bin/env python3
"""
E2E View-Level Smoke Test for Acumatica Customization CI/CD

Reads e2e_probes from publish-manifest.json and executes $select queries
that force SQL column resolution on custom DAC extension fields.

Catches view/table mismatches that $adHocSchema and $top=1 miss.
Example: VendorExt targeting Vendor (view) when columns live on BAccount (table)
→ SELECT [Vendor_Vendor].[UsrFoo] → "Invalid column name" → HTTP 500.

See: docs/plans/2026-03-30-e2e-smoke-test-design.md

Usage:
    python scripts/smoke-e2e.py --manifest publish-manifest.json

Environment variables:
    ACUMATICA_URL, ACUMATICA_USERNAME, ACUMATICA_PASSWORD, ACUMATICA_TENANT
"""

import json
import os
import sys

# Reuse AcumaticaSession from validate-publish.py (same login retry logic)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_publish import AcumaticaSession, log, ok, fail, warn

passed = 0
failed = 0


def run_probe(session, probe):
    """Execute a single e2e probe — $select query forcing column resolution."""
    global passed, failed

    entity = probe["entity"]
    fields = probe["select_fields"]
    note = probe.get("note", "")
    select = ",".join(fields)

    label = f"{entity} → $select={select}"
    if note:
        label += f"  ({note})"

    log(f"Probing: {label}")

    code, body = session.query_entity(entity, top=1, select=select)

    if code == 200:
        ok(f"{entity}: all {len(fields)} fields resolved (HTTP 200)")
        passed += 1
        return True

    if code == 204:
        # No records but query executed — view resolution succeeded
        ok(f"{entity}: query executed, no records (HTTP 204) — view resolution OK")
        passed += 1
        return True

    if code in (401, 403):
        warn(f"{entity}: HTTP {code} — permission issue, not a code bug")
        return True

    # HTTP 500 or other error — parse body for diagnostic info
    error_detail = ""
    if isinstance(body, str):
        if "Invalid column name" in body:
            # Extract the column name from the error
            import re
            match = re.search(r"Invalid column name '([^']+)'", body)
            col = match.group(1) if match else "unknown"
            error_detail = f"Invalid column name {col} — DAC targets wrong view/table"
        elif "does not exist" in body.lower():
            error_detail = "Entity or view does not exist"
        else:
            # Truncate to first 200 chars for readability
            error_detail = body[:200]

    fail(f"{entity}: HTTP {code} — {error_detail or 'unknown error'}")
    failed += 1
    return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="E2E view-level smoke test for Acumatica customizations"
    )
    parser.add_argument("--url", default=os.environ.get("ACUMATICA_URL", ""))
    parser.add_argument("--username", default=os.environ.get("ACUMATICA_USERNAME", ""))
    parser.add_argument("--password", default=os.environ.get("ACUMATICA_PASSWORD", ""))
    parser.add_argument("--tenant", default=os.environ.get("ACUMATICA_TENANT", ""))
    parser.add_argument("--manifest", default="publish-manifest.json")
    args = parser.parse_args()

    if not args.url or not args.username or not args.password:
        print(
            "Error: --url, --username, --password required "
            "(or set ACUMATICA_* env vars)"
        )
        sys.exit(1)

    # Load manifest
    manifest_path = args.manifest
    if not os.path.exists(manifest_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        manifest_path = os.path.join(script_dir, "..", "publish-manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: manifest not found: {args.manifest}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    probes = manifest.get("e2e_probes", [])
    if not probes:
        log("No e2e_probes in manifest — nothing to test")
        sys.exit(0)

    log(f"Loaded {len(probes)} e2e probes from manifest")

    # Authenticate
    session = AcumaticaSession(args.url, args.username, args.password, args.tenant)
    log("Authenticating...")

    if not session.login():
        print("::error::E2E smoke test — login failed")
        sys.exit(1)
    ok("Authenticated")

    try:
        for probe in probes:
            run_probe(session, probe)
    finally:
        session.logout()

    # Summary
    print()
    total = passed + failed
    RED = "\033[91m"
    GREEN = "\033[92m"
    RESET = "\033[0m"

    if failed == 0:
        print(f"{GREEN}E2E SMOKE TEST PASSED{RESET} — {passed}/{total} probes passed")
        sys.exit(0)
    else:
        print(f"{RED}E2E SMOKE TEST FAILED{RESET} — {failed}/{total} probes failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Step 2: Verify script parses correctly**

Run: `python -c "import py_compile; py_compile.compile('scripts/smoke-e2e.py', doraise=True)" && echo "Syntax OK"`
Expected: `Syntax OK`

**Step 3: Verify manifest loading works locally**

Run: `python scripts/smoke-e2e.py --manifest publish-manifest.json 2>&1 || true`
Expected: Error about missing URL (no credentials locally), but proves the script loads and parses the manifest.

**Step 4: Commit**

```bash
git add scripts/smoke-e2e.py
git commit -m "feat: add e2e view-level smoke test script

Forces SQL column resolution on custom DAC extension fields via
\$select queries. Catches view/table mismatches that \$adHocSchema
and \$top=1 miss (e.g., Vendor_Vendor view error 2026-03-30).

Reuses AcumaticaSession from validate-publish.py — no new deps.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Wire into Sandbox Gate

**Files:**
- Modify: `.github/workflows/deploy-customization.yml:440-455`

**Step 1: Add e2e step after sandbox validate-publish.py**

After the existing step at line 440 (`run: python scripts/validate-publish.py --manifest publish-manifest.json`), and BEFORE the "Sandbox gate summary" step, insert:

```yaml
      - name: E2E view-level smoke test
        id: e2e
        env:
          ACUMATICA_URL: ${{ secrets.ACUMATICA_SANDBOX_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ secrets.ACUMATICA_SANDBOX_TENANT }}
        run: python scripts/smoke-e2e.py --manifest publish-manifest.json
```

**Step 2: Update the sandbox summary to include e2e result**

In the "Sandbox gate summary" step (~line 442-455), add a row to the table. Change:

```yaml
          echo "| Field Validation | \`${{ steps.verify.outcome }}\` |" >> "$GITHUB_STEP_SUMMARY"
```

to:

```yaml
          echo "| Field Validation | \`${{ steps.verify.outcome }}\` |" >> "$GITHUB_STEP_SUMMARY"
          echo "| E2E View Smoke | \`${{ steps.e2e.outcome }}\` |" >> "$GITHUB_STEP_SUMMARY"
```

Also update the BLOCKED message to include e2e failures:

```yaml
          if [ "${{ steps.smoke.outcome }}" = "failure" ] || [ "${{ steps.e2e.outcome }}" = "failure" ]; then
            echo "**BLOCKED:** Post-publish validation failed — production deploy prevented." >> "$GITHUB_STEP_SUMMARY"
          fi
```

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "ci: wire e2e smoke test into sandbox gate

Runs after validate-publish.py on sandbox. Hard fail blocks
Heritage Test and production gates.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Wire into Heritage Test Gate

**Files:**
- Modify: `.github/workflows/deploy-customization.yml:524-568`

**Step 1: Add e2e step after Heritage Test validate-publish.py**

After the existing "Validate Heritage Test" step (line 524-532) and BEFORE the "Post-publish login smoke test" step (line 534), insert:

```yaml
      - name: E2E view-level smoke test
        id: e2e
        run: |
          python scripts/smoke-e2e.py \
            --url "${{ secrets.ACUMATICA_URL }}" \
            --username "${{ secrets.ACUMATICA_USERNAME }}" \
            --password "${{ secrets.ACUMATICA_PASSWORD }}" \
            --tenant "${{ vars.ACUMATICA_TEST_TENANT }}" \
            --manifest publish-manifest.json
```

Note: Heritage Test uses `secrets.ACUMATICA_URL` (prod instance URL) with `vars.ACUMATICA_TEST_TENANT` — same pattern as the existing validate-publish.py step.

**Step 2: Update Heritage Test summary to include e2e result**

In the "Heritage Test gate summary" step (~line 556-568), add a row:

```yaml
          echo "| E2E View Smoke | \`${{ steps.e2e.outcome || 'n/a' }}\` |" >> "$GITHUB_STEP_SUMMARY"
```

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "ci: wire e2e smoke test into Heritage Test gate

Same $select probe approach, targeting Heritage Test tenant on
prod instance. Failure blocks production deploy.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Wire into Production Deploy

**Files:**
- Modify: `.github/workflows/deploy-customization.yml:740-755`

**Step 1: Add e2e step after production validate-publish.py**

After the existing "Post-publish field validation" step (line 741-750) and BEFORE the "Auto-rollback on verification failure" step (line 752), insert:

```yaml
      - name: E2E view-level smoke test
        id: e2e
        if: steps.deploy.outcome == 'success'
        continue-on-error: true
        env:
          ACUMATICA_URL: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_URL || secrets.ACUMATICA_SANDBOX_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_TENANT || secrets.ACUMATICA_SANDBOX_TENANT }}
        run: python scripts/smoke-e2e.py --manifest publish-manifest.json
```

Note: Uses `continue-on-error: true` same as the existing verify step — this feeds into the auto-rollback logic.

**Step 2: Update auto-rollback condition to include e2e failures**

The rollback step at line 753-755 currently triggers on `steps.verify.outcome == 'failure'`. Update to also trigger on e2e failure:

```yaml
      - name: Auto-rollback on verification failure
        id: rollback
        if: |
          steps.deploy.outcome == 'success' &&
          (steps.verify.outcome == 'failure' || steps.e2e.outcome == 'failure') &&
          steps.env.outputs.target == 'production' &&
          github.event.inputs.dry_run != 'true'
```

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "ci: wire e2e smoke test into production deploy + rollback

E2E failure on production triggers auto-rollback, same as existing
field validation failure. continue-on-error: true feeds into
rollback condition.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Wire into PR Validation (sandbox-only gate)

**Files:**
- Modify: `.github/workflows/deploy-customization.yml:991-1020`

There is a second sandbox validation block for pull requests (~line 991). This also needs the e2e step.

**Step 1: Add e2e step after PR sandbox validate-publish.py**

After the existing "Validate custom fields on sandbox" step (line 991-1001) and BEFORE the "Comment on PR with results" step (line 1003), insert:

```yaml
      - name: E2E view-level smoke test
        id: e2e
        env:
          ACUMATICA_URL: ${{ secrets.ACUMATICA_SANDBOX_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ secrets.ACUMATICA_SANDBOX_TENANT }}
        run: |
          python scripts/smoke-e2e.py --manifest publish-manifest.json \
            2>&1 | tee e2e-output.txt
```

**Step 2: Update PR comment to include e2e results**

In the "Comment on PR with results" step (~line 1003), update to include e2e output. Change the RESULT logic to check both steps:

```yaml
          RESULT="Passed"
          if [ "${{ steps.verify.outcome }}" = "failure" ] || [ "${{ steps.e2e.outcome }}" = "failure" ]; then
            RESULT="Failed"
          fi
```

And append e2e output to the PR comment body:

```yaml
          E2E_BODY=""
          if [ -f e2e-output.txt ]; then
            E2E_BODY=$(cat e2e-output.txt | head -50)
          fi
```

Then include `${E2E_BODY}` in the comment template below the existing validation output.

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "ci: wire e2e smoke test into PR validation

PR sandbox validation now includes e2e $select probes.
Results included in PR comment alongside field validation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Push and update PR

**Step 1: Push all commits**

```bash
git push
```

**Step 2: Verify PR #95 shows the new commits**

Run: `gh pr view 95 --repo studio-b-ai/acumatica-ci-cd`
Expected: PR shows all new commits on the branch.
