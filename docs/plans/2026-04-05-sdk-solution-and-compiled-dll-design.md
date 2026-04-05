# Acumatica SDK Solution & Compiled DLL — Design

**Date:** 2026-04-05
**Author:** Kevin Bibelhausen / Claude
**Status:** Draft

## Problem

AesthetikContainers defines 24 C# classes as CDATA source code in project.xml. The Acumatica GI engine cannot resolve these types when importing Generic Inquiries because the source isn't compiled into a DLL at GI import time. This caused ~25 failed deploys.

The root cause: GIs reference types like `StudioB.Containers.UsrContainer`, but that type only exists as CDATA text — there's no compiled assembly for the GI engine to load.

## Product Goal: Procurement Command Center

The DLL is the foundation for a dashboard that replaces IIG's Container Information screen. The imports team opens one screen Monday morning and sees:

**Where are my containers?** — KPI tiles: Open, In Transit, Arriving This Week, Customs Hold (red when > 0).

**What do I need to act on?** — Two grids: arrivals this week sorted by ETA (so receiving can prep), and exceptions (customs holds, late containers, stale tracking — the team's to-do list).

**What are the details?** — Click any row, detail panel opens with container fields, events timeline, PO links, and landed cost fields. Editable. Save without leaving.

### How it differs from IIG

| | IIG | AesthetikContainers |
|---|---|---|
| Dashboard | Read-only KPI widgets | Editable workspace ("single pane of glass") |
| Exceptions | Shows counts | Shows specific containers needing action and why |
| API readiness | Separate process screens (Searates/Expeditors/Vessel) | Same dashboard, data source swaps from manual to API |
| Navigation | 6+ screens to manage containers | One screen, detail panel for edits |

### Build sequence

1. **Now:** DLL + inline GIs → data layer works
2. **Next:** Dashboard screen composing GIs into the command center layout
3. **Later:** Carrier API integration replaces manual entry fields

## Reference Architecture: IIG

IIGCONTAINERMGMT (the ISV package we're replacing):

- **`Bin/IGCM.dll`** (1 MB) — pre-compiled DLL with all DACs and graphs
- **Zero `<Graph>` CDATA blocks** — no source code in project.xml
- **8 inline `<GenericInquiryScreen>` blocks** — GIs reference types from the DLL (e.g., `IGCM.DAC.IGCMPOLandedCost`)
- **24 ASPX pages** — compiled code-behind
- GI engine resolves types because the DLL is pre-compiled

## Solution: StudioB.Containers.dll

### Directory structure

```
acumatica-ci-cd/
├── lib/                              ← .gitignored, SDK DLLs
│   ├── README.md                     ← Download instructions
│   ├── PX.Data.dll                   (11 MB)
│   ├── PX.Data.BQL.Fluent.dll        (164 KB)
│   ├── PX.Data.BQL.Dynamic.dll       (40 KB)
│   ├── PX.Objects.dll                (38 MB)
│   ├── PX.Common.dll                 (235 KB)
│   └── PX.Common.Std.dll             (503 KB)
├── src/
│   └── StudioB.Containers/
│       ├── StudioB.Containers.csproj  ← net48, refs lib/
│       ├── DACs/                      ← Custom table DACs
│       │   ├── UsrContainer.cs
│       │   ├── UsrContainerEvent.cs
│       │   ├── UsrContainerPOLink.cs
│       │   ├── UsrContainerType.cs
│       │   ├── UsrPort.cs
│       │   ├── UsrFreightForwarder.cs
│       │   └── UsrContainerPrefs.cs
│       ├── Extensions/                ← DAC extensions on standard tables
│       │   ├── POOrderExt.cs
│       │   ├── POLineExt.cs
│       │   ├── POReceiptLineExt.cs
│       │   ├── ShipmentExt.cs
│       │   ├── VendorExt.cs
│       │   ├── StockItemExt.cs
│       │   └── InventoryAllocDetEnqResultExt.cs
│       └── Graphs/                    ← Graphs and graph extensions
│           ├── ContainerMaint.cs
│           ├── ContainerDatePropagation.cs
│           ├── POOrderEntry_Extension.cs
│           ├── POReceiptEntry_LandedCostExt.cs
│           ├── InventoryAllocDetEnq_Extension.cs
│           ├── FreightForwarderMaint.cs
│           ├── ContainerTypeMaint.cs
│           ├── PortMaint.cs
│           ├── ContainerPrefsMaint.cs
│           └── AesthetikContainersInstall.cs
├── Customization/
│   └── AesthetikContainers/
│       ├── project.xml               ← No <Graph> CDATA, has <File> for DLL + inline GIs
│       ├── Code/                     ← Remove (shadow copies of CDATA, now redundant)
│       └── GenericInquiryScreen_*.xml ← Remove (inlined into project.xml)
└── .gitignore                        ← Updated to exclude lib/*.dll
```

### SDK source

Acumatica 24.R2 (24.208) assemblies extracted from `ErpPackage.zip` downloaded from `builds.acumatica.com`. The ErpPackage contains `Files.zip` with the full ERP `Bin/` directory. We extract only the 6 DLLs needed for compilation.

The `lib/` directory is .gitignored. A `lib/README.md` documents the exact download and extraction steps so any developer can reproduce the setup.

### Project file (.csproj)

Target .NET Framework 4.8 (Acumatica 24.R2 requirement). Reference SDK assemblies via HintPath to `lib/`.

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <AssemblyName>StudioB.Containers</AssemblyName>
    <RootNamespace>StudioB.Containers</RootNamespace>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="PX.Data">
      <HintPath>..\..\lib\PX.Data.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="PX.Data.BQL.Fluent">
      <HintPath>..\..\lib\PX.Data.BQL.Fluent.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="PX.Objects">
      <HintPath>..\..\lib\PX.Objects.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="PX.Common">
      <HintPath>..\..\lib\PX.Common.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="PX.Common.Std">
      <HintPath>..\..\lib\PX.Common.Std.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>
</Project>
```

`Private=false` prevents copying SDK DLLs to output — they already exist on the Acumatica instance.

### What changes in project.xml

**Remove:**
- All 24 `<Graph>` CDATA blocks (lines 3–2039)

**Add:**
- `<File AppRelativePath="Bin\StudioB.Containers.dll" />` — DLL reference
- 7 `<GenericInquiryScreen>` blocks inlined from standalone XML files

**Keep unchanged:**
- `<Page>` blocks (UI customizations on PO, SO, IN, AP screens)
- `<File>` blocks for ASPX pages (SB501000, SB302000, etc.)
- `<ScreenWithRights>` (SiteMap, roles, MUI workspace)
- `<Table>` blocks (custom columns)
- Entity endpoint XML

### Build flow

```
Developer:
  1. Download ErpPackage.zip from builds.acumatica.com (one-time)
  2. Extract PX.* DLLs into lib/ (documented in lib/README.md)
  3. dotnet build src/StudioB.Containers/StudioB.Containers.csproj
     → bin/Debug/net48/StudioB.Containers.dll
  4. Copy DLL to Customization/AesthetikContainers/Bin/
  5. Deploy via existing CI/CD pipeline

CI/CD (future):
  - Build step validates compilation before packaging
  - Catches errors before they reach the server
  - No more app pool restarts for typos
```

### GI mapping to dashboard components

| GI XML file | Dashboard component | Key DACs |
|---|---|---|
| GenericInquiryScreen_POContainers | KPI tiles + main container list | UsrContainer |
| GenericInquiryScreen_ArrivingThisWeek | Arrivals grid (left) | UsrContainer (ETA filter) |
| GenericInquiryScreen_ContainersNeedingAttention | Exceptions grid (right) | UsrContainer (status filter) |
| GenericInquiryScreen_POContainerLines | Detail panel — PO links | UsrContainerPOLink + POOrder + POLine |
| GenericInquiryScreen_ContainerEvents | Detail panel — events timeline | UsrContainerEvent |
| GenericInquiryScreen_LandedCostSummary | Detail panel — landed cost | UsrContainerPOLink + POReceiptLine |
| GenericInquiryScreen_InventoryQuantityDetail | Cross-reference (existing) | InventoryItem + INSiteStatus |

### What this enables

- **GI creation works** — root cause of 25 failed deploys resolved
- **Local compilation** — errors caught before deploy
- **IntelliSense** — proper IDE support for DAC development
- **CI/CD validation** — build step before packaging
- **Dashboard foundation** — GIs power the Procurement Command Center
- **Testability** — can write unit tests against compiled DACs

## Constraints

- Must target .NET Framework 4.8 (Acumatica 24.R2)
- SDK assemblies must match deployed version (24.208)
- When Acumatica upgrades, SDK references need updating
- `lib/` is .gitignored — developers need to run setup once
- macOS can build net48 via `dotnet build` but cannot run the output (Windows-only runtime)

## Risks

| Risk | Mitigation |
|---|---|
| DLL signing requirement | Check if Acumatica instance requires signed assemblies. IIG's IGCM.dll is unsigned (PublicKeyToken=null). |
| Namespace mismatch | GI XMLs already use `StudioB.Containers.*` — matches the project namespace. Verified. |
| Missing assembly references | Start with core 6 DLLs. If compilation fails, extract additional DLLs from ErpPackage.zip. |
| CDATA extraction errors | Extract one class at a time, compile after each, catch errors incrementally. |
| `dotnet build` on macOS for net48 | Requires mono or .NET SDK with net48 targeting pack. May need `Microsoft.NETFramework.ReferenceAssemblies` NuGet package. |

## Heritage Fabrics specifics

- Instance: heritagefabrics.acumatica.com
- Version: 24.208 (24.R2)
- CompanyID 2 = Heritage Fabrics (production)
- CompanyID 3 = Heritage Test
- ALSO_PUBLISH must list ALL published projects (ISVs included)
- publishBegin is instance-wide — Heritage Test shares prod instance
