# ASPX Import Doesn't Overwrite — Root Cause Investigation

## Problem

When the CI/CD pipeline imports a customization package via the Acumatica REST API, ASPX files embedded as CDATA in project.xml do **not** overwrite existing ASPX files already in the customization project on the instance. This means a stale or broken ASPX can persist across deploys.

## Incident (2026-04-05)

SB501000.aspx on production had `TabView.master` (from an unmerged `feat/command-center` branch that somehow reached prod). The project.xml CDATA had the correct `FormDetail.master`. Three deploys to production did not fix the screen — the import never replaced the file.

The fix required merging the master page change into the standalone ASPX file in the repo (PR #221). Even then, it's unclear whether the pipeline import or the standalone file change is what fixed it.

## What to Investigate

1. **How does the Acumatica customization import API handle existing files?**
   - Does `POST /CustomizationApi/Import` with `isReplaceIfExists: true` replace ASPX files?
   - Or does it only replace the project.xml metadata and leave existing files untouched?
   - Is there a difference between `Source="#CDATA"` (inline) and `Source="#FILE"` (physical file) handling?

2. **What actually gets deployed?**
   - The pipeline packages a zip from `Customization/AesthetikContainers/`
   - This includes both standalone files (`Pages/SB/SB501000.aspx`) AND the CDATA in `project.xml`
   - Which one wins when both exist in the package?

3. **Is there a file-level cache?**
   - Does Acumatica cache compiled ASPX files that survive a customization publish?
   - Does the app pool restart clear this cache, or is it a filesystem-level issue?

4. **Reproduction steps:**
   - Deploy a known-good ASPX to sandbox
   - Manually change the ASPX on the instance (via SM204505)
   - Deploy the same package again
   - Check: did the import restore the original ASPX, or is the manual change still there?

## Where to Look

- Acumatica Customization API docs (in `studiob-knowledge` Qdrant, domain=acumatica)
- `pipeline/scripts/deploy.py` — the `import_package` and `preflight_validate` methods
- SM204505 (Customization Projects) on the sandbox instance — inspect how files are stored
- Acumatica community forum — search for "import customization ASPX overwrite"

## Key Files

- `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml` — CDATA block at line ~169
- `/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/Pages/SB/SB501000.aspx` — standalone file
- `/Users/kevin/dev/acuops-pipeline/scripts/deploy.py` — import logic

## Qdrant Query

Search `studiob-knowledge` for related knowledge:
```bash
# "customization import ASPX file overwrite"
# "project.xml CDATA vs physical file"
# "isReplaceIfExists"
```

## Impact

If imports don't overwrite ASPX files, the pipeline has a silent failure mode: code deploys successfully but screens don't update. This undermines the entire CI/CD promise. Understanding the root cause determines whether we need to:
- Always delete before import (add a pre-import cleanup step)
- Use physical files instead of CDATA
- Accept the limitation and document the manual workaround (SM204505)
