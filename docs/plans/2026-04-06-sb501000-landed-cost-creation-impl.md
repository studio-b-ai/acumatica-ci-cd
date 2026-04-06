# SB501000 Phase 2 — Landed Cost Creation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Create Landed Cost" action to SB501000 that generates native Acumatica POLandedCostDoc from container costs, with full GL and AP accounting integration.

**Architecture:** New action on ContainerMaint graph that validates preconditions, creates a POLandedCostDoc via `PXGraph.CreateInstance<POLandedCostDocEntry>()`, maps container costs to landed cost detail lines using configurable LC codes from ContainerPrefs, and stores the reference back on the container.

**Tech Stack:** C# 7.3, Acumatica Fluent BQL, PX.Objects.PO (POLandedCostDoc, POLandedCostDetail, POReceipt, POReceiptLine), net48

---

## Prerequisites

- Phase 1 (Container Costs tab) must be deployed
- Acumatica Landed Costs feature must be enabled (CS100000)
- Landed Cost Codes must be configured in PO201500 (FREIGHT, DUTY, TARIFF, BROKER, OTHER)
- This is a one-time manual Acumatica setup, not code

---

## Task 1: Add LC Code Mapping Fields to ContainerPrefs

**Files:**
- Modify: `src/StudioB.Containers/DACs/UsrContainerPrefs.cs:53` (before NoteID region)

### Step 1: Add 5 LC code mapping fields

After the `TrackingPollIntervalHours` region (line 53), before the `NoteID` region, add:

```csharp
        #region LCCodeShipping
        public abstract class lcCodeShipping : BqlString.Field<lcCodeShipping> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Code — Shipping")]
        public string LCCodeShipping { get; set; }
        #endregion
        #region LCCodeDuty
        public abstract class lcCodeDuty : BqlString.Field<lcCodeDuty> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Code — Duty")]
        public string LCCodeDuty { get; set; }
        #endregion
        #region LCCodeTariff
        public abstract class lcCodeTariff : BqlString.Field<lcCodeTariff> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Code — Tariff")]
        public string LCCodeTariff { get; set; }
        #endregion
        #region LCCodeBrokerage
        public abstract class lcCodeBrokerage : BqlString.Field<lcCodeBrokerage> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Code — Brokerage")]
        public string LCCodeBrokerage { get; set; }
        #endregion
        #region LCCodeOther
        public abstract class lcCodeOther : BqlString.Field<lcCodeOther> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Code — Other")]
        public string LCCodeOther { get; set; }
        #endregion
```

### Step 2: Update SB302030 ASPX

In `Customization/AesthetikContainers/Pages/SB/SB302030.aspx`, after the `TrackingPollIntervalHours` field, add a layout rule and the 5 LC code fields:

```xml
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" GroupCaption="Landed Cost Codes" />
            <px:PXTextEdit ID="edLCCodeShipping" runat="server" DataField="LCCodeShipping" />
            <px:PXTextEdit ID="edLCCodeDuty" runat="server" DataField="LCCodeDuty" />
            <px:PXTextEdit ID="edLCCodeTariff" runat="server" DataField="LCCodeTariff" />
            <px:PXTextEdit ID="edLCCodeBrokerage" runat="server" DataField="LCCodeBrokerage" />
            <px:PXTextEdit ID="edLCCodeOther" runat="server" DataField="LCCodeOther" />
```

### Step 3: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`

### Step 4: Commit

```bash
git add src/StudioB.Containers/DACs/UsrContainerPrefs.cs \
       Customization/AesthetikContainers/Pages/SB/SB302030.aspx
git commit -m "feat: add LC code mapping fields to ContainerPrefs"
```

---

## Task 2: Add LandedCostRefNbr and LandedCostStatus to UsrContainer

**Files:**
- Modify: `src/StudioB.Containers/DACs/UsrContainer.cs` (after SealNbr region, before LastEventCode)

### Step 1: Add 2 new fields

After the `SealNbr` region, add:

```csharp
        #region LandedCostRefNbr
        public abstract class landedCostRefNbr : BqlString.Field<landedCostRefNbr> { }
        [PXDBString(15, IsUnicode = true)]
        [PXUIField(DisplayName = "Landed Cost Ref", Enabled = false)]
        public string LandedCostRefNbr { get; set; }
        #endregion

        #region LandedCostStatus
        public abstract class landedCostStatus : BqlString.Field<landedCostStatus> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "LC Status", Enabled = false)]
        public string LandedCostStatus { get; set; }
        #endregion
```

### Step 2: Build to verify

### Step 3: Commit

```bash
git add src/StudioB.Containers/DACs/UsrContainer.cs
git commit -m "feat: add LandedCostRefNbr and LandedCostStatus to UsrContainer"
```

---

## Task 3: Implement CreateLandedCost Action

**Files:**
- Modify: `src/StudioB.Containers/Graphs/ContainerMaint.cs`

### Step 1: Add the action

In the `#region Actions` section (after the `RefreshTracking` action), add the `CreateLandedCost` action. This is the core of Phase 2.

```csharp
        public PXAction<ContainerFilter> CreateLandedCost;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Create Landed Cost", MapEnableRights = PXCacheRights.Update)]
        protected void createLandedCost()
        {
            UsrContainer container = Container.Current;
            if (container == null) return;

            // Validate: container has costs
            var costs = new List<UsrContainerCost>();
            foreach (UsrContainerCost c in Costs.Select())
            {
                if ((c.Amount ?? 0m) > 0m) costs.Add(c);
            }
            if (costs.Count == 0)
                throw new PXException("Add costs to this container before creating a Landed Cost document.");

            // Validate: container has PO links
            var poLinks = new List<UsrContainerPOLink>();
            foreach (PXResult<UsrContainerPOLink> row in POLinks.Select())
            {
                poLinks.Add((UsrContainerPOLink)row);
            }
            if (poLinks.Count == 0)
                throw new PXException("Link at least one PO to this container before creating a Landed Cost document.");

            // Validate: LC codes configured
            var prefs = PXSelect<UsrContainerPrefs>.Select(this).TopFirst;
            if (prefs == null)
                throw new PXException("Configure Landed Cost Codes in Container Preferences (SB302030).");

            // Warn if LC already created
            if (!string.IsNullOrEmpty(container.LandedCostRefNbr))
            {
                if (Container.Ask("Landed Cost",
                    string.Format("Landed Cost {0} already exists for this container. Create another?", container.LandedCostRefNbr),
                    MessageButtons.YesNo) != WebDialogResult.Yes)
                {
                    return;
                }
            }

            // Find released PO receipts linked to this container's POs
            var receiptLines = new List<Tuple<string, string, int?>>();  // receiptNbr, receiptType, lineNbr
            foreach (var link in poLinks)
            {
                foreach (PXResult<POReceiptLine> rl in PXSelectJoin<POReceiptLine,
                    InnerJoin<POReceipt, On<POReceipt.receiptType, Equal<POReceiptLine.receiptType>,
                        And<POReceipt.receiptNbr, Equal<POReceiptLine.receiptNbr>>>>,
                    Where<POReceiptLine.pOType, Equal<Required<POReceiptLine.pOType>>,
                        And<POReceiptLine.pONbr, Equal<Required<POReceiptLine.pONbr>>,
                        And<POReceipt.released, Equal<True>>>>>
                    .Select(this, link.OrderType, link.OrderNbr))
                {
                    var line = (POReceiptLine)rl;
                    receiptLines.Add(Tuple.Create(line.ReceiptNbr, line.ReceiptType, (int?)line.LineNbr));
                }
            }

            if (receiptLines.Count == 0)
                throw new PXException("No released PO receipts found for the linked POs. Release receipts before creating a Landed Cost document.");

            // Create the Landed Cost document
            var lcGraph = PXGraph.CreateInstance<POLandedCostDocEntry>();
            var lcDoc = lcGraph.Document.Insert(new POLandedCostDoc());
            lcDoc.DocDate = Accessinfo.BusinessDate;

            // Set vendor from first cost row that has one
            foreach (var cost in costs)
            {
                if (cost.VendorID != null)
                {
                    lcDoc.VendorID = cost.VendorID;
                    break;
                }
            }

            lcGraph.Document.Update(lcDoc);

            // Add receipt lines
            foreach (var rl in receiptLines)
            {
                var receiptLine = new POLandedCostReceiptLine();
                receiptLine.POReceiptNbr = rl.Item1;
                receiptLine.POReceiptType = rl.Item2;
                receiptLine.POReceiptLineNbr = rl.Item3;
                lcGraph.ReceiptLines.Insert(receiptLine);
            }

            // Add cost detail lines
            foreach (var cost in costs)
            {
                string lcCode = GetLCCode(prefs, cost.CostType);
                if (string.IsNullOrEmpty(lcCode))
                {
                    throw new PXException(
                        string.Format("No Landed Cost Code configured for cost type '{0}'. Set it in Container Preferences (SB302030).", cost.CostType));
                }

                var detail = new POLandedCostDetail();
                detail.LandedCostCodeID = lcCode;
                detail.CuryLineAmt = cost.Amount;
                detail.Descr = cost.Description ?? cost.CostType;
                lcGraph.Details.Insert(detail);
            }

            lcGraph.Actions.PressSave();

            // Store reference on container
            container.LandedCostRefNbr = lcGraph.Document.Current.RefNbr;
            container.LandedCostStatus = lcGraph.Document.Current.Status;
            Container.Update(container);
            Actions.PressSave();
        }

        private string GetLCCode(UsrContainerPrefs prefs, string costType)
        {
            switch (costType)
            {
                case "SHIPPING": return prefs.LCCodeShipping;
                case "DUTY": return prefs.LCCodeDuty;
                case "TARIFF": return prefs.LCCodeTariff;
                case "BROKERAGE": return prefs.LCCodeBrokerage;
                case "OTHER": return prefs.LCCodeOther;
                default: return prefs.LCCodeOther;
            }
        }
```

**Note:** The exact DAC field names for `POLandedCostDoc`, `POLandedCostDetail`, `POLandedCostReceiptLine`, and the `POLandedCostDocEntry` graph's view names (`Document`, `Details`, `ReceiptLines`) may differ from what's shown here. The implementer MUST verify these against the actual Acumatica 24.208 SDK DLLs. Use `dotnet build` errors and the SDK DLL metadata to find the correct types.

### Step 2: Build to verify

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`

If build fails due to incorrect Acumatica type names, check the SDK DLLs:
```bash
# List types in PX.Objects.dll related to landed cost
dotnet tool install --global ILSpy.CommandLine 2>/dev/null
ilspycmd lib/PX.Objects.dll | grep -i "LandedCost" | head -20
```

Or use reflection:
```bash
python3 -c "
import subprocess
result = subprocess.run(['strings', 'lib/PX.Objects.dll'], capture_output=True, text=True)
for line in result.stdout.split('\n'):
    if 'LandedCost' in line and ('Doc' in line or 'Detail' in line or 'Receipt' in line or 'Entry' in line):
        print(line)
"
```

### Step 3: Commit

```bash
git add src/StudioB.Containers/Graphs/ContainerMaint.cs
git commit -m "feat: CreateLandedCost action on ContainerMaint"
```

---

## Task 4: Update SB501000 ASPX — Action Button and LC Fields

**Files:**
- Modify: `Customization/AesthetikContainers/Pages/SB/SB501000.aspx`

### Step 1: Add the toolbar button

In the `<CallbackCommands>` section, add:

```xml
            <px:PXDSCallbackCommand Name="CreateLandedCost" CommitChanges="True" />
```

### Step 2: Add LC reference fields to detail form

In `frmDetail`, in the right column (after SealNbr), add:

```xml
                    <px:PXTextEdit ID="edLandedCostRefNbr" runat="server" DataField="LandedCostRefNbr" />
                    <px:PXTextEdit ID="edLandedCostStatus" runat="server" DataField="LandedCostStatus" />
```

### Step 3: Commit

```bash
git add Customization/AesthetikContainers/Pages/SB/SB501000.aspx
git commit -m "feat: add Create Landed Cost button and LC fields to SB501000"
```

---

## Task 5: Sync CDATA, Build DLL, Push

### Step 1: Sync project.xml CDATA for both SB501000 and SB302030

Replace CDATA blocks for both ASPX files with their updated standalone content.

### Step 2: Build and copy DLL

```bash
/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/
```

### Step 3: Commit and push

```bash
git add Customization/AesthetikContainers/project.xml \
       Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "build: sync CDATA + rebuild DLL with CreateLandedCost action"
git push origin claude/jovial-montalcini
```

---

## Important Notes for Implementer

### Acumatica SDK Type Verification

The action code in Task 3 uses these Acumatica types that **MUST be verified** against the 24.208 SDK:

| Type Used | Purpose | Verify |
|-----------|---------|--------|
| `POLandedCostDocEntry` | Graph for LC documents | May be named differently |
| `POLandedCostDoc` | LC document header DAC | Field names may differ |
| `POLandedCostDetail` | LC detail line DAC | Field names may differ |
| `POLandedCostReceiptLine` | Receipt line allocation DAC | May not exist as separate DAC |
| `Document` | Header view on graph | View name may differ |
| `Details` | Detail lines view | View name may differ |
| `ReceiptLines` | Receipt allocation view | View name may differ |

**To verify:** Use `strings lib/PX.Objects.dll | grep -i LandedCost` to find exact type names, or check build errors.

### Testing on Sandbox

Before the action will work on sandbox, you must:
1. Enable Landed Costs feature in CS100000 (Enable/Disable Features)
2. Create Landed Cost Codes in PO201500: FREIGHT, DUTY, TARIFF, BROKER, OTHER
3. Set the LC codes in Container Preferences (SB302030)
4. Have at least one container with costs, linked POs, and released PO receipts
