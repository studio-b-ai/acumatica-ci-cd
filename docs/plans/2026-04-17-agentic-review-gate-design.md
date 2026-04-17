# Agentic Review Gate — Design Doc

**Date:** 2026-04-17
**Status:** Design for review (no code yet)
**Owner:** Kevin / Studio B
**Repo:** `studio-b-ai/acumatica-ci-cd`
**Related:** [PR #443 fix for `require-review-label` syntax](https://github.com/studio-b-ai/acumatica-ci-cd/pull/443), `memory/feedback_agentic-gate-pattern.md`

## Context

The `require-review-label` gate (`.github/workflows/require-review-label.yml`) currently demands a human-applied `reviewed` GitHub label before any PR touching production-dangerous paths (Customization, migrations, SQL, Acumatica clients, deploy configs, CI workflows, deploy scripts) can merge. PR #443 fixed a bash syntax error that had been silently failing the gate on every PR; with that fix landed, the gate works — but it routes every sensitive-path PR through Kevin's manual attention.

That conflicts with `feedback_no-manual-handoffs.md` ("never ask Kevin to do tasks doable via API/CLI/MCP"). The label application itself is mechanical once a decision is made — the decision is what needs a human, and only when automated checks can't vouch for the change.

## Goal

Preserve the safety of the current gate (unreviewed AI changes cannot hit production-dangerous paths) while removing Kevin as the default label-applier for PRs that automated qualifiers already validate.

## Non-goals

- Relaxing what counts as a sensitive path. The current path list stays authoritative.
- Removing the human path. It stays — just moves to Slack.
- Gating non-sensitive PRs. Application code, tests, docs still merge without this gate.
- Changing branch-protection yet. That's a follow-up after this design proves out.

## Design overview

```
 PR opened / synced
        │
        ▼
┌───────────────────────┐
│ sensitive path?       │─── no ──▶ gate passes (unchanged)
└──────┬────────────────┘
       │ yes
       ▼
┌───────────────────────┐
│ Phase 1: auto-qualify │   runs validate-project.py --strict, qualify.py,
│ (GitHub Actions job)  │   ui-test-suite smoke (repository_dispatch + wait)
└──────┬────────────────┘
       │
  ┌────┴─────┐
  │          │
  pass       fail
  │          │
  ▼          ▼
┌──────────────┐   ┌────────────────────────────────────┐
│ Phase 2:     │   │ Phase 3: Slack approval            │
│ auto-apply   │   │  - webhook-router posts Block Kit  │
│ `reviewed`   │   │    message to #acuops-approvals    │
│ label via    │   │  - Approve button → webhook-router │
│ GitHub App   │   │    applies `reviewed` label        │
└──────┬───────┘   │  - Reject button → PR comment +    │
       │           │    label withheld                  │
       │           └──────────────┬─────────────────────┘
       │                          │
       └──────────┬───────────────┘
                  ▼
       gate re-runs on `labeled`
       event → passes if label set
```

## Phase 1 — Auto-qualifier

New job in `require-review-label.yml` that runs BEFORE the label check when `sensitive=1`.

**Inputs:** list of changed files (already computed by the existing Detect step).

**Qualifiers (all must pass):**

| Check | Fires when | How |
|-------|-----------|-----|
| `pipeline/scripts/validate-project.py --strict` | Any `Customization/**/project.xml` changed | Run per changed project.xml |
| `pipeline/scripts/qualify.py` | Any `.cs`, `.aspx`, or `project.xml` changed | Existing acuops qualifier |
| ui-test-suite smoke (filtered) | Any `Customization/**` changed | `repository_dispatch` to `studio-b-ai/ui-test-suite`, wait for run, check result |
| Secret scan on diff | All sensitive-path PRs | `gitleaks` or `trufflehog` against PR diff |
| No direct SQL in migrations missing rollback | `migrations/**` or `*.sql` changed | Lint: every `.sql` file has a matching `*.rollback.sql` or includes `-- ROLLBACK:` block |

**Output:** single step summary posted to the PR as a comment:

```
## Auto-qualifier result: ✅ PASS  (or ❌ FAIL)

- validate-project.py --strict: ✅ (2 project.xml checked)
- qualify.py: ✅
- ui-test-suite smoke: ✅ (run 245…)
- secret scan: ✅
- migration rollback lint: n/a

<commit SHA> · auto-qualifier v1 · 2026-04-17 02:45 UTC
```

**Idempotency:** auto-qualifier re-runs on every push to the PR. A new commit invalidates any prior auto-label.

**Timeout budget:** 15 min total. Most qualifiers are fast; ui-test-suite smoke dominates.

## Phase 2 — Auto-label on pass

**Mechanism:** GitHub App (not PAT) with `pull_requests: write` scope, installed only on `studio-b-ai/acumatica-ci-cd` initially.

**Why GitHub App over PAT:**
- Scope is per-repo, not per-user. A PAT leak would expose every repo Kevin's account can write to.
- Rate limits are separate from Kevin's personal account.
- The app-as-actor shows in audit logs as `acuops-review-gate[bot]`, which is auditable. A PAT would show as Kevin, falsely implying human approval.

**Action:** `POST /repos/{owner}/{repo}/issues/{number}/labels` with body `{"labels": ["reviewed"]}`.

**Audit comment:** posted to the PR alongside the label:

```
Label `reviewed` auto-applied by acuops-review-gate at <SHA>.
Auto-qualifier result: ✅ pass (see above).
Override: remove this label to force human approval.
```

**Re-trigger on new commits:** the `reviewed` label is removed automatically on every `synchronize` event (new push). Next auto-qualifier decides fresh.

## Phase 3 — Slack interactive approval

Fires only when Phase 1 fails. The Slack path IS the human path — no GitHub UI labeling by humans.

### Message

Posted to `#acuops-approvals` (new channel) by webhook-router, via Slack Block Kit.

**Blocks:**
1. Header: `🟡 Approval required — acuops-ci-cd PR #443`
2. Section: PR title, author, sensitive paths hit, auto-qualifier summary (which checks failed + link to logs)
3. Divider
4. Actions: `[✅ Approve]` `[❌ Reject]` `[🔗 View PR]`

Approve / Reject carry `value` payloads: `approve:acumatica-ci-cd:443:<sha>` / `reject:...`. The SHA pins the decision to a specific commit — new commits invalidate pending approvals.

### Interaction handler

New route in `webhook-router`: `POST /webhook/slack/interaction`.

**Flow:**
1. Validate Slack signing secret (HMAC-SHA256 of `v0:{timestamp}:{raw body}`, compared against `X-Slack-Signature`). Reject if signature invalid or timestamp > 5 min old (replay guard).
2. Parse `payload.actions[0].value` → `{action, repo, pr, sha}`.
3. Resolve `payload.user.id` → approver identity.
4. Check approver allowlist. If not allowed: respond in thread, no state change.
5. If `approve`: fetch PR head SHA via GitHub API. If SHA drift since button was generated, reject with "commit changed — re-approve after new qualifier run". Otherwise apply `reviewed` label.
6. If `reject`: post PR comment with approver name, reason prompt (Slack modal for freetext), label withheld.
7. Update the Slack message: replace buttons with "✅ Approved by @kevin · 02:47 UTC" or "❌ Rejected by @kevin · 02:47 UTC · reason: …".

**Approver allowlist:** `config/review-approvers.yaml` in acumatica-ci-cd, config-as-code, checked into the repo:

```yaml
approvers:
  - slack_user_id: UXXXXXXXX
    github_login: kbibelhausen
    name: Kevin
    scopes: [all]
  - slack_user_id: UYYYYYYYY
    github_login: sarahb
    name: Sarah
    scopes: [customization]  # only approves Customization/** changes, not workflows
```

Loaded by webhook-router on boot and refreshed on SIGHUP or deploy.

## Security

| Concern | Mitigation |
|---------|-----------|
| Stolen Slack signing secret | Rotatable via Slack app settings; stored in Railway env var; validate on every request |
| Approver account takeover | GitHub App scope limited to this repo; Slack 2FA enforced on workspace; approver actions logged with SHA pin |
| CSRF / forged approval URL | No URL-based approval exists. Only Slack interactive payloads, which require Slack's HMAC. |
| Approver acts while PR is mid-force-push | SHA pin in button `value`. Force-push invalidates pending buttons. |
| Rogue label application via GitHub UI | The auto-label job removes any `reviewed` label on `synchronize` events and lets the qualifier / Slack path decide fresh. |
| Gate bypass via `--admin` | Separate follow-up: add "Require review label" to branch protection required checks once this design is live. |

## Failure modes

| Mode | Behavior |
|------|---------|
| Auto-qualifier flake (qualify.py crashes on unrelated bug) | Auto-label withheld. Falls through to Slack. Human can approve with context. |
| ui-test-suite repo down | Smoke check times out. Auto-qualifier fails. Slack approval path still works. |
| Slack down | PR author can still `gh pr edit --add-label reviewed` manually as emergency break-glass. Document this; don't design around it. |
| webhook-router down | Same as Slack down. |
| Approver unavailable | Another approver in allowlist can click. If none available, break-glass manual label. |
| Approve clicked after new push | SHA mismatch → rejection with "commit changed" message. |

## Rollout

**Week 1 — Phase 1 shadow mode:**
- Add auto-qualifier job as `continue-on-error: true`. It posts its PR comment but doesn't block.
- Observe for false positives / false negatives across 10–20 PRs.
- Tune qualifiers based on real results.

**Week 2 — Phase 2 enable:**
- Switch auto-qualifier to fail the gate on fail (removing `continue-on-error`).
- Enable auto-label on pass.
- `require-review-label` now accepts the bot-applied label.

**Week 3 — Phase 3 enable:**
- Ship webhook-router Slack interaction endpoint + approver config.
- Slack app Interactive Components configured to POST to `/webhook/slack/interaction`.
- Kevin (and anyone else in the allowlist) approves via Slack. No more GitHub UI labeling.

**Week 4 — branch protection:**
- Add "Require review label" to required status checks on `main`.
- Blocks `gh pr merge --admin` bypass.

Each week gates the next. No flipping straight to required checks.

## What's in scope for the first implementation PR

- `require-review-label.yml` grows Phase 1 auto-qualifier job (shadow mode).
- `docs/plans/2026-04-17-agentic-review-gate-design.md` (this file).
- No Slack, no auto-label, no branch-protection changes.

Phases 2, 3, 4 ship in follow-up PRs once Phase 1 proves out.

## Open questions for Kevin

1. **Approver allowlist scope:** start with Kevin only, add Sarah later? Or both from day one?
2. **Slack channel:** new `#acuops-approvals`, or reuse `#deployments`?
3. **Scoped approvers:** does the "Sarah only approves Customization/** changes" idea have teeth, or is it simpler to keep allowlist flat (any approver = any change)?
4. **Timeout budget:** 15 min total for auto-qualifier OK, or tighter?
5. **ui-test-suite smoke scope:** run the full `@acumatica` suite on every sensitive-path PR, or smoke-filter to just the entities the PR's project.xml touches?
6. **Break-glass:** document `gh pr edit --add-label reviewed` as an explicit escape hatch for Slack outages, or leave it implicit?
7. **Audit logging:** comment on PR is enough, or also log to Qdrant `studiob-knowledge` for "who approved what" queries?

## Non-scope / flagged for later

- **AcuOps packaging implications:** if AcuOps ships to VARs, each VAR's own Acumatica pipeline will need its own version of this gate + approver config. Template this after it proves out internally.
- **Cross-repo gate:** right now this lives in acumatica-ci-cd only. Other sensitive-path repos (`heritage-wms`, `webhook-router`, `studiob-api`) could use the same pattern. Don't scope-creep the initial PR — prove it here first.
- **Auto-qualifier quality metrics:** once live, track pass/fail rates and false-positive/false-negative counts. Feed into qualifier tuning.
