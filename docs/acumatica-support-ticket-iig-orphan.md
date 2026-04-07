# Acumatica Support Ticket — Orphan IIG Metadata Blocking merge=True Publish

**Instance:** heritagefabrics.acumatica.com
**Version:** 24.208.0020 (24 R2)
**Severity:** High — blocks multi-project CI/CD publishes
**Workaround in place:** `isMergeWithExistingPackages: false` (introduces separate issue — see Impact)

---

## Summary

We removed the IIG Container Management ISV (`IIGCONTAINERMGMT[24.204.0004][R19]1` and `IIGHFContainerMods[24.204.0004][R04]`) from our tenant in March 2026. The projects are gone from the Customization Projects screen (SM204505), but residual metadata in the publish state causes every `publishBegin` call with `isMergeWithExistingPackages: true` to fail with a generic error. We need the orphaned IIG publish metadata cleaned from the database so we can resume normal merge-enabled publishes.

## Environment

- **Instance:** `heritagefabrics.acumatica.com`
- **Company/Tenant:** `Heritage Fabrics`
- **Acumatica Version:** 24.208.0020 (Acumatica ERP 2024 R2)
- **Published customization projects today:** `AesthetikWMS` (only)
- **Projects that should be published:** `AesthetikWMS`, `AesthetikContainers`, `StudioBAcuOps`, `AcumaticaPacejetCustomFields24.1001`, `KNCentralizedLicense[24.200.0118][19NOV2024][V03]3`, `Ramp`, `FusionWMSBasic[9.4.11][24.201.0052]`, `FusionWMSAdvanced[9.4.11][24.201.0052]`, `AsthetikTheme`
- **Removed IIG projects (source of orphan metadata):** `IIGCONTAINERMGMT[24.204.0004][R19]1`, `IIGHFContainerMods[24.204.0004][R04]`

## Symptom

### With `isMergeWithExistingPackages: true` (normal merge publish)

The `publishBegin` API call or a manual Publish from SM204505 returns the Acumatica generic error page:

> An error has occurred. Please report this error to the technical support and attach the information provided above.

No actionable detail in the response. The publish does not complete. We have reproduced this from both the REST Customization API and the UI (SM204505 → Publish).

### With `isMergeWithExistingPackages: false` (current workaround)

`publishBegin` succeeds, but Acumatica only deploys website files (ASPX, ASPX.CS) for the **primary** project passed in `projectNames[0]`. All co-published projects in the same call have:
- DACs loaded correctly (DLLs deploy)
- SQL migration scripts run (tables/columns verified)
- **Website file extraction silently skipped**

For example, today's production publish ran successfully for AesthetikWMS + AesthetikContainers + StudioBAcuOps + ISV packages. The `publishEnd` API returned `isCompleted: true` and the log contained:

```
[AesthetikContainers] All tables, columns, indexes, and migration verified/created.
```

But `/Pages/SB/SB501000.aspx` (defined inline in AesthetikContainers/project.xml as a `<File>` element with CDATA source) was not written to disk. Navigation to `?ScreenId=SB501000` returns:

```
System.Web.HttpException: The file '/Pages/SB/SB501000.aspx' does not exist.
```

SM204505 shows only `AesthetikWMS` with the "Published" checkbox, even though `publishBegin` was called with `projectNames` including all 8 projects.

## Evidence AesthetikContainers itself is valid

Ran **SM204505 → ... → Validations → Validate Highlighted Project** on `AesthetikContainers` today (2026-04-07):

```
AesthetikContainers
No errors or warnings have been found during validation.
Validation has completed successfully.

File | Bin\StudioB.Containers.dll — Validation has completed successfully.
File | Pages\SB\SB302000.aspx — Validation has completed successfully.
File | Pages\SB\SB302000.aspx.cs — Validation has completed successfully.
File | Pages\SB\SB302010.aspx — Validation has completed successfully.
File | Pages\SB\SB302010.aspx.cs — Validation has completed successfully.
File | Pages\SB\SB302020.aspx — Validation has completed successfully.
File | Pages\SB\SB302020.aspx.cs — Validation has completed successfully.
File | Pages\SB\SB302030.aspx — Validation has completed successfully.
File | Pages\SB\SB302030.aspx.cs — Validation has completed successfully.
File | Pages\SB\SB501000.aspx — Validation has completed successfully.
File | Pages\SB\SB501000.aspx.cs — Validation has completed successfully.
...
```

This confirms:
1. `AesthetikContainers` is a clean, valid customization project.
2. The `SB501000.aspx` file IS inside the project's imported content.
3. The problem is not with the project itself — it is with the publish engine's handling of this specific tenant's metadata state.

## Timeline

| Date | Event |
|------|-------|
| Pre-March 2026 | IIG Container Management packages installed on `heritagefabrics.acumatica.com` |
| March 2026 | IIG unpublished and removed from SM204505 as part of migration to our own `AesthetikContainers` customization |
| March 2026 | Manual publishes began failing intermittently with generic error |
| 2026-04-03 | Added `isMergeWithExistingPackages: false` workaround to CI/CD (PR #150) |
| 2026-04-06 | First customization that added new ASPX files (Procurement Command Center — `SB501000.aspx`) |
| 2026-04-07 | Discovered `merge=false` does not extract files for co-published projects |

## What We Need

Please run a database cleanup on our instance to remove orphaned publish metadata referencing `IIGCONTAINERMGMT[24.204.0004][R19]1` and `IIGHFContainerMods[24.204.0004][R04]`. These packages no longer exist in SM204505 but something in the publish state still references them.

We suspect the relevant tables are:
- `CustomizationProject`
- `CustomizationHistoryLog`
- Possibly others in the publish/compile pipeline

After cleanup, we expect `publishBegin` with `isMergeWithExistingPackages: true` to succeed normally.

## Reproduction Steps (if needed)

1. On `heritagefabrics.acumatica.com`, navigate to SM204505
2. Observe: only `AesthetikWMS` has "Published" checkbox (despite all the projects being imported and validated)
3. Attempt a manual Publish from the UI with any combination of projects selected and merge=True
4. Observe: generic error page ("An error has occurred")

## Related

- CI/CD repo commit `b5096c7` (2026-04-03) added the `--no-merge` flag workaround
- CI/CD repo commit `0fd297b` (2026-04-06) added SQL `ALTER TABLE` scripts for new UsrContainer columns (which did run successfully even under `merge=false`)
- Run ID `24057444112` (2026-04-07 00:05 UTC) is the most recent attempt showing the symptom — logs available on request

## Contact

Kevin Bibelhausen — kevin@heritagefabrics.com
