# Pipeline Split Design: Build vs Deploy Workflow Separation

**Date:** 2026-04-16
**Author:** Kevin Bibelhausen + Claude
**Status:** Approved
**Priority:** P0 — unblocks PCC prod recovery + DRP GI verification

## Problem Statement

The AcuOps pipeline is a single monolithic workflow (`acuops-deploy.yml`) with `cancel-in-progress: false` applied to ALL 9 jobs. This means:

1. **Stale builds block the entire pipeline.** A hung self-hosted Windows runner (build-validate) holds the concurrency lock for hours. New pushes queue behind it even though they don't touch Acumatica at all.
2. **Cycle time is ~90-120 minutes.** Jobs that could run in parallel (build, build-validate) are serialized.
3. **PCC has been broken on prod since 2026-04-15.** Every fix attempt is blocked by the sandbox gate, which is blocked by pre-existing test failures, which are blocked by the pipeline being stuck behind stale runs. The pipeline itself is the constraint.

### 2026-04-16 Incident (Triggering Event)

PR #431 (DRP GI C# plugin migration) merged to main. The deploy run failed at sandbox-gate due to 6 pre-existing UI test failures. PR #432 (xfail markers) was merged and a fresh run dispatched. But the rerun of the old commit (with `cancel-in-progress: false`) held the concurrency lock for the entire workflow — the fresh run couldn't start for hours.

### LSS Waste Analysis

| Waste Type | Description | Impact |
|------------|-------------|--------|
| **Waiting** | build-validate blocks on VM startup; stale runs hold concurrency lock | Hours of delay |
| **Overprocessing** | Single concurrency group covers 9 jobs; only 2 need publish protection | Unnecessary serialization |
| **Defects** | 6 pre-existing xfail tests gate the pipeline | False-negative gates |

## Design

### Split Into Two Workflows

| Workflow | File | Concurrency Group | cancel-in-progress | Purpose |
|----------|------|-------------------|-------------------|---------|
| **Build & Validate** | `acuops-build.yml` | `acuops-build-{ref}` | **true** | Build, compile, qualify — no Acumatica publishes |
| **Deploy** | `acuops-deploy.yml` | `acuops-deploy-{ref}` | **false** | Sandbox gate, prod deploy — publishes to Acumatica |

### Build & Validate Workflow (`acuops-build.yml`)

**Triggers:** push to main/staging, pull_request, workflow_dispatch, repository_dispatch

**Jobs:**

```
dispatch-guard ──┐
                 ▼
              build ──────────► build-validate   (parallel)
                 │                    │
                 ▼                    │
              qualify ◄───────────────┘
                 │
                 ├──► validate (PR-only, continue-on-error)
                 │
                 └──► workflow_call: acuops-deploy.yml (main/staging push only)
```

- **dispatch-guard:** Unchanged. 24h cap, override validation.
- **build:** Package customization .zip, load config, detect changes. Unchanged.
- **build-validate:** Compile C# against Acumatica SDK. Unchanged but now **runs in parallel with build** (it compiles from source, doesn't need build's artifact).
- **qualify:** Pre-deploy qualification against prod. Waits for both build + build-validate.
- **validate:** PR-only staging publish. Unchanged.
- **Handoff:** On success (non-PR), calls `acuops-deploy.yml` via `workflow_call`, passing artifact ID and config outputs.

**Key behavior change:** A new push **cancels in-progress build/validate/qualify immediately**. No more waiting for stale Windows runners.

### Deploy Workflow (`acuops-deploy.yml`)

**Triggers:** `workflow_call` from acuops-build only (not directly from push)

**Jobs:**

```
sandbox-gate ──► deploy ──► post-deploy
      │
      └──► invoke-agent (on failure)
```

- **sandbox-gate:** Publish to sandbox, run UI tests. Unchanged.
- **deploy:** Publish to prod/staging. Unchanged.
- **post-deploy:** Post-deploy verification. Unchanged.
- **invoke-agent:** AI failure recovery on sandbox-gate failure. Unchanged.

**Key behavior change:** `cancel-in-progress: false` only protects these 4 jobs — the ones that actually publish to Acumatica. Build-phase cancellation can't affect in-flight publishes.

### Workflow Call Interface

`acuops-build.yml` calls `acuops-deploy.yml` via `workflow_call` with:

**Inputs (from build outputs):**
- `package_name` — artifact name for download
- `project_name` — customization project name
- `also_publish` — co-publish project list
- `customization_changes` — whether to publish
- `plugin_changes` — whether CustomizationPlugin changed
- `known_projects`, `isv_packages`, `isv_prefix`, `strict`

**Secrets:** Inherited (`secrets: inherit`)

**Emergency overrides:** Passed through from the original workflow_dispatch inputs (force_deploy, skip_sandbox_gate, force_business_hours, etc.)

### What This Saves

| Scenario | Before | After |
|----------|--------|-------|
| Tonight (stale build-validate blocks new run) | ~2+ hours waiting | ~0 (cancelled immediately) |
| Normal flow (build + build-validate serial) | ~15-20 min | ~5-10 min (parallel) |
| Normal full pipeline | ~90-120 min | ~70-100 min |

## Related Work: Test Failure Triage

The 6 xfailed sandbox UI tests need real fixes to restore the sandbox gate as a meaningful quality gate. These are tracked separately but are part of the same critical path:

### Root Cause A: Playwright iframe traversal (4 tests)
- `test_kpi_tiles_show_counts`, `test_metrics_row_visible`, `test_detail_panel_syncs_on_row_click`, `test_stock_item_base_uom_is_yds`
- Playwright's `text_content()` doesn't descend into PXHtmlView's sandboxed `iframe.htmlviewinner`
- Fix: Update `AcumaticaScreen` helper to traverse iframe boundary

### Root Cause B: Missing ASPX fields (2 tests)
- `test_shipping_delivery_fields_exist`, `test_grid_has_add_button`
- Need Playwright probe against live sandbox to determine if genuine ASPX bug or same iframe issue
- Per CLAUDE.md rule 20: verify symptom via Playwright before proposing C# fixes

### PCC Production Recovery

PCC (SB501000/SB501200) has been broken on prod since 2026-04-15. ThreadAbortException during "Updating website files" phase left ASPX pages un-indexed. The pipeline split unblocks the deploy that fixes this:

1. Pipeline split lands (this design)
2. Fix AcumaticaScreen iframe traversal
3. Playwright probe SB501000/SB501200 on sandbox
4. Remove xfails
5. Deploy to prod — PCC finally live

## Implementation Notes

- The `workflow_call` trigger requires the called workflow to be in the same repo (or a reusable workflow in a public repo). Since both files are in acumatica-ci-cd, this works.
- Emergency override inputs (force_deploy, skip_sandbox_gate, etc.) need to be declared as `workflow_call` inputs in the deploy workflow and forwarded from the build workflow's `workflow_dispatch` inputs.
- The build workflow's `workflow_dispatch` inputs remain the user-facing interface — deploy workflow is never dispatched manually.
- PR validation (`validate` job) stays in the build workflow since it publishes to staging (not sandbox/prod) and uses its own concurrency group (`staging-validate`).
