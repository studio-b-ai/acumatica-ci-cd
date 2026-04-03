# Fix Pipeline False Failures

**Date:** 2026-04-03
**Repo:** studio-b-ai/acuops-pipeline
**Context:** docs/prompts/debug-pipeline-post-publish.md

## Problem

Every production deploy shows FAILURE despite successful publish. `validate-publish.py` and `emergency-deploy.py` import a missing `validate_publish_gi` module, crash with `ModuleNotFoundError`, and set `steps.verify.outcome == 'failure'`. This triggers auto-rollback (which also fails — no snapshot). Net result: pipeline always red, masking real failures.

## Root Cause

`validate_publish_gi.py` was referenced in imports before being built. It's supposed to provide `check_gi_health()` for GI subsystem probes, but the module doesn't exist in the repo.

## Decision

Guard the import rather than build the module. Rationale:
- Pipeline already validates custom fields against live API schema post-publish
- 66 automated tests cover entity schemas
- GI corruption post-publish is a narrow edge case
- Existing GI tooling in acumatica-ci-cd covers GI validation if needed later

## Fix

Guard `check_gi_health` import in two files:

**`scripts/validate-publish.py` (line 27):**
```python
try:
    from validate_publish_gi import check_gi_health
except ImportError:
    check_gi_health = None
```

**`scripts/emergency-deploy.py` (line 11):**
Same pattern.

At call sites, wrap with `if check_gi_health is not None:` guard.

## What this fixes

Once the scripts stop crashing, `steps.verify.outcome` reflects real validation results. The existing rollback condition works as designed — no workflow YAML changes needed.

## Out of scope

- `--no-merge` flag (separate decision)
- `ALSO_PUBLISH_PROJECTS` cleanup (separate task)
- SB501000 production error (blocked on trace capture)
- Building the actual `validate_publish_gi.py` module (YAGNI for now)
