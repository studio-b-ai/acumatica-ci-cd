# AcuOps AI-Managed Pipeline — Design

**Date:** 2026-04-05
**Status:** Draft
**Author:** Kevin Bibelhausen + Claude
**Scope:** Issues #1-3 (validation false failures, broken rollback, branch protection) + AI-managed pipeline architecture

## Problem Statement

The current pipeline is script-based infrastructure that runs steps, checks exit codes, and posts results. It requires a human devops engineer to monitor channels, read logs, and debug failures. Kevin is a sole operator wearing 50 hats across multiple businesses — he doesn't have time to be that engineer. The pipeline needs to be self-operating.

### Tonight's Failures (2026-04-05)

1. `validate-publish.py` crashes on import (`ModuleNotFoundError`) → `outcome: failure` → triggers rollback on every successful deploy
2. PO 403 treated as deploy failure (Acumatica support ticket submitted — api-bot is admin but gets 403)
3. Auto-rollback uses corrupt backup zips → rollback fails → two unnecessary app pool restarts
4. `feat/command-center` branch ASPX got onto prod without being merged to main (TabView.master broke SB501000)
5. `workflow_dispatch` allows deploying any branch to production

### Root Causes

- Two validation scripts (`validate-publish.py`, `smoke-e2e.py`) with different pass/fail rules
- Auto-rollback triggers on script crashes, not just validation failures
- No branch protection on prod deploys via manual trigger
- Pipeline requires human monitoring and interpretation — no one is monitoring

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Enhancement Lifecycle                  │
│                                                          │
│  Request Portal ──→ AI Design ──→ AI Implement ──→ PR   │
│       (webhook-router)    (AcuDev KB)    (Claude Code)   │
│                                                          │
│                           │                              │
│                           ▼                              │
│                    AI-Managed Pipeline                    │
│                           │                              │
│              ┌────────────┼────────────┐                 │
│              ▼            ▼            ▼                 │
│           Build     Deploy/Verify    Recover             │
│         (scripts)   (AI agent)     (AI agent)            │
│                         │              │                 │
│              ┌──────────┤              │                 │
│              ▼          ▼              ▼                 │
│          SaaS        SaaS          GCE VM                │
│         Sandbox      Prod        (debug env)             │
│                                                          │
│  AcuDev KB ◄──── lessons learned from every failure      │
└─────────────────────────────────────────────────────────┘
```

### Pipeline Flow

```
Push to main (or merge PR)
    │
    ▼
┌─────────┐
│  Build   │  GitHub Actions job (script-based, no AI needed)
│          │  • Package customization zips
│          │  • Detect what changed (skip if CI-only files)
│          │  • Upload artifacts
└────┬─────┘
     │
     ▼
┌──────────┐
│ Qualify   │  GitHub Actions job (script-based)
│           │  • Static validation (project structure, XML well-formedness)
│           │  • Version checks
│           │  • Pre-flight sanity
└────┬──────┘
     │
     ▼
┌───────────────────────────────────────────────┐
│           AI Agent Takes Over                  │
│                                                │
│  1. Deploy to SaaS Sandbox                     │
│     • Import packages                          │
│     • Publish                                  │
│     • Run unified validation                   │
│     • If fail → diagnose, fix, retry           │
│                                                │
│  2. Deploy to SaaS Prod                        │
│     • Save backup snapshot (as artifact)       │
│     • Import + publish                         │
│     • Run unified validation                   │
│     • If fail → diagnose + recover (see below) │
│                                                │
│  3. Finalize                                   │
│     • Tag deploy                               │
│     • Update deploy history                    │
│     • DM Kevin: "Deployed. All checks pass."   │
└───────────────────────────────────────────────┘
```

### Failure Recovery Flow

```
Verification fails on prod
    │
    ▼
AI Agent analyzes failure
    • Parse error from validation output
    • Query AcuDev KB for matching patterns
    • Check git blame / recent commits for likely cause
    │
    ├── Known pattern found in KB
    │   (e.g., "TabView.master → needs FormDetail.master")
    │   │
    │   ▼
    │   Agent applies fix → opens PR → deploys to sandbox
    │   │
    │   ├── Sandbox passes → auto-merge → redeploy to prod
    │   └── Sandbox fails → iterate (max 3 attempts)
    │
    ├── Unknown failure, needs deeper investigation
    │   │
    │   ▼
    │   Spin up GCE VM (136.115.233.148)
    │   Deploy failing package to VM
    │   Use browser tools / API / SQL to reproduce
    │   Iterate on fix in VM
    │   │
    │   ├── Fix found → PR → sandbox → auto-merge → prod
    │   └── Can't resolve → escalate to Kevin with full diagnosis
    │
    └── Agent can't resolve after N attempts
        │
        ▼
        Slack DM to Kevin:
        "Deploy failed. I tried X, Y, Z. Here's what I found: [diagnosis].
         Prod is running the previously published version.
         No rollback was attempted. Manual action may be needed."
```

### Autonomy Rules

The AI agent can do the following **without Kevin's approval:**
- Build, package, deploy to sandbox
- Deploy to prod (from main only)
- Diagnose failures
- Spin up/shut down GCE VM
- Open PRs with fixes
- Auto-merge PRs if sandbox verification passes
- Retry deploys after fixes

The AI agent **must escalate to Kevin for:**
- Schema changes (new tables, column modifications)
- ISV-related changes (any package in the ALSO_PUBLISH list that isn't Studio B-owned)
- More than 3 failed fix attempts
- Changes it's not confident about
- Any change outside the AesthetikContainers or AesthetikWMS projects

### What the Agent Must Never Do

- Auto-rollback (no automatic re-publish of backup packages)
- Deploy non-main branches to production
- Send notifications to end users (no email, no user-facing Slack)
- Bypass the sandbox gate (every fix must pass sandbox before prod)
- Modify ISV packages (Pacejet, FusionWMS, KN)

## Component Design

### 1. Unified Validation Script

Replace `validate-publish.py` and `smoke-e2e.py` with a single `verify.py`.

**Inputs:**
- `publish-manifest.json` (what was deployed)
- Acumatica URL + credentials
- Environment name (sandbox/prod)

**Checks:**
1. Login smoke test (can we authenticate?)
2. Entity reachability (HTTP GET each declared entity endpoint)
3. Custom field existence (check `$adHocSchema` for declared fields)
4. Screen load test (hit each registered screen URL, check for 200)

**HTTP response handling (single source of truth):**
- 200/204 → PASS
- 401 → FAIL (auth broken)
- 403 → WARN (permission issue, not code bug — log but don't fail)
- 404 → FAIL (entity/field missing)
- 500+ → FAIL (server error, include response body in output)

**Output:** Structured JSON with pass/fail/warn per check, overall result, and human-readable summary. The AI agent parses this; no exit-code gymnastics.

### 2. Branch Protection

**Push triggers:** Only `main` and `staging` branches (already enforced).

**workflow_dispatch:**
```yaml
inputs:
  environment:
    type: choice
    options: [staging, production]
  force_deploy:
    description: 'Type OVERRIDE to bypass test gate'
    required: false
```

**Enforcement in workflow:**
```yaml
- name: Enforce branch protection
  if: inputs.environment == 'production' && github.ref != 'refs/heads/main'
  run: |
    echo "::error::Production deploys must use main branch"
    exit 1
```

### 3. Alert & Notification

**No auto-rollback.** On verification failure:
- Backup snapshot saved as workflow artifact (downloadable for manual restore via SM204505)
- AI agent begins diagnosis (see failure recovery flow)
- Kevin gets a Slack DM (not channel post) with:
  - What failed
  - What the agent is doing about it
  - Final resolution or escalation

**Slack configuration:**
- Direct message to Kevin's user ID, not a channel
- Use Slack Bot API (not webhook — webhooks can't DM)
- Include action buttons: "View PR", "View Logs", "Approve Fix"

### 4. Studio B Knowledge Base (Qdrant)

The knowledge base is the institutional brain for all Studio B operations. It replaces Claude memory files as the primary store for operational knowledge, incident lessons, deploy patterns, and business rules.

#### Collection Architecture

```
Qdrant Collections:
┌─────────────────────────────────────────┐
│  studiob-knowledge (primary)            │
│                                         │
│  Metadata tags:                         │
│  • domain: acumatica | pipeline |       │
│            infrastructure | business    │
│  • client: aesthetik | wasala | studiob │
│  • source: official | incident | policy │
│            | runbook | architecture     │
│  • version: 25.2 (where applicable)    │
│                                         │
│  Contains:                              │
│  • Acumatica official docs (PDFs, wiki) │
│  • Deploy incident reports & lessons    │
│  • Pipeline patterns & anti-patterns    │
│  • Business rules (hours, staff, SOPs)  │
│  • Infrastructure config & runbooks     │
│  • API quirks & workarounds             │
├─────────────────────────────────────────┤
│  acumatica-community (supplemental)     │
│  • Forum threads, quality-scored        │
│  • Searched when primary KB has low     │
│    confidence                           │
├─────────────────────────────────────────┤
│  acumatica-stackoverflow (supplemental) │
│  • SO Q&A, scored                       │
│  • Same fallback role as community      │
└─────────────────────────────────────────┘
```

#### Search Strategy

1. Query `studiob-knowledge` first, filtered by relevant domain + client
2. If confidence is low (top score < 0.7), broaden to community + SO
3. Rerank: official > incident > policy > community > SO

#### What Lives in the KB vs. Claude Memory Files

**In Qdrant (studiob-knowledge):**
- Operational knowledge: deploy patterns, API quirks, incident lessons
- Business rules: staff schedules, notification policies, SOP references
- Infrastructure: service URLs, environment configs, architecture decisions
- Acumatica domain: DAC patterns, graph extensions, customization API behavior
- Incident post-mortems: what broke, why, how it was fixed, prevention rules

**In Claude memory files (kept minimal):**
- User preferences: communication style, response verbosity
- Session context: what repo we're in, what we're working on
- Nothing operational — if an agent needs it to do its job, it goes in Qdrant

#### Memory Migration

The ~40 operational entries currently in CLAUDE.md memory files will be migrated to `studiob-knowledge` with proper domain/client/source tags. Examples:

| Memory Entry | Domain | Client | Source |
|---|---|---|---|
| "publishBegin is instance-wide" | pipeline | aesthetik | incident |
| "Never UPDATE FromUnit/ToUnit on INUnit" | acumatica | aesthetik | incident |
| "Weekend deploys are after-hours" | pipeline | aesthetik | policy |
| "App pool restart causes timeouts" | infrastructure | aesthetik | runbook |
| "api-bot has full screen access" | acumatica | aesthetik | architecture |

#### Auto-Ingestion

Every deployment failure and resolution is automatically ingested:
- Failure pattern (error message, screen, HTTP status)
- Root cause analysis
- Fix applied (with PR link)
- Prevention rule for future agents

The pipeline agent queries the KB before attempting any fix. Over time, the KB becomes the definitive source of "how things work here."

#### Embedding & Infrastructure

- **Embedding model:** Voyage AI `voyage-3` (1024 dimensions)
- **Chunking:** ~500 tokens with 50-token overlap, paragraph-boundary aware
- **Hosting:** Qdrant on Railway (existing)
- **Ingestion:** POST /knowledge/ingest (Railway-hosted, existing)
- **All agents share the same KB** — pipeline agent, AcuDev, request portal, dashboard

### 5. GCE VM Management

**Purpose:** Deep debugging when SaaS API/trace isn't enough.

**Lifecycle:**
- Agent starts VM via GCE API when needed
- Restores latest prod snapshot (data parity)
- Deploys failing package
- Debugs via browser tools, API, SQL
- Auto-shutoff after 2 hours idle or when agent is done

**Not part of the regular pipeline.** Only activated during failure recovery when the agent needs file system / IIS / SQL access that SaaS doesn't expose.

## Environments

| Environment | URL | Purpose | Pipeline Role |
|---|---|---|---|
| SaaS Sandbox | heritagefabrics-sandbox.acumatica.com | Pre-prod validation | Hard gate before prod |
| SaaS Prod | heritagefabrics.acumatica.com | Production (HF=2, Test=3) | Deploy target |
| GCE VM | 136.115.233.148 | Deep debugging | Failure recovery only |

## Migration Path

This is a big system. Build it incrementally:

### Phase 1: Pipeline hardening (this week)
- Unified `verify.py` replacing both validation scripts
- Branch protection on workflow_dispatch (main only for prod)
- Remove auto-rollback, replace with alert (Slack DM to Kevin)
- Test gate becomes hard gate with OVERRIDE escape
- SaaS sandbox as staging environment (configure secrets)

### Phase 2: Knowledge base consolidation
- Create `studiob-knowledge` collection in Qdrant
- Migrate ~40 operational memory entries with domain/client/source tags
- Update ingestion endpoint to support new tagging schema
- Set up auto-ingestion for deploy incidents
- Migrate `acudev-knowledge` official content into `studiob-knowledge`
- Slim down Claude memory files to user preferences only

### Phase 3: AI agent for deploy orchestration
- Claude Code / scheduled task manages the deploy lifecycle
- Agent calls deploy.py, verify.py as tools
- Agent queries studiob-knowledge for context before decisions
- Agent handles sandbox → prod promotion
- Structured output from verify.py feeds agent decisions

### Phase 4: AI agent for failure recovery
- Agent diagnoses failures using KB + logs
- GCE VM spin-up/teardown automation
- Agent iterates on fixes in VM
- Auto-PR + auto-merge on sandbox pass
- Auto-ingestion of incident + resolution into KB

### Phase 5: Full loop with request portal
- Portal enhancement requests trigger the full lifecycle
- AI designs, implements, deploys, verifies
- AcuDev draws from studiob-knowledge for all Acumatica work
- Kevin reviews summaries, not code (unless escalated)

## Open Questions

1. **PO 403:** api-bot is admin but gets 403 on PurchaseOrder. Acumatica support ticket submitted. Pipeline treats 403 as warning until resolved.
2. **SaaS sandbox secrets:** Need to configure sandbox credentials in GitHub Secrets for pipeline to deploy there. Current staging secrets are missing/broken.
3. **Slack Bot setup:** Need a Slack bot with DM permissions (current webhook can't DM). Which workspace — hfabrics.slack.com or studiob-ai.slack.com?
4. **Private cloud consideration:** Kevin is considering moving Acumatica to Railway-hosted private cloud for full CI/CD control. This design works regardless of hosting model — deploy target is just a URL. Private cloud decision is independent.
5. **Auto-merge rules:** What branch protection rules should apply? Required reviews? Status checks? Need to define before Phase 2.
6. **Request portal integration:** The webhook-router portal already feeds enhancement requests into the pipeline. Need to verify the routing is correct (per the 16-branch misrouting AAR).
