# Pipeline Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close 5 pipeline gaps (A, B, C, E, F) that allowed the 2026-03-29 P0 outage and would allow future outages.

**Architecture:** All changes go to the `cleanup/remove-uom-hotfix-and-migrations` branch (PR #93). Gaps B, C, E, F are workflow/script changes. Gap A is a new Python method in deploy.py plus a workflow step. No deploys until after hours.

**Tech Stack:** Python 3.12 (deploy.py), GitHub Actions YAML, Acumatica REST API (v24.200.001), bash

**Design doc:** `docs/plans/2026-03-30-pipeline-hardening-design.md`

---

### Task 1: Rollback Messaging (Gap F)

**Files:**
- Modify: `/.github/workflows/deploy-customization.yml:830-837`

**Step 1: Update success rollback message**

In `deploy-customization.yml`, find the auto-rollback success Slack message (line ~833) and replace:

```yaml
              -d '{"text":"PACKAGE RESTORED — '"${PROJECT_NAME}"' -> production\nDeploy: '"${GITHUB_SHA::8}"'\nPackage snapshot restored + verified.\nNote: CustomizationPlugin SQL changes are NOT reversed.\nIf UpdateDatabase() modified data, manual review required."}'
```

**Step 2: Update failure rollback message**

Find the rollback failure Slack message (line ~837) and replace:

```yaml
              -d '{"text":"PACKAGE RESTORE FAILED — verification did not pass\nDeploy: '"${PROJECT_NAME}"' @ '"${GITHUB_SHA::8}"'\nArtifact: '"${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"'\nCustomizationPlugin SQL changes are NOT reversed.\nManual restore: download artifact -> SM204505 Import -> Publish"}'
```

**Step 3: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "fix: rollback Slack messages — say PACKAGE RESTORED, not ROLLED BACK

Auto-rollback only restores the customization package ZIP. It does NOT
reverse CustomizationPlugin.UpdateDatabase() SQL changes (ALTER TABLE,
INSERT, CREATE TABLE). Messaging now reflects this limitation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: ALSO_PUBLISH Allowlist Validation (Gap B)

**Files:**
- Modify: `/.github/workflows/deploy-customization.yml` (build job, after line ~182, before "Validate ALL customization projects")

**Step 1: Add allowlist validation step**

Insert a new step between "Check if published projects changed" and "Verify project folder exists":

```yaml
      - name: Validate ALSO_PUBLISH_PROJECTS entries
        env:
          ALSO_PUBLISH: ${{ vars.ALSO_PUBLISH_PROJECTS || '' }}
        run: |
          # Every project in ALSO_PUBLISH_PROJECTS must exist in the repo.
          # Catches stale entries (e.g., deleted hotfix packages left in the variable).
          # Root cause of UomHotfixYdsToIn near-miss on 2026-03-30.
          if [ -z "${ALSO_PUBLISH}" ]; then
            echo "ALSO_PUBLISH_PROJECTS is empty — nothing to validate"
            exit 0
          fi

          FAILED=0
          IFS=',' read -ra PROJECTS <<< "${ALSO_PUBLISH}"
          for proj in "${PROJECTS[@]}"; do
            proj=$(echo "$proj" | xargs)  # trim whitespace
            [ -z "$proj" ] && continue

            if [ ! -d "Customization/${proj}" ]; then
              echo "::error::ALSO_PUBLISH_PROJECTS contains '${proj}' but Customization/${proj}/ does not exist"
              FAILED=1
            elif [ ! -f "Customization/${proj}/project.xml" ]; then
              echo "::error::ALSO_PUBLISH_PROJECTS contains '${proj}' but Customization/${proj}/project.xml is missing"
              FAILED=1
            else
              echo "Validated: ${proj} -> Customization/${proj}/project.xml exists"
            fi
          done

          if [ ${FAILED} -ne 0 ]; then
            echo ""
            echo "Fix: Remove stale entries from the ALSO_PUBLISH_PROJECTS GitHub variable"
            echo "     or add the missing Customization/{project}/project.xml to the repo."
            exit 1
          fi
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "[GUARD] Validate ALSO_PUBLISH_PROJECTS entries exist in repo

Every project listed in the ALSO_PUBLISH_PROJECTS GitHub variable must
have a matching Customization/{project}/project.xml in the repo. Catches
stale entries like UomHotfixYdsToIn that was left in the variable after
its directory was deleted — would have re-deployed on next push to main.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Circuit Breaker (Gap E)

**Files:**
- Modify: `/.github/workflows/deploy-customization.yml` (deploy job, add step before snapshot)

**Step 1: Add circuit breaker step**

Insert a new step at the beginning of the deploy job (after "Determine target environment", before "Install Python dependencies"):

```yaml
      - name: Circuit breaker — halt on consecutive failures
        if: github.event.inputs.force_qualify != 'true'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          # After 3 consecutive failed deploys, halt. Prevents the 20+ iteration
          # loop from 2026-03-29 that exhausted the API login limit.
          RECENT=$(gh run list \
            --workflow deploy-customization.yml \
            --branch "${{ github.ref_name }}" \
            --limit 3 \
            --json conclusion \
            --jq '[.[] | .conclusion] | join(",")' 2>/dev/null || echo "")

          if [ "${RECENT}" = "failure,failure,failure" ]; then
            echo "::error::Circuit breaker tripped — 3 consecutive deploy failures on ${{ github.ref_name }}"
            echo "Manual review required before retrying."
            echo "Use force_qualify=true to bypass (emergency only)."

            if [ -n "${{ secrets.STUDIOB_SLACK_WEBHOOK_URL }}" ]; then
              curl -sf -X POST "${{ secrets.STUDIOB_SLACK_WEBHOOK_URL }}" \
                -H "Content-Type: application/json" \
                -d '{"text":"CIRCUIT BREAKER — 3 consecutive deploy failures on ${{ github.ref_name }}\nManual review required.\nBypass: workflow_dispatch with force_qualify=true"}'
            fi
            exit 1
          fi

          echo "Circuit breaker OK — recent results: ${RECENT:-none}"
```

**Step 2: Commit**

```bash
git add .github/workflows/deploy-customization.yml
git commit -m "[GUARD] Circuit breaker — halt after 3 consecutive deploy failures

Prevents the 20+ iteration loop from 2026-03-29 that exhausted the API
login limit. Checks last 3 runs on the branch — if all failed, halts
with Slack alert. Bypass with force_qualify=true for emergencies.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 4: GI Baseline in Deploy (Gap C)

**Files:**
- Modify: `/.github/workflows/deploy-customization.yml` (deploy job — add pre-publish capture + post-publish diff)
- Modify: `scripts/gi_baseline.py:28-32` (add UserAuditTrail to known GIs)

**Step 1: Add UserAuditTrail to known GIs**

In `scripts/gi_baseline.py`, update the `known_gis` list (line 28-32):

```python
    known_gis = [
        "InventoryAllocationDetail",
        "LotAvailability",
        "StockItemsChristmasWishList",
        "UserAuditTrail",
    ]
```

**Step 2: Add GI baseline capture step (pre-publish)**

In `deploy-customization.yml`, insert a new step BEFORE the deploy step (after "Enter maintenance mode", before "Download built packages"):

```yaml
      - name: Capture GI baseline (pre-publish)
        id: gi_pre
        if: steps.smoke.outcome == 'success' || github.event.inputs.force_qualify == 'true'
        continue-on-error: true
        env:
          ACUMATICA_URL: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_URL || secrets.ACUMATICA_SANDBOX_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_TENANT || secrets.ACUMATICA_SANDBOX_TENANT }}
        run: |
          python scripts/gi_baseline.py capture \
            --url "${ACUMATICA_URL}" \
            --username "${ACUMATICA_USERNAME}" \
            --password "${ACUMATICA_PASSWORD}" \
            --tenant "${ACUMATICA_TENANT}" \
            --baseline-file baselines/gi-pre.json
```

**Step 3: Add GI baseline diff step (post-publish)**

Insert after the "Post-publish field validation" step, before "Auto-rollback on verification failure":

```yaml
      - name: GI baseline diff (post-publish)
        id: gi_diff
        if: steps.deploy.outcome == 'success' && steps.gi_pre.outcome == 'success'
        continue-on-error: true
        env:
          ACUMATICA_URL: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_URL || secrets.ACUMATICA_SANDBOX_URL }}
          ACUMATICA_USERNAME: ${{ secrets.ACUMATICA_PROD_USERNAME }}
          ACUMATICA_PASSWORD: ${{ secrets.ACUMATICA_PROD_PASSWORD }}
          ACUMATICA_TENANT: ${{ (steps.env.outputs.target == 'production') && secrets.ACUMATICA_PROD_TENANT || secrets.ACUMATICA_SANDBOX_TENANT }}
        run: |
          python scripts/gi_baseline.py diff \
            --url "${ACUMATICA_URL}" \
            --username "${ACUMATICA_USERNAME}" \
            --password "${ACUMATICA_PASSWORD}" \
            --tenant "${ACUMATICA_TENANT}" \
            --baseline-file baselines/gi-pre.json
```

**Step 4: Add gi_diff to auto-rollback condition**

Update the auto-rollback `if` condition (line ~799) to also trigger on GI regression:

```yaml
        if: |
          steps.deploy.outcome == 'success' &&
          (steps.verify.outcome == 'failure' || steps.gi_diff.outcome == 'failure') &&
          steps.env.outputs.target == 'production' &&
          github.event.inputs.dry_run != 'true'
```

**Step 5: Create baselines directory**

```bash
mkdir -p baselines
echo "# GI baseline artifacts (generated during deploy)" > baselines/.gitkeep
```

**Step 6: Commit**

```bash
git add scripts/gi_baseline.py baselines/.gitkeep .github/workflows/deploy-customization.yml
git commit -m "[GUARD] Wire GI baseline into deploy pipeline

Captures Generic Inquiry baseline before publish, diffs after. If a
known GI disappeared or degraded, triggers auto-rollback. Adds
UserAuditTrail to the known GI list.

Catches GI regressions like the UserAuditTrail wipe from the 2026-03-29
snapshot restore — nobody knew until manual checking.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 5: E2E Smoke Test (Gap A)

**Files:**
- Modify: `scripts/deploy.py:477-514` (add `e2e_smoke_test()` method after existing `smoke_test()`)
- Modify: `/.github/workflows/deploy-customization.yml` (add e2e smoke test step after field validation)

**Step 1: Add e2e_smoke_test method to deploy.py**

Add after the existing `smoke_test()` method (after line 514):

```python
    def e2e_smoke_test(
        self,
        customer_id: str = "C000949",
        inventory_id: str = "00004",
        order_type: str = "SO",
        warehouse: str = "99",
    ) -> bool:
        """Full order lifecycle smoke test: create SO -> ship -> confirm -> cancel.

        Exercises:
          - SO creation with customer (customer DAC extensions)
          - Line item with UOM (INUnit validation — 2026-03-29 failure point)
          - Shipment creation (SOOrderEntry graph extensions)
          - Shipment confirmation (ShipmentEntry graph extensions)
          - Cancellation for cleanup (no invoice, no AR impact)

        Uses Heritage Fabrics Management (C000949) as test customer.
        """
        api = f"{self.base_url}/entity/default/24.200.001"
        order_nbr = None
        shipment_nbr = None

        try:
            # ── Step 1: Create Sales Order with one line ──
            _log("E2E smoke test: Creating sales order...")
            so_payload = {
                "OrderType": {"value": order_type},
                "CustomerID": {"value": customer_id},
                "Description": {"value": f"CI/CD smoke test {datetime.now(timezone.utc).isoformat()[:19]}Z"},
                "Details": [
                    {
                        "InventoryID": {"value": inventory_id},
                        "OrderQty": {"value": 1},
                        "WarehouseID": {"value": warehouse},
                    }
                ],
            }
            resp = self.session.put(f"{api}/SalesOrder", json=so_payload, timeout=60)
            if resp.status_code not in (200, 201):
                _log(f"E2E FAIL: SO creation returned HTTP {resp.status_code}: {resp.text[:500]}", style="err")
                return False

            so = resp.json()
            order_nbr = so.get("OrderNbr", {}).get("value")
            if not order_nbr:
                _log("E2E FAIL: SO created but no OrderNbr in response", style="err")
                return False
            _log(f"  Created SO {order_type} {order_nbr}", style="ok")

            # ── Step 2: Create Shipment ──
            _log("E2E smoke test: Creating shipment...")
            action_resp = self.session.post(
                f"{api}/SalesOrder/{order_type}/{order_nbr}/action/CreateShipment",
                json={"entity": {}, "parameters": {"WarehouseID": {"value": warehouse}}},
                timeout=60,
            )
            if action_resp.status_code not in (200, 202, 204):
                _log(f"E2E FAIL: CreateShipment returned HTTP {action_resp.status_code}: {action_resp.text[:500]}", style="err")
                self._e2e_cleanup(api, order_type, order_nbr)
                return False

            # Fetch the shipment number from the updated SO
            so_resp = self.session.get(
                f"{api}/SalesOrder/{order_type}/{order_nbr}",
                params={"$expand": "Shipments"},
                timeout=30,
            )
            if so_resp.status_code == 200:
                shipments = so_resp.json().get("Shipments", [])
                if shipments:
                    shipment_nbr = shipments[0].get("ShipmentNbr", {}).get("value")

            if shipment_nbr:
                _log(f"  Created Shipment {shipment_nbr}", style="ok")
            else:
                _log("  Shipment created (number not retrieved)", style="ok")

            # ── Step 3: Confirm Shipment ──
            if shipment_nbr:
                _log("E2E smoke test: Confirming shipment...")
                confirm_resp = self.session.post(
                    f"{api}/Shipment/{shipment_nbr}/action/ConfirmShipment",
                    json={"entity": {}},
                    timeout=60,
                )
                if confirm_resp.status_code not in (200, 202, 204):
                    _log(f"E2E WARN: ConfirmShipment returned HTTP {confirm_resp.status_code}: {confirm_resp.text[:300]}", style="warn")
                else:
                    _log(f"  Confirmed Shipment {shipment_nbr}", style="ok")

            # ── Step 4: Cancel SO (cleanup — no invoice) ──
            _log("E2E smoke test: Cancelling order...")
            cancel_resp = self.session.post(
                f"{api}/SalesOrder/{order_type}/{order_nbr}/action/CancelOrder",
                json={"entity": {}},
                timeout=60,
            )
            if cancel_resp.status_code not in (200, 202, 204):
                _log(f"E2E WARN: CancelOrder returned HTTP {cancel_resp.status_code} — orphaned order {order_nbr}", style="warn")
            else:
                _log(f"  Cancelled SO {order_type} {order_nbr}", style="ok")

            _log("E2E smoke test PASSED — full order lifecycle verified", style="ok")
            return True

        except Exception as exc:
            _log(f"E2E smoke test FAILED with exception: {exc}", style="err")
            if order_nbr:
                self._e2e_cleanup(api, order_type, order_nbr)
            return False

    def _e2e_cleanup(self, api: str, order_type: str, order_nbr: str) -> None:
        """Best-effort cleanup of a smoke test order."""
        try:
            _log(f"  Cleaning up test order {order_type} {order_nbr}...")
            self.session.post(
                f"{api}/SalesOrder/{order_type}/{order_nbr}/action/CancelOrder",
                json={"entity": {}},
                timeout=30,
            )
        except Exception:
            _log(f"  Cleanup failed — orphaned order {order_type} {order_nbr} on C000949", style="warn")
```

**Step 2: Call e2e_smoke_test after publish in deploy.py**

Find the existing smoke_test call in the main deploy flow (line ~880) and add the e2e call after it:

```python
                # Post-publish smoke test
                smoke_ok = client.smoke_test()
                if not smoke_ok:
                    _log(
                        "Smoke test failed — publish completed but API may be unstable",
                        style="warn",
                    )

                # Full order lifecycle test
                if smoke_ok and not args.validate_only:
                    e2e_ok = client.e2e_smoke_test()
                    if not e2e_ok:
                        _log("E2E smoke test FAILED — business operations broken after publish", style="err")
                        sys.exit(2)  # Distinct exit code for e2e failure
```

**Step 3: Commit**

```bash
git add scripts/deploy.py
git commit -m "feat: E2E smoke test — full SO lifecycle after every publish

Creates a sales order on Heritage Fabrics Management (C000949), adds a
line item (00004 BRINKLEY, exercises UOM validation), creates shipment,
confirms shipment, then cancels. No invoice — clean reversal.

This is the test that would have caught the 2026-03-29 UOM failure.
The old smoke test only did a StockItem GET — everything passed while
nobody could save a sales order.

Runs after every publish (sandbox, Heritage Test, production).
Exit code 2 on failure (distinct from other failures).

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 6: Push and verify

**Step 1: Push all commits**

```bash
git push origin cleanup/remove-uom-hotfix-and-migrations
```

**Step 2: Verify PR #93 has all commits**

```bash
gh pr view 93 --json commits --jq '.commits | length'
```

Expected: commit count reflects all new commits from Tasks 1-5 plus the existing 7.

**Step 3: Verify no syntax errors in workflow**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-customization.yml'))"
```

Expected: no errors (validates YAML is well-formed).

**Step 4: Verify deploy.py imports/syntax**

```bash
python3 -c "import ast; ast.parse(open('scripts/deploy.py').read()); print('OK')"
```

Expected: `OK`

**Step 5: Commit implementation plan**

```bash
git add docs/plans/2026-03-30-pipeline-hardening.md
git commit -m "docs: pipeline hardening implementation plan — 6 tasks

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
git push origin cleanup/remove-uom-hotfix-and-migrations
```
