# AcuOps AI-Managed Pipeline — Phases 2-5

## Context

Phase 1 is complete (PR #220, #221, #222 merged 2026-04-06):
- No auto-rollback (alert + Slack DM to Kevin on failure)
- Hard test-tenant gate with OVERRIDE escape
- Branch protection (main only for prod)
- validate-publish.py treats 403 as warning
- SaaS sandbox configured as staging target
- Slack DMs on failures only (no channel noise)

The knowledge foundation is in place:
- `studiob-knowledge` Qdrant collection (53 entries, domain/client/source tagged)
- Claude memory files cleaned to instructions-only
- CLAUDE.md has 10 standing rules
- Rigby skill for session close-out

## Design Doc

Read `/Users/kevin/dev/acumatica-ci-cd/docs/plans/2026-04-05-acuops-ai-pipeline-design.md` for the full architecture.

## Phase 2: Knowledge Base Consolidation

**Goal:** Make `studiob-knowledge` the single brain for all agents.

Tasks:
1. Migrate `acudev-knowledge` official content (Acumatica PDFs, help portal pages, GitHub examples) into `studiob-knowledge` with proper domain/client/source tags
2. Update AcuDev service (studiob repo, Railway `acudev` service) to query `studiob-knowledge` instead of `acudev-knowledge`
3. Keep `acumatica-community` and `acumatica-stackoverflow` as supplemental collections (noisier, different quality controls)
4. Update the ingestion endpoint to default to `studiob-knowledge` and support the new tagging schema (domain, client, source)
5. Set up auto-ingestion: every deploy failure/resolution gets ingested automatically
6. Verify search quality — test queries that span domains (e.g., "why did publish break navigation" should return both Acumatica docs and pipeline incident reports)

**Key files:**
- AcuDev service: `/Users/kevin/dev/studiob/apps/server/src/` (or wherever the source lives — check Railway)
- Ingestion endpoint: search for `/knowledge/ingest` route
- Qdrant config: QDRANT_URL from `railway variables --service acudev` in studiob-platform

**Qdrant connection:**
```bash
railway link -p studiob-platform
export QDRANT_URL=$(railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
export VOYAGE_API_KEY=$(railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['VOYAGE_API_KEY'])")
```

## Phase 3: AI Agent for Deploy Orchestration

**Goal:** Claude Code manages the deploy lifecycle. GitHub Actions becomes thin scaffolding that invokes the agent.

Tasks:
1. Create a Claude Code scheduled task or remote trigger that activates on push to main
2. Agent calls deploy.py, verify.py as tools (not scripts running in workflow steps)
3. Agent queries `studiob-knowledge` for context before decisions
4. Agent handles sandbox → prod promotion sequence
5. Structured JSON output from verify.py feeds agent decisions (not exit codes)
6. Agent DMs Kevin with deploy summary (success or failure with diagnosis)

**Autonomy rules:**
- Agent can build, deploy to sandbox, deploy to prod, open PRs, auto-merge if sandbox passes
- Agent must escalate for: schema changes, ISV changes, >3 failed fix attempts, low confidence
- Agent must never: auto-rollback, deploy non-main to prod, notify end users, modify ISV packages

## Phase 4: AI Agent for Failure Recovery

**Goal:** When verification fails, the agent diagnoses and fixes instead of alerting Kevin.

Tasks:
1. Agent analyzes failure logs, queries `studiob-knowledge` for matching patterns
2. If known pattern → apply fix → PR → sandbox verify → auto-merge → redeploy
3. If unknown → spin up GCE VM (136.115.233.148) for deep debugging
4. Agent uses browser tools, API, SQL on the VM to reproduce and diagnose
5. Auto-ingestion: every failure and resolution goes into `studiob-knowledge`
6. Max 3 fix attempts before escalating to Kevin
7. VM auto-shutoff after 2 hours idle

**GCE VM management:**
- Start/stop via GCE API (needs service account key)
- Restore latest prod snapshot for data parity
- Deploy failing package to VM for reproduction

## Phase 5: Full Loop with Request Portal

**Goal:** Enhancement requests flow from portal through AI implementation to production automatically.

Tasks:
1. Request portal (webhook-router) submits enhancement
2. AI designs the implementation (AcuDev + `studiob-knowledge`)
3. AI implements (Claude Code, writes C# DAC/graph extensions)
4. PR created automatically
5. AI-managed pipeline deploys to sandbox → verifies → auto-merges → deploys to prod
6. Kevin gets a summary: "Enhancement X requested, implemented, deployed, verified"

**Existing pieces:**
- webhook-router portal already routes enhancement requests
- AcuDev already generates code and deploys to sandbox
- Pipeline already builds and deploys to prod
- The gap: connecting these into one continuous flow with AI orchestration

## Environment Reference

| Environment | URL | Purpose |
|---|---|---|
| SaaS Sandbox | heritagefabrics-sandbox.acumatica.com | Staging gate |
| SaaS Prod | heritagefabrics.acumatica.com | Production (HF=2, Test=3) |
| GCE VM | 136.115.233.148 | Deep debugging (Phase 4) |
| Qdrant | railway variables --service qdrant | Vector DB |
| AcuDev | railway variables --service acudev | AI agent service |

## Slack Channels (StudioB workspace)

| Channel | ID | Purpose |
|---|---|---|
| #ops | C0AR2UW2S66 | Deploy activity, alerts |
| #engineering | C0ARX7KM17S | AcuDev, enhancements |
| #clients | C0AQWHLJLGK | Business activity |
| Kevin DM | U0ALNRQ4KF0 | Failures and decisions only |
