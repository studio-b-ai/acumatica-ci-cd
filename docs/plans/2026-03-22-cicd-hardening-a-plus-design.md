# CI/CD Hardening — A to A+ Design

**Date:** 2026-03-22
**Scope:** 4 quick wins that prove shipped safety features actually work

## Context

Tonight we shipped: agentic qualify gate, automatic rollback, sandbox PR validation, deploy.py consolidation, countdown offload, and a successful 18-package production deploy (225s). Grade: A.

The A+ gap is proving these features work under real failure conditions. Three of the four items are live tests of existing code. One is a missing CI fix.

## Item 1: Failure Injection Test

**Goal:** Deliberately break a package, publish to sandbox, verify rollback fires and restores.

### Approach

New workflow: `.github/workflows/test-rollback.yml` (manual dispatch only, never auto-triggers).

**Steps:**
1. Create a broken `project.xml` in-workflow (invalid C# — missing semicolons, undefined type references)
2. Package it as a .zip
3. Take a pre-deploy snapshot (backup) of the current sandbox state using `scripts/snapshot.py`
4. Import the broken package to sandbox (`ACUMATICA_STG_*` secrets)
5. Publish — this WILL fail (C# compilation error)
6. deploy.sh detects `isFailed: true` in publishEnd response
7. Manifest validation runs → FAILS (broken fields not present)
8. Rollback triggers: re-import backup → re-publish → poll completion
9. Post-rollback smoke test: entity queries return 200

**Assertions (workflow step outputs):**
- Publish failed (exit code from deploy.sh publish section)
- Rollback executed (backup re-import returned 200/204)
- Rollback publish completed (publishEnd returned `isCompleted: true`)
- Post-rollback smoke: StockItem, SalesOrder, PurchaseOrder all return 200

**Key constraints:**
- Sandbox only (`ACUMATICA_STG_*` secrets) — NEVER production
- Requires `--backup --manifest publish-manifest.json` flags to trigger rollback path
- The broken project must use a UNIQUE name (e.g., `CICDRollbackTest`) so it doesn't clobber real packages
- After test: clean up by re-importing the test project as empty XML (`<Customization level="0"></Customization>`)

### Files

| Action | File |
|--------|------|
| CREATE | `.github/workflows/test-rollback.yml` |
| CREATE | `Customization/CICDRollbackTest/project.xml` — intentionally broken (committed as-is) |
| CREATE | `publish-manifest-rollback-test.json` — manifest with field that won't exist |

### Risk

LOW — sandbox only. Broken project uses unique name. Cleanup step removes it.

---

## Item 2: PR Sandbox Validation Live Test

**Goal:** Open a PR with a real change, verify the `validate` job runs sandbox import and posts results.

### Approach

Create a test branch, make a harmless change to `Customization/AesthetikERP/project.xml` (add a C# comment inside an existing Graph CDATA block), open a PR.

The existing `deploy-customization.yml` validate job runs on PRs:
- Runs `validate-project.py` (strict mode for main)
- Builds and packages the .zip
- Runs `deploy.sh --validate-only` against staging — imports but does NOT publish
- Posts results to GitHub step summary

**Assertions:**
- Workflow triggers on PR creation
- Build job succeeds (validation passes, package created)
- Validate job runs `deploy.sh --validate-only` against staging
- Import returns 200/204 (package accepted by Acumatica)
- Step summary shows "Validation complete"

**Key constraints:**
- The change must be trivially revertible (one comment line)
- Close the PR after validation (don't merge)
- This is operational — no new code, just exercising existing workflow

### Files

| Action | File |
|--------|------|
| MODIFY | `Customization/AesthetikERP/project.xml` — add C# comment in existing Graph block |

### Risk

ZERO — validate-only never publishes. Worst case: import adds an identical package to staging.

---

## Item 3: Countdown Offload Live Test

**Goal:** Verify webhook-router's BullMQ deploy-countdown fires a delayed dispatch.

### Approach

New workflow: `.github/workflows/test-countdown.yml` (manual dispatch only).

**Steps:**
1. POST to webhook-router `/deploy/schedule` with:
   - `repo: "studio-b-ai/acumatica-ci-cd"`
   - `workflow: "deploy-customization.yml"` (doesn't matter — we'll verify job completion, not the dispatch target)
   - `delay_minutes: 1` (minimum practical)
   - `inputs: { dry_run: "true" }` — safety: even if dispatch fires, it won't publish
   - `notifications: [{ minutes_remaining: 1, channel: "slack" }]`
2. Wait 90 seconds
3. Check Slack #deployments for the countdown notification
4. Verify the dispatch job was processed (check BullMQ job status)

**Problem:** There's no `/deploy/status/:jobId` endpoint to check job completion.

**Solution:** Add a minimal `/deploy/status/:jobId` GET endpoint to webhook-router that returns job state from BullMQ. This is a 20-line addition to `deploy-schedule.ts`.

### Files

| Action | Repo | File |
|--------|------|------|
| CREATE | acumatica-ci-cd | `.github/workflows/test-countdown.yml` |
| MODIFY | webhook-router | `src/deploy/deploy-schedule.ts` — add `GET /deploy/status/:jobId` |

### Risk

LOW — the dispatch target uses `dry_run: true`. Even if the countdown fires the workflow, it won't publish.

---

## Item 4: Fix Webhook-Router CI

**Goal:** Add missing `test:api` and `test:e2e` scripts so CI can run targeted test suites.

### Approach

The webhook-router `package.json` only has `"test": "vitest run"`. The CI workflow references `npm test` which works, but there's no way to run subsets. Add:

```json
"test:api": "vitest run tests/routes/",
"test:e2e": "vitest run tests/e2e/",
"test:unit": "vitest run tests/services/"
```

Also create `tests/e2e/health.test.ts` — a basic smoke test that verifies the health endpoint returns 200 with expected shape. This catches "app won't start" regressions.

### Files

| Action | Repo | File |
|--------|------|------|
| MODIFY | webhook-router | `package.json` — add test:api, test:e2e, test:unit scripts |
| CREATE | webhook-router | `tests/e2e/health.test.ts` — health endpoint smoke test |

### Risk

ZERO — additive only. Existing `npm test` behavior unchanged.

---

## Execution Order

1. **Item 4** (webhook-router CI fix) — 15 min, zero risk, unblocks everything
2. **Item 3** (countdown test) — 30 min, needs the `/deploy/status` endpoint from item 4's repo
3. **Item 1** (failure injection) — 1 hr, the big one: proves rollback works
4. **Item 2** (PR sandbox) — 30 min, operational: open PR, watch, close

Total estimated: ~2.5 hours

## Dependencies

- Items 1-3 need GitHub Actions secrets already configured (verified: `ACUMATICA_STG_*` exist)
- Item 3 needs webhook-router Railway env vars (`GH_PAT_DISPATCH`, `STUDIOB_SLACK_WEBHOOK_URL`)
- Item 4 needs push access to `studio-b-ai/webhook-router` (have it via `gh`)

## Success Criteria

All 4 items produce evidence:
1. Rollback test: GitHub Actions run shows "ROLLBACK COMPLETED" in logs
2. PR validation: GitHub Actions run shows "Validation complete" step summary
3. Countdown test: Slack message appears, job status shows "completed"
4. CI fix: `npm run test:api` and `npm run test:e2e` both exit 0
