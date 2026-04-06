# Phase 3 E2E Dry Run — Design

**Date:** 2026-04-06
**Status:** Design
**Depends on:** Phase 3 PR #233 (merged), CLAUDE_TRIGGER_TOKEN (set)

## Problem

The deploy agent runs as a remote trigger — a cloud session with no pre-configured environment. It needs ~14 secrets (Acumatica creds, Slack bot token, Qdrant, etc.) that are stored as GH Secrets. But GH Secrets are write-only from CLI — the agent can't read them at runtime.

## Solution

Pass secrets via the deploy-context artifact. The GHA `invoke-agent` job already uploads `deploy-context.json`. Expand it to include a `secrets` object with all agent env vars. The agent downloads the artifact (authenticated via GH_PAT) and exports the secrets as env vars in a bootstrap step.

Artifact has 7-day retention and requires authenticated download — acceptable security posture for CI secrets.

## Changes

### 1. Workflow: expand deploy-context.json

Add `secrets` block to the heredoc in `.github/workflows/acuops-deploy.yml` invoke-agent job:

```json
{
  ...existing fields...,
  "secrets": {
    "ACUMATICA_SANDBOX_URL": "...",
    "ACUMATICA_SANDBOX_USERNAME": "...",
    "ACUMATICA_SANDBOX_PASSWORD": "...",
    "ACUMATICA_SANDBOX_TENANT": "...",
    "ACUMATICA_PROD_URL": "...",
    "ACUMATICA_PROD_USERNAME": "...",
    "ACUMATICA_PROD_PASSWORD": "...",
    "ACUMATICA_PROD_TENANT": "...",
    "SLACK_BOT_TOKEN": "...",
    "GH_TOKEN": "... (GH_PAT_DISPATCH)",
    "QDRANT_URL": "...",
    "VOYAGE_API_KEY": "...",
    "ACUDEV_URL": "...",
    "ACUDEV_API_KEY": "..."
  }
}
```

### 2. Agent prompt: add Step 0 Bootstrap

Add before current Step 1 in `agents/deploy-agent.md`:

```bash
# Download deploy context (includes secrets)
gh run download "$RUN_ID" --name deploy-context --dir ./context

# Export secrets as env vars
eval $(jq -r '.secrets | to_entries[] | "export \(.key)=\(.value)"' ./context/deploy-context.json)
```

### 3. Agent prompt: update env var table

Change "These are available in your environment" to "These are loaded from deploy-context.json in Step 0 (Bootstrap)."

## What's NOT in scope

- Remote trigger env var configuration (not available from CLI)
- Key rotation / 1Password integration (separate initiative)
- Daily schedule disable (manual action on claude.ai/code/scheduled)
