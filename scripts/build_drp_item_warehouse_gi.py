#!/usr/bin/env python3
"""Build the DRP_ItemWarehouseSnapshot GI (SB401120) and splice it into
Customization/AesthetikContainers/project.xml.

Uses INItemSite as PRIMARY table (not InventoryItem) to avoid restriction
group filtering. Joins InventoryItem for item details.

Fields needed by heritage-wms DRP pipeline:
  InventoryID, SiteID, ReplenishmentSource, ReplenishmentMethod,
  SafetyStock, ReorderPoint, MaxQty, LeadTime

Idempotent: refuses to run if the target DesignID already exists.
"""
import sys
import re
import uuid
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent / "Customization/AesthetikContainers/project.xml"

# UUIDs for this GI
DESIGN_ID = "b7c3d4e5-f6a7-4890-b123-456789abcdef"
NODE_ID   = "c8d4e5f6-a7b8-4901-c234-567890abcdef"

# Row IDs for GIResult entries
ROW_IDS = {
    "InventoryID":         str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-inventoryid")),
    "SiteID":              str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-siteid")),
    "InventoryCD":         str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-inventorycd")),
    "Descr":               str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-descr")),
    "ReplenishmentSource": str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-replsource")),
    "ReplenishmentMethod": str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-replmethod")),
    "SafetyStock":         str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-safetystock")),
    "ReorderPoint":        str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-reorderpoint")),
    "MaxQty":              str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-maxqty")),
    "LeadTime":            str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-leadtime")),
    "ItemStatus":          str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-itemstatus")),
    "ItemClassID":         str(uuid.uuid5(uuid.NAMESPACE_DNS, "drp-iws-itemclass")),
}

# Shared workspace identifiers (Container Tracking folder)
PARENT_ID    = "9c89e3db-7c47-43c0-8554-5d2c9f2c0e87"
WORKSPACE_ID = "95191203-a0b8-4fc0-8b20-4efe831708e9"
SUBCAT_ID    = "acf1bb34-2055-411e-88be-d840efcc7424"


def gir(line, sort, field, width, caption, row_id, default_nav=0):
    return (f'            <GIResult LineNbr="{line}" SortOrder="{sort}" IsActive="1" '
            f'Field="{field}" Width="{width}" IsVisible="1" DefaultNav="{default_nav}" '
            f'QuickFilter="0" FastFilter="1" Caption="{caption}" RowID="{row_id}" />')


def build_gi_block():
    """Build the full GenericInquiryScreen XML block."""

    gi_header = (
        f'        <row DesignID="{DESIGN_ID}" Name="DRP_ItemWarehouseSnapshot" '
        f'ScreenID="SB401120" FilterColCount="3" PageSize="0" ExportTop="0" '
        f'NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" '
        f'MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" '
        f'ExposeViaOData="1" ExposeViaMobile="0">'
    )

    # PRIMARY table: INItemSite (avoids restriction group filtering)
    # Join: InventoryItem for item details
    lines = [
        gi_header,
        '          <GITable Alias="INItemSite" Name="PX.Objects.IN.INItemSite">',
        '            <GIRelation LineNbr="1" ChildTable="InventoryItem" IsActive="1" JoinType="I">',
        '              <GIOn LineNbr="1" ParentField="InventoryID" Condition="E " ChildField="InventoryID" Operation="A" />',
        '            </GIRelation>',
        # INItemSite fields
        gir(1, 1, "InventoryID", "60", "Inventory ID (int)", ROW_IDS["InventoryID"]),
        gir(2, 2, "SiteID", "60", "Site", ROW_IDS["SiteID"]),
        gir(5, 5, "ReplenishmentSource", "100", "Replenishment Source", ROW_IDS["ReplenishmentSource"]),
        gir(6, 6, "ReplenishmentClassID", "100", "Replenishment Method", ROW_IDS["ReplenishmentMethod"]),
        gir(7, 7, "SafetyStock", "80", "Safety Stock", ROW_IDS["SafetyStock"]),
        gir(8, 8, "MinQty", "80", "Reorder Point", ROW_IDS["ReorderPoint"]),
        gir(9, 9, "MaxQty", "80", "Max Qty", ROW_IDS["MaxQty"]),
        gir(10, 10, "LeadTime", "60", "Lead Time (Days)", ROW_IDS["LeadTime"]),
        '          </GITable>',
        # Joined table: InventoryItem
        '          <GITable Alias="InventoryItem" Name="PX.Objects.IN.InventoryItem">',
        gir(3, 3, "InventoryCD", "120", "Inventory ID", ROW_IDS["InventoryCD"], default_nav=1),
        gir(4, 4, "Descr", "220", "Description", ROW_IDS["Descr"]),
        gir(11, 11, "ItemStatus", "80", "Status", ROW_IDS["ItemStatus"]),
        gir(12, 12, "ItemClassID", "100", "Item Class", ROW_IDS["ItemClassID"]),
        '          </GITable>',
        # Filters: stock items only, active/non-stock status
        '          <GIWhere LineNbr="1" IsActive="1" DataFieldName="InventoryItem.StkItem" Condition="E " IsExpression="0" Value1="True" Operation="A" />',
        '          <GIWhere LineNbr="2" OpenBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="AC" Operation="A" />',
        '          <GIWhere LineNbr="3" CloseBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="NS" Operation="O" />',
        # Sort by InventoryCD, SiteID
        '          <GISort LineNbr="1" IsActive="1" DataFieldName="InventoryItem.InventoryCD" SortOrder="A" />',
        '          <GISort LineNbr="2" IsActive="1" DataFieldName="INItemSite.SiteID" SortOrder="A" />',
        # SiteMap
        '          <SiteMap linkname="toDesignById">',
        f'            <row Position="1200" Title="DRP Item Warehouse Snapshot" '
        f'Url="~/GenericInquiry/GenericInquiry.aspx?id={DESIGN_ID}" Expanded="0" IsFolder="0" '
        f'ScreenID="SB401120" NodeID="{NODE_ID}" ParentID="{PARENT_ID}">',
        f'              <MUIScreen IsPortal="0" WorkspaceID="{WORKSPACE_ID}" Order="2100" SubcategoryID="{SUBCAT_ID}" />',
        '            </row>',
        '          </SiteMap>',
        '',
        '        </row>',
    ]
    return "\n".join(lines)


def build_screen_with_rights_entry():
    """Build the ScreenWithRights SiteMap entry for SB401120."""
    return (
        f'                    <row Position="0" Title="DRP Item Warehouse Snapshot" '
        f'Url="~/GenericInquiry/GenericInquiry.aspx?id={DESIGN_ID}" '
        f'ScreenID="SB401120" NodeID="{DESIGN_ID}" '
        f'ParentID="{PARENT_ID}" SelectedUI="E">\n'
        f'                        <RolesInGraph Rolename="Administrator" ApplicationName="/" Accessrights="4" />\n'
        f'                        <RolesInGraph Rolename="*" ApplicationName="/" Accessrights="4" />\n'
        f'                    </row>'
    )


def main():
    if not PROJ.exists():
        print(f"ERROR: {PROJ} not found", file=sys.stderr)
        sys.exit(1)

    xml = PROJ.read_text(encoding="utf-8")

    if DESIGN_ID in xml:
        print(f"Design {DESIGN_ID} already exists in project.xml — skipping.")
        sys.exit(0)

    # 1) Insert GI block after the last </GenericInquiryScreen> before <ScreenWithRights>
    gi_block = build_gi_block()

    # Find the insertion point: after the last GI data-set close, before ScreenWithRights
    # We'll insert a new <GenericInquiryScreen> block
    new_gi_section = f"""    <GenericInquiryScreen>
  <data-set>
                <relations format-version="3" relations-version="20240201" main-table="GIDesign" stable-sharing="True" file-name="(Name)">
    <link from="GIFilter (DesignID)" to="GIDesign (DesignID)" />
    <link from="GIGroupBy (DesignID)" to="GIDesign (DesignID)" />
    <link from="GIMassAction (DesignID)" to="GIDesign (DesignID)" />
    <link from="GIMassUpdateField (DesignID)" to="GIDesign (DesignID)" />
    <link from="GINavigationScreen (DesignID)" to="GIDesign (DesignID)" />
    <link from="GINavigationParameter (DesignID, NavigationScreenLineNbr)" to="GINavigationScreen (DesignID, LineNbr)" />
    <link from="GINavigationCondition (DesignID, NavigationScreenLineNbr)" to="GINavigationScreen (DesignID, LineNbr)" />
    <link from="GIOn (DesignID, RelationNbr)" to="GIRelation (DesignID, LineNbr)" />
    <link from="GIRecordDefault (DesignID)" to="GIDesign (DesignID)" />
    <link from="GIRelation (DesignID, ParentTable)" to="GITable (DesignID, Alias)" />
    <link from="GIRelation (DesignID, ChildTable)" to="GITable (DesignID, Alias)" />
    <link from="GIResult (Alias, DesignID)" to="GITable (Alias, DesignID)" />
    <link from="GITable (DesignID)" to="GIDesign (DesignID)" />
    <link from="GIWhere (DesignID)" to="GIDesign (DesignID)" />
    <link from="GISort (DesignID)" to="GIDesign (DesignID)" />
    <link from="MUIScreen (NodeID)" to="SiteMap (NodeID)" />
    <link from="MUIPinnedScreen (NodeID, WorkspaceID)" to="MUIScreen (NodeID, WorkspaceID)" />
    <link from="MUITile (ScreenID)" to="SiteMap (ScreenID)" />
    <link from="ListEntryPoint (ListScreenID)" to="SiteMap (ScreenID)" />
    <link from="FilterHeader (ScreenID)" to="SiteMap (ScreenID)" />
    <link from="FilterRow (FilterID)" to="FilterHeader (FilterID)" />
    <link from="PivotTable (ScreenID, NoteID)" to="FilterHeader (ScreenID, NoteID)" />
    <link from="PivotField (ScreenID, PivotTableID)" to="PivotTable (ScreenID, PivotTableID)" />
    <link from="MUIFavoriteWorkspace (WorkspaceID)" to="MUIWorkspace (WorkspaceID)" />
    <link from="GIDesign (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIFilter (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIFilter (NoteID)" to="GIFilterKvExt (RecordID)" type="RowKvExt" />
    <link from="GIGroupBy (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIOn (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIRelation (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIResult (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIResult (NoteID)" to="GIResultKvExt (RecordID)" type="RowKvExt" />
    <link from="GISort (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GITable (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="GIWhere (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="FilterHeader (NoteID)" to="Note (NoteID)" type="Note" />
    <link from="FilterHeader (NoteID)" to="FilterHeaderKvExt (RecordID)" type="RowKvExt" />
</relations>
            <layout>
    <table name="GIDesign">
        <table name="GIFilter" uplink="(DesignID) = (DesignID)">
            <table name="Note" uplink="(NoteID) = (NoteID)" />
            <table name="GIFilterKvExt" uplink="(NoteID) = (RecordID)" />
        </table>
        <table name="GIGroupBy" uplink="(DesignID) = (DesignID)">
            <table name="Note" uplink="(NoteID) = (NoteID)" />
        </table>
        <table name="GIMassAction" uplink="(DesignID) = (DesignID)" />
        <table name="GIMassUpdateField" uplink="(DesignID) = (DesignID)" />
        <table name="GINavigationScreen" uplink="(DesignID) = (DesignID)">
            <table name="GINavigationParameter" uplink="(DesignID, LineNbr) = (DesignID, NavigationScreenLineNbr)" />
            <table name="GINavigationCondition" uplink="(DesignID, LineNbr) = (DesignID, NavigationScreenLineNbr)" />
        </table>
        <table name="GIRecordDefault" uplink="(DesignID) = (DesignID)" />
        <table name="GISort" uplink="(DesignID) = (DesignID)">
            <table name="Note" uplink="(NoteID) = (NoteID)" />
        </table>
        <table name="GITable" uplink="(DesignID) = (DesignID)">
            <table name="GIRelation" uplink="(DesignID, Alias) = (DesignID, ParentTable)">
                <table name="GIOn" uplink="(DesignID, LineNbr) = (DesignID, RelationNbr)">
                    <table name="Note" uplink="(NoteID) = (NoteID)" />
                </table>
                <table name="Note" uplink="(NoteID) = (NoteID)" />
            </table>
            <table name="GIResult" uplink="(Alias, DesignID) = (ObjectName, DesignID)">
                <table name="Note" uplink="(NoteID) = (NoteID)" />
                <table name="GIResultKvExt" uplink="(NoteID) = (RecordID)" />
            </table>
            <table name="Note" uplink="(NoteID) = (NoteID)" />
        </table>
        <table name="GIWhere" uplink="(DesignID) = (DesignID)">
            <table name="Note" uplink="(NoteID) = (NoteID)" />
        </table>
        <table name="SiteMap" uplink="(DesignID) = (Url)" linkname="toDesignById">
            <table name="ListEntryPoint" uplink="(ScreenID) = (ListScreenID)" />
            <table name="FilterHeader" uplink="(ScreenID) = (ScreenID)">
                <table name="FilterRow" uplink="(FilterID) = (FilterID)" />
                <table name="PivotTable" uplink="(RefNoteID) = (NoteID)">
                    <table name="PivotField" uplink="(ScreenID, PivotTableID) = (ScreenID, PivotTableID)" />
                </table>
                <table name="Note" uplink="(NoteID) = (NoteID)" />
                <table name="FilterHeaderKvExt" uplink="(NoteID) = (RecordID)" />
            </table>
            <table name="MUIScreen" uplink="(NodeID) = (NodeID)">
                <table name="MUIPinnedScreen" uplink="(NodeID, WorkspaceID) = (NodeID, WorkspaceID)" />
            </table>
            <table name="MUITile" uplink="(ScreenID) = (ScreenID)" />
        </table>
        <table name="SiteMap" uplink="(Name) = (Url)" linkname="toDesignByName">
            <table name="ListEntryPoint" uplink="(ScreenID) = (ListScreenID)" />
            <table name="FilterHeader" uplink="(ScreenID) = (ScreenID)">
                <table name="FilterRow" uplink="(FilterID) = (FilterID)" />
                <table name="PivotTable" uplink="(RefNoteID) = (NoteID)">
                    <table name="PivotField" uplink="(ScreenID, PivotTableID) = (ScreenID, PivotTableID)" />
                </table>
                <table name="Note" uplink="(NoteID) = (NoteID)" />
                <table name="FilterHeaderKvExt" uplink="(NoteID) = (RecordID)" />
            </table>
            <table name="MUIScreen" uplink="(NodeID) = (NodeID)">
                <table name="MUIPinnedScreen" uplink="(NodeID, WorkspaceID) = (NodeID, WorkspaceID)" />
            </table>
            <table name="MUITile" uplink="(ScreenID) = (ScreenID)" />
        </table>
        <table name="SiteMap" uplink="(PrimaryScreenIDNew) = (ScreenID)" linkname="to1Screen">
            <table name="ListEntryPoint" uplink="(ScreenID) = (ListScreenID)" />
            <table name="FilterHeader" uplink="(ScreenID) = (ScreenID)">
                <table name="FilterRow" uplink="(FilterID) = (FilterID)" />
                <table name="PivotTable" uplink="(RefNoteID) = (NoteID)">
                    <table name="PivotField" uplink="(ScreenID, PivotTableID) = (ScreenID, PivotTableID)" />
                </table>
                <table name="Note" uplink="(NoteID) = (NoteID)" />
                <table name="FilterHeaderKvExt" uplink="(NoteID) = (RecordID)" />
            </table>
            <table name="MUIScreen" uplink="(NodeID) = (NodeID)">
                <table name="MUIPinnedScreen" uplink="(NodeID, WorkspaceID) = (NodeID, WorkspaceID)" />
            </table>
            <table name="MUITile" uplink="(ScreenID) = (ScreenID)" />
        </table>
        <table name="Note" uplink="(NoteID) = (NoteID)" />
    </table>
</layout>
    <data>
      <GIDesign>
{gi_block}
      </GIDesign>
    </data>
  </data-set>
</GenericInquiryScreen>"""

    # Insert before <ScreenWithRights>
    anchor = "    <ScreenWithRights"
    if anchor not in xml:
        print("ERROR: <ScreenWithRights> not found in project.xml", file=sys.stderr)
        sys.exit(1)

    xml = xml.replace(anchor, new_gi_section + "\n" + anchor)

    # 2) Add ScreenWithRights entry for SB401120
    swr_entry = build_screen_with_rights_entry()
    # Insert after the last DRP GI entry in ScreenWithRights
    swr_anchor = '                    <row Position="0" Title="DRP Inventory By Site"'
    if swr_anchor in xml:
        # Find end of that row block (closes with </row>)
        idx = xml.index(swr_anchor)
        # Find the closing </row> for this entry
        close_idx = xml.index("</row>", idx) + len("</row>")
        xml = xml[:close_idx] + "\n" + swr_entry + xml[close_idx:]
    else:
        print("WARNING: Could not find DRP Inventory By Site SWR entry — adding at end of SiteMap block")
        swr_close = "                </SiteMap>\n                <Roles>"
        xml = xml.replace(swr_close, "                    " + swr_entry + "\n" + swr_close)

    PROJ.write_text(xml, encoding="utf-8")
    print(f"Inserted DRP_ItemWarehouseSnapshot GI (SB401120) into {PROJ.name}")
    print(f"  DesignID: {DESIGN_ID}")
    print(f"  ScreenID: SB401120")
    print(f"  Primary table: INItemSite (avoids restriction group filtering)")
    print(f"  OData exposed: yes")


if __name__ == "__main__":
    main()
