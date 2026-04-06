# Phase 3: Deploy Agent — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the deploy/test-tenant-gate/notify jobs in acuops-deploy.yml with an AI agent invoked via Claude Code remote trigger.

**Architecture:** GH Actions keeps build+qualify, uploads a deploy-context.json artifact, and POSTs to a remote trigger. The agent (running in Anthropic's cloud VM) downloads the context and artifacts via `gh` CLI, deploys to sandbox then prod using deploy.sh + verify.py, communicates via Slack API, and escalates to Kevin via conversational DM threads.

**Tech Stack:** Claude Code remote triggers, GitHub Actions, Bash (deploy.sh), Python (verify.py), Slack API, Qdrant (studiob-knowledge), Voyage AI

**Design doc:** `docs/plans/2026-04-06-phase3-deploy-agent-design.md`

---

### Task 1: Validate Remote Trigger API Access

This is the gating task. If remote triggers don't work, we need a fallback plan before proceeding.

**Files:**
- None (API exploration only)

**Step 1: Test the RemoteTrigger list API**

Use the RemoteTrigger tool with `action: "list"` to see if the API is accessible. If it fails with "Unable to resolve organization UUID," debug the auth setup:
- Check if the current OAuth session has org context
- Try from the web UI at `claude.ai/code/scheduled`
- Check `claude.ai/settings` for organization membership

**Step 2: If API works, create a test trigger**

```
RemoteTrigger create:
{
  "name": "test-echo",
  "job_config": {
    "prompt": "Echo 'hello from deploy agent test' and exit."
  }
}
```

Note: The exact `job_config` schema may differ — experiment with the create API to discover required fields.

**Step 3: Run the test trigger**

```
RemoteTrigger run: trigger_id from step 2
```

Verify the run completes and produces output.

**Step 4: If API is broken (known bugs as of 2026-04-06)**

Document the error. Fallback options:
- Create the trigger via the web UI at `claude.ai/code/scheduled` instead of the API
- If cloud triggers are fully down, use the `mcp__scheduled-tasks__create_scheduled_task` local scheduled task as an interim solution (polls for new completed workflow runs)

**Step 5: Document findings**

Record what worked, what schema the API expects, and any workarounds needed. Update this plan if the API shape differs from expectations.

---

### Task 2: Write the Deploy Agent Prompt

The agent prompt is the core deliverable. It must be fully self-contained because cloud trigger sessions start fresh with no prior context.

**Files:**
- Create: `agents/deploy-agent.md`

**Step 1: Create the agent prompt file**

Write `agents/deploy-agent.md` with the following sections:

```markdown
# Deploy Agent

You are the AcuOps Deploy Agent for Heritage Fabrics (Acumatica ERP).
You manage the full deploy lifecycle: sandbox verification, production deployment, and post-deploy validation.

## Your Environment

- You are running in a cloud VM with the acumatica-ci-cd repo cloned
- You have access to: deploy.sh, verify.py, publish-manifest.json
- You communicate via Slack API (curl)
- You query studiob-knowledge (Qdrant) for operational context

## Environment Variables

These are available in your environment:
- ACUMATICA_SANDBOX_URL, ACUMATICA_SANDBOX_USERNAME, ACUMATICA_SANDBOX_PASSWORD, ACUMATICA_SANDBOX_TENANT
- ACUMATICA_PROD_URL, ACUMATICA_PROD_USERNAME, ACUMATICA_PROD_PASSWORD, ACUMATICA_PROD_TENANT
- SLACK_BOT_TOKEN
- GH_TOKEN (for gh CLI)
- QDRANT_URL, VOYAGE_API_KEY
- ACUDEV_URL, ACUDEV_API_KEY

## Step 1: Get Deploy Context

Find the latest completed workflow run and download artifacts:

    RUN_ID=$(gh run list --repo studio-b-ai/acumatica-ci-cd \
      --workflow=acuops-deploy.yml --branch=main \
      --status=completed --limit=1 \
      --json databaseId -q '.[0].databaseId')
    gh run download $RUN_ID --name deploy-context --dir ./context
    gh run download $RUN_ID --name package-artifacts --dir ./artifacts

Read `./context/deploy-context.json` for package name, project name, also_publish list, commit SHA, and run ID.

Verify the commit SHA matches the repo HEAD. If not, stop — a newer push may have superseded this deploy.

## Step 2: Pre-deploy KB Check

Query studiob-knowledge for recent incidents related to this project:

    curl -s "$QDRANT_URL/collections/studiob-knowledge/points/search" \
      -H "Content-Type: application/json" \
      -d '{
        "vector": <embed query with Voyage AI>,
        "filter": {
          "must": [
            {"key": "domain", "match": {"any": ["acumatica", "pipeline"]}},
            {"key": "client", "match": {"value": "aesthetik"}}
          ]
        },
        "limit": 5
      }'

If matching incidents found (score > 0.7), factor them into your decision-making.

## Step 3: Post to #ops

    curl -s -X POST "https://slack.com/api/chat.postMessage" \
      -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "channel": "C0AR2UW2S66",
        "text": "Deploying <PROJECT> @ <SHA_SHORT>. Sandbox first."
      }'

## Step 4: Deploy to Sandbox

    bash scripts/deploy.sh \
      --url "$ACUMATICA_SANDBOX_URL" \
      --username "$ACUMATICA_SANDBOX_USERNAME" \
      --password "$ACUMATICA_SANDBOX_PASSWORD" \
      --tenant "$ACUMATICA_SANDBOX_TENANT" \
      --project "<PROJECT>" \
      --package "./artifacts/<PACKAGE>" \
      --also-publish "<ALSO_PUBLISH>"

Then verify:

    python3 scripts/verify.py \
      --manifest publish-manifest.json \
      --url "$ACUMATICA_SANDBOX_URL" \
      --username "$ACUMATICA_SANDBOX_USERNAME" \
      --password "$ACUMATICA_SANDBOX_PASSWORD" \
      --tenant "$ACUMATICA_SANDBOX_TENANT" \
      --environment sandbox \
      --json-output sandbox-result.json

Read sandbox-result.json. If overall != "pass", ESCALATE (see escalation rules below).

## Step 5: Production Countdown

Post to #ops: "Sandbox verified. Deploying <PROJECT> to prod in 20 minutes."

Wait 20 minutes. Skip if the commit message contains [urgent].

## Step 6: Deploy to Production

Pre-deploy snapshot:

    bash scripts/deploy.sh \
      --url "$ACUMATICA_PROD_URL" \
      --username "$ACUMATICA_PROD_USERNAME" \
      --password "$ACUMATICA_PROD_PASSWORD" \
      --tenant "$ACUMATICA_PROD_TENANT" \
      --project "<PROJECT>" \
      --backup --output ./backup

Deploy:

    bash scripts/deploy.sh \
      --url "$ACUMATICA_PROD_URL" \
      --username "$ACUMATICA_PROD_USERNAME" \
      --password "$ACUMATICA_PROD_PASSWORD" \
      --tenant "$ACUMATICA_PROD_TENANT" \
      --project "<PROJECT>" \
      --package "./artifacts/<PACKAGE>" \
      --also-publish "<ALSO_PUBLISH>"

Verify:

    python3 scripts/verify.py \
      --manifest publish-manifest.json \
      --url "$ACUMATICA_PROD_URL" \
      --username "$ACUMATICA_PROD_USERNAME" \
      --password "$ACUMATICA_PROD_PASSWORD" \
      --tenant "$ACUMATICA_PROD_TENANT" \
      --environment production \
      --json-output prod-result.json

If overall != "pass", ESCALATE with full diagnosis.

## Step 7: Finalize

    git tag "deploy/prod/$(date -u +%Y%m%d-%H%M%S)" && git push --tags

Auto-ingest success to KB:

    curl -s -X POST "$ACUDEV_URL/ingest/incident" \
      -H "Authorization: Bearer $ACUDEV_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{
        "type": "deploy_success",
        "project": "<PROJECT>",
        "commit_sha": "<SHA>",
        "environment": "production",
        "verify_result": <contents of prod-result.json>
      }'

DM Kevin:

    curl -s -X POST "https://slack.com/api/chat.postMessage" \
      -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "channel": "U0ALNRQ4KF0",
        "text": "<PROJECT> deployed to prod @ <SHA_SHORT>. All checks pass.\n\nSummary:\n- Sandbox: PASS\n- Prod: PASS\n- Warnings: <list any WARNs or 'none'>"
      }'

## Escalation Rules

When escalating, post a DM to Kevin (U0ALNRQ4KF0) in a NEW message (not a thread reply) with:
1. What happened (error details from verify.py output)
2. KB context (any matching incidents from studiob-knowledge)
3. Your recommended action
4. "Reply to this message and I'll follow your instructions."

Then poll for Kevin's reply:

    # Every 30 seconds, for up to 2 hours:
    curl -s "https://slack.com/api/conversations.replies" \
      -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
      -G -d "channel=<DM_CHANNEL_ID>&ts=<MESSAGE_TS>"

When Kevin replies, interpret the instruction and act on it. Reply in the same thread with your results. Continue the conversation until resolved.

If no reply after 2 hours, post: "Timed out waiting for response. Deploy is paused. Push to main to retry." and terminate.

## Autonomy Rules

### You CAN do without asking:
- Deploy to sandbox and prod (from main only)
- Run verification, interpret results
- Tag deploys, ingest incidents to KB
- Skip countdown on [urgent] commits
- Post to #ops channel

### You MUST escalate to Kevin:
- Schema changes (new tables, column modifications)
- ISV package changes (Pacejet, FusionWMS, KN — check the isv_prefix in deploy-context.json)
- More than 3 failed sandbox verification attempts
- Changes outside AesthetikContainers or AesthetikWMS projects
- Anything you're not confident about

### You must NEVER:
- Auto-rollback (never re-publish backup packages)
- Deploy non-main branches to production
- Send notifications to end users
- Bypass the sandbox gate (every deploy must pass sandbox first)
- Modify ISV packages
- Send email notifications

## WARN Handling

verify.py checks can return WARN status (e.g., 403 on PurchaseOrder). WARNs do NOT block the deploy. Include them in the summary DM to Kevin.
```

**Step 2: Review the prompt for completeness**

Verify the prompt covers all lifecycle steps from the design doc. Check that environment variable names match what deploy.sh and verify.py expect.

**Step 3: Commit**

```bash
git add agents/deploy-agent.md
git commit -m "feat: deploy agent prompt for Phase 3 remote trigger"
```

---

### Task 3: Add deploy-context Artifact to Workflow

The `invoke-agent` job needs to save build outputs as a downloadable artifact so the agent can read them.

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml`

**Step 1: Read the current build job outputs**

The build job already outputs these values (lines 104-120):
- `package_path`, `package_name`, `project_name`, `also_publish`, `also_publish_test`
- `backup_enabled`, `isv_prefix`, `strict`, `known_projects`, `isv_packages`
- `test_tenant_enabled`, `timezone`, `notify_recipients`, `notify_sender`
- `customization_changes`, `plugin_changes`

**Step 2: Add the invoke-agent job**

After the `qualify` job, add:

```yaml
  # ──────────────────────────────────────────────
  # Job 3: Invoke Deploy Agent
  # ──────────────────────────────────────────────
  invoke-agent:
    name: Invoke Deploy Agent
    needs: [build, qualify]
    if: >-
      always() &&
      needs.build.result == 'success' &&
      needs.build.outputs.customization_changes == 'true' &&
      github.event_name != 'pull_request' &&
      (
        needs.qualify.result == 'success' ||
        needs.qualify.result == 'skipped'
      )
    runs-on: ubuntu-latest
    steps:
      - name: Save deploy context
        run: |
          cat > deploy-context.json <<'CONTEXT_EOF'
          {
            "package_name": "${{ needs.build.outputs.package_name }}",
            "package_path": "${{ needs.build.outputs.package_path }}",
            "project_name": "${{ needs.build.outputs.project_name }}",
            "also_publish": "${{ needs.build.outputs.also_publish }}",
            "isv_prefix": "${{ needs.build.outputs.isv_prefix }}",
            "commit_sha": "${{ github.sha }}",
            "commit_message": "${{ github.event.head_commit.message }}",
            "run_id": "${{ github.run_id }}",
            "ref": "${{ github.ref }}",
            "environment": "${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}"
          }
          CONTEXT_EOF

      - name: Upload deploy context
        uses: actions/upload-artifact@v4
        with:
          name: deploy-context
          path: deploy-context.json
          retention-days: 7

      - name: Invoke deploy agent
        env:
          CLAUDE_TRIGGER_TOKEN: ${{ secrets.CLAUDE_TRIGGER_TOKEN }}
          CLAUDE_TRIGGER_ID: ${{ secrets.CLAUDE_TRIGGER_ID }}
        run: |
          if [ -z "$CLAUDE_TRIGGER_TOKEN" ] || [ -z "$CLAUDE_TRIGGER_ID" ]; then
            echo "::warning::Deploy agent trigger not configured. Skipping agent invocation."
            exit 0
          fi

          RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
            "https://api.claude.ai/v1/code/triggers/${CLAUDE_TRIGGER_ID}/run" \
            -H "Authorization: Bearer ${CLAUDE_TRIGGER_TOKEN}" \
            -H "Content-Type: application/json")

          HTTP_CODE=$(echo "$RESPONSE" | tail -1)
          BODY=$(echo "$RESPONSE" | head -n -1)

          echo "Trigger response: HTTP ${HTTP_CODE}"
          echo "$BODY"

          if [ "$HTTP_CODE" -ge 400 ]; then
            echo "::error::Deploy agent trigger failed with HTTP ${HTTP_CODE}"
            exit 1
          fi

          echo "Deploy agent triggered successfully. Agent will manage the deploy lifecycle."
```

**Step 3: Verify the job integrates correctly**

Check that:
- `invoke-agent` runs after build+qualify (same gate conditions as the old deploy job, minus the test-tenant-gate dependency)
- The deploy-context.json has all fields the agent prompt expects
- The trigger invocation is gracefully skipped if secrets aren't configured yet

**Step 4: Commit**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "feat: add invoke-agent job with deploy-context artifact"
```

---

### Task 4: Remove Old Deploy Jobs from Workflow

Delete the `test-tenant-gate`, `deploy`, and email notification logic. Keep `build`, `qualify`, `invoke-agent`, and `validate` (PR checks).

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml`

**Step 1: Identify the line ranges to delete**

From the workflow analysis:
- `test-tenant-gate` job: lines ~486-633
- `deploy` job: lines ~634-1195 (the big one — 560 lines including countdown, snapshot, deploy, verify, notify, lockout, intelligence, regression trigger, tagging)
- Email notification secrets comment block: lines 20-23

Keep:
- `build` job (lines 101-443)
- `qualify` job (lines 444-485)
- `invoke-agent` job (added in Task 3)
- `validate` job for PRs (lines ~1196-1315) — useful for PR checks, separate from deploy

**Step 2: Delete the test-tenant-gate job**

Remove the entire job block.

**Step 3: Delete the deploy job**

Remove the entire job block (lines ~634-1195). This is the biggest deletion — ~560 lines of countdown timers, email notifications, deploy logic, post-deploy validation, lockout, intelligence, etc.

**Step 4: Clean up the email notification comments**

Remove the "Optional GitHub Secrets (for email notifications)" comment block at the top of the file since emails are dropped entirely.

**Step 5: Remove notify_recipients and notify_sender from build outputs**

These are no longer consumed by any job. Remove from the outputs section and the config loading step.

**Step 6: Verify the workflow is valid YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml'))"
```

**Step 7: Verify job dependency graph**

The remaining jobs should be:
- `build` (no deps)
- `qualify` (needs: build)
- `invoke-agent` (needs: build, qualify)
- `validate` (needs: build, PR only)

No dangling references to deleted jobs.

**Step 8: Commit**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "refactor: remove deploy, test-tenant-gate jobs — agent owns deploy lifecycle"
```

---

### Task 5: Configure Slack Bot

The agent needs a Slack bot token with DM capabilities. The current pipeline uses a webhook (can't DM or read threads).

**Files:**
- None (Slack admin + secrets configuration)

**Step 1: Check if a Slack bot already exists**

Check the studiob-ai.slack.com workspace for existing bot apps. Look for an app with `chat:write` and `im:*` scopes.

**Step 2: Create or update the Slack app**

Required OAuth scopes:
- `chat:write` — Post messages to channels
- `im:write` — Send DMs
- `im:read` — Read DM channel info
- `im:history` — Read DM thread replies (for escalation polling)

**Step 3: Get the bot token**

The bot token (xoxb-...) goes into:
- The remote trigger's environment variables (for the cloud agent)
- Optionally GH Secrets if the workflow still needs it

**Step 4: Test DM to Kevin**

```bash
curl -s -X POST "https://slack.com/api/chat.postMessage" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"channel": "U0ALNRQ4KF0", "text": "Deploy agent test message. Ignore."}'
```

Verify Kevin receives the DM.

**Step 5: Test thread reading**

Reply to the test message, then verify the agent can read the reply:

```bash
curl -s "https://slack.com/api/conversations.replies" \
  -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
  -G -d "channel=<DM_CHANNEL>&ts=<MESSAGE_TS>"
```

**Step 6: Document the bot token location**

Note where the token is stored so future sessions know how to access it.

---

### Task 6: Configure Remote Trigger

Create the actual remote trigger with the deploy agent prompt, environment variables, and repo access.

**Files:**
- Uses: `agents/deploy-agent.md` (from Task 2)

**Step 1: Create the remote trigger**

Via the API (if working) or the web UI at `claude.ai/code/scheduled`:

- **Name:** `acuops-deploy-agent`
- **Prompt:** Contents of `agents/deploy-agent.md`
- **Repository:** `studio-b-ai/acumatica-ci-cd`
- **Environment variables:**
  - `ACUMATICA_SANDBOX_URL` = `https://heritagefabrics-sandbox.acumatica.com`
  - `ACUMATICA_SANDBOX_USERNAME` = (from GH Secrets or Railway)
  - `ACUMATICA_SANDBOX_PASSWORD` = (from GH Secrets or Railway)
  - `ACUMATICA_SANDBOX_TENANT` = (sandbox tenant name)
  - `ACUMATICA_PROD_URL` = `https://heritagefabrics.acumatica.com`
  - `ACUMATICA_PROD_USERNAME` = (from existing GH Secrets)
  - `ACUMATICA_PROD_PASSWORD` = (from existing GH Secrets)
  - `ACUMATICA_PROD_TENANT` = (from existing GH Secrets)
  - `SLACK_BOT_TOKEN` = (from Task 5)
  - `GH_TOKEN` = (PAT with repo + actions scope)
  - `QDRANT_URL` = (from `railway variables --service qdrant`)
  - `VOYAGE_API_KEY` = (from `railway variables --service acudev`)
  - `ACUDEV_URL` = (from GH Secrets, already set in Phase 2)
  - `ACUDEV_API_KEY` = (from GH Secrets, already set in Phase 2)
- **Network:** Full internet access (needs Acumatica SaaS, Slack, Qdrant, GitHub)
- **Setup script:** `apt-get update && apt-get install -y gh` (if gh CLI not pre-installed)
- **Schedule:** None (triggered on-demand only, not on a cron)
- **Connectors:** None needed (agent uses Slack API directly via curl)

**Step 2: Save the trigger ID**

Add `CLAUDE_TRIGGER_ID` to GH Secrets.

**Step 3: Add the trigger token**

Add `CLAUDE_TRIGGER_TOKEN` to GH Secrets. This is the OAuth bearer token for invoking the trigger.

**Step 4: Test the trigger**

```
RemoteTrigger run: trigger_id
```

Verify the agent starts, clones the repo, and can access environment variables.

---

### Task 7: End-to-End Dry Run

Test the full flow without actually deploying to production.

**Files:**
- None (testing only)

**Step 1: Modify agent prompt for dry-run**

Temporarily add `--validate-only` to the deploy.sh commands in the agent prompt so it uploads but doesn't publish.

**Step 2: Push a test commit to main**

Make a trivial change to a customization file (e.g., update a comment in a .xml file) and push to main.

**Step 3: Monitor the GH Actions run**

Verify:
- build job completes and uploads package artifact
- qualify job completes (or is skipped)
- invoke-agent job uploads deploy-context.json and triggers the agent
- GH Actions finishes (3 jobs, all green)

**Step 4: Monitor the agent session**

Check the agent's cloud session at `claude.ai/code`:
- Agent starts and clones the repo
- Agent downloads deploy-context.json and package artifacts
- Agent runs deploy.sh with --validate-only on sandbox
- Agent runs verify.py on sandbox
- Agent posts to #ops
- Agent DMs Kevin with success summary

**Step 5: Test escalation flow**

Modify the publish-manifest.json to reference a non-existent entity, causing verify.py to fail. Push to main and verify:
- Agent detects the failure
- Agent queries studiob-knowledge for matching patterns
- Agent DMs Kevin with diagnosis and recommendation
- Reply to the DM and verify the agent reads the reply
- Tell the agent to abort

**Step 6: Restore normal operation**

Remove the `--validate-only` flag from the agent prompt. Revert the manifest change. The pipeline is now live.

**Step 7: Commit any final adjustments**

```bash
git add -A
git commit -m "feat: Phase 3 complete — AI deploy agent via remote trigger"
```

---

## Execution Order & Dependencies

```
Task 1 (validate triggers) ──→ Task 6 (configure trigger)
                                       │
Task 2 (agent prompt)      ────────────┤
                                       │
Task 3 (invoke-agent job)  ──→ Task 4 (remove old jobs) ──→ Task 7 (E2E test)
                                       │
Task 5 (Slack bot)         ────────────┘
```

Tasks 1, 2, 3, 5 can be worked in parallel. Task 4 depends on Task 3. Task 6 depends on 1, 2, 5. Task 7 depends on everything.

## Rollback Plan

If remote triggers prove unreliable during Task 1:
- Keep the old deploy job in the workflow (don't delete in Task 4)
- Add the invoke-agent job alongside it (both run)
- Agent runs in parallel, deploys to sandbox only (shadow mode)
- Once stable, cut over by removing the old deploy job
