#!/usr/bin/env python3
"""Build 3 new <GenericInquiryScreen> blocks for DRP Phase 0 Stream A
(A.1 DRP_VelocityHistory, A.2 DRP_OpenSOCommitments, A.4 DRP_InventoryBySite)
and splice them into Customization/AesthetikContainers/project.xml after
the POContainers block (end of SB401000).

Idempotent: refuses to run if any of the target DesignIDs already exist.
"""
import sys
import re
from pathlib import Path

WT = Path("/Users/kevin/dev/acumatica-ci-cd/.claude/worktrees/drp-a124-gis")
PROJ = WT / "Customization/AesthetikContainers/project.xml"

# UUIDs generated 2026-04-09 for Stream A
A1_DESIGN = "1ce25f0a-cde6-4f0a-b939-d274fe343574"
A1_NODE   = "aed2bb14-04d3-4715-ba57-6bd405423270"
A1_ROW = {
    "InventoryID":  "ecce5bee-e6cc-4c36-9636-eb69f32d9047",
    "ShippedQty":   "b4130772-382a-428b-8bc1-dec67f717da2",
    "ShippedDate":  "84dcef53-9d20-4bb9-a928-f8cccedfc6e6",
    "SOType":       "f0fbb9dd-6d4e-491e-b29c-58ecaea6b06d",
    "SONbr":        "da571808-98c9-4843-8418-3e864278c52c",
    "CustomerID":   "3dc9d2ad-cb01-4bac-b9ca-ea4af2e3b247",
    "SiteID":       "7f7b5991-23b6-4c61-8a6a-3cdec6aac5f6",
    "UOM":          "7a7b593d-a702-4a58-9ef2-f56ab8ed493b",
}

A2_DESIGN = "f918a504-7620-461c-aad8-f1b3395d1e79"
A2_NODE   = "af758f49-f888-4d32-b162-838a5fa34c52"
A2_ROW = {
    "InventoryID":       "2d95b7be-2bb2-406f-bddd-2bc9fe95f567",
    "SOType":            "d120b57e-74b5-4ca2-8567-024fcbafa79e",
    "SONbr":             "640b01fe-d1a2-4b7d-99a4-5db8f2348195",
    "SOLineNbr":         "56581d1c-89dc-4458-8e0e-49905f93fcf1",
    "OrderQty":          "8e257121-86d8-46ff-944c-4a0f8dd8459e",
    "ShippedQty":        "ea7b4ec5-17d0-40b4-ba57-32ad3f1cb0e7",
    "OpenQty":           "b820f682-e2a8-401c-8d9e-5c5004b8d6ea",
    "RequestedShipDate": "8f870880-3313-497e-9846-41f3286ecad0",
    "CustomerID":        "3ec70280-a871-419e-9525-6a117a502b6f",
    "SiteID":            "7501a3a2-2147-4369-96f6-f44490f8440a",
    "UOM":               "812a72b9-c8bc-47b8-a738-e839a814a529",
}

A4_DESIGN = "a5337a02-6d79-42e9-b400-d7178ac3fd24"
A4_NODE   = "1fb65d0f-ebc6-4ec5-8e19-5c5022245ff5"
A4_ROW = {
    "InventoryID":  "79173e70-3a85-4d70-a5a4-cd71ae7ae80e",
    "Descr":        "872a8b14-9db6-4978-8214-32c8f5670646",
    "ItemStatus":   "e24ba55f-863f-45be-a4f9-7ed06db4b49b",
    "ItemClassID":  "6b15d7cd-e2f1-4166-a7b4-b2b7c6fd1eed",
    "SiteID":       "45834d20-dc12-430f-a291-9c8b3576f12a",
    "QtyOnHand":    "169233bb-3c3e-4657-8dcd-cba20887a558",
    "QtyAvail":     "8ce9d3cb-34ed-4983-85e3-00b844b380eb",
    "QtyHardAvail": "d1cb550a-2817-4469-ab21-742e368f2ee5",
    "QtyAllocated": "78f5dc04-3821-493e-822d-984b1805f2d5",
}

# Shared workspace identifiers for the Container Tracking folder
# (copied from existing SB401xxx GIs — same parent, same workspace, same subcategory)
PARENT_ID    = "9c89e3db-7c47-43c0-8554-5d2c9f2c0e87"
WORKSPACE_ID = "95191203-a0b8-4fc0-8b20-4efe831708e9"
SUBCAT_ID    = "acf1bb34-2055-411e-88be-d840efcc7424"

# GIResult() helper — produces one line
def gir(line, sort, field, width, caption, row_id, default_nav=0):
    return (f'            <GIResult LineNbr="{line}" SortOrder="{sort}" IsActive="1" '
            f'Field="{field}" Width="{width}" IsVisible="1" DefaultNav="{default_nav}" '
            f'QuickFilter="0" FastFilter="1" Caption="{caption}" RowID="{row_id}" />')

def gitable(alias, name, inner_lines):
    inner = "\n".join(inner_lines) if inner_lines else ""
    return f'          <GITable Alias="{alias}" Name="{name}">\n{inner}\n          </GITable>'

def girelation(line_nbr, child_table, ons, join="L"):
    ons_xml = "\n".join(
        f'              <GIOn LineNbr="{i+1}" ParentField="{p}" Condition="E " ChildField="{c}" Operation="A" />'
        for i, (p, c) in enumerate(ons)
    )
    return (f'            <GIRelation LineNbr="{line_nbr}" ChildTable="{child_table}" IsActive="1" JoinType="{join}">\n'
            f'{ons_xml}\n'
            f'            </GIRelation>')

def sitemap_row(position, title, design_id, screen_id, node_id, order_num):
    return (f'          <SiteMap linkname="toDesignById">\n'
            f'            <row Position="{position}" Title="{title}" '
            f'Url="~/GenericInquiry/GenericInquiry.aspx?id={design_id}" '
            f'Expanded="0" IsFolder="0" ScreenID="{screen_id}" '
            f'NodeID="{node_id}" ParentID="{PARENT_ID}">\n'
            f'              <MUIScreen IsPortal="0" WorkspaceID="{WORKSPACE_ID}" '
            f'Order="{order_num}" SubcategoryID="{SUBCAT_ID}" />\n'
            f'            </row>\n'
            f'          </SiteMap>')

# ===========================================================================
# A.1 DRP_VelocityHistory — SOShipLine × SOShipment × SOLine
# ===========================================================================
# Base: SOShipLine (shipment line qty)
# Join L: SOShipment on ShipmentNbr
# Join L: SOLine on (OrigOrderType→OrderType, OrigOrderNbr→OrderNbr, OrigLineNbr→LineNbr)
# Filter: SOShipment.Confirmed=True AND SOShipment.Operation='I'
# Sort: SOShipment.ShipDate DESC

a1_shipline_relations = [
    girelation(1, "SOShipment", [("ShipmentNbr", "ShipmentNbr")]),
    girelation(2, "SOLine", [
        ("OrigOrderType", "OrderType"),
        ("OrigOrderNbr", "OrderNbr"),
        ("OrigLineNbr", "LineNbr"),
    ]),
]
a1_shipline_results = [
    gir(1, 1, "InventoryID",  120, "Inventory ID",  A1_ROW["InventoryID"], default_nav=1),
    gir(2, 2, "ShippedQty",   100, "Shipped Qty",   A1_ROW["ShippedQty"]),
    gir(3, 3, "OrigOrderType", 60, "SO Type",       A1_ROW["SOType"]),
    gir(4, 4, "OrigOrderNbr", 100, "SO Nbr",        A1_ROW["SONbr"]),
    gir(5, 5, "SiteID",        60, "Site",          A1_ROW["SiteID"]),
    gir(6, 6, "UOM",           60, "UOM",           A1_ROW["UOM"]),
]
a1_shipment_results = [
    gir(7, 7, "ShipDate", 100, "Shipped Date", A1_ROW["ShippedDate"]),
]
a1_soline_results = [
    gir(8, 8, "CustomerID", 100, "Customer", A1_ROW["CustomerID"]),
]

A1_GIDESIGN = f'''        <row DesignID="{A1_DESIGN}" Name="DRP_VelocityHistory" ScreenID="SB401080" FilterColCount="3" PageSize="0" ExportTop="0" NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" ExposeViaOData="1" ExposeViaMobile="0">
{gitable("SOShipLine", "PX.Objects.SO.SOShipLine", a1_shipline_relations + a1_shipline_results)}
{gitable("SOShipment", "PX.Objects.SO.SOShipment", a1_shipment_results)}
{gitable("SOLine", "PX.Objects.SO.SOLine", a1_soline_results)}
          <GIWhere LineNbr="1" IsActive="1" DataFieldName="SOShipment.Confirmed" Condition="E " IsExpression="0" Value1="True" Operation="A" />
          <GIWhere LineNbr="2" IsActive="1" DataFieldName="SOShipment.Operation" Condition="E " IsExpression="0" Value1="I" Operation="A" />
          <GISort LineNbr="1" IsActive="1" DataFieldName="SOShipment.ShipDate" SortOrder="D" />
{sitemap_row(1160, "DRP Velocity History", A1_DESIGN, "SB401080", A1_NODE, 2070)}

        </row>'''

# ===========================================================================
# A.2 DRP_OpenSOCommitments — SOLine × SOOrder
# ===========================================================================
a2_soline_relations = [
    girelation(1, "SOOrder", [
        ("OrderType", "OrderType"),
        ("OrderNbr",  "OrderNbr"),
    ]),
]
a2_soline_results = [
    gir(1, 1, "InventoryID",   120, "Inventory ID", A2_ROW["InventoryID"], default_nav=1),
    gir(2, 2, "OrderType",      60, "SO Type",      A2_ROW["SOType"]),
    gir(3, 3, "OrderNbr",      100, "SO Nbr",       A2_ROW["SONbr"]),
    gir(4, 4, "LineNbr",        60, "Line Nbr",     A2_ROW["SOLineNbr"]),
    gir(5, 5, "OrderQty",       80, "Order Qty",    A2_ROW["OrderQty"]),
    gir(6, 6, "ShippedQty",     80, "Shipped Qty",  A2_ROW["ShippedQty"]),
    gir(7, 7, "OpenQty",        80, "Open Qty",     A2_ROW["OpenQty"]),
    gir(8, 8, "RequestedDate", 100, "Req Ship Date", A2_ROW["RequestedShipDate"]),
    gir(10, 10, "SiteID",       60, "Site",         A2_ROW["SiteID"]),
    gir(11, 11, "UOM",          60, "UOM",          A2_ROW["UOM"]),
]
a2_soorder_results = [
    gir(9, 9, "CustomerID", 100, "Customer", A2_ROW["CustomerID"]),
]

A2_GIDESIGN = f'''        <row DesignID="{A2_DESIGN}" Name="DRP_OpenSOCommitments" ScreenID="SB401090" FilterColCount="3" PageSize="0" ExportTop="0" NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" ExposeViaOData="1" ExposeViaMobile="0">
{gitable("SOLine", "PX.Objects.SO.SOLine", a2_soline_relations + a2_soline_results)}
{gitable("SOOrder", "PX.Objects.SO.SOOrder", a2_soorder_results)}
          <GIWhere LineNbr="1" IsActive="1" DataFieldName="SOLine.LineType" Condition="E " IsExpression="0" Value1="GoodsForInventory" Operation="A" />
          <GIWhere LineNbr="2" IsActive="1" DataFieldName="SOLine.OpenQty" Condition="G " IsExpression="0" Value1="0" Operation="A" />
          <GIWhere LineNbr="3" OpenBrackets="1" IsActive="1" DataFieldName="SOLine.OrderType" Condition="E " IsExpression="0" Value1="CO" Operation="A" />
          <GIWhere LineNbr="4" IsActive="1" DataFieldName="SOLine.OrderType" Condition="E " IsExpression="0" Value1="SO" Operation="O" />
          <GIWhere LineNbr="5" CloseBrackets="1" IsActive="1" DataFieldName="SOLine.OrderType" Condition="E " IsExpression="0" Value1="PC" Operation="O" />
          <GISort LineNbr="1" IsActive="1" DataFieldName="SOLine.RequestedDate" SortOrder="A" />
{sitemap_row(1170, "DRP Open SO Commitments", A2_DESIGN, "SB401090", A2_NODE, 2080)}

        </row>'''

# ===========================================================================
# A.4 DRP_InventoryBySite — InventoryItem × INSiteStatus
# ===========================================================================
a4_item_relations = [
    girelation(1, "INSiteStatus", [("InventoryID", "InventoryID")]),
]
a4_item_results = [
    gir(1, 1, "InventoryCD",  120, "Inventory ID", A4_ROW["InventoryID"], default_nav=1),
    gir(2, 2, "Descr",        220, "Description",  A4_ROW["Descr"]),
    gir(3, 3, "ItemStatus",    80, "Status",       A4_ROW["ItemStatus"]),
    gir(4, 4, "ItemClassID",  100, "Item Class",   A4_ROW["ItemClassID"]),
]
a4_site_results = [
    gir(5, 5, "SiteID",        60, "Site",          A4_ROW["SiteID"]),
    gir(6, 6, "QtyOnHand",    100, "Qty On Hand",   A4_ROW["QtyOnHand"]),
    gir(7, 7, "QtyAvail",     100, "Qty Available", A4_ROW["QtyAvail"]),
    gir(8, 8, "QtyHardAvail", 100, "Qty Hard Avail", A4_ROW["QtyHardAvail"]),
    gir(9, 9, "QtyAllocated", 100, "Qty Allocated", A4_ROW["QtyAllocated"]),
]

A4_GIDESIGN = f'''        <row DesignID="{A4_DESIGN}" Name="DRP_InventoryBySite" ScreenID="SB401110" FilterColCount="3" PageSize="0" ExportTop="0" NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" ExposeViaOData="1" ExposeViaMobile="0">
{gitable("InventoryItem", "PX.Objects.IN.InventoryItem", a4_item_relations + a4_item_results)}
{gitable("INSiteStatus", "PX.Objects.IN.INSiteStatus", a4_site_results)}
          <GIWhere LineNbr="1" IsActive="1" DataFieldName="InventoryItem.StkItem" Condition="E " IsExpression="0" Value1="True" Operation="A" />
          <GIWhere LineNbr="2" OpenBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="AC" Operation="A" />
          <GIWhere LineNbr="3" CloseBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="NS" Operation="O" />
          <GISort LineNbr="1" IsActive="1" DataFieldName="InventoryItem.InventoryCD" SortOrder="A" />
          <GISort LineNbr="2" IsActive="1" DataFieldName="INSiteStatus.SiteID" SortOrder="A" />
{sitemap_row(1180, "DRP Inventory By Site", A4_DESIGN, "SB401110", A4_NODE, 2090)}

        </row>'''


def main():
    text = PROJ.read_text()

    # Idempotency: refuse if any target DesignID already present
    for tag, did in [("A.1", A1_DESIGN), ("A.2", A2_DESIGN), ("A.4", A4_DESIGN)]:
        if did in text:
            print(f"ERROR: {tag} DesignID {did} already present in project.xml — refusing to duplicate.",
                  file=sys.stderr)
            sys.exit(1)

    # Locate POContainers boilerplate (relations + layout) so we can reuse it.
    # Pattern: <GenericInquiryScreen>\n  <data-set>\n                <relations .. POContainers .. </data-set>\n</GenericInquiryScreen>
    # Simpler: extract relations + layout blocks from the first GI and clone.
    rel_match = re.search(
        r'(<GenericInquiryScreen>\s*<data-set>\s*<relations format-version="3".*?</layout>)',
        text, flags=re.DOTALL)
    if not rel_match:
        print("ERROR: could not locate <relations>...</layout> boilerplate in project.xml",
              file=sys.stderr)
        sys.exit(1)
    boilerplate_header = rel_match.group(1)

    # Build one complete <GenericInquiryScreen> block per GI.
    # Structure mirrors existing blocks exactly:
    #    <GenericInquiryScreen>
    #      <data-set>
    #        <relations> ... </relations>
    #        <layout> ... </layout>
    #        <data>
    #          <GIDesign>
    #            {row}
    #          </GIDesign>
    #        </data>
    #      </data-set>
    #    </GenericInquiryScreen>
    def wrap(gidesign_row):
        return (f'    {boilerplate_header}\n'
                f'    <data>\n'
                f'      <GIDesign>\n'
                f'{gidesign_row}\n'
                f'      </GIDesign>\n'
                f'    </data>\n'
                f'  </data-set>\n'
                f'</GenericInquiryScreen>')

    new_blocks = "\n".join([wrap(A1_GIDESIGN), wrap(A2_GIDESIGN), wrap(A4_GIDESIGN)])

    # Splice: insert right before <ScreenWithRights AccessRightsMergeRule="ApplyAndKeep">
    # (which comes immediately after the POContainers </GenericInquiryScreen>)
    anchor = '    <ScreenWithRights AccessRightsMergeRule="ApplyAndKeep">'
    if anchor not in text:
        print(f"ERROR: anchor not found: {anchor}", file=sys.stderr)
        sys.exit(1)
    if text.count(anchor) != 1:
        print(f"ERROR: anchor not unique (count={text.count(anchor)})", file=sys.stderr)
        sys.exit(1)

    updated = text.replace(anchor, new_blocks + "\n" + anchor)

    if "--dry-run" in sys.argv:
        print(f"OK: would insert {len(new_blocks)} chars ({new_blocks.count(chr(10))+1} lines)")
        print(f"    A.1 DesignID = {A1_DESIGN}")
        print(f"    A.2 DesignID = {A2_DESIGN}")
        print(f"    A.4 DesignID = {A4_DESIGN}")
        return

    PROJ.write_text(updated)
    print(f"WROTE: {PROJ}")
    print(f"  file grew from {len(text)} to {len(updated)} bytes ({len(updated)-len(text):+d})")


if __name__ == "__main__":
    main()
