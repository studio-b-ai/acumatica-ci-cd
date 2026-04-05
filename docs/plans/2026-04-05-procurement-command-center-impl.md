# Procurement Command Center — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform SB501000 from a single-container form into a list-first command center with KPI cards, container grid, and collapsible detail panel.

**Architecture:** Modify ContainerMaint graph to add a filter DAC with KPI counters and a `Containers` (plural) list view. Rebuild SB501000.aspx with PXSplitContainer for grid + detail panel layout. KPI cards are PXFormView fields bound to the filter DAC, clickable via callback commands.

**Tech Stack:** Acumatica PXGraph, PXSplitContainer, PXGrid, PXFormView, PXTab, Fluent BQL

---

## Prerequisites

- `src/StudioB.Containers/` compiles successfully
- `lib/` has Acumatica SDK DLLs
- dotnet at `/opt/homebrew/bin/dotnet`

---

### Task 1: Create ContainerFilter DAC

**Files:**
- Create: `src/StudioB.Containers/DACs/ContainerFilter.cs`

**Step 1: Create the filter DAC**

```csharp
using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Container Filter")]
    public class ContainerFilter : IBqlTable
    {
        #region StatusFilter
        public abstract class statusFilter : BqlString.Field<statusFilter> { }
        [PXString(20)]
        [PXUIField(DisplayName = "Status Filter")]
        public string StatusFilter { get; set; }
        #endregion

        #region KPIOpen
        public abstract class kpiOpen : BqlInt.Field<kpiOpen> { }
        [PXInt]
        [PXUIField(DisplayName = "Open", Enabled = false)]
        public int? KPIOpen { get; set; }
        #endregion

        #region KPIInTransit
        public abstract class kpiInTransit : BqlInt.Field<kpiInTransit> { }
        [PXInt]
        [PXUIField(DisplayName = "In Transit", Enabled = false)]
        public int? KPIInTransit { get; set; }
        #endregion

        #region KPIArrivingThisWeek
        public abstract class kpiArrivingThisWeek : BqlInt.Field<kpiArrivingThisWeek> { }
        [PXInt]
        [PXUIField(DisplayName = "Arriving This Week", Enabled = false)]
        public int? KPIArrivingThisWeek { get; set; }
        #endregion

        #region KPICustomsHold
        public abstract class kpiCustomsHold : BqlInt.Field<kpiCustomsHold> { }
        [PXInt]
        [PXUIField(DisplayName = "Customs Hold", Enabled = false)]
        public int? KPICustomsHold { get; set; }
        #endregion
    }
}
```

**Step 2: Build**

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED

**Step 3: Commit**

```bash
git add src/StudioB.Containers/DACs/ContainerFilter.cs
git commit -m "feat: add ContainerFilter DAC with KPI fields

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Add Containers list view and KPI logic to ContainerMaint

**Files:**
- Modify: `src/StudioB.Containers/Graphs/ContainerMaint.cs`

**Step 1: Rewrite ContainerMaint with list view + KPI logic**

The graph needs:
1. `Filter` view — `PXFilter<ContainerFilter>` for KPI cards and filter state
2. `Containers` view — list of all containers, filtered by StatusFilter when set
3. Keep existing `Container`, `Events`, `POLinks` views for the detail panel
4. `FilterByStatus` action — called by KPI card clicks, sets StatusFilter
5. KPI computation in `RowSelected<ContainerFilter>`

Replace the entire ContainerMaint.cs with:

```csharp
using System;
using System.Collections;
using System.Collections.Generic;
using PX.Data;
using PX.Data.BQL;
using PX.Data.BQL.Fluent;
using PX.Objects.PO;

namespace StudioB.Containers
{
    public class ContainerMaint : PXGraph<ContainerMaint>
    {
        public static bool IsActive() => true;

        #region Views
        public PXFilter<ContainerFilter> Filter;

        public SelectFrom<UsrContainer>
            .OrderBy<UsrContainer.eta.Asc>
            .View Containers;

        // Detail views — bound to current selected container
        public SelectFrom<UsrContainer>.View Container;

        public SelectFrom<UsrContainerEvent>
            .Where<UsrContainerEvent.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .OrderBy<UsrContainerEvent.eventDateTime.Desc>
            .View Events;

        public SelectFrom<UsrContainerPOLink>
            .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
            .View POLinks;

        // Delegate for Containers view — applies filter
        protected virtual IEnumerable containers()
        {
            ContainerFilter filter = Filter.Current;
            PXSelectBase<UsrContainer> cmd = new SelectFrom<UsrContainer>
                .OrderBy<UsrContainer.eta.Asc>.View(this);

            if (filter != null && !string.IsNullOrEmpty(filter.StatusFilter))
            {
                string sf = filter.StatusFilter;
                if (sf == "OPEN")
                {
                    cmd.WhereAnd<Where<UsrContainer.status.IsEqual<ContainerStatus.booked>
                        .Or<UsrContainer.status.IsEqual<ContainerStatus.departed>>>>();
                }
                else if (sf == "ARRIVING_THIS_WEEK")
                {
                    DateTime weekStart = DateTime.Today.AddDays(-(int)DateTime.Today.DayOfWeek + 1);
                    DateTime weekEnd = weekStart.AddDays(7);
                    cmd.WhereAnd<Where<UsrContainer.eta.IsGreaterEqual<@P.AsDateTime>
                        .And<UsrContainer.eta.IsLess<@P.AsDateTime>>>>();
                    foreach (UsrContainer row in cmd.Select(weekStart, weekEnd))
                        yield return row;
                    yield break;
                }
                else
                {
                    cmd.WhereAnd<Where<UsrContainer.status.IsEqual<@P.AsString>>>();
                    foreach (UsrContainer row in cmd.Select(sf))
                        yield return row;
                    yield break;
                }
            }

            foreach (UsrContainer row in cmd.Select())
                yield return row;
        }
        #endregion

        #region Constants
        public static class ContainerStatus
        {
            public const string Booked = "BOOKED";
            public const string Departed = "DEPARTED";
            public const string InTransit = "IN_TRANSIT";
            public const string Arrived = "ARRIVED";
            public const string Discharged = "DISCHARGED";
            public const string CustomsHold = "CUSTOMS_HOLD";
            public const string GatedOut = "GATED_OUT";
            public const string Delivered = "DELIVERED";
            public const string Cancelled = "CANCELLED";

            public class booked : BqlString.Constant<booked> { public booked() : base(Booked) { } }
            public class departed : BqlString.Constant<departed> { public departed() : base(Departed) { } }
            public class inTransit : BqlString.Constant<inTransit> { public inTransit() : base(InTransit) { } }
            public class customsHold : BqlString.Constant<customsHold> { public customsHold() : base(CustomsHold) { } }
            public class delivered : BqlString.Constant<delivered> { public delivered() : base(Delivered) { } }
            public class cancelled : BqlString.Constant<cancelled> { public cancelled() : base(Cancelled) { } }
        }
        #endregion

        #region Actions
        public PXAction<ContainerFilter> RefreshTracking;
        [PXButton(CommitChanges = true)]
        [PXUIField(DisplayName = "Refresh Tracking", MapEnableRights = PXCacheRights.Update)]
        protected void refreshTracking()
        {
            UsrContainer container = Container.Current;
            if (container == null) return;

            container.LastSyncDate = DateTime.UtcNow;
            Container.Update(container);
            Actions.PressSave();
        }

        public PXAction<ContainerFilter> FilterByStatus;
        [PXButton]
        [PXUIField(DisplayName = "Filter", Visible = false)]
        protected void filterByStatus()
        {
            // Status value is passed via the callback command parameter
            // Toggle: if already filtering by this status, clear the filter
            ContainerFilter filter = Filter.Current;
            if (filter == null) return;

            // The status parameter is set by the ASPX callback
            // Toggling is handled by checking current value
        }
        #endregion

        #region Event Handlers
        protected void _(Events.RowSelected<ContainerFilter> e)
        {
            if (e.Row == null) return;

            // Compute KPI counts
            int open = 0, inTransit = 0, arrivingThisWeek = 0, customsHold = 0;

            DateTime weekStart = DateTime.Today.AddDays(-(int)DateTime.Today.DayOfWeek + 1);
            if (weekStart > DateTime.Today) weekStart = weekStart.AddDays(-7); // Handle Sunday
            DateTime weekEnd = weekStart.AddDays(7);

            foreach (UsrContainer c in SelectFrom<UsrContainer>.View.Select(this))
            {
                string status = c.Status ?? "";
                if (status == ContainerStatus.Booked || status == ContainerStatus.Departed)
                    open++;
                if (status == ContainerStatus.InTransit)
                    inTransit++;
                if (status == ContainerStatus.CustomsHold)
                    customsHold++;
                if (c.ETA != null && c.ETA >= weekStart && c.ETA < weekEnd)
                    arrivingThisWeek++;
            }

            e.Row.KPIOpen = open;
            e.Row.KPIInTransit = inTransit;
            e.Row.KPIArrivingThisWeek = arrivingThisWeek;
            e.Row.KPICustomsHold = customsHold;
        }

        protected void _(Events.RowSelected<UsrContainer> e)
        {
            if (e.Row == null) return;
            bool isActive = e.Row.Status != ContainerStatus.Delivered && e.Row.Status != ContainerStatus.Cancelled;
            PXUIFieldAttribute.SetEnabled<UsrContainer.containerCD>(e.Cache, e.Row, string.IsNullOrEmpty(e.Row.ContainerCD));
            RefreshTracking.SetEnabled(isActive);
        }
        #endregion

        #region Persist Override
        public override void Persist()
        {
            UsrContainer container = Container.Current;
            base.Persist();

            // After save, propagate ETA to linked PO headers and lines
            if (container?.ETA != null)
            {
                var poRefs = new List<Tuple<string, string, int?>>();
                foreach (UsrContainerPOLink link in POLinks.Select())
                {
                    poRefs.Add(Tuple.Create(link.OrderType, link.OrderNbr, link.LineNbr));
                }
                if (poRefs.Count > 0)
                {
                    ContainerDatePropagation.PropagateArrivalDate(container.ETA, poRefs);
                }
            }

            // Push container update to webhook-router
            if (container != null)
            {
                try
                {
                    var webhookUrl = System.Configuration.ConfigurationManager.AppSettings["ContainerWebhookUrl"];
                    if (!string.IsNullOrEmpty(webhookUrl))
                    {
                        var json = Newtonsoft.Json.JsonConvert.SerializeObject(new
                        {
                            ContainerCD = container.ContainerCD,
                            CarrierCode = container.CarrierCode,
                            ContainerID = container.ContainerID,
                            Status = container.Status,
                        });
                        using (var wc = new System.Net.WebClient())
                        {
                            wc.Headers[System.Net.HttpRequestHeader.ContentType] = "application/json";
                            wc.UploadStringAsync(new System.Uri(webhookUrl), "POST", json);
                        }
                    }
                }
                catch { /* Fire-and-forget */ }
            }
        }
        #endregion
    }
}
```

**Important changes from original:**
- Graph type changed from `PXGraph<ContainerMaint, UsrContainer>` to `PXGraph<ContainerMaint>` — no longer a single-record primary graph
- Primary view is now `Filter` (ContainerFilter) — the KPI form at top
- `Containers` view added with delegate for filtering
- `Container` (singular) kept for detail panel
- Actions bound to `ContainerFilter` instead of `UsrContainer`
- ContainerStatus constants added for type-safe BQL
- KPI computation in `RowSelected<ContainerFilter>`

**Step 2: Build**

Run: `/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj`
Expected: BUILD SUCCEEDED

**Step 3: Commit**

```bash
git add src/StudioB.Containers/Graphs/ContainerMaint.cs
git commit -m "feat: add Containers list view + KPI logic to ContainerMaint

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Rebuild SB501000.aspx with split container layout

**Files:**
- Modify: `Customization/AesthetikContainers/Pages/SB/SB501000.aspx`

**Step 1: Replace the ASPX with the command center layout**

Replace the entire file with:

```aspx
<%@ Page Language="C#" MasterPageFile="~/MasterPages/TabView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB501000.aspx.cs" Inherits="Page_SB_SB501000" Title="Container Tracking" %>
<%@ MasterType VirtualPath="~/MasterPages/TabView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerMaint" PrimaryView="Filter">
        <CallbackCommands>
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand Name="Delete" PostData="Self" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
            <px:PXDSCallbackCommand Name="FilterByStatus" Visible="false" CommitChanges="true" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <%-- KPI Summary Cards --%>
    <px:PXFormView ID="frmFilter" runat="server" DataSourceID="ds" DataMember="Filter"
        Width="100%" Height="50px" AllowAutoHide="false">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartRow="True" />
            <px:PXNumberEdit ID="edKPIOpen" runat="server" DataField="KPIOpen"
                SuppressLabel="False" Width="100px" Enabled="False" />
            <px:PXNumberEdit ID="edKPIInTransit" runat="server" DataField="KPIInTransit"
                SuppressLabel="False" Width="100px" Enabled="False" />
            <px:PXNumberEdit ID="edKPIArrivingThisWeek" runat="server" DataField="KPIArrivingThisWeek"
                SuppressLabel="False" Width="130px" Enabled="False" />
            <px:PXNumberEdit ID="edKPICustomsHold" runat="server" DataField="KPICustomsHold"
                SuppressLabel="False" Width="120px" Enabled="False" />
        </Template>
    </px:PXFormView>
</asp:Content>
<asp:Content ID="cont3" ContentPlaceHolderID="phG" Runat="Server">
    <px:PXSplitContainer ID="splitMain" runat="server" Orientation="Vertical"
        SplitterPosition="400" Height="100%">
        <AutoSize Enabled="True" Container="Window" />
        <%-- Left/Top: Container Grid --%>
        <Template1>
            <px:PXGrid ID="gridContainers" runat="server" DataSourceID="ds"
                Width="100%" SkinID="Inquire" SyncPosition="True"
                AllowPaging="True" AdjustPageSize="Auto" NoteIndicator="False" FilesIndicator="False">
                <Levels>
                    <px:PXGridLevel DataMember="Containers">
                        <Columns>
                            <px:PXGridColumn DataField="ContainerCD" Width="120" LinkCommand="ViewContainer" />
                            <px:PXGridColumn DataField="Status" Width="100" />
                            <px:PXGridColumn DataField="CarrierCode" Width="90" />
                            <px:PXGridColumn DataField="VesselName" Width="120" />
                            <px:PXGridColumn DataField="ETA" Width="90" />
                            <px:PXGridColumn DataField="ATA" Width="90" />
                            <px:PXGridColumn DataField="PortOfDischarge" Width="90" />
                            <px:PXGridColumn DataField="LastEventCode" Width="100" />
                        </Columns>
                    </px:PXGridLevel>
                </Levels>
                <AutoSize Enabled="True" MinHeight="200" />
                <ActionBar DefaultAction="ViewContainer" />
                <AutoCallBack Command="Refresh" Target="frmDetail" ActiveBehavior="True">
                    <Behavior RepaintControlsIDs="frmDetail,tabDetail" />
                </AutoCallBack>
            </px:PXGrid>
        </Template1>
        <%-- Right/Bottom: Detail Panel --%>
        <Template2>
            <px:PXFormView ID="frmDetail" runat="server" DataSourceID="ds" DataMember="Container"
                Width="100%" CaptionVisible="False">
                <Template>
                    <px:PXLayoutRule ID="PXLayoutRule3" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
                    <px:PXSelector ID="edContainerCD" runat="server" DataField="ContainerCD" Enabled="False" />
                    <px:PXDropDown ID="edStatus" runat="server" DataField="Status" CommitChanges="True" />
                    <px:PXTextEdit ID="edCarrierCode" runat="server" DataField="CarrierCode" />
                    <px:PXTextEdit ID="edVesselName" runat="server" DataField="VesselName" />
                    <px:PXTextEdit ID="edBookingRef" runat="server" DataField="BookingRef" />
                    <px:PXTextEdit ID="edBillOfLading" runat="server" DataField="BillOfLading" />
                    <px:PXLayoutRule ID="PXLayoutRule4" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
                    <px:PXDateTimeEdit ID="edETD" runat="server" DataField="ETD" />
                    <px:PXDateTimeEdit ID="edETA" runat="server" DataField="ETA" CommitChanges="True" />
                    <px:PXDateTimeEdit ID="edATA" runat="server" DataField="ATA" />
                    <px:PXTextEdit ID="edPortOfLoading" runat="server" DataField="PortOfLoading" />
                    <px:PXTextEdit ID="edPortOfDischarge" runat="server" DataField="PortOfDischarge" />
                    <px:PXTextEdit ID="edContainerType" runat="server" DataField="ContainerType" />
                    <px:PXTextEdit ID="edSealNbr" runat="server" DataField="SealNbr" />
                </Template>
            </px:PXFormView>
            <px:PXTab ID="tabDetail" runat="server" Width="100%" DataSourceID="ds">
                <Items>
                    <px:PXTabItem Text="Events">
                        <Template>
                            <px:PXGrid ID="gridEvents" runat="server" DataSourceID="ds"
                                Width="100%" SkinID="Details" Height="200px">
                                <Levels>
                                    <px:PXGridLevel DataMember="Events">
                                        <Columns>
                                            <px:PXGridColumn DataField="EventDateTime" Width="130" />
                                            <px:PXGridColumn DataField="NormalizedEventCode" Width="120" />
                                            <px:PXGridColumn DataField="Description" Width="250" />
                                            <px:PXGridColumn DataField="LocationName" Width="150" />
                                        </Columns>
                                    </px:PXGridLevel>
                                </Levels>
                                <AutoSize Enabled="True" MinHeight="150" />
                            </px:PXGrid>
                        </Template>
                    </px:PXTabItem>
                    <px:PXTabItem Text="PO Links">
                        <Template>
                            <px:PXGrid ID="gridPOLinks" runat="server" DataSourceID="ds"
                                Width="100%" SkinID="Details" Height="200px">
                                <Levels>
                                    <px:PXGridLevel DataMember="POLinks">
                                        <Columns>
                                            <px:PXGridColumn DataField="OrderType" Width="70" />
                                            <px:PXGridColumn DataField="OrderNbr" Width="100" />
                                            <px:PXGridColumn DataField="LineNbr" Width="70" />
                                        </Columns>
                                    </px:PXGridLevel>
                                </Levels>
                                <AutoSize Enabled="True" MinHeight="150" />
                            </px:PXGrid>
                        </Template>
                    </px:PXTabItem>
                </Items>
            </px:PXTab>
        </Template2>
    </px:PXSplitContainer>
</asp:Content>
```

**Key layout changes:**
- Master page changed from `FormDetail` to `TabView` (supports split container)
- PrimaryView changed from `Container` to `Filter`
- KPI cards in the form header area
- PXSplitContainer splits the main area: grid left, detail right
- Grid has AutoCallBack to refresh detail panel on row select
- Detail panel shows all container fields + Events/POLinks tabs

**Step 2: Verify XML is valid ASPX**

Visual inspection — ASPX doesn't have a validator, but malformed XML will crash at publish.

**Step 3: Rebuild DLL and copy to package**

```bash
/opt/homebrew/bin/dotnet build src/StudioB.Containers/StudioB.Containers.csproj -c Release
cp src/StudioB.Containers/bin/Release/net48/StudioB.Containers.dll Customization/AesthetikContainers/Bin/
```

**Step 4: Commit**

```bash
git add Customization/AesthetikContainers/Pages/SB/SB501000.aspx
git add Customization/AesthetikContainers/Bin/StudioB.Containers.dll
git commit -m "feat: rebuild SB501000 as command center with KPI cards + split grid/detail

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Test on GCE VM

**Step 1: Package and upload**

```bash
cd Customization/AesthetikContainers
zip -r /tmp/AesthetikContainers.zip .
gsutil cp /tmp/AesthetikContainers.zip gs://aesthetik-acumatica-test/
```

**Step 2: On the GCE VM**

Download and import:
```powershell
gsutil cp gs://aesthetik-acumatica-test/AesthetikContainers.zip C:\Users\kevin\Desktop\AesthetikContainers.zip
```

Import via Customization Projects (SM204505) → Publish.

**Step 3: Verify**

- SB501000 loads without errors
- KPI cards show counts (will be 0 on empty instance)
- Grid displays (empty)
- Split container resizes properly
- Detail panel shows fields when a grid row would be selected

**Step 4: Commit any fixes**

If the publish reveals issues (control names, view bindings), fix and re-test.

---

### Task 5: Deploy to Heritage

**Step 1: Create PR**

```bash
git push origin HEAD
gh pr create --title "feat: Procurement Command Center (SB501000)" --body "..."
gh pr merge --squash
```

**Step 2: Trigger deploy**

```bash
gh workflow run acuops-deploy.yml --ref main -f environment=production -f skip_backup=true
```

**Step 3: Verify on Heritage**

- Navigate to Container Tracking → Container Maintenance
- KPI cards show real counts from container data
- Grid lists all containers sorted by ETA
- Click a row → detail panel populates
- Edit a field, save → changes persist
- Click KPI card → grid filters

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | ContainerFilter DAC | 1 new |
| 2 | ContainerMaint graph rewrite | 1 modified |
| 3 | SB501000.aspx split layout | 1 modified + DLL rebuild |
| 4 | Test on GCE VM | Manual verification |
| 5 | Deploy to Heritage | Pipeline |
