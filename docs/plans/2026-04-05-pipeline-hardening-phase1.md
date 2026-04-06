# Pipeline Hardening Phase 1 — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Stop the pipeline from breaking production on every deploy. Fix the three bugs that caused tonight's outage: false validation failures triggering rollback, auto-rollback with corrupt zips, and no branch protection on prod deploys.

**Architecture:** Four targeted changes to two repos (acumatica-ci-cd workflow, acuops-pipeline scripts). No restructuring — surgical fixes to stop the bleeding. The bigger redesign (separate jobs, AI agent) is Phase 2+.

**Tech Stack:** GitHub Actions YAML, Python 3

**Repos involved:**
- `acumatica-ci-cd` — `.github/workflows/acuops-deploy.yml`
- `acuops-pipeline` — `scripts/validate-publish.py`

---

### Task 1: Fix validate-publish.py — treat HTTP 403 as warning

The direct cause of tonight's false rollback. `validate-publish.py` treats any non-200 response as a failure. `smoke-e2e.py` correctly treats 401/403 as a warning. They need to agree.

**Files:**
- Modify: `/Users/kevin/dev/acuops-pipeline/scripts/validate-publish.py:196-203`

**Step 1: Add 403 handling to match smoke-e2e.py**

In `validate_entity()` function, add explicit 401/403 handling before the generic non-200 check:

```python
    # Step 1: Entity reachability — can we query without HTTP 500?
    code, body = session.query_entity(entity_name)

    if code == 500:
        fail(f"{entity_name}: HTTP 500 — graph extension may be broken")
        return False
    elif code in (401, 403):
        warn(f"{entity_name}: HTTP {code} — permission issue, not a code bug")
        return True
    elif code != 200:
        fail(f"{entity_name}: HTTP {code} (expected 200)")
        return False
```

**Step 2: Verify the warn() function exists**

Check that `warn()` is defined in validate-publish.py. If not, add it:

```python
def warn(msg):
    global warnings
    warnings += 1
    print(f"{YELLOW}[ WARN ]{RESET} {msg}")
```

**Step 3: Test locally**

```bash
cd /Users/kevin/dev/acuops-pipeline
python3 -c "
import ast
with open('scripts/validate-publish.py') as f:
    tree = ast.parse(f.read())
# Verify no syntax errors
print('Syntax OK')
"
```

**Step 4: Commit**

```bash
cd /Users/kevin/dev/acuops-pipeline
git add scripts/validate-publish.py
git commit -m "fix: treat HTTP 401/403 as warning in validate-publish.py

Matches smoke-e2e.py behavior. Permission issues are not code bugs
and should not trigger rollback.

Fixes: PO301000 403 causing false deploy failures on every deploy."
```

---

### Task 2: Remove auto-rollback from the workflow

Auto-rollback is actively harmful. It uses corrupt backup zips, causes a second app pool restart, and triggered tonight on a successful deploy. Replace with an alert.

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml:903-960`

**Step 1: Replace the auto-rollback step with an alert step**

Replace lines 903-953 (the `Auto-rollback on verification failure` step) with:

```yaml
      # ── Alert on verification failure (NO auto-rollback) ─────────────
      - name: Alert on verification failure
        id: alert
        if: >
          steps.deploy.outcome == 'success' &&
          (steps.verify.outcome == 'failure' || steps.e2e.outcome == 'failure') &&
          steps.env.outputs.target == 'production' &&
          github.event.inputs.dry_run != 'true'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          PROJECT="${{ needs.build.outputs.project_name }}"
          VERIFY="${{ steps.verify.outcome }}"
          E2E="${{ steps.e2e.outcome }}"
          RUN_URL="${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"

          echo "::error::Post-publish verification failed (verify=${VERIFY}, e2e=${E2E})"
          echo "Backup snapshot available as workflow artifact for manual restore via SM204505"

          if [ -n "${SLACK_WEBHOOK_URL}" ]; then
            curl -sf -X POST "${SLACK_WEBHOOK_URL}" \
              -H "Content-Type: application/json" \
              -d "{\"text\":\"⚠️ Deploy VERIFICATION FAILED — ${PROJECT}\nVerify: ${VERIFY} | E2E: ${E2E}\nCommit: ${GITHUB_SHA::8}\nLogs: ${RUN_URL}\nNo rollback attempted. Backup artifact available for manual restore via SM204505.\"}"
          fi
          exit 1
```

**Step 2: Remove the rolled-back tag step**

Delete lines 955-960 (the `Tag rolled-back deploy` step) since rollback no longer happens.

**Step 3: Verify YAML syntax**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python3 -c "
import yaml
with open('.github/workflows/acuops-deploy.yml') as f:
    yaml.safe_load(f)
print('YAML valid')
"
```

**Step 4: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add .github/workflows/acuops-deploy.yml
git commit -m "fix: replace auto-rollback with alert on verification failure

Auto-rollback was causing harm:
- Corrupt backup zips (InvalidDataException on Central Directory)
- Unnecessary second app pool restart
- Triggered on false positives (PO 403, script crashes)

New behavior: alert via Slack with failure details and link to logs.
Backup snapshot remains as workflow artifact for manual restore."
```

---

### Task 3: Make test-tenant gate a hard requirement (with override)

Currently the deploy job allows test-tenant-gate failure (line 641). Make it a hard gate but add a `force_deploy` escape hatch.

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml:58-78` (inputs)
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml:636-645` (deploy condition)

**Step 1: Add force_deploy input**

After the existing `skip_countdown` input (~line 78), add:

```yaml
    force_deploy:
      description: 'Type OVERRIDE to bypass test gate (emergency only)'
      required: false
      type: string
```

**Step 2: Update deploy job condition**

Replace lines 636-645 with:

```yaml
    if: >
      always() &&
      needs.build.result == 'success' &&
      needs.build.outputs.customization_changes == 'true' &&
      github.event_name != 'pull_request' &&
      (
        needs.test-tenant-gate.result == 'success' ||
        needs.test-tenant-gate.result == 'skipped' ||
        github.event.inputs.force_deploy == 'OVERRIDE'
      ) && (
        needs.qualify.result == 'success' ||
        needs.qualify.result == 'skipped' ||
        github.event.inputs.force_qualify == 'true'
      )
```

**Step 3: Verify YAML syntax**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python3 -c "
import yaml
with open('.github/workflows/acuops-deploy.yml') as f:
    yaml.safe_load(f)
print('YAML valid')
"
```

**Step 4: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add .github/workflows/acuops-deploy.yml
git commit -m "feat: make test-tenant gate a hard requirement

Test-tenant-gate failure now blocks production deploy.
Emergency override: set force_deploy to 'OVERRIDE' on workflow_dispatch.

Previously test-tenant-gate failure was allowed through (advisory only)."
```

---

### Task 4: Lock workflow_dispatch to main branch for production

Prevent deploying feature branches to production via manual trigger.

**Files:**
- Modify: `/Users/kevin/dev/acumatica-ci-cd/.github/workflows/acuops-deploy.yml` (add new step after checkout in deploy job)

**Step 1: Add branch enforcement step**

After the `Determine target environment` step (~line 661), add:

```yaml
      - name: Enforce branch protection
        if: steps.env.outputs.target == 'production' && github.ref != 'refs/heads/main'
        run: |
          echo "::error::Production deploys must use the main branch. Current ref: ${{ github.ref }}"
          echo "If this is an emergency, merge to main first."
          exit 1
```

**Step 2: Verify YAML syntax**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python3 -c "
import yaml
with open('.github/workflows/acuops-deploy.yml') as f:
    yaml.safe_load(f)
print('YAML valid')
"
```

**Step 3: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git add .github/workflows/acuops-deploy.yml
git commit -m "feat: enforce main branch for production deploys

workflow_dispatch with environment=production now requires ref=main.
Prevents feature branches from deploying directly to production.

Root cause: feat/command-center ASPX reached prod without merge,
broke SB501000 with wrong master page."
```

---

### Task 5: Create PR for acuops-pipeline changes

**Step 1: Push and create PR for validate-publish.py fix**

```bash
cd /Users/kevin/dev/acuops-pipeline
git checkout -b fix/403-warning
git push -u origin fix/403-warning
gh pr create --title "fix: treat HTTP 401/403 as warning in validation" \
  --body "$(cat <<'EOF'
## Summary
- Treats HTTP 401/403 responses as warnings (permission issue, not code bug)
- Matches existing smoke-e2e.py behavior
- Prevents false deploy failures and rollback triggers

## Root Cause
PO301000 returns HTTP 403 for api-bot (Acumatica support ticket open).
This was triggering auto-rollback on every successful deploy.

## Test plan
- [ ] Deploy to Heritage Test, verify PO 403 is logged as WARN not FAIL
- [ ] Verify exit code 0 when only 403 warnings (no real failures)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

### Task 6: Create PR for acumatica-ci-cd workflow changes

**Step 1: Push and create PR for workflow changes (Tasks 2-4 combined)**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git checkout -b fix/pipeline-hardening-phase1
git push -u origin fix/pipeline-hardening-phase1
gh pr create --title "fix: pipeline hardening — no auto-rollback, hard test gate, branch lock" \
  --body "$(cat <<'EOF'
## Summary
- Replace auto-rollback with alert (Slack notification + artifact)
- Make test-tenant gate a hard requirement (OVERRIDE escape hatch)
- Enforce main branch for production deploys via workflow_dispatch

## What this fixes
- Auto-rollback using corrupt zips (InvalidDataException)
- Auto-rollback triggering on false positives (PO 403, script crashes)
- Feature branches deploying to prod without merge (TabView.master incident)
- Test-tenant gate failure not blocking production deploy

## Test plan
- [ ] Push to main, verify test-tenant gate blocks deploy on failure
- [ ] Manual dispatch with force_deploy=OVERRIDE, verify it bypasses gate
- [ ] Manual dispatch from non-main branch with environment=production, verify it's blocked
- [ ] Trigger verification failure, verify Slack alert instead of rollback attempt

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Execution Notes

- **Task 1** is in the `acuops-pipeline` repo (separate from this repo)
- **Tasks 2-4** are all in `acuops-deploy.yml` in this repo — can be one branch/PR
- **Tasks 5-6** create the PRs
- These changes are safe to merge independently — Task 1 makes validation tolerant, Tasks 2-4 make the workflow safer
- After merge, the next push to main will test the full flow
