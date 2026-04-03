# Debug SB501000 Screen Creation — Showstopper

## Priority: P0 — blocks IIG sunset and container tracking go-live

## Problem Statement

SB501000 (Container Maintenance) ASPX file is deployed on production (HTTP HEAD returns 200), the ContainerMaint graph is compiled and running, the SiteMap entry exists in SM200520 — but the screen will NOT load. Navigating to ScreenId=SB501000 redirects to the Acumatica home page.

## Root Cause Chain

1. The `<File AppRelativePath="Pages\SB\SB501000.aspx">` element in project.xml deployed the ASPX to the CstPublished overlay directory, NOT the physical `Pages/SB/` directory
2. Cloud Acumatica's router looks for screens in the physical directory, not CstPublished
3. The CustomizationPlugin SQL (`SetSiteMapGraphType`) that was supposed to register the screen failed with `Invalid column name 'ScreenID'` — the SiteMap table on this Acumatica version (24.208) uses different column names than assumed
4. The CREATE NEW SCREEN wizard in the Customization Project Editor is the Acumatica-supported way to create new screens on cloud instances, but it fails because it cannot resolve `StudioB.Containers` as a valid Graph Namespace — despite the graph being compiled and running

## What We Tried (All Failed)

| Approach | Result |
|----------|--------|
| `<File>` element in project.xml with CDATA ASPX content | ASPX goes to CstPublished overlay, not physical Pages/SB/ — screen won't route |
| CustomizationPlugin SQL to INSERT into SiteMap | `Invalid column name 'ScreenID'` — table schema different on cloud 24.208 |
| Manual SiteMap entry via SM200520 (Site Map screen) | Entry saved but screen still redirects to home — missing internal fields |
| SiteMap entry via Customization Project Editor → Site Map section | Same result — entry exists but screen doesn't route |
| CREATE NEW SCREEN with `StudioB.Containers` namespace | "Invalid graph namespace" error |
| CREATE NEW SCREEN with `StudioB.Containers.ContainerMaint` as namespace | Still doesn't resolve |
| CREATE NEW SCREEN with blank namespace | Required field |
| CREATE NEW SCREEN with `PX.Objects` as placeholder | "Object Name cannot be empty, Content cannot be empty" |
| CUSTOMIZE EXISTING SCREEN with SB.50.10.00 | "Nullable object must have a value" — screen not in internal registry |
| Direct URL `/Pages/SB/SB501000.aspx` | Redirects to home — ASPX not in physical directory |

## What IS Working

- AesthetikContainers published with all 6 Page elements (AP303000 ParentId fix applied)
- All DAC extensions compiled (ContainerMaint, POOrderExt, POLineExt, StockItemExt, etc.)
- Custom fields visible on PO301000, IN202500, PO302000, AP303000, SO302000, IN402000
- ContainerTracking REST endpoint (EntityEndpoint XML deployed)
- IIG unpublished from production
- Kevin has IIG backup .zips for rollback

## Environment

- **Instance:** heritagefabrics.acumatica.com (cloud-hosted)
- **Version:** 24.208
- **Tenant:** Heritage Fabrics (production)
- **Package:** AesthetikContainers (Level 3, published)
- **Graph:** StudioB.Containers.ContainerMaint (compiled, IsActive()=true)
- **DACs:** UsrContainer, UsrContainerEvent, UsrContainerPOLink (tables exist, data present)
- **ASPX:** SB501000.aspx delivered via `<File>` element — in CstPublished but not physical Pages/SB/

## Screen Specification

SB501000 is a FormDetail screen with:

**Header (PXFormView, DataMember="Container"):**
- ContainerCD (PXSelector) — key field
- Status (PXDropDown)
- CarrierCode, VesselName, VesselIMO, ContainerType (PXTextEdit)
- ETD, ETA, ATA (PXDateTimeEdit)
- PortOfLoading, PortOfDischarge (PXTextEdit)
- BookingRef, BillOfLading, VoyageNbr, SealNbr (PXTextEdit)

**Detail Tabs (PXTab):**
- Tab 1 "Events" (PXGrid, DataMember="Events"): EventDateTime, NormalizedEventCode, Description, LocationName
- Tab 2 "PO Links" (PXGrid, DataMember="POLinks"): OrderType, OrderNbr, LineNbr

**Graph:** StudioB.Containers.ContainerMaint
- Views: Container (UsrContainer), Events (UsrContainerEvent), POLinks (UsrContainerPOLink)
- Action: RefreshTracking (PXAction, placeholder)
- Persist override: propagates ETA to linked POs via ContainerDatePropagation

## Questions to Answer

1. **How does Acumatica cloud register new screens?** The CREATE NEW SCREEN wizard is the only path — what does it need to resolve a custom graph namespace? Does the graph need to be in a .dll extension library instead of CDATA?

2. **What is the actual SiteMap table schema on 24.208?** The CustomizationPlugin failed because `ScreenID` is not a valid column. What are the real column names? Is it `ScreenId` (different casing) or a completely different schema?

3. **Can we bypass the CREATE NEW SCREEN wizard?** Is there a way to register a screen directly through the Customization API or by adding specific elements to project.xml that trigger physical ASPX deployment (not just CstPublished overlay)?

4. **What's the difference between `<File>` deployment and CREATE NEW SCREEN deployment?** The `<File>` element puts ASPX in CstPublished. CREATE NEW SCREEN puts it somewhere else. Where, and why does only the latter work for routing?

5. **Can a C# extension library (.dll) solve the namespace resolution?** If the graph is compiled into a .dll via a .csproj in the customization package instead of inline CDATA, will CREATE NEW SCREEN be able to resolve the namespace?

## Files

- `acumatica-ci-cd/Customization/AesthetikContainers/project.xml` — full customization package
- `acumatica-ci-cd/Customization/AesthetikContainers/EntityEndpoint_24_200_001_ContainerTracking.xml` — REST endpoint definition
- `acumatica-ci-cd/Customization/AesthetikContainers/Code/` — standalone .cs files (DACs + graphs)
- `webhook-router/src/lib/acumatica-containers.ts` — CRUD operations using the REST endpoint
- `webhook-router/src/lib/carriers/container-types.ts` — normalized event taxonomy

## AcuDev Training Item

After this is resolved, train AcuDev on:
1. **Screen creation on cloud Acumatica** — CREATE NEW SCREEN workflow, namespace resolution requirements, FormDetail/FormGrid templates
2. **SiteMap registration** — proper way to register screens in customization packages (not raw SQL)
3. **ASPX deployment on cloud vs on-premise** — `<File>` element limitations on cloud instances
4. **Customization Project Editor automation** — if browser-based screen creation is the only path, AcuDev needs browser capabilities for this step
