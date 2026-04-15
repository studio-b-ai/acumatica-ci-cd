# Orphan Customization Metadata Cleanup

One-shot tooling to reconcile + remove the 3 orphan `CustProject` entries
that block `isMergeWithExistingPackages=true` on Heritage Fabrics.

## Background

Three customization projects were removed in March/April 2026 without proper
unpublishing. Their entries in `CustProject` / `CustPublishedProject` survived
deletion, causing `publishBegin` with `merge=true` to crash with the generic
"An error has occurred" message. Workaround since April 3: pipeline uses
`merge=false`, which silently skips GI OData re-registration.

The 3 orphans:
- `IIGCONTAINERMGMT[24.204.0004][R19]1` (IIG ISV)
- `IIGHFContainerMods[24.204.0004][R04]` (IIG ISV)
- `AesthetikContainerGIs` (our package, deleted 2026-04-09 per PR #303)

## Strategy

Re-import each orphan via the Customization API (creates matching `CustProject`
row), then call `POST /CustomizationApi/delete` so Acumatica's own deletion
logic cleans the metadata properly. Avoids any direct system-table SQL.

**No publish step.** Import only stages the project content; nothing executes
against the running instance until `publishBegin` is called. We never call it.

## Files

| File | Purpose |
|---|---|
| `IIGCONTAINERMGMT.zip` | Original IIG installer (50 files, 691KB) — provided by Kevin |
| `IIGHFContainerMods.zip` | Original IIG installer (2 files, 9KB) — provided by Kevin |
| `AesthetikContainerGIs.zip` | Minimal stub with matching project name |
| `cleanup-orphans.py` | Import + delete + verify merge=true script |

## Usage

Use the `Orphan Cleanup (one-shot)` GitHub Actions workflow:

1. **Sandbox dry-run** — set `environment=sandbox`, `dry_run=true`. Verifies
   credentials and zip presence, prints plan, no changes.

2. **Sandbox live** — set `environment=sandbox`, `dry_run=false`. Imports +
   deletes each orphan, then runs a `merge=true` validation publish to confirm
   the cleanup worked. Sandbox has the same orphan rows as production.

3. **Production live** — set `environment=production`, `dry_run=false`,
   `confirm_production="YES I HAVE TESTED ON SANDBOX"`. Run after 6pm CT.

## After successful production cleanup

Switch the pipeline back to `merge=true`:

```python
# acuops-pipeline/packages/pipeline/scripts/deploy.py:198
"isMergeWithExistingPackages": True,  # was False (orphan workaround)
```

This restores GI OData registration on every deploy and eliminates the
manual SM208000 toggling overhead.

## Risks

1. **Import validation may fail** if the IIG zip references DACs/views that
   conflict with the current state. Mitigation: import is non-destructive;
   failure aborts before delete is attempted.
2. **Delete may fail** if Acumatica refuses to remove a project still
   referenced elsewhere. Mitigation: error is reported per-project; other
   orphans still attempt cleanup.
3. **The IIG `<Table>` declarations** add `UsrIGCM*` columns to many tables.
   Those columns were already added during the original IIG install and were
   never dropped on uninstall. Re-importing without publishing means we never
   touch them. They remain as dead schema (which is what they already are).
