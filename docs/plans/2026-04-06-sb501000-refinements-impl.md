# SB501000 Refinements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add transport mode field, vendor visibility, PO line details, and SiteMap title fix to the Procurement Command Center.

**Architecture:** Add TransportMode field to UsrContainer DAC, expand the POLinks view with LeftJoins to POOrder/BAccount/POLine/InventoryItem for read-only vendor and line data, update the ASPX grid columns, and fix the SiteMap title in project.xml.

**Tech Stack:** C# 7.3, Acumatica Fluent BQL (PX.Data.BQL.Fluent), PX.Objects.PO, PX.Objects.IN, PX.Objects.CR, net48

---

## Task 1: Add TransportMode Field to UsrContainer DAC

**Files:**
- Modify: `src/StudioB.Containers/DACs/UsrContainer.cs:135-136` (after Status region)

### Step 1: Add TransportMode field

Add this region after the `#endregion` of the Status region (after line 136):

```csharp
        #region TransportMode
        public abstract class transportMode : BqlString.Field<transportMode> { }
        [PXDBString(10, IsUnicode = true)]
        [PXUIField(DisplayName = "Transport Mode")]
        [PXStringList(new string[] { "OCEAN", "AIR", "RAIL", "TRUCK" },
                       new string[] { "Ocean", "Air", "Rail", "Truck" })]
        public string TransportMode { get; set; }
        #endregion
```

### Step 2: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: Build succeeded

### Step 3: Commit

```bash
git add src/StudioB.Containers/DACs/UsrContainer.cs
git commit -m "feat: add TransportMode field to UsrContainer DAC"
```

---

## Task 2: Expand POLinks View with Vendor and Line Details

**Files:**
- Modify: `src/StudioB.Containers/Graphs/ContainerMaint.cs:29-31` (POLinks view)

### Step 1: Update using directives

Add these imports at the top of `ContainerMaint.cs` (after line 7, `using PX.Objects.PO;`):

```csharp
using PX.Objects.CR;
using PX.Objects.IN;
```

### Step 2: Replace the POLinks view

Replace lines 29-31:
```csharp
        public SelectFrom<UsrContainerPOLink>
            .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View POLinks;
```

With:
```csharp
        public SelectFrom<UsrContainerPOLink>
            .LeftJoin<POOrder>.On<POOrder.orderType.IsEqual<UsrContainerPOLink.orderType>
                .And<POOrder.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>>
            .LeftJoin<BAccount>.On<BAccount.bAccountID.IsEqual<POOrder.vendorID>>
            .LeftJoin<POLine>.On<POLine.orderType.IsEqual<UsrContainerPOLink.orderType>
                .And<POLine.orderNbr.IsEqual<UsrContainerPOLink.orderNbr>>
                .And<POLine.lineNbr.IsEqual<UsrContainerPOLink.lineNbr>>>
            .LeftJoin<InventoryItem>.On<InventoryItem.inventoryID.IsEqual<POLine.inventoryID>>
            .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View POLinks;
```

**Why LeftJoin:** LineNbr is nullable (container-level PO link without specific line), and a PO may not have a vendor or line yet. LeftJoin ensures the parent row always appears even if joined data is missing.

### Step 3: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: Build succeeded

### Step 4: Commit

```bash
git add src/StudioB.Containers/Graphs/ContainerMaint.cs
git commit -m "feat: expand POLinks view with vendor and PO line joins"
```

---

## Task 3: Update ASPX — Grid Columns and Detail Form

**Files:**
- Modify: `Customization/AesthetikContainers/Pages/SB/SB501000.aspx`

### Step 1: Add TransportMode to the container grid

In `gridContainers`, after the `Status` column (line 38), add:
```xml
                            <px:PXGridColumn DataField="TransportMode" Width="90" />
```

### Step 2: Add TransportMode to the detail form

In `frmDetail`, after the `CarrierCode` field (line 62), add:
```xml
                    <px:PXDropDown ID="edTransportMode" runat="server" DataField="TransportMode" />
```

### Step 3: Expand PO Links grid columns

Replace the PO Links grid columns (lines 100-103):
```xml
                                            <px:PXGridColumn DataField="OrderType" Width="70" />
                                            <px:PXGridColumn DataField="OrderNbr" Width="100" />
                                            <px:PXGridColumn DataField="LineNbr" Width="70" />
```

With:
```xml
                                            <px:PXGridColumn DataField="OrderType" Width="60" />
                                            <px:PXGridColumn DataField="OrderNbr" Width="90" />
                                            <px:PXGridColumn DataField="BAccount__AcctName" Width="140" />
                                            <px:PXGridColumn DataField="LineNbr" Width="50" />
                                            <px:PXGridColumn DataField="InventoryItem__InventoryCD" Width="120" />
                                            <px:PXGridColumn DataField="InventoryItem__Descr" Width="180" />
                                            <px:PXGridColumn DataField="POLine__OrderQty" Width="80" />
                                            <px:PXGridColumn DataField="POLine__UOM" Width="60" />
```

**Column naming convention:** Acumatica uses `JoinedDAC__FieldName` syntax for fields from joined tables in grids.

### Step 4: Commit

```bash
git add Customization/AesthetikContainers/Pages/SB/SB501000.aspx
git commit -m "feat: add TransportMode, vendor, and PO line columns to SB501000 ASPX"
```

---

## Task 4: Sync project.xml CDATA and Fix SiteMap Title

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`

### Step 1: Update the SB501000 CDATA

Replace the CDATA block for SB501000.aspx (between `<![CDATA[` and `]]>` after line 170) with the full content of the updated `Pages/SB/SB501000.aspx` file from Task 3.

### Step 2: Fix SiteMap title

On line 1713, change:
```xml
<row Position="7.5" Title="Container Maintenance"
```
To:
```xml
<row Position="7.5" Title="Procurement Command Center"
```

### Step 3: Commit

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: sync SB501000 CDATA and fix SiteMap title to Procurement Command Center"
```

---

## Task 5: Build DLL and Package

**Files:**
- Modify: `Customization/AesthetikContainers/Bin/StudioB.Containers.dll` (binary, rebuilt)

### Step 1: Build the DLL

Run:
```bash
/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
```
Expected: Build succeeded

### Step 2: Copy the DLL

```bash
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/
```

### Step 3: Commit the DLL

```bash
git add Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "build: rebuild StudioB.Containers.dll with TransportMode and POLinks joins"
```

---

## Task 6: Push to Stage and Verify Pipeline

### Step 1: Push the branch

```bash
git push origin claude/jovial-montalcini
```

### Step 2: Verify the pipeline runs

Check that the pipeline:
- Packages the zip correctly (includes updated ASPX + DLL)
- Imports to sandbox with `isReplaceIfExists: true`
- Publishes successfully (including DB column creation for TransportMode)
- ASPX verification step passes (new feature from this PR)
- Post-publish field validation passes

### Step 3: Verify on sandbox

After pipeline completes, check:
- SB501000 loads with "Procurement Command Center" in nav menu
- TransportMode dropdown appears in grid and detail form
- PO Links grid shows VendorName, InventoryID, ItemDescr, OrderQty, UOM columns
- Existing container data is unaffected (TransportMode is null for existing rows)
