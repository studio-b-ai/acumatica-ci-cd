#!/usr/bin/env python3
"""Build the P0-A.3 DRP_OpenPOLines GI (SB401100) and splice it into
Customization/AesthetikContainers/project.xml after the POContainers block.

Depends on POOrder.UsrAcknowledgedDate and POOrder.UsrFactoryReadyDate
being present in the compiled StudioB.Containers DLL (added by #311
via POOrderExt.cs — merged to main as commit c03a48a).

Idempotent: refuses to run if the target DesignID already exists.
"""
import sys
import re
from pathlib import Path

WT = Path("/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/drp-a3-open-po-lines")
PROJ = WT / "Customization/AesthetikContainers/project.xml"

# UUIDs generated 2026-04-09
A3_DESIGN = "89912975-c6ed-41ad-b514-a0f775a89362"
A3_NODE   = "660b0c64-b2bf-4848-a863-468f5ff34fbd"
A3_ROW = {
    "POType":              "d708e601-603b-4976-a9d6-87995b39b562",
    "POOrderNbr":          "a4ca68b7-fd7c-4fc5-b2b9-37561a4b356e",
    "POLineNbr":           "3a6373a9-0922-4901-8364-dc3408bf9221",
    "InventoryID":         "54ff852c-644c-484f-8cbe-0a01889b92ad",
    "VendorID":            "f8643af1-993a-480b-90bb-d0110be7e72e",
    "OrderQty":            "a249525f-f5a8-42cb-afb9-8ce335e331f0",
    "ReceivedQty":         "d1e7376f-f209-4d68-924e-5e6bff3d4d79",
    "OpenQty":             "a7b6ebc5-24a5-4827-89fd-f3d1f1b70eec",
    "PromisedDate":        "202a8b2e-87d7-4407-ae00-80a992b5686b",
    "UsrAcknowledgedDate": "ccc39a8e-89cf-435f-8e39-c35ecd032bc6",
    "UsrFactoryReadyDate": "db94eb69-50b0-468b-ac76-81f3515ce171",
    "ContainerNbr":        "93ed61d7-5194-4c5e-9c2e-dc02f6a7059b",
}

# Shared workspace identifiers (Container Tracking folder)
PARENT_ID    = "9c89e3db-7c47-43c0-8554-5d2c9f2c0e87"
WORKSPACE_ID = "95191203-a0b8-4fc0-8b20-4efe831708e9"
SUBCAT_ID    = "acf1bb34-2055-411e-88be-d840efcc7424"


def gir(line, sort, field, width, caption, row_id, default_nav=0):
    return (f'            <GIResult LineNbr="{line}" SortOrder="{sort}" IsActive="1" '
            f'Field="{field}" Width="{width}" IsVisible="1" DefaultNav="{default_nav}" '
            f'QuickFilter="0" FastFilter="1" Caption="{caption}" RowID="{row_id}" />')


def gitable(alias, name, inner_lines):
    inner = "\n".join(inner_lines) if inner_lines else ""
    if inner:
        return f'          <GITable Alias="{alias}" Name="{name}">\n{inner}\n          </GITable>'
    return f'          <GITable Alias="{alias}" Name="{name}">\n          </GITable>'


def girelation(line_nbr, child_table, ons, join="L"):
    ons_xml = "\n".join(
        f'              <GIOn LineNbr="{i+1}" ParentField="{p}" Condition="E " ChildField="{c}" Operation="A" />'
        for i, (p, c) in enumerate(ons)
    )
    return (f'            <GIRelation LineNbr="{line_nbr}" ChildTable="{child_table}" IsActive="1" JoinType="{join}">\n'
            f'{ons_xml}\n'
            f'            </GIRelation>')


# ===========================================================================
# A.3 DRP_OpenPOLines — POLine × POOrder × UsrContainerPOLink × UsrContainer
# ===========================================================================
# Base: POLine (alias "Line")
#   join L POOrder on (OrderType, OrderNbr)
#   join L UsrContainerPOLink on (OrderType, OrderNbr, LineNbr)
# UsrContainerPOLink
#   join L UsrContainer on (ContainerID)
#
# POOrderExt.UsrAcknowledgedDate and UsrFactoryReadyDate are automatically
# available as POOrder.UsrAcknowledgedDate / POOrder.UsrFactoryReadyDate
# inside a GI once the DAC extension is deployed (per #311). No separate
# <GITable> entry needed for POOrderExt.
#
# Filters:
#   POLine.LineType = 'GoodsForInventory'
#   POLine.OpenQty > 0
#   POOrder.Status IN ('N','O')   -- Pending or Open
#
# Sort: POLine.PromisedDate ASC (soonest-due first — drives DRP urgency)

line_relations = [
    girelation(1, "POOrder", [
        ("OrderType", "OrderType"),
        ("OrderNbr",  "OrderNbr"),
    ]),
    girelation(2, "ContainerLink", [
        ("OrderType", "OrderType"),
        ("OrderNbr",  "OrderNbr"),
        ("LineNbr",   "LineNbr"),
    ]),
]

# Default nav on POOrderNbr so users can drill into the PO from the GI.
line_results = [
    gir(1, 1, "OrderType",     60, "PO Type",      A3_ROW["POType"]),
    gir(2, 2, "OrderNbr",     100, "PO Nbr",       A3_ROW["POOrderNbr"], default_nav=1),
    gir(3, 3, "LineNbr",       60, "Line Nbr",     A3_ROW["POLineNbr"]),
    gir(4, 4, "InventoryID",  120, "Inventory ID", A3_ROW["InventoryID"]),
    gir(5, 5, "VendorID",     100, "Vendor",       A3_ROW["VendorID"]),
    gir(6, 6, "OrderQty",      80, "Order Qty",    A3_ROW["OrderQty"]),
    gir(7, 7, "ReceivedQty",   80, "Received",     A3_ROW["ReceivedQty"]),
    gir(8, 8, "OpenQty",       80, "Open Qty",     A3_ROW["OpenQty"]),
    gir(9, 9, "PromisedDate", 100, "Promised Date", A3_ROW["PromisedDate"]),
]

order_results = [
    gir(10, 10, "UsrAcknowledgedDate", 110, "Vendor Ack'd",   A3_ROW["UsrAcknowledgedDate"]),
    gir(11, 11, "UsrFactoryReadyDate", 110, "Factory Ready",  A3_ROW["UsrFactoryReadyDate"]),
]

container_link_relations = [
    girelation(3, "Container", [("ContainerID", "ContainerID")]),
]

container_results = [
    gir(12, 12, "ContainerCD", 120, "Container Nbr", A3_ROW["ContainerNbr"]),
]

A3_GIDESIGN = f'''        <row DesignID="{A3_DESIGN}" Name="DRP_OpenPOLines" ScreenID="SB401100" FilterColCount="3" PageSize="0" ExportTop="0" NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" ExposeViaOData="1" ExposeViaMobile="0">
{gitable("Line", "PX.Objects.PO.POLine", line_relations + line_results)}
{gitable("POOrder", "PX.Objects.PO.POOrder", order_results)}
{gitable("ContainerLink", "StudioB.Containers.UsrContainerPOLink", container_link_relations)}
{gitable("Container", "StudioB.Containers.UsrContainer", container_results)}
          <GIWhere LineNbr="1" IsActive="1" DataFieldName="Line.LineType" Condition="E " IsExpression="0" Value1="GoodsForInventory" Operation="A" />
          <GIWhere LineNbr="2" IsActive="1" DataFieldName="Line.OpenQty" Condition="G " IsExpression="0" Value1="0" Operation="A" />
          <GIWhere LineNbr="3" OpenBrackets="1" IsActive="1" DataFieldName="POOrder.Status" Condition="E " IsExpression="0" Value1="N" Operation="A" />
          <GIWhere LineNbr="4" CloseBrackets="1" IsActive="1" DataFieldName="POOrder.Status" Condition="E " IsExpression="0" Value1="O" Operation="O" />
          <GISort LineNbr="1" IsActive="1" DataFieldName="Line.PromisedDate" SortOrder="A" />
          <SiteMap linkname="toDesignById">
            <row Position="1190" Title="DRP Open PO Lines" Url="~/GenericInquiry/GenericInquiry.aspx?id={A3_DESIGN}" Expanded="0" IsFolder="0" ScreenID="SB401100" NodeID="{A3_NODE}" ParentID="{PARENT_ID}">
              <MUIScreen IsPortal="0" WorkspaceID="{WORKSPACE_ID}" Order="2100" SubcategoryID="{SUBCAT_ID}" />
              <RolesInGraph Rolename="Administrator" ApplicationName="/" Accessrights="4" />
              <RolesInGraph Rolename="*" ApplicationName="/" Accessrights="4" />
            </row>
          </SiteMap>

        </row>'''


def main():
    text = PROJ.read_text()

    if A3_DESIGN in text:
        print(f"ERROR: A.3 DesignID {A3_DESIGN} already present — refusing to duplicate.",
              file=sys.stderr)
        sys.exit(1)

    # Extract relations+layout boilerplate from the first GI in the file.
    rel_match = re.search(
        r'(<GenericInquiryScreen>\s*<data-set>\s*<relations format-version="3".*?</layout>)',
        text, flags=re.DOTALL)
    if not rel_match:
        print("ERROR: could not locate <relations>...</layout> boilerplate", file=sys.stderr)
        sys.exit(1)
    boilerplate_header = rel_match.group(1)

    new_block = (
        f'    {boilerplate_header}\n'
        f'    <data>\n'
        f'      <GIDesign>\n'
        f'{A3_GIDESIGN}\n'
        f'      </GIDesign>\n'
        f'    </data>\n'
        f'  </data-set>\n'
        f'</GenericInquiryScreen>'
    )

    anchor = '    <ScreenWithRights AccessRightsMergeRule="ApplyAndKeep">'
    if text.count(anchor) != 1:
        print(f"ERROR: anchor not unique (count={text.count(anchor)})", file=sys.stderr)
        sys.exit(1)

    updated = text.replace(anchor, new_block + "\n" + anchor)

    if "--dry-run" in sys.argv:
        print(f"OK: would insert {len(new_block)} chars ({new_block.count(chr(10))+1} lines)")
        print(f"    A.3 DesignID = {A3_DESIGN}")
        return

    PROJ.write_text(updated)
    print(f"WROTE: {PROJ}")
    print(f"  file grew from {len(text)} to {len(updated)} bytes ({len(updated)-len(text):+d})")


if __name__ == "__main__":
    main()
