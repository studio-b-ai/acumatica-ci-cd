# Container Tracking Feature Parity — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build 5 screens (4 GIs + 1 ASPX) to replace the IIG Container Management ISV screens, then add Playwright tests for each, then produce an end-user migration guide.

**Architecture:** GIs built via `gi_builder.py` → SQL embedded in `AesthetikContainersInstall.UpdateDatabase()`. Freight Forwarders is a new DAC + Graph + ASPX in `project.xml`. SiteMap entries via SQL. All deployed through AcuOps CI/CD pipeline (branch → PR → merge → auto-deploy).

**Tech Stack:** Python (gi_builder.py, Playwright), C# (Acumatica DAC/Graph), ASPX (Acumatica UI), SQL (GI definitions, DDL)

**Key Files:**
- `Customization/AesthetikContainers/project.xml` — all DACs, graphs, ASPX, CustomizationPlugin
- `scripts/heritage/gi_builder.py` — GI SQL generator
- `scripts/heritage/gi_schema.py` — GI schema map
- `scripts/heritage/poc_user_audit_trail.py` — reference GI builder usage
- `tests/ui/test_container_tracking.py` — Playwright tests (27 existing, add ~15 new)
- `tests/ui/helpers.py` — `ACUMATICA_URL`, `find_custom_fields()`, login helpers
- `tests/ui/conftest.py` — `acumatica_page` fixture (session-scoped login), `dialog_messages`

**Constraints:**
- After-hours deploys only (publishes restart Acumatica app pool)
- Never commit to main — always branch + PR
- `navigate_to_screen_safe()` + `wait_for_screen()` for all Playwright navigation (no `networkidle`)
- GI SQL must include `-- REVIEWED: gi-sql-safe` marker
- All DDL must use `EnsureTable()` / `EnsureColumn()` / `EnsureIndex()` (idempotent)
- Container Tracking workspace ParentID: `9c89e3db-7c47-43c0-8554-5d2c9f2c0e87`

---

## Task 1: Generate PO Containers GI SQL (SB401000)

**Files:**
- Create: `scripts/heritage/gi_container_tracking.py`
- Reference: `scripts/heritage/poc_user_audit_trail.py`

**Step 1: Create the GI definition script**

Create `scripts/heritage/gi_container_tracking.py` with 4 GI definitions. Start with PO Containers:

```python
"""Generate Container Tracking GI SQL using GI Builder Engine.

Generates SQL for 4 GIs:
  1. PO Containers (SB401000) — active containers with PO counts
  2. SO Containers (SB401010) — outbound shipment containers
  3. Container Events (SB401020) — tracking event timeline
  4. Custom Classification (SB401030) — stock item classification fields
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gi_builder import GIDefinition, GIBuilder
from gi_schema import GISchemaMap

# Mock schema — same as POC, known-good for 24.200.001
MOCK_SCHEMA = {
    "GIDesign": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "ScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "FilterColCount": {"data_type": "int", "nullable": "YES", "max_length": None, "default": "((3))"},
        "PageSize": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "ExportTop": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "ExposeViaOData": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "NoteID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CreatedByScreenID": {"data_type": "nvarchar", "nullable": "YES", "max_length": 8, "default": None},
        "CreatedDateTime": {"data_type": "datetime", "nullable": "YES", "max_length": None, "default": None},
        "LastModifiedByID": {"data_type": "uniqueidentifier", "nullable": "YES", "max_length": None, "default": None},
    },
    "GITable": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "Alias": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 512, "default": None},
        "Type": {"data_type": "int", "nullable": "NO", "max_length": None, "default": "((0))"},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIResult": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Field": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "SortOrder": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "Width": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "IsVisible": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "DefaultNav": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "Caption": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "RowID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIFilter": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "Name": {"data_type": "nvarchar", "nullable": "NO", "max_length": 128, "default": None},
        "DisplayName": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "DataType": {"data_type": "int", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GIWhere": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "Condition": {"data_type": "nvarchar", "nullable": "YES", "max_length": 2, "default": None},
        "Value1": {"data_type": "nvarchar", "nullable": "YES", "max_length": 256, "default": None},
        "IsExpression": {"data_type": "bit", "nullable": "NO", "max_length": None, "default": "((0))"},
        "Operation": {"data_type": "nvarchar", "nullable": "YES", "max_length": 1, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
    "GISort": {
        "DesignID": {"data_type": "uniqueidentifier", "nullable": "NO", "max_length": None, "default": None},
        "LineNbr": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "SortOrder": {"data_type": "nvarchar", "nullable": "YES", "max_length": 1, "default": None},
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
}

TEMPLATE_ROW = {
    "CreatedByID": "B5344897-037E-4D58-B5C3-1BDFD0F47BF4",
    "CreatedByScreenID": "SM208000",
}


def po_containers_spec() -> GIDefinition:
    """PO Containers GI (SB401000) — browse active containers with PO link counts."""
    return GIDefinition(
        name="PO Containers",
        screen_id="SB401000",
        tables=[
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "CarrierCode", "caption": "Carrier", "width": 100},
            {"field": "VesselName", "caption": "Vessel", "width": 150},
            {"field": "PortOfLoading", "caption": "Origin", "width": 120},
            {"field": "PortOfDischarge", "caption": "Destination", "width": 120},
            {"field": "ETD", "caption": "ETD", "width": 100},
            {"field": "ETA", "caption": "ETA", "width": 100},
            {"field": "ATA", "caption": "ATA", "width": 100},
            {"field": "ContainerType", "caption": "Type", "width": 80},
            {"field": "BookingRef", "caption": "Booking Ref", "width": 120},
        ],
        filters=[
            {"name": "StatusFilter", "display_name": "Status", "data_type": 6},
            {"name": "CarrierFilter", "display_name": "Carrier", "data_type": 6},
        ],
        where=[
            {"field": "Container.Status", "condition": "E ", "value": "@StatusFilter", "operation": "A"},
            {"field": "Container.CarrierCode", "condition": "E ", "value": "@CarrierFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Container.ETA", "order": "D"},
        ],
    )


def so_containers_spec() -> GIDefinition:
    """SO Containers GI (SB401010) — outbound shipment container visibility."""
    return GIDefinition(
        name="SO Containers",
        screen_id="SB401010",
        tables=[
            {"dac": "PX.Objects.SO.SOShipment", "alias": "Shipment"},
        ],
        results=[
            {"field": "ShipmentNbr", "caption": "Shipment", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "CustomerID", "caption": "Customer", "width": 120},
            {"field": "ShipDate", "caption": "Ship Date", "width": 100},
            {"field": "UsrContainerID", "caption": "Container", "width": 120},
            {"field": "UsrIncludeInContainer", "caption": "In Container", "width": 80},
        ],
        filters=[
            {"name": "StatusFilter", "display_name": "Status", "data_type": 6},
        ],
        where=[
            {"field": "Shipment.Status", "condition": "E ", "value": "@StatusFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Shipment.ShipDate", "order": "D"},
        ],
    )


def container_events_spec() -> GIDefinition:
    """Container Events GI (SB401020) — tracking event timeline."""
    return GIDefinition(
        name="Container Events",
        screen_id="SB401020",
        tables=[
            {"dac": "StudioB.Containers.UsrContainerEvent", "alias": "Event"},
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container", "width": 120},
            {"field": "EventDateTime", "caption": "Date/Time", "width": 150},
            {"field": "NormalizedEventCode", "caption": "Event", "width": 120},
            {"field": "EventClassifier", "caption": "Type", "width": 80},
            {"field": "LocationName", "caption": "Location", "width": 150},
            {"field": "VesselName", "caption": "Vessel", "width": 120},
            {"field": "Description", "caption": "Description", "width": 200},
        ],
        filters=[
            {"name": "ContainerFilter", "display_name": "Container", "data_type": 6},
            {"name": "EventCodeFilter", "display_name": "Event Code", "data_type": 6},
        ],
        where=[
            {"field": "Container.ContainerCD", "condition": "E ", "value": "@ContainerFilter", "operation": "A"},
            {"field": "Event.NormalizedEventCode", "condition": "E ", "value": "@EventCodeFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Event.EventDateTime", "order": "D"},
        ],
    )


def custom_classification_spec() -> GIDefinition:
    """Custom Classification GI (SB401030) — stock item classification fields."""
    return GIDefinition(
        name="Custom Classification",
        screen_id="SB401030",
        tables=[
            {"dac": "PX.Objects.IN.InventoryItem", "alias": "Item"},
        ],
        results=[
            {"field": "InventoryCD", "caption": "Item ID", "width": 120},
            {"field": "Descr", "caption": "Description", "width": 200},
            {"field": "ItemClassID", "caption": "Item Class", "width": 120},
            {"field": "UsrFiberContent", "caption": "Fiber Content", "width": 150},
            {"field": "UsrDutyRate", "caption": "Duty Rate", "width": 100},
            {"field": "UsrPreferentialTariff", "caption": "Pref. Tariff", "width": 100},
            {"field": "UsrFreightClass", "caption": "Freight Class", "width": 100},
        ],
        filters=[
            {"name": "ItemClassFilter", "display_name": "Item Class", "data_type": 6},
        ],
        where=[
            {"field": "Item.ItemClassID", "condition": "E ", "value": "@ItemClassFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Item.InventoryCD", "order": "A"},
        ],
    )


ALL_SPECS = [
    ("po_containers", po_containers_spec),
    ("so_containers", so_containers_spec),
    ("container_events", container_events_spec),
    ("custom_classification", custom_classification_spec),
]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate Container Tracking GI SQL")
    parser.add_argument("--output-dir", default="data/container-tracking", help="Output directory")
    parser.add_argument("--company-id", type=int, default=2, help="Acumatica CompanyID")
    parser.add_argument("--gi", help="Generate only this GI (po_containers|so_containers|container_events|custom_classification)")
    args = parser.parse_args()

    schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")
    builder = GIBuilder(schema, template_row=TEMPLATE_ROW, company_id=args.company_id)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    specs_to_build = ALL_SPECS
    if args.gi:
        specs_to_build = [(n, f) for n, f in ALL_SPECS if n == args.gi]
        if not specs_to_build:
            print(f"Unknown GI: {args.gi}. Options: {', '.join(n for n, _ in ALL_SPECS)}")
            sys.exit(1)

    for name, spec_fn in specs_to_build:
        spec = spec_fn()
        sql = builder.build_sql(spec)
        out_path = output_dir / f"{name}.sql"
        out_path.write_text(sql)
        print(f"  {name}: {len(sql)} bytes -> {out_path}")
        print(f"    GI: {spec.name} ({len(spec.tables)} tables, {len(spec.results)} cols, "
              f"{len(spec.filters)} filters)")
```

**Step 2: Run the script to generate all 4 GI SQL files**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python scripts/heritage/gi_container_tracking.py --output-dir data/container-tracking
```

Expected: 4 SQL files in `data/container-tracking/` — each with `REVIEWED: gi-sql-safe` marker, idempotent, transactional.

**Step 3: Verify the generated SQL is valid**

```bash
# Check each file has the REVIEWED marker and key structure
grep -l "REVIEWED: gi-sql-safe" data/container-tracking/*.sql
grep -l "BEGIN TRANSACTION" data/container-tracking/*.sql
grep -l "GIDesign" data/container-tracking/*.sql
```

Expected: All 4 files listed for each check.

**Step 4: Commit**

```bash
git add scripts/heritage/gi_container_tracking.py data/container-tracking/
git commit -m "feat: GI builder specs for 4 container tracking inquiries

PO Containers (SB401000), SO Containers (SB401010),
Container Events (SB401020), Custom Classification (SB401030).
SQL generated via gi_builder.py, ready for CustomizationPlugin embed."
```

---

## Task 2: Add Freight Forwarders DAC + Graph to project.xml

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`

**Step 1: Add UsrFreightForwarder DAC as a new `<Graph>` element**

Add this `<Graph>` element after the existing `UsrContainerPOLink` Graph element in project.xml:

```xml
<Graph ClassName="UsrFreightForwarder" Source="#CDATA" IsNew="True" FileType="NewFile">
    <CDATA name="Source"><![CDATA[using System;
using PX.Data;
using PX.Data.BQL;

namespace StudioB.Containers
{
    [Serializable]
    [PXCacheName("Freight Forwarder")]
    public class UsrFreightForwarder : IBqlTable
    {
        #region ForwarderID
        public abstract class forwarderID : BqlInt.Field<forwarderID> { }
        [PXDBIdentity]
        public int? ForwarderID { get; set; }
        #endregion

        #region ForwarderCD
        public abstract class forwarderCD : BqlString.Field<forwarderCD> { }
        [PXDBString(15, IsUnicode = true, IsKey = true, InputMask = ">CCCCCCCCCCCCCCC")]
        [PXDefault]
        [PXUIField(DisplayName = "Forwarder ID", Visibility = PXUIVisibility.SelectorVisible)]
        [PXSelector(typeof(Search<UsrFreightForwarder.forwarderCD>),
            typeof(UsrFreightForwarder.forwarderCD),
            typeof(UsrFreightForwarder.name),
            typeof(UsrFreightForwarder.carrierAPIType),
            typeof(UsrFreightForwarder.active))]
        public string ForwarderCD { get; set; }
        #endregion

        #region Name
        public abstract class name : BqlString.Field<name> { }
        [PXDBString(100, IsUnicode = true)]
        [PXDefault]
        [PXUIField(DisplayName = "Company Name")]
        public string Name { get; set; }
        #endregion

        #region ContactName
        public abstract class contactName : BqlString.Field<contactName> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Contact Name")]
        public string ContactName { get; set; }
        #endregion

        #region Phone
        public abstract class phone : BqlString.Field<phone> { }
        [PXDBString(30, IsUnicode = true)]
        [PXUIField(DisplayName = "Phone")]
        public string Phone { get; set; }
        #endregion

        #region Email
        public abstract class email : BqlString.Field<email> { }
        [PXDBString(100, IsUnicode = true)]
        [PXUIField(DisplayName = "Email")]
        public string Email { get; set; }
        #endregion

        #region Website
        public abstract class website : BqlString.Field<website> { }
        [PXDBString(200, IsUnicode = true)]
        [PXUIField(DisplayName = "Website")]
        public string Website { get; set; }
        #endregion

        #region CarrierAPIType
        public abstract class carrierAPIType : BqlString.Field<carrierAPIType> { }
        [PXDBString(20, IsUnicode = true)]
        [PXUIField(DisplayName = "API Type")]
        [PXStringList(
            new[] { "SEATRATES", "MAERSK", "FEDEX", "UPS", "OTHER" },
            new[] { "Seatrates", "Maersk", "FedEx", "UPS", "Other" })]
        public string CarrierAPIType { get; set; }
        #endregion

        #region CarrierAPIKey
        public abstract class carrierAPIKey : BqlString.Field<carrierAPIKey> { }
        [PXRSACryptString(200, IsUnicode = true)]
        [PXUIField(DisplayName = "API Key")]
        public string CarrierAPIKey { get; set; }
        #endregion

        #region Active
        public abstract class active : BqlBool.Field<active> { }
        [PXDBBool]
        [PXDefault(true)]
        [PXUIField(DisplayName = "Active")]
        public bool? Active { get; set; }
        #endregion

        #region NoteID
        public abstract class noteID : BqlGuid.Field<noteID> { }
        [PXNote]
        public Guid? NoteID { get; set; }
        #endregion

        #region CreatedByID
        public abstract class createdByID : BqlGuid.Field<createdByID> { }
        [PXDBCreatedByID]
        public Guid? CreatedByID { get; set; }
        #endregion

        #region CreatedByScreenID
        public abstract class createdByScreenID : BqlString.Field<createdByScreenID> { }
        [PXDBCreatedByScreenID]
        public string CreatedByScreenID { get; set; }
        #endregion

        #region CreatedDateTime
        public abstract class createdDateTime : BqlDateTime.Field<createdDateTime> { }
        [PXDBCreatedDateTime]
        public DateTime? CreatedDateTime { get; set; }
        #endregion

        #region LastModifiedByID
        public abstract class lastModifiedByID : BqlGuid.Field<lastModifiedByID> { }
        [PXDBLastModifiedByID]
        public Guid? LastModifiedByID { get; set; }
        #endregion

        #region LastModifiedByScreenID
        public abstract class lastModifiedByScreenID : BqlString.Field<lastModifiedByScreenID> { }
        [PXDBLastModifiedByScreenID]
        public string LastModifiedByScreenID { get; set; }
        #endregion

        #region LastModifiedDateTime
        public abstract class lastModifiedDateTime : BqlDateTime.Field<lastModifiedDateTime> { }
        [PXDBLastModifiedDateTime]
        public DateTime? LastModifiedDateTime { get; set; }
        #endregion

        #region Tstamp
        public abstract class tstamp : BqlByteArray.Field<tstamp> { }
        [PXDBTimestamp]
        public byte[] Tstamp { get; set; }
        #endregion
    }
}
]]></CDATA>
</Graph>
```

**Step 2: Add FreightForwarderMaint graph**

Add after the UsrFreightForwarder DAC graph:

```xml
<Graph ClassName="FreightForwarderMaint" Source="#CDATA" IsNew="True" FileType="NewFile">
    <CDATA name="Source"><![CDATA[using PX.Data;
using PX.Data.BQL.Fluent;

namespace StudioB.Containers
{
    public class FreightForwarderMaint : PXGraph<FreightForwarderMaint, UsrFreightForwarder>
    {
        public SelectFrom<UsrFreightForwarder>.View Forwarder;
    }
}
]]></CDATA>
</Graph>
```

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: add UsrFreightForwarder DAC + FreightForwarderMaint graph

New DAC for carrier/forwarder master data with API key storage
(PXRSACryptString for encryption). Simple maintenance graph.
Replaces IIG IG.CM.30.91 Freight Forwarders screen."
```

---

## Task 3: Add Freight Forwarders ASPX screen to project.xml

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml`

**Step 1: Add SB302000.aspx `<File>` element**

Add after the existing SB501000.aspx File element:

```xml
<File AppRelativePath="Pages\SB\SB302000.aspx" Source="#CDATA">
    <CDATA name="Source"><![CDATA[<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB302000.aspx.cs" Inherits="Page_SB_SB302000" Title="Freight Forwarders" %>
<%@ MasterType VirtualPath="~/MasterPages/FormView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.FreightForwarderMaint" PrimaryView="Forwarder">
        <CallbackCommands>
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="Delete" PostData="Self" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="Forwarder" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXSelector ID="edForwarderCD" runat="server" DataField="ForwarderCD" />
            <px:PXTextEdit ID="edName" runat="server" DataField="Name" />
            <px:PXCheckBox ID="chkActive" runat="server" DataField="Active" />
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXTextEdit ID="edContactName" runat="server" DataField="ContactName" />
            <px:PXTextEdit ID="edPhone" runat="server" DataField="Phone" />
            <px:PXMaskEdit ID="edEmail" runat="server" DataField="Email" />
            <px:PXTextEdit ID="edWebsite" runat="server" DataField="Website" />
            <px:PXLayoutRule ID="PXLayoutRule3" runat="server" StartGroup="True" GroupCaption="API Configuration" />
            <px:PXDropDown ID="edCarrierAPIType" runat="server" DataField="CarrierAPIType" />
            <px:PXTextEdit ID="edCarrierAPIKey" runat="server" DataField="CarrierAPIKey" />
        </Template>
    </px:PXFormView>
</asp:Content>
]]></CDATA>
</File>
```

**Step 2: Add SB302000.aspx.cs code-behind**

```xml
<File AppRelativePath="Pages\SB\SB302000.aspx.cs" Source="#CDATA">
    <CDATA name="Source"><![CDATA[using System;
using PX.Web.UI;

public partial class Page_SB_SB302000 : PXPage
{
    protected void Page_Load(object sender, EventArgs e)
    {
    }
}
]]></CDATA>
</File>
```

**Step 3: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: add SB302000 Freight Forwarders ASPX screen

Two-column form layout: left column for ID/name/active,
right column for contact info, bottom group for API config.
Uses FormView master page (single record maintenance)."
```

---

## Task 4: Add DDL + SiteMap SQL to CustomizationPlugin

**Files:**
- Modify: `Customization/AesthetikContainers/project.xml` (CustomizationPlugin CDATA)

**Step 1: Add UsrFreightForwarder table creation to UpdateDatabase()**

Find the section after `EnsureIndex(conn, "UsrContainerPOLink"` calls and add:

```csharp
// ── Freight Forwarders Table ──────────────────────────────
EnsureTable(conn, "UsrFreightForwarder", @"
    CompanyID int NOT NULL DEFAULT 0,
    ForwarderID int IDENTITY(1,1) NOT NULL,
    ForwarderCD nvarchar(15) NOT NULL,
    Name nvarchar(100) NOT NULL,
    ContactName nvarchar(100) NULL,
    Phone nvarchar(30) NULL,
    Email nvarchar(100) NULL,
    Website nvarchar(200) NULL,
    CarrierAPIType nvarchar(20) NULL,
    CarrierAPIKey nvarchar(200) NULL,
    Active bit NOT NULL DEFAULT 1,
    NoteID uniqueidentifier NULL,
    CreatedByID uniqueidentifier NULL,
    CreatedByScreenID char(8) NULL,
    CreatedDateTime datetime NULL,
    LastModifiedByID uniqueidentifier NULL,
    LastModifiedByScreenID char(8) NULL,
    LastModifiedDateTime datetime NULL,
    tstamp timestamp NOT NULL,
    CONSTRAINT PK_UsrFreightForwarder PRIMARY KEY (CompanyID, ForwarderID)
");
EnsureIndex(conn, "UsrFreightForwarder", "IX_UsrFreightForwarder_CD", "CompanyID, ForwarderCD");
```

**Step 2: Add GI creation SQL for all 4 GIs**

After the DDL section, add a new method call `EnsureContainerTrackingGIs(conn);` and the method itself. Paste the SQL from each of the 4 generated files in `data/container-tracking/*.sql` into the method body, wrapped in the existing `using (var cmd = new SqlCommand(..., conn))` pattern.

The SQL is already idempotent (IF EXISTS check) so safe to re-run on every publish.

**Step 3: Add SiteMap SQL for all 5 new screens**

Add a new method `EnsureContainerTrackingSiteMap(conn)` that inserts SiteMap entries for the 5 new screens under the Container Tracking workspace parent (`9c89e3db-7c47-43c0-8554-5d2c9f2c0e87`):

```csharp
private void EnsureContainerTrackingSiteMap(SqlConnection conn)
{
    // SiteMap entries for Container Tracking workspace screens
    // ParentID = 9c89e3db-7c47-43c0-8554-5d2c9f2c0e87 (Container Tracking workspace)
    string[] entries = new[]
    {
        // NodeID, ScreenID, Title, Url, Position
        "('a1b2c3d4-0001-4000-8000-000000000001', 'SB401000', 'PO Containers', '~/GenericInquiry/GenericInquiry.aspx?id=SB401000', '7.6')",
        "('a1b2c3d4-0002-4000-8000-000000000002', 'SB401010', 'SO Containers', '~/GenericInquiry/GenericInquiry.aspx?id=SB401010', '7.7')",
        "('a1b2c3d4-0003-4000-8000-000000000003', 'SB401020', 'Container Events', '~/GenericInquiry/GenericInquiry.aspx?id=SB401020', '7.8')",
        "('a1b2c3d4-0004-4000-8000-000000000004', 'SB302000', 'Freight Forwarders', '~/Pages/SB/SB302000.aspx', '7.9')",
        "('a1b2c3d4-0005-4000-8000-000000000005', 'SB401030', 'Custom Classification', '~/GenericInquiry/GenericInquiry.aspx?id=SB401030', '8.0')",
    };

    foreach (var entry in entries)
    {
        // Idempotent: skip if ScreenID already in SiteMap
        string screenId = entry.Split('\'')[5]; // extract ScreenID from tuple
        string checkSql = string.Format(
            "IF NOT EXISTS (SELECT 1 FROM SiteMap WHERE ScreenID = '{0}' AND CompanyID = 2) " +
            "INSERT INTO SiteMap (CompanyID, NodeID, ScreenID, Title, Url, Position, ParentID, Expanded, SelectedUI) " +
            "VALUES (2, {1})",
            screenId,
            entry.Replace(")", ", '9c89e3db-7c47-43c0-8554-5d2c9f2c0e87', 0, 'E')")
        );
        using (var cmd = new SqlCommand(checkSql, conn)) { cmd.ExecuteNonQuery(); }
    }
    WriteLog("[AesthetikContainers] SiteMap entries for Container Tracking screens — OK");
}
```

**Step 4: Add `<ScreenWithRights>` entries for SB302000**

In the `<ScreenWithRights>` section of project.xml, add a new row for SB302000 (the ASPX screen). GI screens (SB401000-SB401030) get their access rights from the GI framework automatically — they don't need ScreenWithRights entries.

```xml
<row Position="7.9" Title="Freight Forwarders" Url="~/Pages/SB/SB302000.aspx" ScreenID="SB302000" NodeID="a1b2c3d4-0004-4000-8000-000000000004" ParentID="9c89e3db-7c47-43c0-8554-5d2c9f2c0e87" SelectedUI="E">
    <RolesInGraph Rolename="Administrator" ApplicationName="/" Accessrights="4" />
    <RolesInGraph Rolename="*" ApplicationName="/" Accessrights="0" />
</row>
```

**Step 5: Commit**

```bash
git add Customization/AesthetikContainers/project.xml
git commit -m "feat: DDL + GI SQL + SiteMap for container tracking screens

UsrFreightForwarder table, 4 GIs (PO Containers, SO Containers,
Container Events, Custom Classification), SiteMap entries for all 5
new screens under Container Tracking workspace. All idempotent."
```

---

## Task 5: Validate project.xml

**Files:**
- Read: `Customization/AesthetikContainers/project.xml`

**Step 1: Run validate-project.py**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python scripts/validate-project.py Customization/AesthetikContainers/project.xml --strict
```

Expected: PASS with no errors. Warnings acceptable for GI SQL if `REVIEWED: gi-sql-safe` marker present.

**Step 2: Verify CDATA matches source**

Check that all Graph elements have matching CDATA content (no stale CDATA):
- `UsrFreightForwarder` DAC CDATA matches the C# source
- `FreightForwarderMaint` graph CDATA matches
- CustomizationPlugin CDATA includes the new EnsureTable + GI + SiteMap methods

**Step 3: Check for common issues**

- All `[PXDBx]` fields have matching `<Sql>` or `EnsureTable`/`EnsureColumn` DDL
- No `System.TypeCode` unqualified references
- No CRM DAC references in non-CRM graphs
- `-- REVIEWED: gi-sql-safe` marker on all GI SQL blocks

---

## Task 6: Add Playwright tests for new screens

**Files:**
- Modify: `tests/ui/test_container_tracking.py`

**Step 1: Add test constants for new screens**

At the top of the file, after the `IGCM_SCREENS` list, add:

```python
# ── New container tracking screens (AesthetikContainers) ────────────────
NEW_CONTAINER_SCREENS = {
    "SB401000": "PO Containers",
    "SB401010": "SO Containers",
    "SB401020": "Container Events",
    "SB302000": "Freight Forwarders",
    "SB401030": "Custom Classification",
}
```

**Step 2: Add GI screen test class**

```python
class TestContainerTrackingGIs:
    """Verify new container tracking GI screens load and display data."""

    @pytest.mark.parametrize("screen_id,name", [
        ("SB401000", "PO Containers"),
        ("SB401010", "SO Containers"),
        ("SB401020", "Container Events"),
        ("SB401030", "Custom Classification"),
    ])
    def test_gi_screen_loads(self, acumatica_page, screen_id, name):
        """GI screen should load without error."""
        navigate_to_screen_safe(acumatica_page, screen_id)
        wait_for_screen(acumatica_page, screen_id)

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            f"{name} ({screen_id}) redirected to error page"

    @pytest.mark.parametrize("screen_id,name", [
        ("SB401000", "PO Containers"),
        ("SB401010", "SO Containers"),
        ("SB401020", "Container Events"),
        ("SB401030", "Custom Classification"),
    ])
    def test_gi_grid_visible(self, acumatica_page, screen_id, name):
        """GI screen should show a data grid."""
        navigate_to_screen_safe(acumatica_page, screen_id)
        wait_for_screen(acumatica_page, screen_id)

        # GI screens render a PXGrid — look for grid container
        grid = acumatica_page.locator("div[class*='GridContent'], div[id*='grid']").first
        assert grid.is_visible(timeout=5000), \
            f"{name} ({screen_id}) — grid not visible"

    def test_po_containers_has_status_filter(self, acumatica_page):
        """PO Containers GI should have a Status filter."""
        navigate_to_screen_safe(acumatica_page, "SB401000")
        wait_for_screen(acumatica_page, "SB401000")

        # GI filter area
        filter_area = acumatica_page.locator("text=Status")
        assert filter_area.count() > 0, \
            "PO Containers GI missing Status filter"
```

**Step 3: Add Freight Forwarders ASPX test class**

```python
class TestFreightForwarders:
    """Verify Freight Forwarders maintenance screen (SB302000)."""

    def test_screen_loads(self, acumatica_page):
        """SB302000 should load without error."""
        navigate_to_screen_safe(acumatica_page, "SB302000")
        wait_for_screen(acumatica_page, "SB302000")

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "SB302000 Freight Forwarders redirected to error page"

    def test_form_fields_visible(self, acumatica_page):
        """Form should display key fields."""
        navigate_to_screen_safe(acumatica_page, "SB302000")
        wait_for_screen(acumatica_page, "SB302000")

        fields = find_custom_fields(acumatica_page, [
            "ForwarderCD", "Name", "Active", "CarrierAPIType"
        ])

        for field_name, found in fields.items():
            assert found, f"Freight Forwarders — field {field_name} not found"

    def test_new_record_button(self, acumatica_page):
        """Should be able to click Add New Record."""
        navigate_to_screen_safe(acumatica_page, "SB302000")
        wait_for_screen(acumatica_page, "SB302000")

        add_btn = acumatica_page.locator("div[icon='AddNew'], [id*='btnInsert']").first
        if add_btn.is_visible(timeout=3000):
            add_btn.click()
            acumatica_page.wait_for_timeout(2000)

        assert "ScreenId=ERROR" not in acumatica_page.url, \
            "Add New Record on Freight Forwarders caused error"
```

**Step 4: Add workspace completeness test**

```python
class TestContainerTrackingWorkspaceComplete:
    """Verify all container tracking screens appear in the workspace."""

    def test_all_screens_in_workspace(self, acumatica_page):
        """Container Tracking workspace should list all 6 screens."""
        navigate_to_screen_safe(acumatica_page, "SB501000")
        acumatica_page.wait_for_timeout(2000)

        # Click Container Tracking workspace to expand it
        workspace_link = acumatica_page.locator("text=Container Tracking").first
        if workspace_link.is_visible(timeout=3000):
            workspace_link.click()
            acumatica_page.wait_for_timeout(2000)

        page_text = acumatica_page.locator("body").text_content() or ""

        expected_screens = [
            "Container Maintenance",
            "PO Containers",
            "SO Containers",
            "Container Events",
            "Freight Forwarders",
            "Custom Classification",
        ]

        for screen_name in expected_screens:
            assert screen_name in page_text, \
                f"'{screen_name}' not found in Container Tracking workspace"
```

**Step 5: Run the tests locally to verify syntax**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
python -m py_compile tests/ui/test_container_tracking.py
```

Expected: No syntax errors.

**Step 6: Commit**

```bash
git add tests/ui/test_container_tracking.py
git commit -m "test: Playwright tests for 5 new container tracking screens

13 new tests: GI load + grid visible (4x2), PO status filter,
Freight Forwarders form/fields/new-record (3), workspace completeness.
Uses navigate_to_screen_safe() and wait_for_screen() — no networkidle."
```

---

## Task 7: Create PR

**Step 1: Push branch and create PR**

```bash
cd /Users/kevin/dev/acumatica-ci-cd
git push -u origin HEAD
gh pr create --title "feat: container tracking feature parity — 5 new screens" --body "$(cat <<'EOF'
## Summary

Builds 5 screens to replace IIG Container Management ISV (unpublished in PRs #154-159):

- **SB401000** — PO Containers GI (browse containers, ETAs, delays)
- **SB401010** — SO Containers GI (outbound shipment container visibility)
- **SB401020** — Container Events GI (tracking event timeline)
- **SB302000** — Freight Forwarders ASPX (carrier master + API config)
- **SB401030** — Custom Classification GI (stock item HTS/duty/freight fields)

All registered under Container Tracking workspace. GIs built via gi_builder.py.
New `UsrFreightForwarder` DAC + `FreightForwarderMaint` graph.

## Changes

- `project.xml`: New DAC, graph, 2 ASPX files, DDL, GI SQL, SiteMap entries
- `scripts/heritage/gi_container_tracking.py`: GI builder specs for 4 inquiries
- `data/container-tracking/*.sql`: Generated GI SQL (4 files)
- `tests/ui/test_container_tracking.py`: 13 new Playwright tests

## Test plan

- [ ] `python -m py_compile tests/ui/test_container_tracking.py` — syntax check
- [ ] `python scripts/validate-project.py --strict` — project.xml validation
- [ ] After-hours deploy → verify all 5 screens load in production
- [ ] Run Playwright test suite against production

## Deploy note

⚠️ After-hours only — publish restarts Acumatica app pool.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Task 8: Write end-user migration guide

**Files:**
- Create: `docs/guides/container-tracking-migration-guide.md`

**Step 1: Write the guide**

Create a formatted guide covering:
1. **What changed** — IIG removed, AesthetikContainers replaces it
2. **Screen mapping** — old IIG screen → new screen (or "deferred")
3. **Navigation** — how to find each screen in the Container Tracking workspace
4. **Per-screen instructions** — what each screen shows, how to use filters, key columns
5. **What's coming** — Phase 2-3 features (webhooks, master data)

The guide should be suitable for emailing to the Heritage Fabrics team.

**Step 2: Commit**

```bash
git add docs/guides/container-tracking-migration-guide.md
git commit -m "docs: container tracking end-user migration guide

IIG → AesthetikContainers screen mapping, navigation instructions,
per-screen usage, and Phase 2-3 roadmap. For Heritage Fabrics team."
```

**Step 3: Update the PR**

```bash
git push
```

---

## Execution Order Summary

| Task | Description | Depends On |
|------|-------------|------------|
| 1 | Generate GI SQL via gi_builder.py | — |
| 2 | Add Freight Forwarders DAC + Graph | — |
| 3 | Add Freight Forwarders ASPX screen | Task 2 |
| 4 | Add DDL + GI SQL + SiteMap to CustomizationPlugin | Tasks 1, 2, 3 |
| 5 | Validate project.xml | Task 4 |
| 6 | Add Playwright tests | Tasks 1-4 |
| 7 | Create PR | Tasks 1-6 |
| 8 | Write end-user migration guide | Tasks 1-6 |

Tasks 1 and 2 can run in parallel. Task 3 depends on 2. Task 4 depends on 1+2+3. Tasks 6 and 8 can run in parallel after 4+5.
