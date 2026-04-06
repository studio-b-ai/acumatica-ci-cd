# SB501000 Container Costs Tab Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Costs tab to the Procurement Command Center with an editable grid for shipping, duty, tariff, and brokerage cost tracking per container.

**Architecture:** New `UsrContainerCost` DAC with parent relationship to `UsrContainer`, new `Costs` view on `ContainerMaint` graph, new "Costs" tab in the ASPX with an editable grid. Follow existing patterns from `UsrContainerEvent` and `UsrContainerPOLink`.

**Tech Stack:** C# 7.3, Acumatica Fluent BQL, PX.Objects.AP (for VendorID selector), net48

---

## Task 1: Create UsrContainerCost DAC

**Files:**
- Create: `src/StudioB.Containers/DACs/UsrContainerCost.cs`

### Step 1: Create the DAC file

Follow the exact pattern of `UsrContainerPOLink.cs` (parent relationship via PXDBDefault + PXParent).

```csharp
using System;
using PX.Data;
using PX.Data.BQL;
using PX.Objects.AP;
using PX.Objects.CR;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Cost")]
    public class UsrContainerCost : PXBqlTable, IBqlTable
    {
        #region CostID
        public abstract class costID : BqlInt.Field<costID> { }
        [PXDBIdentity(IsKey = true)]
        public int? CostID { get; set; }
        #endregion

        #region ContainerID
        public abstract class containerID : BqlInt.Field<containerID> { }
        [PXDBInt]
        [PXDBDefault(typeof(UsrContainer.containerID))]
        [PXParent(typeof(Select<UsrContainer, Where<UsrContainer.containerID, Equal<Current<UsrContainerCost.containerID>>>>))]
        public int? ContainerID { get; set; }
        #endregion

        #region CostType
        public abstract class costType : BqlString.Field<costType> { }
        [PXDBString(20, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Cost Type")]
        [PXStringList(new string[] { "SHIPPING", "DUTY", "TARIFF", "BROKERAGE", "OTHER" },
                       new string[] { "Shipping", "Duty", "Tariff", "Brokerage", "Other" })]
        public string CostType { get; set; }
        #endregion

        #region Description
        public abstract class description : BqlString.Field<description> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Description")]
        public string Description { get; set; }
        #endregion

        #region Amount
        public abstract class amount : BqlDecimal.Field<amount> { }
        [PXDBDecimal(2)]
        [PXDefault(TypeCode.Decimal, "0.00")]
        [PXUIField(DisplayName = "Amount")]
        public decimal? Amount { get; set; }
        #endregion

        #region VendorID
        public abstract class vendorID : BqlInt.Field<vendorID> { }
        [PXDBInt]
        [PXUIField(DisplayName = "Vendor")]
        [PXSelector(typeof(Search<BAccount.bAccountID,
            Where<BAccount.type, Equal<BAccountType.vendorType>,
                Or<BAccount.type, Equal<BAccountType.combinedType>>>>),
            typeof(BAccount.acctCD),
            typeof(BAccount.acctName),
            SubstituteKey = typeof(BAccount.acctCD))]
        public int? VendorID { get; set; }
        #endregion

        #region ReferenceNbr
        public abstract class referenceNbr : BqlString.Field<referenceNbr> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Reference Nbr")]
        public string ReferenceNbr { get; set; }
        #endregion
    }
}
```

### Step 2: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: Build succeeded (SDK DLLs must be in `lib/`)

### Step 3: Commit

```bash
git add src/StudioB.Containers/DACs/UsrContainerCost.cs
git commit -m "feat: add UsrContainerCost DAC for container cost tracking"
```

---

## Task 2: Add Costs View to ContainerMaint Graph

**Files:**
- Modify: `src/StudioB.Containers/Graphs/ContainerMaint.cs`

### Step 1: Add the Costs view

After the `POLinks` view declaration (around line 40), add:

```csharp
        public SelectFrom<UsrContainerCost>
            .Where<UsrContainerCost.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View Costs;
```

### Step 2: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: Build succeeded

### Step 3: Commit

```bash
git add src/StudioB.Containers/Graphs/ContainerMaint.cs
git commit -m "feat: add Costs view to ContainerMaint graph"
```

---

## Task 3: Add Costs Tab to ASPX

**Files:**
- Modify: `Customization/AesthetikContainers/Pages/SB/SB501000.aspx`

### Step 1: Add the Costs tab

In the `<px:PXTab>` element, after the PO Links `</px:PXTabItem>` closing tag, add a new tab item:

```xml
                    <px:PXTabItem Text="Costs">
                        <Template>
                            <px:PXGrid ID="gridCosts" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                                <Levels>
                                    <px:PXGridLevel DataMember="Costs">
                                        <Columns>
                                            <px:PXGridColumn DataField="CostType" Width="100" CommitChanges="True" />
                                            <px:PXGridColumn DataField="Description" Width="180" />
                                            <px:PXGridColumn DataField="Amount" Width="100" />
                                            <px:PXGridColumn DataField="VendorID" Width="140" CommitChanges="True" />
                                            <px:PXGridColumn DataField="ReferenceNbr" Width="120" />
                                        </Columns>
                                    </px:PXGridLevel>
                                </Levels>
                                <AutoSize Enabled="True" MinHeight="150" />
                            </px:PXGrid>
                        </Template>
                    </px:PXTabItem>
```

### Step 2: Commit

```bash
git add Customization/AesthetikContainers/Pages/SB/SB501000.aspx
git commit -m "feat: add Costs tab to SB501000 ASPX"
```

---

## Task 4: Sync project.xml CDATA

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`

### Step 1: Replace SB501000 CDATA

Replace the CDATA block for `AppRelativePath="Pages\SB\SB501000.aspx"` with the full content of the updated standalone ASPX file from Task 3.

### Step 2: Commit

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix: sync SB501000 CDATA with Costs tab"
```

---

## Task 5: Build DLL and Package

### Step 1: Build

```bash
/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
```

### Step 2: Copy DLL

```bash
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/
```

### Step 3: Commit

```bash
git add Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "build: rebuild DLL with UsrContainerCost DAC and Costs view"
```

---

## Task 6: Push and Create PR

### Step 1: Push

```bash
git push origin claude/jovial-montalcini
```

### Step 2: Create PR

```bash
gh pr create --title "feat: SB501000 Container Costs tab" --body "$(cat <<'EOF'
## Summary
- New UsrContainerCost DAC (CostType, Description, Amount, Vendor, Reference)
- Costs view on ContainerMaint graph
- New Costs tab on SB501000 with editable grid
- Phase 1 of Bucket B (cost tracking, landed costs, invoices)

## Context
User feedback requested shipping (up to 4 rows), duty, and tariff tracking per container.
This is the foundation for Phase 2 (Landed Cost document creation) and Phase 3 (AP invoice linking).

## Test plan
- [ ] Deploy to sandbox
- [ ] SB501000 shows Costs tab
- [ ] Can add/edit/delete cost rows
- [ ] Vendor selector works
- [ ] Cost type dropdown works
EOF
)"
```
