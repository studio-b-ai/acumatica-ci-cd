# StudioB.Containers DLL — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compile all AesthetikContainers DACs and graphs into `StudioB.Containers.dll`, ship it in the customization package, inline the GI XML files, and remove all CDATA source code from project.xml — enabling GI creation and the Procurement Command Center dashboard.

**Architecture:** Extract 24 C# classes from project.xml CDATA blocks into proper .cs files under `src/StudioB.Containers/`. Build against Acumatica 24.R2 SDK assemblies in `lib/`. Ship the compiled DLL as `Bin\StudioB.Containers.dll` in the customization package, matching the IIG ISV pattern.

**Tech Stack:** .NET Framework 4.8, Acumatica 24.R2 SDK (PX.Data, PX.Objects), MSBuild via `dotnet build`

---

## Prerequisites

- SDK DLLs already extracted to `lib/` (PX.Data.dll, PX.Objects.dll, PX.Common.dll, PX.Common.Std.dll, PX.Data.BQL.Fluent.dll, PX.Data.BQL.Dynamic.dll, PX.Web.Customization.dll)
- Working in worktree: `.claude/worktrees/quirky-spence`

---

### Task 1: Create the .csproj and verify SDK references compile

**Files:**
- Create: `src/StudioB.Containers/StudioB.Containers.csproj`

**Step 1: Create directory structure**

```bash
mkdir -p src/StudioB.Containers/DACs
mkdir -p src/StudioB.Containers/Extensions
mkdir -p src/StudioB.Containers/Graphs
```

**Step 2: Create .csproj file**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <AssemblyName>StudioB.Containers</AssemblyName>
    <RootNamespace>StudioB.Containers</RootNamespace>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
    <LangVersion>7.3</LangVersion>
  </PropertyGroup>

  <!-- Required for net48 targeting on non-Windows -->
  <ItemGroup>
    <PackageReference Include="Microsoft.NETFramework.ReferenceAssemblies" Version="1.0.3" PrivateAssets="all" />
  </ItemGroup>

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
    <Reference Include="PX.Web.Customization">
      <HintPath>..\..\lib\PX.Web.Customization.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="System.Configuration" />
  </ItemGroup>
</Project>
```

**Step 3: Create a minimal test file to verify compilation**

Create `src/StudioB.Containers/DACs/_CompileTest.cs`:

```csharp
// Temporary file to verify SDK references resolve correctly.
// Delete after Task 2 is complete.
using PX.Data;
using PX.Data.BQL;
using PX.Objects.PO;

namespace StudioB.Containers
{
    // Verifies PX.Data, PX.Data.BQL, and PX.Objects all resolve
    public class CompileTest : IBqlField { }
}
```

**Step 4: Build and verify**

Run: `dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED. If it fails on net48 targeting pack, the `Microsoft.NETFramework.ReferenceAssemblies` NuGet package should resolve it. If `dotnet` is not installed, install via `brew install dotnet`.

**Step 5: Commit**

```bash
git add src/StudioB.Containers/StudioB.Containers.csproj src/StudioB.Containers/DACs/_CompileTest.cs
git commit -m "feat: scaffold StudioB.Containers project with Acumatica SDK references"
```

---

### Task 2: Extract DAC extension classes (7 files)

These are extensions on standard Acumatica DACs — adding custom fields to POOrder, POLine, etc.

**Files:**
- Create: `src/StudioB.Containers/Extensions/POOrderExt.cs`
- Create: `src/StudioB.Containers/Extensions/POLineExt.cs`
- Create: `src/StudioB.Containers/Extensions/InventoryAllocDetEnqResultExt.cs`
- Create: `src/StudioB.Containers/Extensions/StockItemExt.cs`
- Create: `src/StudioB.Containers/Extensions/POReceiptLineExt.cs`
- Create: `src/StudioB.Containers/Extensions/ShipmentExt.cs`
- Create: `src/StudioB.Containers/Extensions/VendorExt.cs`
- Delete: `src/StudioB.Containers/DACs/_CompileTest.cs`

**Step 1: Extract each class from project.xml CDATA blocks**

For each `<Graph ClassName="X">` block in `Customization/AesthetikContainers/project.xml`:
1. Find the `<Graph ClassName="POOrderExt"` block (starts at line 3)
2. Copy the content between `<![CDATA[` and `]]>`
3. Write it to the corresponding .cs file
4. Repeat for all 7 DAC extension classes

The class names and their source line ranges in project.xml:
- `POOrderExt` — lines 4-33 → `Extensions/POOrderExt.cs`
- `POLineExt` — lines 37-71 → `Extensions/POLineExt.cs`
- `InventoryAllocDetEnqResultExt` — lines 75-93 → `Extensions/InventoryAllocDetEnqResultExt.cs`
- `StockItemExt` — lines 352-385 → `Extensions/StockItemExt.cs`
- `POReceiptLineExt` — lines 389-425 → `Extensions/POReceiptLineExt.cs`
- `ShipmentExt` — lines 474-507 → `Extensions/ShipmentExt.cs`
- `VendorExt` — lines 510-547 → `Extensions/VendorExt.cs`

**Step 2: Delete _CompileTest.cs**

```bash
rm src/StudioB.Containers/DACs/_CompileTest.cs
```

**Step 3: Build and verify**

Run: `dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED with 7 source files compiled.

**Step 4: Commit**

```bash
git add src/StudioB.Containers/Extensions/
git commit -m "feat: extract 7 DAC extension classes from project.xml CDATA"
```

---

### Task 3: Extract custom table DACs (7 files)

These define the custom tables — UsrContainer, UsrContainerEvent, etc.

**Files:**
- Create: `src/StudioB.Containers/DACs/UsrContainer.cs`
- Create: `src/StudioB.Containers/DACs/UsrContainerEvent.cs`
- Create: `src/StudioB.Containers/DACs/UsrContainerPOLink.cs`
- Create: `src/StudioB.Containers/DACs/UsrContainerType.cs`
- Create: `src/StudioB.Containers/DACs/UsrPort.cs`
- Create: `src/StudioB.Containers/DACs/UsrFreightForwarder.cs`
- Create: `src/StudioB.Containers/DACs/UsrContainerPrefs.cs`

**Step 1: Extract from project.xml CDATA blocks**

Line ranges:
- `UsrContainer` — lines 551-763 → `DACs/UsrContainer.cs`
- `UsrContainerEvent` — lines 767-868 → `DACs/UsrContainerEvent.cs`
- `UsrContainerPOLink` — lines 872-926 → `DACs/UsrContainerPOLink.cs`
- `UsrFreightForwarder` — lines 1546-1685 → `DACs/UsrFreightForwarder.cs`
- `UsrContainerType` — lines 1702-1805 → `DACs/UsrContainerType.cs`
- `UsrPort` — lines 1809-1896 → `DACs/UsrPort.cs`
- `UsrContainerPrefs` — lines 1900-1994 → `DACs/UsrContainerPrefs.cs`

**Step 2: Build and verify**

Run: `dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED with 14 source files compiled.

**Step 3: Commit**

```bash
git add src/StudioB.Containers/DACs/
git commit -m "feat: extract 7 custom table DACs from project.xml CDATA"
```

---

### Task 4: Extract graph classes (10 files)

Graphs (PXGraph) and graph extensions that contain business logic.

**Files:**
- Create: `src/StudioB.Containers/Graphs/ContainerMaint.cs`
- Create: `src/StudioB.Containers/Graphs/ContainerDatePropagation.cs`
- Create: `src/StudioB.Containers/Graphs/POOrderEntry_Extension.cs`
- Create: `src/StudioB.Containers/Graphs/POReceiptEntry_LandedCostExt.cs`
- Create: `src/StudioB.Containers/Graphs/InventoryAllocDetEnq_Extension.cs`
- Create: `src/StudioB.Containers/Graphs/FreightForwarderMaint.cs`
- Create: `src/StudioB.Containers/Graphs/ContainerTypeMaint.cs`
- Create: `src/StudioB.Containers/Graphs/PortMaint.cs`
- Create: `src/StudioB.Containers/Graphs/ContainerPrefsMaint.cs`
- Create: `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs`

**Step 1: Extract from project.xml CDATA blocks**

Line ranges:
- `POOrderEntry_Extension` — lines 97-223 → `Graphs/POOrderEntry_Extension.cs`
- `InventoryAllocDetEnq_Extension` — lines 226-291 → `Graphs/InventoryAllocDetEnq_Extension.cs`
- `ContainerDatePropagation` — lines 294-349 → `Graphs/ContainerDatePropagation.cs`
- `POReceiptEntry_LandedCostExt` — lines 429-471 → `Graphs/POReceiptEntry_LandedCostExt.cs`
- `ContainerMaint` — lines 928-1028 → `Graphs/ContainerMaint.cs`
- `AesthetikContainersInstall` — lines 1031-1543 → `Graphs/AesthetikContainersInstall.cs`
- `FreightForwarderMaint` — lines 1688-1698 → `Graphs/FreightForwarderMaint.cs`
- `ContainerTypeMaint` — lines 1997-2007 → `Graphs/ContainerTypeMaint.cs`
- `PortMaint` — lines 2010-2020 → `Graphs/PortMaint.cs`
- `ContainerPrefsMaint` — lines 2023-2038 → `Graphs/ContainerPrefsMaint.cs`

**Important:** `AesthetikContainersInstall` uses `Customization.CustomizationPlugin` — this is why we added `PX.Web.Customization.dll` to lib/. It also uses `System.Configuration` and `System.Data.SqlClient` which are framework assemblies (already available via net48 targeting).

**Step 2: Build and verify**

Run: `dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED with 24 source files compiled.

**Step 3: Commit**

```bash
git add src/StudioB.Containers/Graphs/
git commit -m "feat: extract 10 graph classes from project.xml CDATA"
```

---

### Task 5: Update project.xml — remove CDATA, add DLL reference

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`

**Step 1: Remove all 24 `<Graph>` blocks**

Delete everything from line 3 (`<Graph ClassName="POOrderExt"`) through the last `</Graph>` before the first `<Page>` block. This is approximately lines 3–2039.

**Step 2: Add DLL file reference**

Add this line in the `<File>` section (after the ASPX file blocks, before `<ScreenWithRights>`):

```xml
<File AppRelativePath="Bin\StudioB.Containers.dll" />
```

**Step 3: Verify project.xml is valid XML**

Run: `python3 -c "import xml.etree.ElementTree as ET; ET.parse('Customization/AesthetikContainers/project.xml'); print('Valid XML')"`
Expected: `Valid XML`

**Step 4: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "refactor: remove CDATA source blocks, add StudioB.Containers.dll reference"
```

---

### Task 6: Inline GI XML files into project.xml

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_ArrivingThisWeek.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_ContainerEvents.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_ContainersNeedingAttention.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_InventoryQuantityDetail.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_LandedCostSummary.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_POContainerLines.xml`
- Remove: `Customization/AesthetikContainers/GenericInquiryScreen_POContainers.xml`

**Step 1: Read each standalone GI XML file**

Each file contains a `<GenericInquiryScreen>` block. Read all 7 files.

**Step 2: Insert GI blocks into project.xml**

Add each `<GenericInquiryScreen>` block inside the `<Customization>` root element, after the `<File>` blocks and before `<ScreenWithRights>`. This matches IIG's structure.

**Step 3: Delete standalone GI XML files**

```bash
rm Customization/AesthetikContainers/GenericInquiryScreen_*.xml
```

**Step 4: Verify XML validity**

Run: `python3 -c "import xml.etree.ElementTree as ET; ET.parse('Customization/AesthetikContainers/project.xml'); print('Valid XML')"`

**Step 5: Commit**

```bash
git add Customization/AesthetikContainers/
git commit -m "feat: inline 7 GI definitions into project.xml (matches IIG pattern)"
```

---

### Task 7: Clean up redundant Code/ directory

**Files:**
- Remove: `Customization/AesthetikContainers/Code/` (shadow copies of CDATA, now redundant)

**Step 1: Verify Code/ files match what we extracted**

Compare `Code/Graph/POOrderEntry_Extension.cs` with `src/StudioB.Containers/Graphs/POOrderEntry_Extension.cs` to confirm they're duplicates.

**Step 2: Remove Code/ directory**

```bash
rm -rf Customization/AesthetikContainers/Code/
```

**Step 3: Commit**

```bash
git add -A Customization/AesthetikContainers/Code/
git commit -m "cleanup: remove redundant Code/ directory (source now in src/StudioB.Containers/)"
```

---

### Task 8: Update lib/README.md and design doc

**Files:**
- Modify: `lib/README.md` — add PX.Web.Customization.dll to the table
- Modify: `docs/plans/2026-04-05-sdk-solution-and-compiled-dll-design.md` — update status to Approved

**Step 1: Update lib/README.md**

Add `PX.Web.Customization.dll` (2.2 MB, CustomizationPlugin base class) to the DLL table and extraction command.

**Step 2: Commit**

```bash
git add lib/README.md docs/plans/
git commit -m "docs: update lib README and design doc with final DLL list"
```

---

### Task 9: End-to-end build verification

**Step 1: Clean build**

```bash
dotnet clean src/StudioB.Containers/StudioB.Containers.csproj
dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
```

Expected: BUILD SUCCEEDED, producing `src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll`

**Step 2: Verify DLL contains expected types**

```bash
strings src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll | grep 'StudioB.Containers.Usr' | sort -u
```

Expected output should include:
- `StudioB.Containers.UsrContainer`
- `StudioB.Containers.UsrContainerEvent`
- `StudioB.Containers.UsrContainerPOLink`
- `StudioB.Containers.UsrContainerType`
- `StudioB.Containers.UsrPort`
- `StudioB.Containers.UsrFreightForwarder`
- `StudioB.Containers.UsrContainerPrefs`

**Step 3: Verify project.xml references match compiled types**

```bash
grep 'GITable.*Name="StudioB' Customization/AesthetikContainers/project.xml | sort -u
```

Every `Name="StudioB.Containers.X"` should match a type in the DLL output from Step 2.

**Step 4: Copy DLL to customization package location**

```bash
mkdir -p Customization/AesthetikContainers/Bin
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/
```

**Step 5: Final commit**

```bash
git add Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "feat: ship compiled StudioB.Containers.dll in customization package"
```

---

## Post-Implementation: Deploy to Heritage Test

**NOT part of this plan.** After merging, deploy to Heritage Test (CompanyID 3) first:

1. Run the existing CI/CD pipeline targeting Heritage Test
2. Verify GIs appear in the Acumatica GI designer
3. Verify container screens (SB501000, SB302000, etc.) still work
4. Verify no compilation errors in the Customization Projects screen
5. Only then consider deploying to production (CompanyID 2)

## Summary

| Task | What | Files | Commit |
|------|------|-------|--------|
| 1 | Scaffold .csproj, verify SDK compiles | 2 new | `feat: scaffold project` |
| 2 | Extract 7 DAC extensions | 7 new | `feat: extract DAC extensions` |
| 3 | Extract 7 custom table DACs | 7 new | `feat: extract custom DACs` |
| 4 | Extract 10 graphs | 10 new | `feat: extract graphs` |
| 5 | Remove CDATA from project.xml, add DLL ref | 1 modified | `refactor: remove CDATA` |
| 6 | Inline 7 GI XMLs, delete standalone files | 1 modified, 7 deleted | `feat: inline GIs` |
| 7 | Remove redundant Code/ directory | 6 deleted | `cleanup: remove Code/` |
| 8 | Update docs | 2 modified | `docs: update` |
| 9 | End-to-end build + ship DLL | 1 new (binary) | `feat: ship DLL` |
