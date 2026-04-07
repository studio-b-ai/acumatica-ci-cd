# Investigate: Heritage Fabrics production restart at ~11:00 AM ET on 2026-04-07

## Mission

Identify what restarted the Heritage Fabrics production Acumatica instance
(`heritagefabrics.acumatica.com`) at approximately **11:00 AM ET on
Tuesday 2026-04-07** (15:00 UTC). Users reported the restart to Kevin.
Our CI/CD pipeline is NOT the cause — every acumatica-ci-cd workflow run
in the window 14:00–16:00 UTC had the Deploy job skipped, and sandbox-gate
publishes only to the separate sandbox instance
(`heritagefabrics-sandbox.acumatica.com`). We need to find the real cause
so we can either prevent it or tell users it was upstream maintenance.

## What has already been ruled out

1. **acumatica-ci-cd `AcuOps Deploy` workflow** — verified every run in
   the window (24087775904, 24087780932, 24087787231, 24088114876,
   24088128092) had `deploy` result = skipped. Sandbox-gate ran and in
   some cases published, but sandbox is a different Acumatica instance.
2. **Sandbox vs prod are different hosts** — confirmed via open Chrome
   tabs: sandbox = `heritagefabrics-sandbox.acumatica.com`, prod =
   `heritagefabrics.acumatica.com`. Separate IIS app pools. Sandbox
   publishes do not restart the prod pool.
3. **`studio-b-ai/webhook-router` and `studio-b-ai/studiob` workflows** —
   no GitHub Actions activity in the 14:00–16:00 UTC window.
4. **`sync-test-env.yml` scheduled workflow** — ran at 08:16 UTC (04:16
   ET), failed on missing `scripts/entity-sync.py` path, did not publish.
5. **`heritagefabrics.acumatica.com/Main?ScreenId=SM204505`** — Last
   Modified column for our three customization projects
   (AesthetikContainers, AesthetikWMS, StudioBAcuOps) shows 4/6/2026,
   description `Deployed via AcuOps at 2026-04-07T00:07:15Z` (and :16Z)
   by `api-bot`. That was Monday 8:07 PM ET — yesterday's after-hours
   merge train from PRs #243/#245/#246. No prod publish since.

## What to check

### 1. Acumatica audit log / publish history on production

Navigate to production Acumatica (already logged in as
`kevin@heritagefabrics.com` in tab `1858720148` if that session is still
alive; otherwise the user must re-auth — do not attempt to enter a
password) and check:

- **SM205510 Audit History** — filter to 2026-04-07 14:00–16:00 UTC and
  look for: customization publishes, user logins from new IPs, bulk
  operations, SM204505 POSTs, business events firing. Who triggered
  them?
- **SM204505 → Publish History** tab (if present) — shows every publish
  event on the instance. We need every publish between 2026-04-06 20:00
  ET and 2026-04-07 12:00 ET.
- **SM205020 Event History** — scheduled automation firings.
- **SM205030 Business Events** — any event subscriptions that trigger
  something heavy at ~11 ET.
- **SM205035 Schedules** — any schedule with a cron near 11 ET.

### 2. Railway-hosted services making API calls to prod

Check Railway projects for any service that calls prod Acumatica:

```bash
railway list
# For each project with an acumatica-prod-url:
railway variables --service <svc> --json | grep -i acumatica
railway logs --service <svc> --since 2h | grep -i "POST.*publish\|customization\|restart"
```

Services likely to be relevant:
- `aesthetik-production` project → `acudev` service (knowledge ingestion)
- `aesthetik-production` project → `webhook-router` service (Slack intake)
- Any `acuops` deploy agent service

### 3. Acumatica SaaS maintenance

- Check <https://status.acumatica.com/> (or whichever status page
  Acumatica hosts for SaaS) for any maintenance/incident around
  2026-04-07 15:00 UTC.
- Check email `kevin@heritagefabrics.com` for any
  `support@acumatica.com` or `saas@acumatica.com` notifications about
  maintenance in the last 24h.

### 4. Manual human publishes

- Ask the user (Kevin) whether Sarah Bibelhausen or any other admin
  performed a manual publish/unpublish via the Acumatica UI around
  11 AM ET. Sarah's `DropKNMCLogs` package appeared in the customization
  list earlier (Last Modified 3/30/2026) so she has publish access.

### 5. Other workflows and scripts in acumatica-ci-cd

Scan for anything else that could touch prod:

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman
ls .github/workflows/
grep -r "ACUMATICA_PROD_URL\|heritagefabrics.acumatica.com" .github/
grep -r "restart\|iisreset\|CustomizationPublish" scripts/ tests/ .github/ 2>/dev/null
```

Workflows to specifically audit:
- `.github/workflows/acuops-deploy.yml` — primary, already vetted
- `.github/workflows/sync-test-env.yml` — failed this morning, vet anyway
- `.github/workflows/configure-endpoint.yml` — might POST to SM208000
- `.github/workflows/create-business-events.yml` — might POST to
  SM302050; business events can trigger restarts if deployed
- `.github/workflows/deploy-hotfix.yml` — emergency path, could have
  been invoked
- `.github/workflows/test-countdown.yml` — only sends notifications, but
  verify
- `.github/workflows/test-rollback.yml` — rollback hits prod
- `.github/workflows/update-audit-fixtures.yml`

For each, check if it ran in the window:
```bash
gh run list --workflow <name> --limit 20 --json createdAt,conclusion
```

### 6. Knowledge base context

Search the Qdrant `studiob-knowledge` collection for:
- `production restart source`
- `publish triggered restart`
- `SM204505 publish audit`
- `heritage fabrics app pool recycle`

Query via the pattern in `~/.claude/CLAUDE.md` rule 9 — grab
`QDRANT_URL` and `VOYAGE_API_KEY` from the `acudev` Railway service
inside the `aesthetik-production` project.

Also search session history for prior instances of "prod restart" or
"app pool recycle":
```
/recall graph last week
/recall prod restart
```

## Deliverable

A short report posted as a comment on the handoff issue (or printed to
stdout if running solo) with:

1. **Root cause**: what actually restarted production at 11 AM ET.
2. **Evidence**: screenshots, log snippets, workflow run IDs, audit
   entries, Railway log lines, etc. Use absolute paths / links.
3. **Recommendation**: one of
   - Add a GHA guard (if it was a workflow we own)
   - Disable/move a scheduled job (if it was automation inside
     Acumatica)
   - Accept as external (if it was Acumatica SaaS maintenance)
   - Add a new KB entry in `studiob-knowledge` describing the pattern
4. **Prevention**: what code/config change prevents recurrence.

## Hard constraints

- **Never publish, unpublish, or modify any Acumatica customization
  project** during this investigation. Read-only queries only.
- **Never enter a password into Acumatica.** If the session is dead,
  stop and tell the user.
- **Never touch the webhook-router or AcuDev Railway environment
  variables.** Log reads only.
- **Follow `~/.claude/CLAUDE.md` rules 9–11** — search `studiob-knowledge`
  and `/recall` BEFORE reading code or debugging manually.
- All file references in the report must be absolute paths.

## Context dump

- Date: 2026-04-07 (Tuesday)
- Timezone: America/New_York (Heritage Fabrics operating hours are
  6 AM – 6 PM ET Mon–Fri)
- Acumatica version: 24.208.0020
- Acumatica prod host: `heritagefabrics.acumatica.com`
- Acumatica sandbox host: `heritagefabrics-sandbox.acumatica.com`
  (separate SaaS instance, not a tenant)
- Prod tenant: `Heritage Fabrics`
- Test tenant (prod instance): `Heritage Test` — publishing to this
  tenant DOES restart the prod app pool
- Sandbox tenant (sandbox instance): `Heritage Fabrics` (confirmed in
  Chrome tab URL)
- Current customizations on prod: `AesthetikWMS`, `AesthetikContainers`,
  `StudioBAcuOps`, `Ramp`, `AcumaticaPacejetCustomFields24.1001`,
  `DropKNMCLogs`, and a few ISVs
- api-bot is the service account used by the pipeline
- Kevin is the escalation point and cannot be continuously monitoring
  Slack — any finding must be reported with a clear summary and
  recommended action (per rule 8 in `~/.claude/CLAUDE.md`)
- A hard after-hours gate has been added in PR #257 on
  `fix/after-hours-gate` — merge after 6 PM ET today to guarantee our
  own pipeline cannot publish to prod during business hours
- The memory file at
  `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_acumatica_environments.md`
  documents the instance/tenant topology

## Absolute paths you will need

- This prompt: `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/prompts/2026-04-07-prod-restart-investigation.md`
- Repo root: `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman`
- Workflow file: `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/.github/workflows/acuops-deploy.yml`
- `acuops.yaml`: `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/acuops.yaml`
- Memory dir: `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/`
- Global rules: `/Users/kevin/.claude/CLAUDE.md`
- Studiob monorepo (for Railway CLI linking): `/Users/kevin/dev/studiob`
- Webhook-router repo: `/Users/kevin/dev/webhook-router`
- AcuOps pipeline shared package: `/Users/kevin/dev/acuops-pipeline`
