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

## Phase 2 Completion (2026-04-06)

Phase 2 is **complete**. PRs merged: acumatica-ci-cd#227, acudev#13.

### What was delivered

**Unified verify.py** (`scripts/verify.py` in acumatica-ci-cd):
- Replaces `validate-publish.py` + `smoke-e2e.py` (both still exist in acuops-pipeline but workflow no longer calls them)
- 5 check types: login, entity reachability, custom field schema, E2E DAC probes, GI health
- Structured JSON output to stdout (for Phase 3 AI agent), human-readable to stderr
- HTTP classification single source of truth: 200/204=PASS, 401=FAIL, 403=WARN, 404=FAIL, 500+=FAIL with body snippet
- CLI: `python scripts/verify.py --manifest publish-manifest.json --environment production --json-output verify-result.json`
- 43 unit tests, zero external dependencies

**Knowledge base consolidation** (acudev repo):
- `acudev-knowledge` (126K points) migrated into `studiob-knowledge` with domain/client/source_type tags
- `acudev-knowledge` collection deleted
- `studiob-knowledge` now has 126,018 points (official docs + operational knowledge)
- AcuDev service queries `studiob-knowledge` exclusively
- SearchFilter extended with domain/client/source filters
- All ingestion pipelines tag new content with domain/client/source_type

**Auto-ingestion** (wired into GH Actions workflow):
- Deploy failures POST to `POST /ingest/incident` on AcuDev service
- Deploy successes POST to same endpoint (production only)
- Every incident feeds `studiob-knowledge` automatically
- GitHub secrets set: `ACUDEV_URL`, `ACUDEV_API_KEY`

**Supplemental collections** (unchanged, still separate):
- `acumatica-community` — forum threads
- `acumatica-stackoverflow` — SO Q&A

### Key files

| File | Repo | Purpose |
|------|------|---------|
| `scripts/verify.py` | acumatica-ci-cd | Unified post-publish verification |
| `tests/test_verify.py` | acumatica-ci-cd | 43 tests for verify.py |
| `.github/workflows/acuops-deploy.yml` | acumatica-ci-cd | Updated workflow (verify.py + auto-ingestion) |
| `src/ingest/qdrant-ingest.ts` | acudev | STUDIOB_COLLECTION, extended SearchFilter |
| `src/ingest/incident-ingestion.ts` | acudev | Deploy incident ingestion module |
| `src/ingest/migrate-collection.ts` | acudev | One-time migration script (already run) |

## Decisions Made (2026-04-06)

### Phase 3 agent invocation
GH Actions triggers a Claude Code remote trigger via API after build/qualify pass. No AcuDev Railway hop — the agent IS the orchestrator. Build/qualify stay as GH Actions jobs (fast, stateless, no AI needed).

```yaml
- name: Invoke deploy agent
  if: steps.qualify.outcome == 'success'
  run: |
    curl -X POST "https://api.claude.ai/v1/code/triggers/$TRIGGER_ID/run" \
      -H "Authorization: Bearer $CLAUDE_TRIGGER_TOKEN"
```

### verify.py — ready for Phase 3
`verify.py` produces structured JSON that the Phase 3 AI agent will parse. The agent calls it via Bash, reads the JSON output, and makes decisions. No exit-code gymnastics.

### studiob-knowledge — single brain
All agents query `studiob-knowledge`. Filter by `domain` (acumatica|pipeline|infrastructure|business), `client` (aesthetik|wasala|studiob), `source_type` (official|incident|runbook|policy|architecture). The KB grows automatically via auto-ingestion — every deploy failure and resolution becomes searchable context for the Phase 4 recovery agent.
