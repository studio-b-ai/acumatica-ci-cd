# Agentic Pipeline — Next Stage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate the only HIGH-severity production landmine remaining (webhook-router STG_* trap), close out PR #257's mess, retire the personal PAT from CI checkouts, and re-enable the AI Failure Recovery agent CORRECTLY with a full safety package.

**Architecture:** Four parallel tracks with explicit milestone gates. Track 0 runs immediately and doubles as the first dogfood test of vm-agent.yml. Track 1 splits PR #257 into clean PRs and merges after the after-hours window. Track 2 hardens the agentic layer culminating in invoke-agent re-enable + failure dry-run. Track 3 captures the Studio B platform vision in design docs only — no code lands until Track 2 milestone 2.4 succeeds.

**Tech Stack:** GitHub Actions (workflow_dispatch + repository_dispatch), claude-code-action@v1, gh CLI, Railway CLI, Acumatica REST API, Voyage AI + Qdrant for KB, Anthropic API (Studio B workspace, $200/mo cap), self-hosted Windows runner on GCE VM with Acumatica install.

**Design doc:** `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/docs/plans/2026-04-07-agentic-pipeline-next-stage-design.md`

**Hard rules from `~/.claude/CLAUDE.md`:**
- Rule 9: operational knowledge lives in studiob-knowledge Qdrant
- Rule 10: search KB + recall BEFORE debugging
- Rule 11: every Acumatica deploy restarts the prod app pool — get it right before deploying
- Verify before claiming success (`@superpowers:verification-before-completion`)

---

## Track 0 — webhook-router STG_* trap elimination (IMMEDIATE)

**Why immediate:** the only HIGH-severity item remaining after PR #258. Same trap pattern as today's outage on a different label. Doubles as the first real `vm-agent.yml` dispatch test.

### Task 0.1: Dispatch the first `vm-agent.yml` run with the STG_* investigation prompt

**Files:**
- Read: `/Users/kevin/dev/acumatica-ci-cd/docs/prompts/2026-04-08-prod-restart-followups.md` (P1 section is the prompt content)
- Reference: `/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman/.github/workflows/vm-agent.yml` (already on main from PR #259)

**Step 1: Confirm runner is online + idle**

```bash
gh api repos/studio-b-ai/acumatica-ci-cd/actions/runners --jq '.runners[] | "\(.name)  status=\(.status)  busy=\(.busy)  labels=\(.labels | map(.name) | join(","))"'
```

Expected: `acumatica-test  status=online  busy=false  labels=self-hosted,Windows,X64,acumatica-sdk`

If offline, RDP into VM and check: `Get-Service actions.runner.* | Format-List Name,Status`

**Step 2: Dispatch the workflow**

```bash
gh workflow run vm-agent.yml \
  -f prompt_file=docs/prompts/2026-04-08-prod-restart-followups.md \
  -f task_name=webhook-router-stg-investigation \
  -f timeout_minutes=45
```

Expected: `✓ Created workflow_dispatch event for vm-agent.yml at main`

**Step 3: Watch the run**

```bash
sleep 5
gh run list --workflow vm-agent.yml --limit 1 --json databaseId,status,conclusion
RUN_ID=$(gh run list --workflow vm-agent.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch $RUN_ID
```

Expected: queued → in_progress → completed (success). Wall time 5–30 min depending on agent depth.

**Step 4: Read the agent's output**

```bash
gh run view $RUN_ID --log | grep -A 200 "Run agent via claude-code-action" | head -250
```

Look for: list of `ACUMATICA_STG_*` consumers, characterized as GET (read-only) or POST/PUT/DELETE (write), with file paths and line numbers.

**Step 5: Save the findings to memory**

If the agent posted to Slack #ops, screenshot or copy the message. Save to `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/incident_2026_04_07_webhook_router_stg_findings.md` (temporary scratch, will be promoted to KB later).

**Step 6: Commit** (no code change in this task — verification-only)

Skip commit. Artifact is the run output and the findings note.

---

### Task 0.2: Decide remediation path with Kevin

**Step 1: Present findings to Kevin in the chat**

Format:

```
## Track 0.1 results

ACUMATICA_STG_* consumers found:
  1. <repo>:<file>:<line> — <GET|POST|PUT|DELETE> — <description>
  2. ...

All-read-only? <yes|no>
Write call sites that would cause prod app pool restart? <count>

Recommended remediation:
  (a) Redirect STG_* to actual sandbox — best if writes exist or might be added
  (b) Rename to ACUMATICA_PROD_TEST_* — best if writes exist and the test
      tenant on prod is the intentional target
  (c) Remove entirely — best if no consumers found

My recommendation: <a|b|c>, because <reason>
```

**Step 2: Get Kevin's decision (a/b/c)**

Wait for explicit answer. Do not proceed without it.

**Step 3: Commit** (no code change — decision-only)

Skip commit.

---

### Task 0.3: Execute the chosen remediation

**Files (depend on choice):**
- (a) `railway variables --service webhook-router` updates + possibly `/Users/kevin/dev/acumatica-ci-cd/scripts/secrets-map.env`
- (b) Code changes in `/Users/kevin/dev/webhook-router/src/**` to rename consumer references + Railway env var renames
- (c) `railway variables --service webhook-router --remove ACUMATICA_STG_*` + delete consumer code

**Step 1: For (a) — redirect STG_* to actual sandbox**

```bash
cd ~/dev/studiob && railway link -p studiob-platform
SANDBOX_URL="https://heritagefabrics-sandbox.acumatica.com"
SANDBOX_TENANT="Heritage Fabrics"
SANDBOX_USER="api-test"
SANDBOX_PASS=$(op item get "acumatica-api-test" --vault "Studio B Infrastructure" --fields password --reveal)

railway variables --service webhook-router --set "ACUMATICA_STG_URL=$SANDBOX_URL"
railway variables --service webhook-router --set "ACUMATICA_STG_COMPANY=$SANDBOX_TENANT"
railway variables --service webhook-router --set "ACUMATICA_STG_USER=$SANDBOX_USER"
railway variables --service webhook-router --set "ACUMATICA_STG_PASSWORD=$SANDBOX_PASS"
```

Expected: 4 ✔ confirmations from Railway CLI.

**Step 2: For (b) — rename env vars in code + Railway**

```bash
cd ~/dev/webhook-router
grep -rn "ACUMATICA_STG_" src/ --include="*.py" --include="*.ts" --include="*.js"
```

For each match, edit the file to use `ACUMATICA_PROD_TEST_*`. Then update Railway:

```bash
cd ~/dev/studiob && railway link -p studiob-platform
for var in URL COMPANY USER PASSWORD; do
  OLD=$(railway variables --service webhook-router --json | python3 -c "import sys,json; print(json.load(sys.stdin).get('ACUMATICA_STG_$var',''))")
  if [ -n "$OLD" ]; then
    railway variables --service webhook-router --set "ACUMATICA_PROD_TEST_$var=$OLD"
    railway variables --service webhook-router --remove "ACUMATICA_STG_$var"
  fi
done
```

**Step 3: For (c) — remove entirely**

```bash
cd ~/dev/studiob && railway link -p studiob-platform
railway variables --service webhook-router --remove ACUMATICA_STG_URL
railway variables --service webhook-router --remove ACUMATICA_STG_COMPANY
railway variables --service webhook-router --remove ACUMATICA_STG_USER
railway variables --service webhook-router --remove ACUMATICA_STG_PASSWORD
```

Then delete consumer code in webhook-router (paths from Task 0.1 findings).

**Step 4: Wait for webhook-router redeploy**

```bash
railway logs --service webhook-router --since 5m | tail -50
```

Expected: clean restart, no Acumatica connection errors.

**Step 5: Verify webhook-router functionality**

If Track 0.1 found any read-only OData consumers, exercise one:

```bash
# Identify the trigger from findings (e.g., a Slack command or API endpoint)
# Example: trigger a Slack command that does an Acumatica OData GET
# Then watch logs:
railway logs --service webhook-router --since 2m | grep -i acumatica
```

Expected: HTTP 200 from Acumatica, no errors.

**Step 6: Commit** (if path b — code changes were made)

```bash
cd ~/dev/webhook-router
git checkout -b fix/rename-acumatica-stg-to-prod-test
git add src/
git commit -m "$(cat <<'EOF'
fix: rename ACUMATICA_STG_* to ACUMATICA_PROD_TEST_* — stop the trap

ACUMATICA_STG_URL pointed at heritagefabrics.acumatica.com (prod
instance) and ACUMATICA_STG_COMPANY was Heritage Test (a tenant on
prod). The STG label suggested separation but the values were
production. Same trap pattern as the 2026-04-07 outage on
acumatica-ci-cd.

Renaming to ACUMATICA_PROD_TEST_* makes the values honest. The host
and tenant did not change — webhook-router still talks to the test
tenant on prod, but the env var name no longer lies about it.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin fix/rename-acumatica-stg-to-prod-test
gh pr create --title "fix: rename ACUMATICA_STG_* to ACUMATICA_PROD_TEST_*" --body "..."
```

For (a) and (c) — Railway env var change only, no code commit needed.

---

### Task 0.4: Mirror the host-assertion guard into webhook-router

**Files:**
- Modify: `/Users/kevin/dev/webhook-router/src/<acumatica-client-module>` (path TBD from 0.1 findings)
- Test: `/Users/kevin/dev/webhook-router/tests/<acumatica-client-test>`

**Step 1: Find the central Acumatica client module**

```bash
cd ~/dev/webhook-router
grep -rn "def.*acumatica\|class.*Acumatica" src/ --include="*.py" | head -10
```

Identify the file that wraps Acumatica login/HTTP. Let's call it `<file>`.

**Step 2: Write a failing test for the host assertion**

```python
# tests/test_acumatica_client_host_assertion.py
import pytest
from src.<module> import AcumaticaClient

def test_rejects_prod_host_when_named_sandbox():
    """A client labeled 'sandbox' must refuse to talk to the prod host."""
    with pytest.raises(ValueError, match="prod host with sandbox label"):
        AcumaticaClient(
            label="sandbox",
            url="https://heritagefabrics.acumatica.com",  # prod host
            tenant="Heritage Fabrics",
            username="api-bot",
            password="x",
        )

def test_rejects_heritage_test_tenant_when_named_sandbox():
    """A client labeled 'sandbox' must refuse to use the Heritage Test tenant."""
    with pytest.raises(ValueError, match="Heritage Test tenant"):
        AcumaticaClient(
            label="sandbox",
            url="https://heritagefabrics-sandbox.acumatica.com",
            tenant="Heritage Test",
            username="api-test",
            password="x",
        )

def test_accepts_correct_sandbox_config():
    """The correct sandbox config must work."""
    client = AcumaticaClient(
        label="sandbox",
        url="https://heritagefabrics-sandbox.acumatica.com",
        tenant="Heritage Fabrics",
        username="api-test",
        password="x",
    )
    assert client is not None
```

**Step 3: Run test to verify it fails**

```bash
cd ~/dev/webhook-router
python -m pytest tests/test_acumatica_client_host_assertion.py -v
```

Expected: 3 FAIL (because the assertion doesn't exist yet)

**Step 4: Add the assertion to AcumaticaClient.__init__**

```python
def __init__(self, label: str, url: str, tenant: str, username: str, password: str):
    # Sandbox/STG naming trap guard — see incident 2026-04-07
    if label.lower() in ("sandbox", "stg", "test"):
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        if host == "heritagefabrics.acumatica.com":
            raise ValueError(
                f"prod host with sandbox label: client labeled '{label}' "
                f"cannot point at {host}. Use heritagefabrics-sandbox.acumatica.com."
            )
        if tenant == "Heritage Test":
            raise ValueError(
                f"Heritage Test tenant with sandbox label: client labeled "
                f"'{label}' cannot use 'Heritage Test' (which lives on prod). "
                f"Use 'Heritage Fabrics' on the sandbox host."
            )
    self.url = url
    self.tenant = tenant
    self.username = username
    self.password = password
    self.label = label
```

**Step 5: Run test to verify it passes**

```bash
python -m pytest tests/test_acumatica_client_host_assertion.py -v
```

Expected: 3 PASS

**Step 6: Run full webhook-router test suite to make sure nothing else broke**

```bash
python -m pytest -x --timeout=60
```

Expected: all green

**Step 7: Commit**

```bash
git add tests/test_acumatica_client_host_assertion.py src/<module>
git commit -m "$(cat <<'EOF'
feat: host assertion guard for AcumaticaClient — close incident 2026-04-07 trap

Mirrors the sandbox-gate host-assertion guard from acumatica-ci-cd
PR #258 into webhook-router. Any AcumaticaClient labeled 'sandbox',
'stg', or 'test' that points at heritagefabrics.acumatica.com OR uses
the Heritage Test tenant now fails fast at construction with a clear
error.

This closes the same trap class on a second surface. The 2026-04-07
incident was caused by ACUMATICA_SANDBOX_* secrets pointing at the
prod instance with the Heritage Test tenant on acumatica-ci-cd.
webhook-router has a parallel ACUMATICA_STG_* / ACUMATICA_PROD_TEST_*
codepath that needs the same guard.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git push
gh pr create --title "feat: host assertion guard for AcumaticaClient" --body "..."
```

---

### Task 0.5: Update studiob-knowledge KB with broadened guidance

**Step 1: Build the knowledge entry**

```python
# Local script — does not need to be committed
import requests, json, os

QDRANT_URL = os.environ["QDRANT_URL"]
VOYAGE_API_KEY = os.environ["VOYAGE_API_KEY"]

text = """
# Sandbox/STG naming trap — host assertion pattern for any pipeline secret

Any pipeline secret or env var named *_SANDBOX_*, *_STG_*, or *_TEST_*
whose URL host contains heritagefabrics.acumatica.com (without -sandbox)
is misconfigured and will cause a prod outage when consumed by code
that publishes Acumatica customizations or makes write calls.

The Heritage Test tenant lives on the prod instance and shares the
prod IIS app pool. Publishing to Heritage Test recycles prod for all
real users.

Mitigation pattern:
1. At every entry point that accepts a sandbox/stg/test-labeled config,
   validate the host with a hard assertion. Reject prod host or
   Heritage Test tenant immediately with a clear error.
2. Implementations:
   - acumatica-ci-cd: sandbox-gate workflow step (PR #258, b9e242d)
   - webhook-router: AcumaticaClient.__init__ (Track 0.4)
   - any new code path that talks to Acumatica must replicate this guard

Reference incidents:
- 2026-04-07 production restart loop (8 dispatches in 14h via misconfigured
  ACUMATICA_SANDBOX_* secrets + invoke-agent dispatch loop). Root cause:
  one-shot gh secret set on 2026-04-06 with copy-paste error.
"""

# Embed
resp = requests.post(
    "https://api.voyageai.com/v1/embeddings",
    headers={"Authorization": f"Bearer {VOYAGE_API_KEY}", "Content-Type": "application/json"},
    json={"input": [text], "model": "voyage-3", "input_type": "document"}
)
vector = resp.json()["data"][0]["embedding"]

# Upsert
import uuid
point_id = str(uuid.uuid4())
upsert = requests.put(
    f"{QDRANT_URL}/collections/studiob-knowledge/points",
    json={
        "points": [{
            "id": point_id,
            "vector": vector,
            "payload": {
                "title": "Sandbox/STG naming trap — host assertion pattern",
                "text": text,
                "domain": "infrastructure",
                "client": "studiob",
                "source": "runbook",
                "date": "2026-04-07",
                "related_incident": "2026-04-07 prod restart dispatch loop",
            }
        }]
    }
)
print(upsert.status_code, upsert.text[:200])
```

**Step 2: Run + verify ingestion**

```bash
export QDRANT_URL=$(cd ~/dev/studiob && railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['QDRANT_URL'])")
export VOYAGE_API_KEY=$(cd ~/dev/studiob && railway variables --service acudev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['VOYAGE_API_KEY'])")
python3 /tmp/ingest_kb.py
```

Expected: HTTP 200 from Qdrant.

**Step 3: Verify search returns the entry**

```bash
python3 -c "
import requests, json, os
resp = requests.post('https://api.voyageai.com/v1/embeddings',
    headers={'Authorization': f'Bearer {os.environ[\"VOYAGE_API_KEY\"]}', 'Content-Type': 'application/json'},
    json={'input': ['sandbox naming trap host assertion'], 'model': 'voyage-3', 'input_type': 'query'})
v = resp.json()['data'][0]['embedding']
r = requests.post(f'{os.environ[\"QDRANT_URL\"]}/collections/studiob-knowledge/points/search',
    json={'vector': v, 'limit': 3, 'with_payload': True})
for h in r.json()['result']:
    print(h['score'], h['payload'].get('title'))
"
```

Expected: top hit is "Sandbox/STG naming trap — host assertion pattern" with score > 0.7.

**Step 4: Update the memory file**

Edit `/Users/kevin/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/reference_acumatica_environments.md` — add a paragraph under "Sandbox naming trap" that mentions:
- The pattern is now mirrored into webhook-router (Track 0.4)
- Any new code path that talks to Acumatica must replicate the guard

**Step 5: Commit memory file** (memory files are git-tracked separately, in `~/.claude/`)

This is a memory file update, not a repo file. No git commit needed unless your `.claude/` is in version control.

**Step 6: Mark Track 0 complete**

In TodoWrite, mark Track 0 tasks 0.1–0.5 as completed.

---

## Track 1 — PR #257 cleanup + after-hours merge (today)

**Goal:** Split PR #257's 4 unrelated commits into 3 clean PRs, close PR #257, merge after 6pm ET tonight, verify SB501000 on prod.

### Task 1.1: Cherry-pick the after-hours gate onto a clean branch

**Files:**
- Source commit: `c3e3fb7` on `fix/after-hours-gate` branch
- New branch: `fix/after-hours-gate-clean` off `origin/main`

**Step 1: Confirm we're in the worktree**

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman
git status -sb
```

**Step 2: Fetch latest main**

```bash
git fetch origin main
```

**Step 3: Create clean branch off main**

```bash
git checkout -b fix/after-hours-gate-clean origin/main
```

**Step 4: Cherry-pick c3e3fb7**

```bash
git cherry-pick c3e3fb7
```

Expected: clean cherry-pick, no conflicts. If conflicts, abort with `git cherry-pick --abort` and STOP — investigate before retrying.

**Step 5: Verify only one commit on top of main**

```bash
git log --oneline origin/main..HEAD
```

Expected: 1 line — the after-hours gate commit.

**Step 6: Push and open PR**

```bash
git push -u origin fix/after-hours-gate-clean
gh pr create --title "fix: hard-gate prod/staging deploys during business hours" --body "$(cat <<'EOF'
## Summary

Adds a hard gate that blocks prod/staging deploys during business hours (Mon–Fri 6am–6pm ET) unless force_business_hours=true. Sandbox-gate is unaffected because sandbox publishes to a separate instance.

## Why

Publishing to the production Acumatica instance restarts the IIS app pool and disconnects every live Heritage Fabrics user. The pipeline previously had only a notification suppression check, not a hard gate.

## Why this PR (vs PR #257)

PR #257 became messy with 4 unrelated commits (after-hours gate + 3 VM bootstrap commits) and now conflicts with main after PR #258 + #259 merged. This PR is a clean cherry-pick of just commit c3e3fb7 on top of fresh main. The other 3 commits get their own PRs (1.2, 1.3 in this stage).

## Test plan

- [ ] Merge after 6pm ET tonight
- [ ] Verify the next business-hours push hits the gate and fails fast
- [ ] Verify a 6:01pm push deploys normally

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 7: Commit** (already done by cherry-pick — Step 6 just pushes)

---

### Task 1.2: Cherry-pick VM bootstrap commits onto a clean branch

**Files:**
- Source commits: `2fd8bb2` (runner service install fix), `c8427a0` (Node + Claude Code install)
- New branch: `feat/vm-bootstrap-windows` off `origin/main`

**Step 1: Create branch**

```bash
git checkout -b feat/vm-bootstrap-windows origin/main
```

**Step 2: Cherry-pick both commits**

```bash
git cherry-pick 2fd8bb2 c8427a0
```

Expected: clean cherry-pick. If conflicts, abort and investigate.

**Step 3: Verify**

```bash
git log --oneline origin/main..HEAD
```

Expected: 2 lines.

**Step 4: Push and open PR**

```bash
git push -u origin feat/vm-bootstrap-windows
gh pr create --title "feat: VM bootstrap script — runner service + Node.js + Claude Code" --body "..."
```

**Step 5: Commit** (done)

---

### Task 1.3: Cherry-pick build-validate (excluding vm-agent.yml) onto a clean branch

**Files:**
- Source commit: `fb4b1a1` (contains both build-validate AND vm-agent.yml)
- vm-agent.yml is already on main from PR #259 — must EXCLUDE it
- New branch: `feat/build-validate-windows` off `origin/main`

**Step 1: Create branch**

```bash
git checkout -b feat/build-validate-windows origin/main
```

**Step 2: Apply only the non-conflicting parts of fb4b1a1**

The cleanest way: cherry-pick `-n` (no commit) so we can edit before committing, then `git restore --staged --worktree` the vm-agent.yml file:

```bash
git cherry-pick -n fb4b1a1
git restore --staged --worktree .github/workflows/vm-agent.yml docs/prompts/2026-04-07-prod-restart-investigation.md
git status
```

Expected: only `.github/workflows/acuops-deploy.yml` should be modified (the build-validate job addition).

**Step 3: Verify the diff is just build-validate**

```bash
git diff --cached --stat
git diff --cached .github/workflows/acuops-deploy.yml | head -100
```

Expected: ~100 lines added in acuops-deploy.yml around build-validate, qualify needs update, sandbox-gate needs update, deploy needs update.

**Step 4: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat: build-validate job on self-hosted Windows runner (Acuminator gating)

Adds a new build-validate job between build and qualify that runs on
the acumatica-test self-hosted Windows runner. It runs dotnet build on
the customization C# projects, which fires Acuminator (PX1000-series
Roslyn analyzers) — Windows-only because the analyzer uses named
memory maps.

Linux build (existing build job) skips Acuminator entirely. This job
catches DAC/BQL bugs before sandbox-gate publishes anything.

Errors-only gate: compile errors and Acuminator errors fail the job.
Warnings surface in step summary but do not block.

Downstream gates qualify, sandbox-gate, and deploy all now require
build-validate.result in (success, skipped).

SDK DLLs come from the local Acumatica install at C:\Program Files\
Acumatica ERP\Bin (guaranteed to match runtime publish target, no GCS
round-trip).

Build log uploaded as artifact (retention 14 days).

Cherry-picked from PR #257's fb4b1a1, excluding vm-agent.yml which
already landed in main via PR #259.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

**Step 5: Push and open PR**

```bash
git push -u origin feat/build-validate-windows
gh pr create --title "feat: build-validate job on self-hosted Windows runner" --body "..."
```

**Step 6: Commit** (done in step 4)

---

### Task 1.4: Close PR #257

**Step 1: Comment on PR #257 explaining the split**

```bash
gh pr comment 257 --body "$(cat <<'EOF'
Closing in favor of clean split:

- After-hours gate → PR #260 (or whichever number `fix/after-hours-gate-clean` got)
- VM bootstrap → PR #261 (or whichever number `feat/vm-bootstrap-windows` got)
- Build-validate → PR #262 (or whichever number `feat/build-validate-windows` got)

This branch became messy with 4 unrelated commits and conflicts with main after PR #258 + #259 merged. Splitting into clean focused PRs per the followups prompt at \`docs/prompts/2026-04-08-prod-restart-followups.md\`.
EOF
)"
```

**Step 2: Close the PR**

```bash
gh pr close 257
```

**Step 3: Delete the local + remote branch**

```bash
git push origin --delete fix/after-hours-gate
# Don't delete the local branch in the worktree — ExitWorktree will handle it
```

**Step 4: Verify closed**

```bash
gh pr view 257 --json state
```

Expected: `{"state":"CLOSED"}`

**Step 5: Commit** (no commit — git operation only)

---

### Task 1.5: Merge the 3 new PRs after 6pm ET tonight

**Wait until 6pm ET (18:00 America/New_York).** Do NOT proceed before this time. Verify with `TZ=America/New_York date`.

**Step 1: Merge PR for `fix/after-hours-gate-clean` first**

```bash
gh pr merge <number> --squash --delete-branch
```

Expected: merged. Watch the AcuOps Deploy run that fires:

```bash
gh run watch
```

Expected: build → build-validate (skipped, this PR doesn't add it) → qualify → sandbox-gate → deploy → SUCCESS (because we're past 6pm ET so the new gate allows it).

**Step 2: Merge PR for `feat/vm-bootstrap-windows`**

```bash
gh pr merge <number> --squash --delete-branch
gh run watch
```

Expected: pipeline passes. No customization changes, so deploy may skip.

**Step 3: Merge PR for `feat/build-validate-windows`**

```bash
gh pr merge <number> --squash --delete-branch
gh run watch
```

Expected: build → **build-validate runs on self-hosted runner** (this is the first time!) → qualify → sandbox-gate → deploy → SUCCESS.

If build-validate fails because the self-hosted runner is offline, RDP into VM and run:

```powershell
Get-Service actions.runner.* | Format-List Name,Status
Start-Service actions.runner.studio-b-ai-acumatica-ci-cd.acumatica-test
```

Then re-run the workflow: `gh run rerun <run_id>`.

**Step 4: Verify all 3 merges landed**

```bash
git fetch origin main
git log --oneline origin/main | head -5
```

Expected: 3 new squash-merge commits from the 3 PRs.

**Step 5: Commit** (no commit — merges only)

---

### Task 1.6: Verify SB501000 on production

**Step 1: Open the production browser tab**

Use Chrome MCP to navigate to:

```
https://heritagefabrics.acumatica.com/Main?ScreenId=SB501000
```

**Step 2: Wait for the screen to load**

```
mcp__Claude_in_Chrome__computer wait 5s
mcp__Claude_in_Chrome__find query "Procurement Command Center title or column headers"
```

Expected: screen loads, columns visible (TransportMode, LandedCostRefNbr, LandedCostStatus from PR #252).

**Step 3: If screen is broken, diagnose**

```bash
# Check the latest deploy run
gh run list --workflow "AcuOps Deploy" --limit 5
gh run view <latest_id> --log | tail -100
```

If deploy was skipped, force a re-deploy via workflow_dispatch with `force_qualify=true`.

**Step 4: Post success to Slack**

```python
# Use the Slack MCP to send a message to #ops
```

Message: `✅ SB501000 (Procurement Command Center) live on production. Original Monday issue resolved end-to-end via PR #252 (EnsureColumn) → PR <build-validate> deploy <after-hours-gate>`

**Step 5: Commit** (no commit — verification only)

**Step 6: Mark Track 1 complete**

In TodoWrite, mark all Track 1 tasks completed.

---

## Track 2 — Agentic hardening (this week)

**Goal:** Retire GH_PAT_DISPATCH from `actions/checkout`, build the daily-dispatch cap, re-enable invoke-agent CORRECTLY with the full Safety Package, run the failure dry-run, ship one Mode-3 sentinel, set up VM autostop.

### Task 2.1: Generate deploy keys + retire GH_PAT_DISPATCH from cross-repo checkout

**Files:**
- New: SSH keypair (local generation, do NOT commit private key)
- Modify: `.github/workflows/acuops-deploy.yml` (6 `actions/checkout` references)
- New GH secret: `ACUOPS_PIPELINE_DEPLOY_KEY`
- New deploy key on `studio-b-ai/acuops-pipeline`

**Step 1: Generate the SSH keypair**

```bash
TMPDIR=$(mktemp -d)
ssh-keygen -t ed25519 -C "acuops-pipeline-deploy-2026-04-07" -f "$TMPDIR/key" -N ""
ls -la "$TMPDIR"
```

Expected: `key` (private) and `key.pub` (public) in temp dir.

**Step 2: Add public key as deploy key on acuops-pipeline (read-only)**

```bash
PUB=$(cat "$TMPDIR/key.pub")
gh api repos/studio-b-ai/acuops-pipeline/keys \
  -f title="acumatica-ci-cd checkout (2026-04-07)" \
  -f key="$PUB" \
  -f read_only=true
```

Expected: HTTP 201 with key id.

**Step 3: Add private key as GH secret on acumatica-ci-cd**

```bash
gh secret set ACUOPS_PIPELINE_DEPLOY_KEY --repo studio-b-ai/acumatica-ci-cd < "$TMPDIR/key"
```

Expected: `✓ Set Actions secret ACUOPS_PIPELINE_DEPLOY_KEY for studio-b-ai/acumatica-ci-cd`

**Step 4: Securely delete the temp keypair**

```bash
shred -u "$TMPDIR/key" "$TMPDIR/key.pub" 2>/dev/null || rm -f "$TMPDIR/key" "$TMPDIR/key.pub"
rmdir "$TMPDIR"
```

**Step 5: Write a failing test (smoke test on a feature branch)**

Create a test branch off main that adds the deploy key change to one checkout. We'll watch a workflow run on this branch to verify before touching the other 5.

```bash
cd /Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/quirky-perlman
git fetch origin main
git checkout -b chore/deploy-key-smoke-test origin/main
```

Edit `.github/workflows/acuops-deploy.yml` line ~109 (the first `actions/checkout` of acuops-pipeline):

```yaml
      - name: Checkout AcuOps pipeline
        uses: actions/checkout@v4
        with:
          repository: studio-b-ai/acuops-pipeline
          ref: ${{ vars.ACUOPS_PIPELINE_VERSION || 'main' }}
          path: pipeline
          ssh-key: ${{ secrets.ACUOPS_PIPELINE_DEPLOY_KEY }}
          # token: ${{ secrets.GH_PAT_DISPATCH }}    # ← retired, replaced by ssh-key above
```

**Step 6: Push the smoke test and watch**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "chore: smoke test deploy key for acuops-pipeline checkout"
git push -u origin chore/deploy-key-smoke-test
```

Open a draft PR so the workflow runs:

```bash
gh pr create --draft --title "chore: deploy key smoke test (DRAFT)" --body "Testing deploy key replacement for one checkout. Will close after verification."
gh run watch
```

Expected: Build job's "Checkout AcuOps pipeline" step succeeds using ssh-key.

**Step 7: If smoke test passes, replace the other 5 checkouts**

```bash
# Find all 6 references
grep -n "GH_PAT_DISPATCH" .github/workflows/acuops-deploy.yml
```

For each `actions/checkout` that uses `token: ${{ secrets.GH_PAT_DISPATCH }}` to clone acuops-pipeline, replace with `ssh-key: ${{ secrets.ACUOPS_PIPELINE_DEPLOY_KEY }}`.

Do NOT touch the `GH_TOKEN: ${{ secrets.GH_PAT_DISPATCH }}` env vars in invoke-agent — those are Task 2.3.

**Step 8: Commit + push to the same branch**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "$(cat <<'EOF'
feat: replace GH_PAT_DISPATCH with deploy key for acuops-pipeline checkout

Six actions/checkout references to studio-b-ai/acuops-pipeline (a
private repo with proprietary product code) used GH_PAT_DISPATCH —
Kevin's personal PAT. This is the same identity-attribution problem
that made the 2026-04-07 incident look like Kevin caused the
production restarts.

Generated a read-only ed25519 deploy key for acuops-pipeline. Public
half registered on acuops-pipeline (read_only=true). Private half in
ACUOPS_PIPELINE_DEPLOY_KEY GH secret on acumatica-ci-cd. All six
checkouts now use ssh-key instead of token.

acuops-pipeline contains proprietary code that will be sold through
the Acumatica VAR channel — keeping it private is a business
requirement, hence deploy keys instead of making the repo public.

invoke-agent's two GH_TOKEN env blocks (lines 1306, 1351) are NOT
touched in this PR — those become GITHUB_TOKEN in the invoke-agent
re-enable PR (Track 2.3).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git push
```

**Step 9: Promote draft PR to ready**

```bash
gh pr ready
gh run watch
```

Expected: full pipeline passes, every checkout step uses ssh-key.

**Step 10: Merge after 6pm ET if business hours**

```bash
TZ=America/New_York date  # check time
gh pr merge --squash --delete-branch
```

---

### Task 2.2: Build the daily-dispatch-cap composite action

**Files:**
- Create: `.github/actions/daily-dispatch-cap/action.yml`
- Test: `.github/workflows/test-daily-dispatch-cap.yml` (temporary, for unit testing)

**Step 1: Write the failing test workflow**

```yaml
# .github/workflows/test-daily-dispatch-cap.yml
name: Test daily-dispatch-cap
on:
  workflow_dispatch:
    inputs:
      cap:
        description: 'Cap value to test'
        required: true
        default: '999'
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: cap_check
        uses: ./.github/actions/daily-dispatch-cap
        with:
          workflow: 'Test daily-dispatch-cap'
          max_per_24h: ${{ inputs.cap }}
          gh_token: ${{ secrets.GITHUB_TOKEN }}
      - run: echo "Pass — cap not exceeded"
```

**Step 2: Run the workflow without the action existing**

```bash
git add .github/workflows/test-daily-dispatch-cap.yml
git commit -m "chore: test workflow for daily-dispatch-cap (test will fail until action exists)"
git push
gh workflow run test-daily-dispatch-cap.yml -f cap=999
sleep 10
gh run watch
```

Expected: FAIL with error about missing action `./.github/actions/daily-dispatch-cap`.

**Step 3: Implement the composite action**

Create `.github/actions/daily-dispatch-cap/action.yml`:

```yaml
name: 'Daily Dispatch Cap'
description: 'Fail if this workflow has been dispatched more than max_per_24h times in the last 24 hours'
inputs:
  workflow:
    description: 'Workflow file name or display name to count'
    required: true
  max_per_24h:
    description: 'Maximum allowed runs in the last 24 hours'
    required: true
  gh_token:
    description: 'GitHub token with actions:read scope'
    required: true
runs:
  using: 'composite'
  steps:
    - id: count
      shell: bash
      env:
        GH_TOKEN: ${{ inputs.gh_token }}
        WORKFLOW: ${{ inputs.workflow }}
        CAP: ${{ inputs.max_per_24h }}
      run: |
        SINCE=$(date -u -d '24 hours ago' --iso-8601=seconds 2>/dev/null || gdate -u -d '24 hours ago' --iso-8601=seconds)
        COUNT=$(gh api "repos/${{ github.repository }}/actions/runs?per_page=100&created=>$SINCE" \
          --jq "[.workflow_runs[] | select(.name == \"$WORKFLOW\")] | length")
        echo "Found $COUNT runs of '$WORKFLOW' in last 24h (cap: $CAP)"
        if [ "$COUNT" -ge "$CAP" ]; then
          echo "::error::Daily dispatch cap exceeded: $COUNT >= $CAP for workflow '$WORKFLOW'"
          echo "## 🚫 Daily dispatch cap exceeded" >> "$GITHUB_STEP_SUMMARY"
          echo "" >> "$GITHUB_STEP_SUMMARY"
          echo "| Field | Value |" >> "$GITHUB_STEP_SUMMARY"
          echo "|-------|-------|" >> "$GITHUB_STEP_SUMMARY"
          echo "| Workflow | $WORKFLOW |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Runs in last 24h | $COUNT |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Cap | $CAP |" >> "$GITHUB_STEP_SUMMARY"
          echo "| Action | Blocked. Wait 24h or raise cap with care." >> "$GITHUB_STEP_SUMMARY"
          exit 1
        fi
```

**Step 4: Run test with cap=999 (should pass)**

```bash
git add .github/actions/daily-dispatch-cap/action.yml
git commit -m "feat: daily-dispatch-cap composite action — bound runaway dispatches"
git push
gh workflow run test-daily-dispatch-cap.yml -f cap=999
sleep 10
gh run watch
```

Expected: PASS. Step summary shows count.

**Step 5: Run test with cap=0 (should fail)**

```bash
gh workflow run test-daily-dispatch-cap.yml -f cap=0
sleep 10
gh run watch
```

Expected: FAIL with "Daily dispatch cap exceeded: 1 >= 0".

**Step 6: Run test with cap=1 twice in a row**

```bash
gh workflow run test-daily-dispatch-cap.yml -f cap=2
sleep 5
gh workflow run test-daily-dispatch-cap.yml -f cap=2
sleep 10
gh run list --workflow test-daily-dispatch-cap.yml --limit 5
```

Expected: first PASSES, second FAILS (because by the time the second runs, count = 2 already).

**Step 7: Remove the test workflow**

```bash
git rm .github/workflows/test-daily-dispatch-cap.yml
git commit -m "chore: remove daily-dispatch-cap test workflow (action verified)"
git push
```

**Step 8: Open PR for the action**

```bash
gh pr create --title "feat: daily-dispatch-cap composite action" --body "..."
gh pr merge --squash --delete-branch  # after 6pm ET
```

---

### Task 2.3: Re-enable invoke-agent with the full Safety Package

**Files:**
- Modify: `.github/workflows/acuops-deploy.yml` (the invoke-agent job)
- New GH variable: `INVOKE_AGENT_ENABLED` (default: `false` initially, flip to `true` after dry run)

**Step 1: Read the current invoke-agent job**

```bash
grep -n "invoke-agent\|INVOKE_AGENT" .github/workflows/acuops-deploy.yml
```

Find the `if:` line that has `false &&`. Find the two `GH_TOKEN: ${{ secrets.GH_PAT_DISPATCH }}` env vars. Find where the agent prompt is set.

**Step 2: Create the GH variable, default false**

```bash
gh api -X POST repos/studio-b-ai/acumatica-ci-cd/actions/variables \
  -f name=INVOKE_AGENT_ENABLED \
  -f value=false
```

Expected: HTTP 201.

**Step 3: Branch off main**

```bash
git fetch origin main
git checkout -b feat/reenable-invoke-agent-with-safety-package origin/main
```

**Step 4: Edit acuops-deploy.yml — Safety Package implementation**

Replace the invoke-agent job's steps. Start of the steps block, BEFORE the existing checkout:

```yaml
      # ── E. Kill-switch ───────────────────────────────────────────
      - name: Check kill-switch
        id: killswitch
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          ENABLED=$(gh api repos/${{ github.repository }}/actions/variables/INVOKE_AGENT_ENABLED --jq '.value' 2>/dev/null || echo "false")
          echo "INVOKE_AGENT_ENABLED=$ENABLED"
          if [ "$ENABLED" != "true" ]; then
            echo "::notice::invoke-agent kill-switch is engaged ($ENABLED), skipping agent run"
            echo "## 🛑 invoke-agent kill-switch engaged" >> "$GITHUB_STEP_SUMMARY"
            echo "" >> "$GITHUB_STEP_SUMMARY"
            echo "GH variable INVOKE_AGENT_ENABLED = $ENABLED" >> "$GITHUB_STEP_SUMMARY"
            echo "Flip to 'true' in repo Settings → Variables to re-enable." >> "$GITHUB_STEP_SUMMARY"
            echo "skip=true" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          echo "skip=false" >> "$GITHUB_OUTPUT"

      # ── C. Hard daily cap ────────────────────────────────────────
      - uses: actions/checkout@v4
        if: steps.killswitch.outputs.skip != 'true'
      - name: Daily dispatch cap
        if: steps.killswitch.outputs.skip != 'true'
        uses: ./.github/actions/daily-dispatch-cap
        with:
          workflow: 'AcuOps Deploy'
          max_per_24h: '3'
          gh_token: ${{ secrets.GITHUB_TOKEN }}

      # ── D. Pre-notification ──────────────────────────────────────
      - name: Pre-notify Slack
        if: steps.killswitch.outputs.skip != 'true'
        env:
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
        run: |
          curl -X POST "$SLACK_WEBHOOK_URL" -H 'Content-Type: application/json' --data "$(cat <<JSON
          {
            "text": "🤖 invoke-agent will run in 30 seconds for failed sandbox-gate on ${{ github.sha }}. Reply 'cancel' in next 5 min to abort. Run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
          }
          JSON
          )"
          sleep 30
```

Then the existing "Download sandbox test logs" + "Run failure recovery agent" steps need their `if:` updated to also check `steps.killswitch.outputs.skip != 'true'`.

Then the "Run failure recovery agent" step needs:
1. **B. Identity attributed** — change `GH_TOKEN: ${{ secrets.GH_PAT_DISPATCH }}` to `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` (both env blocks)
2. **F. Bounded scope** — append a hard constraint section to the agent prompt:

```yaml
          prompt: |
            [...existing prompt content...]

            ## HARD CONSTRAINTS — DO NOT VIOLATE

            1. You may ONLY edit files matching these globs:
               - Customization/**
               - tests/**
               - acuops.yaml
               - .github/workflows/acuops-deploy.yml
            2. You may NOT edit:
               - .github/workflows/*.yml (except acuops-deploy.yml above)
               - secrets-map.env or any *.env file
               - scripts/** (unless explicitly listed above)
               - package.json or any dependency manifest
            3. You may NOT push directly to main. PR only.
            4. You may NOT use force-push or amend commits.
            5. Your max attempts in this loop is 1 (the daily-dispatch-cap
               handles broader bounds at the workflow level).
```

Finally, REMOVE the `false &&` from the job's top-level `if:` condition.

**Step 5: Verify YAML parses**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/acuops-deploy.yml'))"
echo "exit: $?"
```

Expected: exit 0.

**Step 6: Commit + push + PR (DRAFT)**

```bash
git add .github/workflows/acuops-deploy.yml
git commit -m "$(cat <<'EOF'
feat: re-enable invoke-agent with Safety Package A-F (DRAFT — needs dry run)

Re-enables the AI Failure Recovery agent that was disabled in PR #258
after the 2026-04-07 production restart loop. The re-enable is gated
by all six controls from the Safety Package design (docs/plans/
2026-04-07-agentic-pipeline-next-stage-design.md):

A. Cause eliminated — sandbox host-assertion guard from PR #258 still
   in place; sandbox secrets verified correct
B. Identity attributed — GH_TOKEN changes from GH_PAT_DISPATCH (Kevin's
   personal PAT) to GITHUB_TOKEN (built-in, audit shows
   github-actions[bot])
C. Hard daily cap — daily-dispatch-cap composite action enforces max 3
   AcuOps Deploy runs per 24h before agent runs
D. Pre-notification — posts to Slack #ops with run URL and 30s delay
   before claude-code-action fires, giving humans a window to abort
E. Kill-switch — reads GH variable INVOKE_AGENT_ENABLED. Default false.
   Flip to true after dry run succeeds. Flip back to false in 5 sec
   from GH UI to disable without a code change.
F. Bounded scope — agent prompt has hard constraints: file glob
   restriction (Customization/**, tests/**, acuops.yaml, this workflow
   file), no direct push to main (PR only), no force-push, max 1
   attempt per loop.

Status: DRAFT PR. Do NOT merge until Track 2.4 (failure dry run)
passes end-to-end.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feat/reenable-invoke-agent-with-safety-package
gh pr create --draft --title "feat: re-enable invoke-agent with Safety Package A-F" --body "See commit message + design doc."
```

---

### Task 2.4: Failure dry-run end-to-end

**Goal:** Prove the Safety Package works under realistic conditions before flipping the kill-switch to enable in main.

**Step 1: Create a deliberate sandbox-gate-breaking change on a feature branch**

```bash
git checkout -b chore/dryrun-invoke-agent-recovery
```

Edit `Customization/AesthetikContainers/project.xml` and introduce a syntax error (e.g., remove a closing tag) OR edit `acuops.yaml` to reference a non-existent project. The change must be SAFE — it must not actually publish anything. The point is to make sandbox-gate fail.

**Step 2: Push and watch**

```bash
git add .
git commit -m "chore: deliberate sandbox-gate failure for invoke-agent dry run"
git push -u origin chore/dryrun-invoke-agent-recovery
```

This is a feature branch — sandbox-gate runs only for main pushes per the workflow's `if:`. Need to dispatch the workflow manually with the branch as ref:

```bash
# Hmm — workflow_dispatch only runs on default branch usually.
# Alternative: open a PR to main and rely on the PR-triggered runs
gh pr create --draft --title "DRY RUN — do not merge" --body "Deliberate failure for invoke-agent Safety Package dry run."
gh run watch
```

Expected: build → build-validate → qualify (skipped on PR) → sandbox-gate (RUNS on PR? check workflow if: condition).

If sandbox-gate doesn't run on PRs, push directly to main is the only way — DON'T DO THAT in business hours. Wait until after-hours window.

**Alternative dry-run path:** Temporarily modify the invoke-agent's trigger to also run on `workflow_dispatch` for one test, then revert. This is safer than pushing the deliberate failure to main.

**DECISION POINT:** The dry-run mechanism needs Kevin's input before Task 2.4 executes. Two options:

- **(i) Push to main after-hours** — riskier but realistic. The pipeline runs end-to-end.
- **(ii) Add `workflow_dispatch: { inputs: { simulate_sandbox_failure: bool } }`** — safer, contained, but tests a different code path.

Pause here and ask Kevin which dry-run mechanism he wants.

**Step 3: Watch the dry run end-to-end**

(Steps depend on choice from Step 2 above.)

Expected observations:
- Slack #ops receives the pre-notification
- 30 second delay
- claude-code-action fires
- Agent reads logs, diagnoses the deliberate failure
- Agent files a PR (NOT a direct push) within the file glob bounds
- Audit log shows the dispatch as `github-actions[bot]`
- Daily-dispatch-cap step shows count progressing (e.g., 1 of 3)
- A second deliberate-failure run within 24h triggers the cap and BLOCKS at the cap step before reaching claude-code-action

**Step 4: Toggle kill-switch mid-test**

```bash
gh api -X PATCH repos/studio-b-ai/acumatica-ci-cd/actions/variables/INVOKE_AGENT_ENABLED \
  -f name=INVOKE_AGENT_ENABLED \
  -f value=false
```

Trigger another deliberate failure. Expected: invoke-agent step shows "kill-switch engaged, skipping" and no claude-code-action run.

**Step 5: Re-enable kill-switch**

```bash
gh api -X PATCH repos/studio-b-ai/acumatica-ci-cd/actions/variables/INVOKE_AGENT_ENABLED \
  -f name=INVOKE_AGENT_ENABLED \
  -f value=true
```

**Step 6: Clean up the dry-run branch + PR**

```bash
gh pr close <dryrun_pr_number>
git push origin --delete chore/dryrun-invoke-agent-recovery
```

Close any PRs the agent filed during the dry run (don't merge them — they were against deliberate failures).

**Step 7: If all 6 observations passed, mark Track 2.3's PR ready and merge**

```bash
gh pr ready <invoke-agent-reenable-pr-number>
gh pr merge --squash --delete-branch  # after 6pm ET
```

**Step 8: Commit a runbook entry to studiob-knowledge**

```python
# similar to Task 0.5 — ingest a new KB entry: "invoke-agent dry run runbook"
```

---

### Task 2.5: Mode-3 sentinel — orphan CustProject scan (summary level)

This task is contingent on Tasks 2.1–2.4 succeeding. Detail intentionally light at this layer of the plan.

- Write a small Python script `scripts/sentinels/scan_orphan_custproject.py` that connects to the prod SQL Server (Windows auth from VM, read-only query), checks for CustProject rows whose Project name is not in the active customizations list (from SM204505 OData), posts to Slack #ops only if any orphans found
- Configure Windows Task Scheduler on VM to run hourly: `claude -p --model claude-haiku-4-5-20251001 "Run scripts/sentinels/scan_orphan_custproject.py and post results to Slack only if anomalies"`
- Verify first run posts a "0 orphans found" baseline
- Cost ceiling: $1–2/mo on Haiku
- Skill reference: `@superpowers:test-driven-development` for the script

### Task 2.6: VM autostop schedule (summary level)

Also contingent on Tasks 2.1–2.4. Light detail.

- Create Cloud Scheduler jobs:
  - `acumatica-test-stop` — cron `0 20 * * 5` (Fri 8pm ET) → stops VM
  - `acumatica-test-start` — cron `0 5 * * 1` (Mon 5am ET) → starts VM
- Verify VM offline Sat morning, online Mon morning
- Document in deployment runbook so weekend pushers understand why build-validate fails

---

## Track 3 — Studio B platform vision (planning only — no code)

### Task 3.1: Read the architecture review output

Read `/Users/kevin/.claude/sessions-export/2026-04-07_98f99883.md` (the 10am scheduled task). Extract: current state table, target state, dogfooding gaps, closest-to-product apps.

### Task 3.2: Codify Studio B / tenant separation

- Edit `~/.claude/CLAUDE.md` to add platform-vs-tenant section under Conventions
- Create memory file `~/.claude/projects/-Users-kevin-dev-acumatica-ci-cd/memory/project_studiob_platform_vision.md`

### Task 3.3: Scope multi-tenant abstractions for acuops-pipeline (design doc only)

- Identify tenant-scoped values: acuops.yaml fields, also_publish_test, secrets per tenant, deploy targets, notification channels
- Write `docs/plans/2026-04-XX-acuops-multi-tenant-design.md` in acuops-pipeline repo
- NO CODE CHANGES

### Task 3.4: Pilot tenant migration checklist

- Pick Heritage Fabrics as alpha
- Enumerate the migration: what changes about Heritage's deployment when it becomes tenant-of-Studio-B vs only-customer

### Task 3.5: Trip-wire — block multi-tenant code merges until Track 2.4 succeeds

- Add hard rule to `~/.claude/CLAUDE.md`: "No multi-tenant code merges to acuops-pipeline until Track 2.4 (invoke-agent dry run) is complete."

---

## Verification gates between tracks

| Gate | Required before | Verification |
|---|---|---|
| Track 0 complete | Track 2.3 starts | Slack #ops post + KB entry searchable |
| Track 1 complete | Track 2.3 starts | SB501000 visible on prod + 3 PRs merged |
| Track 2.1 + 2.2 complete | Track 2.3 starts | All 6 deploy-key checkouts work + cap action unit-tested |
| Track 2.4 dry run passes | Track 2.5 starts + Track 3.3 design landed | Audit shows bot, cap blocks, kill-switch verified, agent files PR within bounds |
| Track 2.5 + 2.6 complete | "Stage complete" claimed | First sentinel run posted + VM autostop verified |

## Rollback

- Track 0 (a)/(c): re-set Railway env vars to old values via `railway variables --set`
- Track 0 (b): revert webhook-router PR
- Track 0.4: revert webhook-router host-assertion PR
- Track 1.1–1.3: revert each merged PR individually with `gh pr revert`
- Track 2.1: re-add `token: secrets.GH_PAT_DISPATCH` to checkout steps + delete deploy key from acuops-pipeline
- Track 2.3: flip GH variable `INVOKE_AGENT_ENABLED` to `false` (5 seconds, no code change). Or revert the PR.
- Track 2.5: disable Task Scheduler entry on VM
- Track 2.6: delete Cloud Scheduler jobs

---

## Skills referenced

- `@superpowers:executing-plans` — to execute this plan
- `@superpowers:verification-before-completion` — before claiming any task complete
- `@superpowers:test-driven-development` — for Tasks 0.4 and 2.5
- `@superpowers:systematic-debugging` — if any task hits an unexpected failure
- `@recall` — to find related past sessions for any task
- `@rigby` — at end of stage, to close out the work

## Stop conditions

Stop and ask Kevin if:

- Track 0.1's investigation finds POST/PUT/DELETE consumers of `ACUMATICA_STG_*` (changes the remediation calculus)
- Track 0.3 webhook-router redeploy fails or shows Acumatica errors after the env var change
- Track 1.5's PR merges trigger an unexpected pipeline failure
- Track 1.6's SB501000 check shows the screen still broken after deploy
- Track 2.1's smoke test fails on the deploy key (suggests deploy key permissions wrong)
- Track 2.4's dry run shows the agent over-reaching the file glob bounds
- Any task takes more than 2x the expected wall time
