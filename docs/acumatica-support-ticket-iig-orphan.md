# Email to VAR — Orphan Customization Metadata Cleanup Request

**To:** [VAR contact]
**Subject:** Heritage Fabrics — need Acumatica support to clean orphan publish metadata from removed customization projects

---

Hi [Name],

We need an Acumatica support case opened for our production tenant (`heritagefabrics.acumatica.com`). Residual metadata from an old IIG package removal is blocking multi-project publishes, and I need Acumatica to clean it up at the database level. Details below — please forward to Acumatica support as-is.

## What's broken

Every `publishBegin` call (REST API or SM204505 UI) with `isMergeWithExistingPackages: true` fails with the generic Acumatica error:

> An error has occurred. Please report this error to the technical support and attach the information provided above.

No actionable detail. The publish does not complete. This happens whether I trigger it from the UI or from the Customization API.

## What I'm pretty sure is causing it

We removed three customization projects from the tenant in March and April 2026:

- `IIGCONTAINERMGMT[24.204.0004][R19]1` (IIG ISV, removed March 2026)
- `IIGHFContainerMods[24.204.0004][R04]` (IIG ISV, removed March 2026)
- `AesthetikContainerGIs` (our own package, determined to be a duplicate of GIs already shipped inside `AesthetikContainers` and deleted on 2026-04-09)

They're gone from the Customization Projects screen (SM204505), but something in the publish state still references them. When Acumatica tries to merge any new publish with "existing published packages," it runs into these ghost entries and crashes.

The `AesthetikContainerGIs` entry is particularly useful for diagnosis — we can confirm it has been gone from our source repo and co-publish lists since 2026-04-09, the project content was never anything unique (every GI in it was a verbatim duplicate of GIs already shipping in `AesthetikContainers`), and yet the orphan row persists and still blocks `merge=true`. This rules out any theory that the orphan state is being recreated by our pipeline.

## Current workaround (and why it's now biting us)

Since April 3 we've been using `isMergeWithExistingPackages: false` in our CI/CD pipeline as a workaround. That got us through OK for a while — DAC extensions, DLLs, and SQL migrations all deploy fine with `merge=false`. But we just discovered a side effect: with `merge=false`, Acumatica only extracts website files (`.aspx`, `.aspx.cs`) for the **primary** project passed as `projectNames[0]`. All co-published projects in the same call get their DACs/DLLs/SQL deployed but their ASPX files are silently skipped.

We didn't notice this until yesterday (2026-04-06) when we pushed our first customization that adds new ASPX files to a co-published project — the Procurement Command Center (`SB501000`). The deploy reported success, `publishEnd` returned `isCompleted: true`, and the publish log said:

```
[AesthetikContainers] All tables, columns, indexes, and migration verified/created.
```

But navigating to the screen returns:

```
System.Web.HttpException: The file '/Pages/SB/SB501000.aspx' does not exist.
```

SM204505 shows only `AesthetikWMS` with the "Published" checkbox, even though `publishBegin` was called with `projectNames` listing all 8 projects including `AesthetikContainers`.

## Proof the project itself is clean

Today I ran **SM204505 → ... → Validations → Validate Highlighted Project** on `AesthetikContainers`. Acumatica's own validator came back clean:

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
```

So the project content is fine, `SB501000.aspx` is in the imported content, and Acumatica's own validator approves it. The blocker is the orphan metadata, not the project.

## What I need from Acumatica support

Database-level cleanup of orphaned publish metadata referencing:

- `IIGCONTAINERMGMT[24.204.0004][R19]1`
- `IIGHFContainerMods[24.204.0004][R04]`
- `AesthetikContainerGIs`

I suspect the relevant tables are `CustProject`, `CustomizationHistoryLog`, and possibly others in the publish/compile pipeline — but I'd rather Acumatica engineering do the cleanup properly than guess at the SQL.

Once the cleanup is done, `publishBegin` with `isMergeWithExistingPackages: true` should work normally again, and I can drop the `--no-merge` workaround in our CI/CD.

## Environment details

- **Instance:** `heritagefabrics.acumatica.com`
- **Tenant:** `Heritage Fabrics`
- **Version:** 24.208.0020 (Acumatica ERP 2024 R2 Update 8)
- **Currently published:** `AesthetikWMS` only
- **Should be published:** `AesthetikWMS`, `AesthetikContainers`, `StudioBAcuOps`, `AcumaticaPacejetCustomFields24.1001`, `KNCentralizedLicense[24.200.0118][19NOV2024][V03]3`, `Ramp`, `FusionWMSBasic[9.4.11][24.201.0052]`, `FusionWMSAdvanced[9.4.11][24.201.0052]`, `AsthetikTheme`

## Reproduction steps

If Acumatica support wants to see the failure themselves:

1. Log into `heritagefabrics.acumatica.com` as admin
2. Navigate to SM204505 (Customization Projects)
3. Observe: only `AesthetikWMS` has the "Published" checkbox
4. Attempt a manual Publish from the UI with any combination of projects selected and the default merge=true setting
5. Observe: generic error page ("An error has occurred. Please report this error to the technical support…")

## Impact

This is blocking our internal development team from deploying new customizations cleanly. The Procurement Command Center feature has been sitting undeployed for a day because of this. We also have a longer list of queued improvements that will hit the same wall as soon as they add or modify ASPX files.

Not a SEV-1 (no data loss, no users blocked from work), but definitely a high-priority blocker on our side. Would appreciate a quick turnaround.

Happy to provide any additional logs, screenshots, or access Acumatica needs to work the case.

Thanks,
Kevin Bibelhausen
kevin@heritagefabrics.com

---

## For VAR reference (not for forwarding to Acumatica)

Related context you might want if Acumatica has questions back:

- We've had IIG-related issues since March — there's history with this tenant.
- Our CI/CD repo (`studio-b-ai/acumatica-ci-cd`) commit `b5096c7` (2026-04-03) added the `--no-merge` flag workaround.
- The most recent run showing the symptom is GitHub Actions run `24057444112` on 2026-04-07 at 00:05 UTC — I can pull logs if needed.
- We've been incredibly disciplined about NOT touching the publish state manually. Everything has gone through the Customization API via our pipeline. This isn't user error.
