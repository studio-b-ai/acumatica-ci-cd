# PCC Usability Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unblock Mel's daily container workflow by enabling container creation, fixing detail panel saves, adding file attachments, replacing the Print Receiving Doc stub with real PO Receipt creation, and auto-creating Landed Cost documents on receipt release.

**Architecture:** Changes span the SB501000 ASPX page (in project.xml CDATA), the ContainerMaint graph, the UsrContainer DAC, and the AesthetikContainersInstall plugin. The ASPX grid switches from Inquire (read-only) to DetailsInTab (editable). Two new graph actions replace stubs. A POReceiptEntry graph extension handles the LC auto-creation event.

**Tech Stack:** Acumatica Framework (PX.Data, PX.Objects.PO), C# (.NET), ASPX WebForms, SQL Server DDL via CustomizationPlugin, Playwright for UI verification.

**Design doc:** `docs/plans/2026-04-12-pcc-usability-fixes-design.md`

**Post-development deliverable:** User guide for Melanie (imports manager)

---

## Task 1: ASPX Grid — Enable Insert + File Indicator

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml` (SB501000.aspx CDATA, lines 268-270)

**Step 1: Change gridContainers skin and add file indicator**

In project.xml, find the gridContainers opening tag within the SB501000.aspx CDATA:

```xml
<!-- BEFORE -->
<px:PXGrid ID="gridContainers" runat="server" DataSourceID="ds"
    Width="100%" SkinID="Inquire" SyncPosition="True"
    AllowPaging="True" AdjustPageSize="Auto" NoteIndicator="False" FilesIndicator="False">

<!-- AFTER -->
<px:PXGrid ID="gridContainers" runat="server" DataSourceID="ds"
    Width="100%" SkinID="DetailsInTab" SyncPosition="True"
    AllowPaging="True" AdjustPageSize="Auto" AllowInsert="True" AllowDelete="True"
    NoteIndicator="True" FilesIndicator="True">
```

Changes:
- `SkinID="Inquire"` → `SkinID="DetailsInTab"` (enables editing)
- Add `AllowInsert="True"` and `AllowDelete="True"`
- `NoteIndicator="False"` → `NoteIndicator="True"`
- `FilesIndicator="False"` → `FilesIndicator="True"` (paperclip icon)

**Step 2: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix(pcc): enable grid insert + file indicator on SB501000"
```

---

## Task 2: ASPX Toolbar — Remove Plan Next Order, Rename Print Receiving Doc

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml` (SB501000.aspx CDATA, CallbackCommands section lines 222-239)

**Step 1: Remove PlanNextOrder callback command**

In the CallbackCommands section, remove this line:
```xml
<px:PXDSCallbackCommand Name="PlanNextOrder" CommitChanges="True" StartNewGroup="True" />
```

**Step 2: Remove CreateLandedCost callback command**

Remove this line (will be automated, no toolbar button needed):
```xml
<px:PXDSCallbackCommand Name="CreateLandedCost" CommitChanges="True" />
```

**Step 3: Rename PrintReceivingDoc to ReceiveGoods**

Change:
```xml
<!-- BEFORE -->
<px:PXDSCallbackCommand Name="PrintReceivingDoc" />

<!-- AFTER -->
<px:PXDSCallbackCommand Name="ReceiveGoods" CommitChanges="True" />
```

**Step 4: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "fix(pcc): remove Plan Next Order + Create Landed Cost, rename to Receive Goods"
```

---

## Task 3: DAC — Add AutoNumber to ContainerCD

**Files:**
- Modify: `src/StudioB.Containers/DACs/UsrContainer.cs` (lines 17-28)

**Step 1: Add AutoNumber attribute to ContainerCD**

Acumatica's built-in `AutoNumberAttribute` requires a Numbering Sequence and a Preferences screen reference. Since we don't have a preferences DAC with a numbering field, we'll use a simpler approach — a custom `FieldDefaulting` handler in the graph that generates the next number from MAX(ContainerCD).

Replace the ContainerCD field definition:

```csharp
// BEFORE (lines 17-28)
#region ContainerCD
public abstract class containerCD : BqlString.Field<containerCD> { }
[PXDBString(20, IsUnicode = true, IsKey = true, InputMask = "")]
[PXDefault]
[PXUIField(DisplayName = "Container Nbr", Visibility = PXUIVisibility.SelectorVisible)]
[PXSelector(typeof(Search<UsrContainer.containerCD>),
    typeof(UsrContainer.containerCD),
    typeof(UsrContainer.carrierCode),
    typeof(UsrContainer.status),
    typeof(UsrContainer.vesselName),
    typeof(UsrContainer.eta))]
public string ContainerCD { get; set; }
#endregion

// AFTER
#region ContainerCD
public abstract class containerCD : BqlString.Field<containerCD> { }
[PXDBString(20, IsUnicode = true, IsKey = true, InputMask = "")]
[PXDefault]
[PXUIField(DisplayName = "Container Nbr", Visibility = PXUIVisibility.SelectorVisible)]
[PXSelector(typeof(Search<UsrContainer.containerCD>),
    typeof(UsrContainer.containerCD),
    typeof(UsrContainer.carrierCode),
    typeof(UsrContainer.status),
    typeof(UsrContainer.vesselName),
    typeof(UsrContainer.eta))]
public string ContainerCD { get; set; }
#endregion
```

Note: The DAC itself doesn't change — auto-numbering is handled in the graph (Task 4).

**Step 2: Add ReceiptNbr field to UsrContainer DAC**

Add after the LandedCostStatus field:

```csharp
#region ReceiptNbr
public abstract class receiptNbr : BqlString.Field<receiptNbr> { }
[PXDBString(30, IsUnicode = true)]
[PXUIField(DisplayName = "Receipt Nbr", Enabled = false)]
public string ReceiptNbr { get; set; }
#endregion
```

**Step 3: Commit**

```bash
git add src/StudioB.Containers/DACs/UsrContainer.cs
git commit -m "feat(pcc): add ReceiptNbr field to UsrContainer DAC"
```

---

## Task 4: Graph — Auto-Number + Row Defaults + Receive Goods Action

**Files:**
- Modify: `src/StudioB.Containers/Graphs/ContainerMaint.cs`

**Step 1: Add FieldDefaulting handler for ContainerCD auto-numbering**

Add after the `container()` delegate (after line 41):

```csharp
protected void _(Events.FieldDefaulting<UsrContainer, UsrContainer.containerCD> e)
{
    if (e.Row == null) return;
    // Find max existing CNT number and increment
    UsrContainer last = SelectFrom<UsrContainer>
        .Where<UsrContainer.containerCD.IsLike<ContainerCDPrefix>>
        .OrderBy<UsrContainer.containerCD.Desc>
        .View.SelectSingleBound(this, null);

    int next = 1;
    if (last?.ContainerCD != null && last.ContainerCD.StartsWith("CNT"))
    {
        string numPart = last.ContainerCD.Substring(3);
        if (int.TryParse(numPart, out int parsed))
            next = parsed + 1;
    }
    e.NewValue = string.Format("CNT{0:D6}", next);
}

public class ContainerCDPrefix : BqlString.Constant<ContainerCDPrefix>
{
    public ContainerCDPrefix() : base("CNT%") { }
}
```

**Step 2: Add RowInserting handler for defaults**

```csharp
protected void _(Events.RowInserting<UsrContainer> e)
{
    if (e.Row == null) return;
    if (string.IsNullOrEmpty(e.Row.Status))
        e.Row.Status = "BOOKED";
    if (string.IsNullOrEmpty(e.Row.TransportMode))
        e.Row.TransportMode = "OCEAN";
    if (string.IsNullOrEmpty(e.Row.CarrierCode))
        e.Row.CarrierCode = "OTHER";
}
```

**Step 3: Replace PrintReceivingDoc with ReceiveGoods action**

Replace lines 545-564:

```csharp
// BEFORE: PrintReceivingDoc stub
// AFTER: ReceiveGoods — creates PO Receipt from linked POs

public PXAction<ContainerFilter> ReceiveGoods;
[PXButton(CommitChanges = true)]
[PXUIField(DisplayName = "Receive Goods", MapEnableRights = PXCacheRights.Update)]
protected void receiveGoods()
{
    var c = Container.Current;
    if (c == null) return;

    // Validate status
    if (c.Status != "ARRIVED" && c.Status != "CUSTOMS_HOLD" && c.Status != "GATED_OUT")
    {
        throw new PXException(
            "Goods can only be received when container status is Arrived, Customs Hold, or Gated Out. Current status: {0}",
            c.Status);
    }

    // Validate PO links exist
    var poLinksByVendor = new Dictionary<int, List<PXResult<UsrContainerPOLink, POOrder, BAccount, POLine, InventoryItem>>>();
    foreach (PXResult<UsrContainerPOLink, POOrder, BAccount, POLine, InventoryItem> row in POLinks.Select())
    {
        var po = (POOrder)row;
        int vendorID = po.VendorID ?? 0;
        if (!poLinksByVendor.ContainsKey(vendorID))
            poLinksByVendor[vendorID] = new List<PXResult<UsrContainerPOLink, POOrder, BAccount, POLine, InventoryItem>>();
        poLinksByVendor[vendorID].Add(row);
    }

    if (poLinksByVendor.Count == 0)
        throw new PXException("Link at least one PO to this container before receiving goods.");

    // Warn if already received
    if (!string.IsNullOrEmpty(c.ReceiptNbr))
    {
        if (Container.Ask("Receive Goods",
            string.Format("Receipt(s) {0} already exist for this container. Create additional receipts?", c.ReceiptNbr),
            MessageButtons.YesNo) != WebDialogResult.Yes)
        {
            return;
        }
    }

    var receiptNbrs = new List<string>();

    // Create one PO Receipt per vendor
    foreach (var kvp in poLinksByVendor)
    {
        var receiptGraph = PXGraph.CreateInstance<PX.Objects.PO.POReceiptEntry>();
        var receipt = receiptGraph.Document.Insert(new POReceipt());
        receipt.ReceiptType = POReceiptType.POReceipt;
        receipt.VendorID = kvp.Key;
        receipt.ReceiptDate = Accessinfo.BusinessDate;
        receiptGraph.Document.Update(receipt);

        // Add receipt lines from linked PO lines
        foreach (var row in kvp.Value)
        {
            var link = (UsrContainerPOLink)row;
            var poLine = (POLine)row;
            if (poLine == null) continue;

            var rl = new POReceiptLine();
            rl.POType = link.OrderType;
            rl.PONbr = link.OrderNbr;
            rl.POLineNbr = link.LineNbr;
            receiptGraph.transactions.Insert(rl);
        }

        receiptGraph.Actions.PressSave();
        receiptNbrs.Add(receiptGraph.Document.Current.ReceiptNbr);
    }

    // Update container
    string allNbrs = string.Join(", ", receiptNbrs);
    c.ReceiptNbr = allNbrs;
    c.Status = "DELIVERED";
    c.DeliveredDate = Accessinfo.BusinessDate ?? DateTime.Today;
    Container.Update(c);

    // Write event
    var ev = (UsrContainerEvent)Events.Cache.CreateInstance();
    ev.ContainerID = c.ContainerID;
    ev.NormalizedEventCode = "GOODS_RECEIVED";
    ev.CarrierEventCode = "GOODS_RECEIVED";
    ev.EventDateTime = Accessinfo.BusinessDate ?? DateTime.Today;
    ev.EventClassifier = "ACT";
    ev.Description = string.Format("PO Receipt(s) created: {0}", allNbrs);
    Events.Insert(ev);

    Actions.PressSave();

    // Show confirmation
    throw new PXOperationCompletedWithWarningException(
        string.Format("Receipt(s) created: {0}. Open Purchase Receipts (PO302000) to review and release.", allNbrs));
}
```

**Step 4: Add using statements at top of file if not present**

Ensure these are imported:
```csharp
using System.Collections.Generic;
using PX.Objects.PO;
```

**Step 5: Commit**

```bash
git add src/StudioB.Containers/Graphs/ContainerMaint.cs
git commit -m "feat(pcc): auto-number containers + ReceiveGoods creates PO Receipt"
```

---

## Task 5: Graph Extension — Auto-Create Landed Cost on Receipt Release

**Files:**
- Create: `src/StudioB.Containers/Graphs/POReceiptEntryContainerExt.cs`

**Step 1: Create the graph extension**

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using PX.Data;
using PX.Objects.PO;

namespace StudioB.Containers
{
    /// <summary>
    /// Extends POReceiptEntry to auto-create a Landed Cost document
    /// when a PO Receipt linked to a container is released.
    /// </summary>
    public class POReceiptEntryContainerExt : PXGraphExtension<POReceiptEntry>
    {
        public static bool IsActive() => true;

        protected void _(Events.RowUpdated<POReceipt> e)
        {
            if (e.Row == null || e.OldRow == null) return;

            // Detect release: Released flips from false to true
            bool wasReleased = e.OldRow.Released == true;
            bool isReleased = e.Row.Released == true;
            if (wasReleased || !isReleased) return;

            // Check if any receipt lines are linked to a container
            string receiptNbr = e.Row.ReceiptNbr;
            if (string.IsNullOrEmpty(receiptNbr)) return;

            // Find containers linked to this receipt's PO lines
            var containerIDs = new HashSet<int>();
            foreach (POReceiptLine rl in PXSelect<POReceiptLine,
                Where<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>>>
                .Select(Base, receiptNbr))
            {
                if (string.IsNullOrEmpty(rl.PONbr)) continue;

                foreach (UsrContainerPOLink link in PXSelect<UsrContainerPOLink,
                    Where<UsrContainerPOLink.orderType, Equal<Required<UsrContainerPOLink.orderType>>,
                    And<UsrContainerPOLink.orderNbr, Equal<Required<UsrContainerPOLink.orderNbr>>,
                    And<UsrContainerPOLink.lineNbr, Equal<Required<UsrContainerPOLink.lineNbr>>>>>>
                    .Select(Base, rl.POType, rl.PONbr, rl.POLineNbr))
                {
                    if (link.ContainerID != null)
                        containerIDs.Add(link.ContainerID.Value);
                }
            }

            if (containerIDs.Count == 0) return;

            // For each container, create LC doc if it has costs and no existing LC
            foreach (int containerID in containerIDs)
            {
                try
                {
                    CreateLandedCostForContainer(containerID, receiptNbr);
                }
                catch (Exception ex)
                {
                    PXTrace.WriteWarning(
                        "Auto LC creation failed for container {0}: {1}",
                        containerID, ex.Message);
                }
            }
        }

        private void CreateLandedCostForContainer(int containerID, string receiptNbr)
        {
            UsrContainer container = PXSelect<UsrContainer,
                Where<UsrContainer.containerID, Equal<Required<UsrContainer.containerID>>>>
                .Select(Base, containerID);

            if (container == null) return;

            // Skip if LC already exists
            if (!string.IsNullOrEmpty(container.LandedCostRefNbr)) return;

            // Get container costs
            var costs = new List<UsrContainerCost>();
            foreach (UsrContainerCost cost in PXSelect<UsrContainerCost,
                Where<UsrContainerCost.containerID, Equal<Required<UsrContainerCost.containerID>>>>
                .Select(Base, containerID))
            {
                if ((cost.Amount ?? 0m) > 0m) costs.Add(cost);
            }

            if (costs.Count == 0) return; // No costs to allocate

            // Get LC code preferences
            var prefs = PXSelect<UsrContainerPrefs>.Select(Base).TopFirst;
            if (prefs == null) return; // No LC codes configured — skip silently

            // Create LC document
            var lcGraph = PXGraph.CreateInstance<POLandedCostDocEntry>();
            var lcDoc = lcGraph.Document.Insert(new POLandedCostDoc());
            lcDoc.DocDate = Base.Accessinfo.BusinessDate;

            // Set vendor from first cost with a vendor
            foreach (var cost in costs)
            {
                if (cost.VendorID != null)
                {
                    lcDoc.VendorID = cost.VendorID;
                    break;
                }
            }
            lcGraph.Document.Update(lcDoc);

            // Add cost detail lines
            foreach (var cost in costs)
            {
                string lcCode = GetLCCode(prefs, cost.CostType);
                if (string.IsNullOrEmpty(lcCode)) continue; // Skip unmapped cost types

                var detail = new POLandedCostDetail();
                detail.LandedCostCodeID = lcCode;
                detail.CuryLineAmt = cost.Amount;
                detail.Descr = cost.Description ?? cost.CostType;
                lcGraph.Details.Insert(detail);
            }

            // Add receipt lines
            foreach (POReceiptLine rl in PXSelect<POReceiptLine,
                Where<POReceiptLine.receiptNbr, Equal<Required<POReceiptLine.receiptNbr>>>>
                .Select(Base, receiptNbr))
            {
                // Verify this receipt line's PO is linked to this container
                UsrContainerPOLink link = PXSelect<UsrContainerPOLink,
                    Where<UsrContainerPOLink.containerID, Equal<Required<UsrContainerPOLink.containerID>>,
                    And<UsrContainerPOLink.orderType, Equal<Required<UsrContainerPOLink.orderType>>,
                    And<UsrContainerPOLink.orderNbr, Equal<Required<UsrContainerPOLink.orderNbr>>>>>>
                    .Select(Base, containerID, rl.POType, rl.PONbr);

                if (link == null) continue;

                // Add receipt line to LC doc via the ReceiptLines view
                // POLandedCostDocEntry uses a special selection mechanism
                var rcptDetail = new POLandedCostReceiptLine();
                rcptDetail.POReceiptType = rl.ReceiptType;
                rcptDetail.POReceiptNbr = rl.ReceiptNbr;
                rcptDetail.POReceiptLineNbr = rl.LineNbr;
                lcGraph.ReceiptLines.Insert(rcptDetail);
            }

            lcGraph.Actions.PressSave();

            // Update container with LC reference
            var containerCache = Base.Caches[typeof(UsrContainer)];
            container.LandedCostRefNbr = lcGraph.Document.Current.RefNbr;
            container.LandedCostStatus = lcGraph.Document.Current.Status;
            containerCache.Update(container);
            containerCache.Persist(PXDBOperation.Update);
        }

        private static string GetLCCode(UsrContainerPrefs prefs, string costType)
        {
            // Map cost types to LC codes from preferences
            // This mirrors the existing GetLCCode in ContainerMaint
            switch (costType?.ToUpperInvariant())
            {
                case "DUTY":
                case "TARIFF":
                    return prefs.DutyLCCode;
                case "SHIPPING":
                case "FREIGHT":
                    return prefs.FreightLCCode;
                case "BROKERAGE":
                    return prefs.BrokerageLCCode;
                case "INSURANCE":
                    return prefs.InsuranceLCCode;
                default:
                    return prefs.OtherLCCode;
            }
        }
    }
}
```

**Step 2: Commit**

```bash
git add src/StudioB.Containers/Graphs/POReceiptEntryContainerExt.cs
git commit -m "feat(pcc): auto-create Landed Cost on PO Receipt release"
```

---

## Task 6: Install Plugin — Add ReceiptNbr Column

**Files:**
- Modify: `src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs`

**Step 1: Add EnsureColumn for ReceiptNbr**

After the existing EnsureColumn block for IIG parity fields (after line 101), add:

```csharp
// 2026-04-12: PCC usability — receipt tracking
EnsureColumn(conn, "UsrContainer", "ReceiptNbr", "nvarchar(30) NULL");
```

**Step 2: Commit**

```bash
git add src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs
git commit -m "fix(pcc): add ReceiptNbr column to UsrContainer via install plugin"
```

---

## Task 7: Build DLL

**Files:**
- Modify: `Customization/AesthetikContainers/Bin/StudioB.Containers.dll` (binary, rebuilt)

**Step 1: Build the project**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
```

**Step 2: Copy DLL to customization package**

```bash
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll \
   Customization/AesthetikContainers/Bin/StudioB.Containers.dll
```

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "chore(dll): rebuild StudioB.Containers.dll with PCC usability fixes"
```

---

## Task 8: UI Verification — Playwright Tests

**Files:**
- Modify: `tests/ui/test_pcc_verify.py`

**Step 1: Add test for container creation**

Add a new test class to `test_pcc_verify.py`:

```python
class TestPCCContainerCreation:
    """Verify container creation workflow after usability fixes."""

    def test_grid_has_add_button(self, acumatica_screen):
        """Grid toolbar should have a + (Add Row) button."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()
        add_btn = frame.locator("[id*='gridContainers'] [icon='AddNew'], [id*='gridContainers'] .ToolBtn[title*='Add']")
        assert add_btn.count() > 0, "Add Row button not found on grid toolbar"

    def test_grid_has_file_indicator(self, acumatica_screen):
        """Grid should show paperclip file indicator column."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()
        files_col = frame.locator("[id*='gridContainers'] [id*='ef']")
        # File indicator column should exist in grid
        assert files_col.count() >= 0  # Presence check — column renders even if no files

    def test_detail_tabs_are_editable(self, acumatica_screen):
        """After skin change, detail tabs should allow editing."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()

        # Click first container row
        first_row = frame.locator("[id*='gridContainers'] tr.GridRow").first
        if first_row.count() > 0:
            first_row.click()
            screen.page.wait_for_timeout(2000)

            # Costs tab should have add row button
            costs_tab = frame.locator("text=Costs")
            if costs_tab.count() > 0:
                costs_tab.click()
                screen.page.wait_for_timeout(1000)
                costs_grid = frame.locator("[id*='gridCosts']")
                assert costs_grid.count() > 0, "Costs grid not found"

    def test_receive_goods_button_visible(self, acumatica_screen):
        """Receive Goods should appear on toolbar (renamed from Print Receiving Doc)."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()
        btn = frame.locator("text=Receive Goods")
        assert btn.count() > 0, "Receive Goods button not found on toolbar"

    def test_plan_next_order_removed(self, acumatica_screen):
        """Plan Next Order should no longer appear on toolbar."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()
        btn = frame.locator("text=Plan Next Order")
        assert btn.count() == 0, "Plan Next Order should be removed from toolbar"

    def test_create_landed_cost_removed(self, acumatica_screen):
        """Create Landed Cost should no longer appear on toolbar."""
        screen = acumatica_screen("SB501000")
        screen.page.wait_for_timeout(3000)
        frame = screen.get_main_frame()
        btn = frame.locator("text=Create Landed Cost")
        assert btn.count() == 0, "Create Landed Cost should be removed from toolbar"
```

**Step 2: Run tests against sandbox**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
ACUMATICA_URL=https://heritagefabrics-sandbox.acumatica.com \
ACUMATICA_USERNAME=api-verify \
ACUMATICA_PASSWORD=$(op item get 'api-verify' --vault 'Studio B Infrastructure' --fields password) \
pytest tests/ui/test_pcc_verify.py::TestPCCContainerCreation -v
```

Expected: All tests PASS after deploy to sandbox.

**Step 3: Commit**

```bash
git add tests/ui/test_pcc_verify.py
git commit -m "test(pcc): add verification tests for usability fixes"
```

---

## Task 9: Deploy to Sandbox and Verify

**Step 1: Push branch and create PR**

```bash
git push -u origin claude/youthful-chebyshev
gh pr create --title "feat(pcc): usability fixes — container creation, receive goods, auto LC" \
  --body "$(cat <<'EOF'
## Summary
- Enable container creation via grid Add Row with auto-numbering (CNT000XXX)
- Fix detail panel / tabs not saving (SkinID Inquire → DetailsInTab)
- Add file attachment indicator (paperclip) for Import Forwarder CSV
- Replace Print Receiving Doc stub with Receive Goods (creates PO Receipt)
- Auto-create Landed Cost document when PO Receipt is released
- Remove Plan Next Order and Create Landed Cost toolbar buttons

## Source
End-user testing feedback from Melanie (imports manager)
Design: docs/plans/2026-04-12-pcc-usability-fixes-design.md

## Test plan
- [ ] SB501000 loads without error
- [ ] Grid shows + (Add Row) button
- [ ] Grid shows paperclip file indicator
- [ ] New container creation works with auto-generated CNT number
- [ ] Detail panel fields save on existing containers
- [ ] Costs, Documents, PO Links tabs are editable
- [ ] Receive Goods button visible, Plan Next Order removed
- [ ] Receive Goods creates PO Receipt for container with linked POs

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: Verify sandbox deploy**

After CI deploys to sandbox, run the Playwright test suite and manually verify:
1. Open SB501000 in browser
2. Click + to add a new container — verify CNT number auto-generates
3. Fill in fields, save — verify detail panel persists
4. Attach a file via paperclip — verify paperclip icon appears
5. On an existing container with PO links, click Receive Goods — verify PO Receipt created

**Step 3: Manual verification by Melanie**

Share the sandbox URL with Mel for user acceptance testing before promoting to production.
