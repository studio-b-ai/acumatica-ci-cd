# Railway Consolidation Audit

## Background for the agent

You're working with Kevin Bibelhausen, Principal at Studio B AI. Studio B is a management consulting firm providing software and professional services to Acumatica VARs. Kevin's primary client is Ästhetik (parent of Heritage Fabrics), a mid-market textile distributor running Acumatica ERP.

Studio B's infrastructure runs on Railway in a single project called **aesthetik-production**. It has grown to 28 services organically over several months. Kevin suspects significant dead weight, redundancy, and wasted spend. He wants a clean, intentional infrastructure — every service should earn its place.

### Repo map (for context)

| Repo | Purpose |
|------|---------|
| `studio-b-ai/studiob` | Monorepo: Hono API server + MCP servers + clients (deployed as `studiob-api` on Railway) |
| `studio-b-ai/webhook-router` | Fastify event router + BullMQ workers + enhancement portal + intranet (deployed as `webhook-router` on Railway) |
| `studio-b-ai/acumatica-ci-cd` | CI/CD pipeline for Acumatica customization deploys (GitHub Actions, not on Railway) |
| `studio-b-ai/b-studio-website` | Static marketing site at b.studio (GitHub Pages, not Railway) |
| `studio-b-ai/business-dashboard` | Ops dashboard (deployed as `business-dashboard` on Railway, domain: dashboard.b.studio) |
| `studio-b-ai/support-agent` | AI customer support agent |
| `studio-b-ai/acudev` | AcuDev — AI developer agent for Acumatica customizations |
| `studio-b-ai/aesthetik-portal` | B2B customer self-service portal (domain: portal.asthetik.com) |
| `studio-b-ai/heritage-wms` | Warehouse management system (domain: wms.asthetik.com) |
| `studio-b-ai/skuba-apps` | Shopify connector product (paused, not abandoned) |
| `studio-b-ai/skuba-theme` | Shopify theme (part of Skuba product, paused) |
| `studio-b-ai/doc-generator` | AcuDocs Chrome extension guide generator (currently sleeping on Railway) |
| `studio-b-ai/note-intelligence` | AI note classification engine for Acumatica |
| `studio-b-ai/acuops` | AcuOps — ERP environment management product |
| `studio-b-ai/acusync` | AcuSync — integration pattern agent |
| `studio-b-ai/acuconfig` | AcuConfig — system configuration agent |
| `studio-b-ai/acureport` | AcuReport — reporting agent |

### Studio B product names

| Product | Service Name on Railway | What it does |
|---------|------------------------|--------------|
| AcuDev | acudev + enhancement-executor | AI agent that writes/deploys Acumatica customizations |
| AcuOps | (runs via acumatica-ci-cd GitHub Actions) | ERP environment management, CI/CD, health monitoring |
| AcuDocs | acudocs + doc-generator | Auto-generate training guides from screen captures |
| AcuSync | acusync | Integration pattern agent |
| AcuConfig | acuconfig | System configuration agent |
| AcuReport | acureport | Reporting agent |
| Skuba | skuba-apps + skuba-theme | Shopify connector (paused) |
| Luminary | marketing-engine | BD/marketing automation (Kevin just named this) |

## What to do

### 1. Check the 5 suspect services

Open Railway (https://railway.com), go to aesthetik-production project. For each service below, check: last deploy, deployment logs, metrics (CPU/memory over 30d), and whether any other service calls it.

**integration-tester**
- Repo: unknown — check Railway Settings > Source to find the GitHub repo
- Check logs for last 30 days. Is it running tests? Are results going anywhere?
- If it's just running and nobody looks at it, recommend killing it

**note-intelligence**
- Repo: `studio-b-ai/note-intelligence`
- AI note classification for Acumatica. Check if any downstream system reads its output (webhook-router? acudev?).
- If nothing consumes its output, it's burning compute for nothing

**compliance-engine**
- Kevin forgot what this does. Figure it out:
  - Check the source repo
  - Read the code to understand its purpose
  - Check if any other service references it (BullMQ queue names, API calls, Redis keys)
  - Recommend keep/kill with reasoning

**provisioning-agent**
- Repo: `studio-b-ai/provisioning-agent`
- Has a warning flag on Railway. Check health, check recent deploys, check if HR/IT provisioning is actually running
- The repo description says "DRY_RUN" — is it still in dry run mode?

**studiob-api**
- Repo: `studio-b-ai/studiob` (apps/server)
- This is a Hono REST API with MCP servers + external service clients (GitHub, Railway, Slack, LinkedIn, Acumatica, etc.)
- webhook-router is Fastify with BullMQ workers + portal + intranet + HubSpot sync
- Question: should these merge? Consider:
  - Deploy coupling (webhook-router deploys frequently, studiob-api is more stable)
  - Blast radius (webhook-router crash takes down portal + all workers)
  - Shared dependencies (both talk to Acumatica, Redis, Postgres)
  - Recommend: merge, keep separate, or refactor boundaries

### 2. Postgres volume audit

There are 5-7 Postgres volumes visible on Railway:
- postgres-volume-0KQj
- wms-postgres-volume
- postgres-volume-z6B0
- postgres-volume-uuVo
- postgres-qctq-volume
- postgres-eni-volume
- postgres-volume (at bottom of canvas)

For each, determine: which Postgres instance is it attached to? Which service uses that Postgres? Is the data still needed? Any that are orphaned (not attached to a running Postgres instance) can be flagged for deletion.

### 3. Rename marketing-engine → Luminary

Kevin chose "Luminary" as the product name. Rename the Railway service. Check if anything references "marketing-engine" by name (env vars, other services) and update those too.

### 4. Cost analysis

Go to Railway Usage (sidebar > Usage) or check per-service metrics. Calculate:
- Total monthly cost for aesthetik-production
- Top 5 most expensive services
- Services with near-zero CPU/traffic that could be sleeping or removed
- Estimated savings if suspect services are killed

### 5. Check aesthetik-staging project

It shows 3 services on the Railway dashboard. Is it being used? If not, consider shutting it down entirely.

## Reference files

- Memory: `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_railway_consolidation.md` — full service inventory with status
- Memory: `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_bstudio_site.md` — domain mapping for all Studio B sites
- Kevin's global instructions: `~/.claude/CLAUDE.md` — repo map, cloud storage, conventions

## Deliverable

Write a recommendation doc with:
1. Kill list (services to remove) with reasoning
2. Consolidation plan (services to merge) with migration steps
3. Rename list (services to rename)
4. Orphaned volume list
5. Estimated monthly savings
6. Any services that need attention but shouldn't be killed (e.g., sleeping doc-generator)

Save to `docs/plans/YYYY-MM-DD-railway-consolidation.md` in this repo.
