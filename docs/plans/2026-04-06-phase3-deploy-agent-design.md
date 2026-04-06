# Phase 3: AI Deploy Agent — Design

**Date:** 2026-04-06
**Status:** Approved
**Author:** Kevin Bibelhausen + Claude
**Depends on:** Phase 1 (pipeline hardening), Phase 2 (KB consolidation + verify.py)

## Goal

Replace the deploy/verify/notify portion of the GH Actions workflow with an AI agent invoked via Claude Code remote trigger. GitHub Actions becomes thin scaffolding (build + qualify + trigger). The agent owns the full deploy lifecycle: sandbox gate, prod deploy, verification, Slack communication, and escalation.

## Architecture

```
Push to main
    │
    ▼
┌─────────┐     ┌──────────┐     ┌──────────────┐
│  build   │ ──→ │ qualify   │ ──→ │ invoke-agent │
│ Package  │     │ Static    │     │ curl trigger │
│ zips     │     │ checks    │     │ + context    │
└─────────┘     └──────────┘     └──────┬───────┘
                                        │
                              GH Actions done.
                                        │
                                        ▼
                              ┌─────────────────┐
                              │  Deploy Agent    │
                              │  (remote trigger)│
                              └────────┬────────┘
                                       │
                    ┌──────────────────┼───────────────────┐
                    ▼                  ▼                   ▼
             Download artifacts  Query KB for       Post to #ops
             (gh run download)   recent incidents   "deploying..."
                    │
                    ▼
             Deploy to sandbox
             (deploy.sh + verify.py)
                    │
               ┌────┴────┐
               ▼         ▼
            PASS       FAIL → DM Kevin, wait for reply
               │
               ▼
            20-min countdown (#ops)
               │
               ▼
            Deploy to prod
            (snapshot + deploy.sh + verify.py)
               │
           ┌───┴────┐
           ▼        ▼
        PASS      FAIL → DM Kevin with diagnosis, wait for reply
           │
           ▼
        Finalize
        • git tag deploy/prod/YYYYMMDD-HHMMSS
        • auto-ingest to studiob-knowledge
        • DM Kevin: "Done. All checks pass."
```

## Workflow Simplification

The current 1300-line, 5-job workflow becomes 3 jobs.

**Kept as-is:**
- `build` — Package customization zips, validate projects, config loading
- `qualify` — Static checks, version validation, pre-flight sanity

**New (~20 lines):**
- `invoke-agent` — Upload artifacts, POST to remote trigger with deploy context

**Deleted entirely:**
- `test-tenant-gate` — Agent handles sandbox deploy
- `deploy` — Agent handles prod deploy, countdown, snapshot, verify, notify
- `validate` — PR validation can remain as a separate lightweight job if needed
- **Email notifications** — Dropped. No more maintenance emails to HF staff. Agent communicates exclusively via Slack.

## Remote Trigger & Invocation

### Trigger Setup (one-time)

Create a Claude Code remote trigger with the deploy agent prompt. The trigger ID and auth token go into GH Secrets.

### Invocation from GH Actions

```yaml
invoke-agent:
  needs: [build, qualify]
  runs-on: ubuntu-latest
  steps:
    - name: Invoke deploy agent
      run: |
        curl -X POST "https://api.claude.ai/v1/code/triggers/$TRIGGER_ID/run" \
          -H "Authorization: Bearer $CLAUDE_TRIGGER_TOKEN" \
          -H "Content-Type: application/json" \
          -d '{
            "context": {
              "package": "${{ needs.build.outputs.package_name }}",
              "project": "${{ needs.build.outputs.project_name }}",
              "also_publish": "${{ needs.build.outputs.also_publish }}",
              "environment": "production",
              "commit_sha": "${{ github.sha }}",
              "run_id": "${{ github.run_id }}"
            }
          }'
```

### Artifact Handoff

Agent downloads build artifacts via `gh run download --run-id $RUN_ID`. Requires a `GH_TOKEN` in the agent's environment.

### Secrets

**GH Secrets (new):**
- `CLAUDE_TRIGGER_TOKEN` — For invoking the remote trigger

**Agent environment needs:**
- `ACUMATICA_URL` (sandbox + prod)
- `ACUMATICA_USERNAME`, `ACUMATICA_PASSWORD`, `ACUMATICA_TENANT` (sandbox + prod)
- `SLACK_BOT_TOKEN` (with im:read, im:write, im:history, chat:write scopes)
- `GH_TOKEN` (for artifact download + tagging)
- `QDRANT_URL`, `VOYAGE_API_KEY` (for KB queries)
- `ACUDEV_URL`, `ACUDEV_API_KEY` (for auto-ingestion)

## Agent Deploy Lifecycle

### Step 1: Download Artifacts

```bash
gh run download $RUN_ID --name package-artifacts --dir ./artifacts
```

### Step 2: Deploy to Sandbox

```bash
scripts/deploy.sh \
  --url $SANDBOX_URL \
  --username $SANDBOX_USER \
  --password $SANDBOX_PASS \
  --tenant $SANDBOX_TENANT \
  --project $PROJECT \
  --package ./artifacts/$PACKAGE \
  --also-publish "$ALSO_PUBLISH"
```

Then verify:

```bash
python scripts/verify.py \
  --manifest publish-manifest.json \
  --url $SANDBOX_URL \
  --environment sandbox \
  --json-output sandbox-result.json
```

Parse `sandbox-result.json`. If overall=PASS, proceed. If overall=FAIL, escalate to Kevin.

### Step 3: Production Countdown

Post to #ops: "Deploying [project] to prod in 20 minutes."
Wait 20 minutes. Skip countdown for commits with `[urgent]` in the message.

### Step 4: Deploy to Production

Pre-deploy snapshot:
```bash
scripts/deploy.sh \
  --url $PROD_URL --backup --project $PROJECT --output ./backup
```

Deploy:
```bash
scripts/deploy.sh \
  --url $PROD_URL \
  --username $PROD_USER \
  --password $PROD_PASS \
  --tenant $PROD_TENANT \
  --project $PROJECT \
  --package ./artifacts/$PACKAGE \
  --also-publish "$ALSO_PUBLISH"
```

Verify:
```bash
python scripts/verify.py \
  --manifest publish-manifest.json \
  --url $PROD_URL \
  --environment production \
  --json-output prod-result.json
```

If PASS → finalize. If FAIL → escalate to Kevin with diagnosis.

### Step 5: Finalize

- Tag: `git tag deploy/prod/YYYYMMDD-HHMMSS && git push --tags`
- Auto-ingest: POST to `/ingest/incident` on AcuDev (success record)
- DM Kevin: "Deployed [project] @ [sha]. All checks pass."

## WARN Handling

verify.py can return checks with WARN status (e.g., 403 on PurchaseOrder). WARNs do not block the deploy. The agent includes WARNs in the summary DM to Kevin.

## Escalation Model

The agent is Kevin's on-call developer. Escalation is a Slack DM conversation, not a one-way alert.

### Flow

1. Agent posts a parent message to Kevin's DM with:
   - What happened
   - What the agent tried (if anything)
   - Recommended action
   - "Reply in this thread"
2. Agent polls the Slack thread for Kevin's reply (every 30 seconds, up to 2 hours)
3. Kevin replies in natural language: "go ahead", "try X instead", "abort", etc.
4. Agent interprets the reply and acts on it, replying in the same thread
5. Conversation continues until resolved or Kevin says stop
6. If timeout (2 hours) → agent posts "Timed out. Deploy paused." and terminates

### Resumability

If the remote trigger session times out during escalation, a new session can use the recall skill to pull context from the previous session and continue the conversation.

### Escalation Triggers

| Trigger | Agent behavior |
|---|---|
| Schema change detected | DM Kevin: "[PR] adds [table/column]. Won't deploy schema changes without approval." |
| ISV package change | DM Kevin: "[package] was modified. ISV packages are hands-off." |
| 3 sandbox failures | DM Kevin: "Failed 3x. Errors: [...]. My attempts: [...]." |
| Low confidence | DM Kevin: "Not sure about [X]. Here's what I see: [...]." |
| Verify.py overall=FAIL on prod | DM Kevin with full diagnosis from KB + verify output |

## Autonomy Rules

### Can do without approval

- Build, deploy to sandbox and prod (from main only)
- Run verification, interpret results
- Tag deploys, ingest incidents to KB
- Skip countdown on `[urgent]` commits
- Post to #ops channel
- Query studiob-knowledge for context

### Must escalate to Kevin

- Schema changes (new tables, column modifications)
- ISV package changes (Pacejet, FusionWMS, KN)
- More than 3 failed sandbox attempts
- Changes outside AesthetikContainers/AesthetikWMS projects
- Low confidence on any decision

### Must never do

- Auto-rollback (no re-publish of backup packages)
- Deploy non-main branches to production
- Notify end users (no email, no user-facing Slack)
- Bypass the sandbox gate
- Modify ISV packages
- Send maintenance emails to HF staff

## Slack Communication

All communication via Slack API (bot token). No email.

| Event | Destination | Content |
|---|---|---|
| Deploy starting | #ops (C0AR2UW2S66) | "Deploying [project] @ [sha]. Sandbox first." |
| Sandbox pass | #ops | "Sandbox verified. Prod in 20 min." |
| Prod countdown | #ops | "Deploying [project] to prod in 20 min." |
| Escalation | Kevin DM (U0ALNRQ4KF0) | Diagnosis + recommendation + "reply in this thread" |
| Success | Kevin DM | "[project] deployed to prod. All checks pass. [summary]" |
| Failure (after attempts) | Kevin DM | Diagnosis + what was tried + current state |

**Bot token scopes:** `chat:write`, `im:write`, `im:read`, `im:history`

## Qdrant Integration

### Pre-deploy Context

Before deploying to prod, the agent searches studiob-knowledge for recent incidents related to the project being deployed. Known patterns inform the agent's decision-making.

### Post-failure Diagnosis

When verify.py returns failures, the agent embeds the error signature and searches the KB for matching patterns. Results inform the diagnosis sent to Kevin.

### Mechanics

```
1. Embed query with Voyage AI (voyage-3)
2. POST /collections/studiob-knowledge/points/search
   - filter: domain IN [acumatica, pipeline]
   - filter: client = aesthetik
   - limit: 5
3. Top score > 0.7 → use as context
4. Top score < 0.7 → "no matching patterns in KB"
```

### Auto-ingestion

Every deploy (success or failure) → POST /ingest/incident on AcuDev. Already wired from Phase 2.

## Key Risks

1. **Remote trigger session lifetime** — Unknown. If sessions time out quickly, the escalation-wait model needs recall-based resumption. Validate during implementation.
2. **Remote trigger environment** — What tools/secrets are available? Need to validate what the agent can access.
3. **Remote trigger auth setup** — "Unable to resolve organization UUID" error on initial test. Org/auth config needed.
4. **Artifact handoff** — Agent needs `gh` CLI and a GH token to download build artifacts.

## What Changes in the Repo

| Change | Description |
|---|---|
| `acuops-deploy.yml` | Delete deploy, test-tenant-gate jobs. Add invoke-agent job. |
| Remote trigger | Create trigger with deploy agent prompt (one-time) |
| Agent prompt | Core deliverable — lifecycle, autonomy, escalation behavior |
| GH Secrets | Add `CLAUDE_TRIGGER_TOKEN` |
| Email notifications | Removed entirely from pipeline |

## What Doesn't Change

- build and qualify jobs
- deploy.sh, verify.py, publish-manifest.json
- Auto-ingestion endpoint (Phase 2)
- Qdrant/KB infrastructure
- acuops.yaml config structure

## Phase 4 Hooks

This design leads naturally into Phase 4 (failure recovery). When the agent diagnoses a failure, it already has KB context and a Slack thread with Kevin. Phase 4 adds: instead of just reporting, try to fix it (open PR, deploy fix to sandbox, verify, auto-merge if pass — up to 3 attempts before escalating).
