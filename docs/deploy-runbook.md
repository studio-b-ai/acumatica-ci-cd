# Acumatica CI/CD Deploy Runbook

**Repo:** [studio-b-ai/acumatica-ci-cd](https://github.com/studio-b-ai/acumatica-ci-cd)
**Escalation contact:** Kevin Bibelhausen — kevin@heritagefabrics.com
**Production instance:** https://heritagefabrics.acumatica.com
**Sandbox instance:** https://heritagefabrics-sandbox.acumatica.com
**After-hours requirement:** All production publishes MUST run after 6pm CT. Publishing restarts the Acumatica app pool and terminates all active user sessions.

---

## Quick Reference

### Workflow Files

| Workflow | File | Trigger |
|----------|------|---------|
| Deploy Customization | `.github/workflows/deploy-customization.yml` | Push to `main`, manual `workflow_dispatch` |
| Sync Test Env | `.github/workflows/sync-test-env.yml` | Manual |
| Test Rollback | `.github/workflows/test-rollback.yml` | Manual |
| Test Countdown | `.github/workflows/test-countdown.yml` | Manual |

### Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/qualify.py` | Pre-deploy qualification gate (6 checks) |
| `scripts/deploy.py` | Import + publish via Customization API |
| `scripts/snapshot.py` | Pre-deploy backup download |
| `scripts/validate-publish.py` | Post-publish field verification against `publish-manifest.json` |
| `scripts/notify.py` | Slack notification on success/failure |

### GitHub Actions Secrets

| Secret | Purpose |
|--------|---------|
| `ACUMATICA_PROD_URL` | `https://heritagefabrics.acumatica.com` |
| `ACUMATICA_PROD_USERNAME` | api-bot service account |
| `ACUMATICA_PROD_PASSWORD` | api-bot password |
| `ACUMATICA_PROD_TENANT` | Heritage Fabrics tenant name |
| `ACUMATICA_STG_URL` | Staging URL (same instance, test company) |
| `ACUMATICA_STG_USERNAME` | Staging api-bot |
| `ACUMATICA_STG_PASSWORD` | Staging password |
| `ACUMATICA_STG_TENANT` | Staging tenant |
| `SLACK_WEBHOOK_URL` | Incoming webhook for #deployments |

### GitHub Actions Variables

| Variable | Purpose |
|----------|---------|
| `CUSTOMIZATION_PROJECT_NAME` | Primary project (e.g., `HeritageFabricsPOv5`) |
| `ALSO_PUBLISH_PROJECTS` | Comma-separated co-publish list (e.g., `HeritageFabricsPOv5,StudioBPORelations`) |

---

## Normal Deploy Flow

```
Push to main
  -> qualify.py (6 checks)
  -> snapshot.py (backup current .zip)
  -> deploy.py --import
  -> deploy.py --publishBegin (co-publish all projects)
  -> deploy.py --publishEnd (poll until done, 600s timeout)
  -> validate-publish.py (check fields against publish-manifest.json)
  -> notify.py (Slack #deployments)
```

---

## Escalation 1: Qualify Gate Blocks Deploy

The qualify gate (`scripts/qualify.py`) runs 6 checks before any deploy proceeds. Exit code 1 halts the pipeline.

### The 6 Checks

| # | Check | Pass Condition | Fail Action |
|---|-------|----------------|-------------|
| 1 | **Health** | api-bot can login and query StockItem | See "api-bot locked out" below |
| 2 | **Orphans** | No unknown customization projects on instance | Inspect SM204505 (see below) |
| 3 | **Diff scope** | Changed files are within expected directories | Review commit — may contain unintended files |
| 4 | **Failures** | No recent failed deploys in last 3 runs | Investigate previous failure before retrying |
| 5 | **Cooldown** | 30 minutes since last publish | Wait, or override (see below) |
| 6 | **Timing** | After 6pm CT (business hours check) | Wait, or override (see below) |

### Health check fails

api-bot may be locked out. See Escalation 3.

If login succeeds but StockItem query fails, check for `NullReferenceException` in the response. This indicates customization subsystem corruption. Do NOT retry. Contact Kevin immediately.

### Orphans found

Unknown customization projects exist on the Acumatica instance that are not in the `ALSO_PUBLISH_PROJECTS` list. This matters because co-publish must include all active projects to detect conflicts.

**Resolution:**
1. Log into Acumatica as admin
2. Navigate to SM204505 (Customization Projects)
3. Identify the orphan project name(s) from the qualify output
4. Determine if they are legitimate (ISV packages, VAR packages) or leftover from failed experiments
5. Either add them to `ALSO_PUBLISH_PROJECTS` in GitHub Variables, or delete them from SM204505

### Cooldown not met

The 30-minute cooldown prevents back-to-back publishes that compound app pool restart risk.

**Override:** Run the workflow manually via `workflow_dispatch` with `force_qualify=true`. This skips the cooldown check only. All other checks still run.

### Business hours block

Deploys are blocked before 6pm CT to protect active users from app pool restarts.

**Override:** Run the workflow manually via `workflow_dispatch` with `skip_countdown=true`. Use only for emergency hotfixes with Kevin's explicit approval.

---

## Escalation 2: Rollback Fires During Deploy

The pipeline takes a pre-deploy snapshot via `scripts/snapshot.py`. If publish fails, the auto-rollback re-imports that snapshot .zip over the broken package.

### Auto-rollback succeeds

No action needed. The Slack notification will indicate rollback occurred. Investigate the publish failure in the GitHub Actions logs before attempting another deploy. Look for C# compilation errors in the publishEnd response.

### Auto-rollback itself fails

1. Go to the GitHub Actions run that failed
2. Download the `snapshot-backup` artifact (contains the pre-deploy .zip files)
3. Log into Acumatica as admin
4. Navigate to SM204505 (Customization Projects)
5. Import the .zip manually using the Upload button
6. Publish all projects together (check all active projects, then Publish)

### No snapshot was taken

If `snapshot.py` failed silently (it exits 0 even on failure — snapshot is advisory, not a gate):

1. Find the previous successful deploy by checking git tags:
   ```
   git tag -l 'deploy/prod/*' --sort=-version:refname | head -5
   ```
2. Check out that commit:
   ```
   git checkout deploy/prod/YYYYMMDD-HHMMSS
   ```
3. The `Customization/_project/` directory at that commit contains the known-good package
4. Zip it and import manually via SM204505, or re-run the deploy workflow from that tag

---

## Escalation 3: api-bot Locked Out

### Symptoms

All of the following stop working simultaneously:
- Acumatica MCP tools return auth errors
- Webhook-router sync workers (orders, customers, products, cases) fail
- Health probes report Acumatica as down
- Integration tester canaries fail
- Business dashboard shows Acumatica probe failures

### Cascading Impact

8 Railway services depend on api-bot credentials:

| Service | Impact |
|---------|--------|
| webhook-router | HubSpot sync stops (orders, customers, products, cases) |
| acumatica-mcp | All 26 MCP tools fail |
| business-dashboard | Health probes + sales intelligence fail |
| support-agent | Cannot look up customer/order data |
| integration-tester | All Acumatica test paths fail |
| note-intelligence | Cannot fetch SalesOrder notes |
| compliance-engine | Cannot verify requirements against Acumatica |
| provisioning-agent | Cannot create/deactivate Employee records |

### Immediate Fix

1. Log into Acumatica as admin (not api-bot)
2. Navigate to SM201020 (User Security, or Users screen)
3. Find `api-bot` in the user list
4. Click the **Unlock** button
5. Save
6. Verify recovery: hit `https://heritagefabrics.acumatica.com/entity/auth/login` with api-bot creds, expect 204

### Root Cause

Multiple CI/CD runs or sync workers competing for the single api-bot session during an app pool restart. The app pool restart invalidates all sessions. Rapid re-login attempts trigger the Acumatica account lockout policy.

### Prevention

- **Concurrency control:** The deploy workflow uses `concurrency: acumatica-deploy` to prevent parallel runs
- **Maintenance mode:** Deploys should enter maintenance mode on webhook-router (`POST /maintenance/start`) before publishing to pause BullMQ workers
- **Separate service accounts:** Long-term fix is to create a dedicated CI/CD service account separate from the api-bot used by runtime services. This has not been implemented yet.

---

## Escalation 4: Publish Succeeds but Fields Missing

After publish completes, `scripts/validate-publish.py` checks `publish-manifest.json` against the live Acumatica REST API schema. If expected custom fields are missing, the validation step fails.

### Diagnosis

A custom field requires BOTH of these to exist:
1. **DAC extension** in C# code (defines the field in the application layer)
2. **Database column** via `<Sql>` element or migration (defines the field in the database)

If only one exists, the field will not appear in the REST API response.

### Check DAC extension

Look in `Customization/_project/Code/` for the relevant `*Ext.cs` file. Verify the field is declared with `[PXDBString]`, `[PXDBDate]`, or similar attribute.

### Check SQL column

Look in `Customization/_project/project.xml` for `<Sql>` elements. Verify the `ALTER TABLE ... ADD` statement references the correct table and column name. Column names must match the DAC field name exactly (e.g., `UsrHubSpotDealId`).

Cloud-hosted Acumatica does NOT support `<Table>` elements in customization projects (causes NullReferenceException). All column creation must use `<Sql>` with `IF NOT EXISTS` guards.

### Force Re-Import

If the schema template is stale, force a clean re-import:

```bash
python scripts/deploy.py \
  --url https://heritagefabrics.acumatica.com \
  --username $USERNAME \
  --password $PASSWORD \
  --tenant "$TENANT" \
  --project HeritageFabricsPOv5 \
  --package dist/HeritageFabricsPOv5.zip \
  --is-replace-if-exists
```

Then publish all projects together. The `isReplaceIfExists: true` flag forces Acumatica to regenerate the schema template from the DAC extensions.

---

## Escalation 5: App Pool Restart Takes Too Long

### Expected Timing

| Scenario | Duration |
|----------|----------|
| Simple publish (no SQL, few DACs) | 30-60 seconds |
| Complex publish (SQL migrations, many DACs) | 2-3 minutes |
| Co-publish with ISV packages | 3-5 minutes |

### Timeout Behavior

`deploy.py` polls `POST /CustomizationApi/publishEnd` at 10-second intervals with a 600-second (10-minute) total timeout. The response body is `{}` while publishing is in progress. When done, it returns `isCompleted: true` or `isFailed: true` with log entries.

### If Timeout Is Hit

1. **Do NOT re-run the deploy.** The publish may still be running server-side. Re-importing during an active publish causes corruption.
2. Wait 5 additional minutes, then try hitting the Acumatica login page manually in a browser
3. If the instance comes back, log in and check SM204505 for the project status
4. If the instance does not come back after 15 minutes total, contact Kevin. He may need to engage Acumatica cloud hosting support.

### If publishEnd Returns isFailed

The response includes a `log` array with error and warning entries. The `deploy.py` script parses and displays these. Common causes:
- C# compilation errors (check the error text for file/line references)
- SQL migration failures (table already exists, column type mismatch)
- Conflict between co-published projects (same field defined in two projects)

---

## Escalation 6: Session Gate Conflicts

api-bot is configured for single-session access. Only one active session is allowed at a time. If a sync worker holds the session when CI/CD tries to login, the login will fail or kill the worker's session.

### Enter Maintenance Mode Before Publishing

Before any production publish, pause all BullMQ workers:

```bash
curl -X POST https://webhook-router-production-e161.up.railway.app/maintenance/start \
  -H "Authorization: Bearer $WEBHOOK_ROUTER_TOKEN"
```

This pauses: order sync, customer sync, product sync, case sync, and all omnichannel workers.

### Resume After Publishing

After publish completes and `validate-publish.py` passes:

```bash
curl -X POST https://webhook-router-production-e161.up.railway.app/maintenance/stop \
  -H "Authorization: Bearer $WEBHOOK_ROUTER_TOKEN"
```

### If You Forgot Maintenance Mode

Symptoms: deploy fails with "already logged in" or sync workers report auth errors mid-cycle.

1. Enter maintenance mode immediately (URL above)
2. Wait 30 seconds for active sessions to drain
3. Re-run the deploy workflow

### Services That Compete for api-bot Sessions

| Service | Session Pattern |
|---------|----------------|
| webhook-router (sync workers) | 15-min cron, holds session for 10-60s per cycle |
| acumatica-mcp | On-demand, holds session per tool call |
| integration-tester | Weekly canary (Sunday 2am), holds session for ~35s |
| note-intelligence | On-demand, holds session per classification batch |
| compliance-engine | On-demand, holds session per requirement check |

---

## Pre-Deploy Checklist

Use this before every production deploy:

- [ ] It is after 6pm CT (or `skip_countdown=true` approved by Kevin)
- [ ] Maintenance mode enabled on webhook-router
- [ ] No other CI/CD runs in progress (check GitHub Actions)
- [ ] Changes reviewed and merged to `main`
- [ ] `ALSO_PUBLISH_PROJECTS` includes all active customization projects
- [ ] `publish-manifest.json` updated if new custom fields were added

## Post-Deploy Checklist

- [ ] `validate-publish.py` passed (check GitHub Actions logs)
- [ ] Slack notification received in #deployments
- [ ] Maintenance mode disabled on webhook-router
- [ ] Spot-check one affected screen in Acumatica (e.g., SO301000 for SalesOrder fields)
- [ ] Confirm sync workers resume (check webhook-router logs for next 15-min cycle)
