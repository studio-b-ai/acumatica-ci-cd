# CI/CD Pipeline Hardening — Design

**Date:** 2026-03-30
**Trigger:** 2026-03-29 P0 outage (UOM migration, 30+ hours, snapshot restore) and 2026-03-28 cascading outage (CustomizationPlugin)
**Scope:** 6 gaps in the deploy pipeline that allowed or would allow production outages

## Context

The current pipeline (Build → Qualify → Sandbox Gate → Heritage Test Gate → Deploy + Validate) passed every check on 2026-03-29 while sales order entry was completely broken. The smoke test only verified API login + StockItem GET. Field validation passed because the UOM failure didn't remove any custom fields — it deleted INUnit conversion records that are invisible to schema checks.

Additionally:
- One-time hotfix packages were left in `ALSO_PUBLISH_PROJECTS` and would have re-deployed on next push to main
- The UserAuditTrail GI was wiped by the snapshot restore with no detection
- 20+ publish iterations exhausted the API login limit with no automatic stop
- Auto-rollback Slack messages claimed "ROLLED BACK" when only the package was restored, not database changes

PR #93 (`cleanup/remove-uom-hotfix-and-migrations`) already addresses:
- Removed all UOM migration/hotfix code from the codebase
- Added `[GUARD] Block destructive SQL` in `validate-project.py` (DELETE/UPDATE/DROP/TRUNCATE = hard fail)
- Flipped StudioBAcuOps to GI-create mode (restores UserAuditTrail GI)
- Skip sandbox publish when no published projects changed

This design covers the remaining 6 gaps.

---

## Gap A: E2E Smoke Test

### Problem
The current `smoke_test()` in `deploy.py` only does a StockItem GET after publish. It verifies the API responds but not that business operations work. The 2026-03-29 UOM failure passed this check while no one could save a sales order.

### Design
New method `e2e_smoke_test()` in `deploy.py` that runs a full order lifecycle:

```
Create SO (customer C000949, item 00004, qty 1)
  → Verify SO saved (OrderNbr returned)
  → Create Shipment (action: CreateShipment)
  → Confirm Shipment (action: ConfirmShipment)
  → Cancel SO (action: CancelOrder)
```

**Fixtures:**
- Customer: `C000949` (HERITAGE FABRICS MANAGEMENT LLC) — test customer, no real business impact
- Item: `00004` (BRINKLEY Jute, BaseUOM=PIECE, SalesUOM=PIECE, Warehouse=99)
- OrderType: `SO`

**What this exercises:**
- SO creation with customer (customer DAC extensions)
- Line item with UOM (INUnit validation — the exact 2026-03-29 failure point)
- Shipment creation via action (SOOrderEntry graph extensions)
- Shipment confirmation (ShipmentEntry graph extensions)
- Cancellation to clean up (no invoice, no AR impact)

**Runs after:** Every publish — sandbox, Heritage Test, and production. The existing `smoke_test()` stays as a fast pre-check (can the API respond after app pool restart?). The e2e runs after that passes.

**Failure behavior:** If any step fails, log exactly which step failed and the API error. Pipeline fails and triggers existing auto-rollback (package restore). No retry — one attempt only.

**Cleanup:** Cancel action reverses shipment and order. If test fails mid-way, cleanup step attempts to cancel whatever was created. Worst case: orphaned test order on C000949 — visible and easy to spot.

**No invoice.** Invoice creation/reversal is complex to undo and not worth the risk in a smoke test.

---

## Gap B: ALSO_PUBLISH Allowlist Validation

### Problem
One-time packages get added to `ALSO_PUBLISH_PROJECTS` and silently deploy on every future push to main. `UomHotfixYdsToIn` was in this variable after its directory was deleted — it would have re-deployed on the next push.

### Design
New step in the build job of `deploy-customization.yml`, before packaging:

```bash
for each project in ALSO_PUBLISH_PROJECTS (comma-separated):
  if Customization/{project}/ does not exist → HARD FAIL
  if Customization/{project}/project.xml does not exist → HARD FAIL
```

Simple bash loop. No Python, no external dependencies. Fails the build immediately if any project in the variable doesn't have a matching directory and project.xml in the repo.

---

## Gap C: GI Baseline Wired Into Deploy

### Problem
GI regressions go undetected. The UserAuditTrail GI was wiped by snapshot restore and nobody knew until manually checking. `gi_baseline.py` already exists but isn't called by the pipeline.

### Design
Two new steps in the deploy job of `deploy-customization.yml`:

1. **Pre-publish:** `python scripts/gi_baseline.py capture --output baselines/pre.json`
2. **Post-publish (after e2e smoke test):** `python scripts/gi_baseline.py diff --before baselines/pre.json`

**Known GIs (default list in gi_baseline.py):**
- `InventoryAllocationDetail`
- `LotAvailability`
- `StockItemsChristmasWishList`
- `UserAuditTrail` (added after StudioBAcuOps deploys tonight)

**Failure behavior:**
- GI existed before publish, missing after → FAIL (triggers auto-rollback)
- GI has fewer result columns after publish → WARNING (logged, not blocking)
- New GI appeared → INFO (logged)

Uses the same Acumatica credentials already in the deploy job. Runs against whichever tenant just got published.

---

## Gap D: Playwright Business-Operation Tests

### Status: BLOCKED

Blocked until StudioBAcuOps deploys tonight and the UserAuditTrail GI starts capturing audit data. Once audit data flows, we design Playwright tests around the operations that matter most.

**Target tests (initial set, post-unblock):**
- Create a sales order on Heritage Fabrics Management
- Verify inventory allocation inquiry reflects the order
- Verify lot/serial assignment works on a PIECENBR item

**Trigger:** Post-deploy `repository_dispatch` from `acumatica-ci-cd` to `ui-test-suite` (already wired in the Trigger Runtime Tests job).

**Design deferred** until audit data reveals which screens and operations are most fragile.

---

## Gap E: Max-Attempts Circuit Breaker

### Problem
20+ manual publish iterations on 2026-03-29 exhausted the API login limit. No automatic stop prevented the operator from retrying indefinitely.

### Design
New step at the start of the deploy job that checks recent workflow run history:

```bash
# Query last 3 completed runs for this branch
# If all 3 failed → HALT
gh run list --branch {branch} --limit 3 --json conclusion \
  | check if all conclusions == "failure"
```

**If tripped:** Post to Slack: `"Circuit breaker tripped — 3 consecutive deploy failures on {branch}. Manual review required."` and exit 1.

**Scope:** Only checks `workflow_dispatch` and `push` events (not PR events). Only checks runs from the last 24 hours to avoid stale history blocking deploys after fixes are applied.

---

## Gap F: Rollback Messaging

### Problem
Auto-rollback Slack alerts say "ROLLED BACK" but the rollback only restores the customization package. `CustomizationPlugin.UpdateDatabase()` SQL changes (ALTER TABLE, INSERT, CREATE TABLE) persist. The messaging is misleading.

### Design
Text changes in `deploy-customization.yml` auto-rollback step:

**Success message:**
- Old: `"Deploy ROLLED BACK — {project} -> production"`
- New: `"PACKAGE RESTORED — {project} -> production\nCustomizationPlugin SQL changes are NOT reversed.\nIf UpdateDatabase() modified data, manual review required."`

**Failure message:**
- Old: `"ROLLBACK FAILED — ..."`
- New: `"PACKAGE RESTORE FAILED — ...\nManual restore: download artifact -> SM204505 Import -> Publish"`

---

## Implementation Order

| Task | Gap | Depends On | Size |
|------|-----|-----------|------|
| 1 | F — Rollback messaging | Nothing | Trivial |
| 2 | B — ALSO_PUBLISH validation | Nothing | Small |
| 3 | E — Circuit breaker | Nothing | Small |
| 4 | C — GI baseline | Nothing | Small |
| 5 | A — E2E smoke test | Nothing | Medium |
| 6 | D — Playwright tests | StudioBAcuOps deploy + audit data | Deferred |

Tasks 1–4 are independent and can be implemented in parallel. Task 5 (e2e smoke test) is the largest and most important.

All changes go into PR #93 (`cleanup/remove-uom-hotfix-and-migrations`) or a new PR branched from it. No deploys until after hours — code only.
