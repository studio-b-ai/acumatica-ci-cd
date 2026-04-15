#!/usr/bin/env python3
"""Build DRP_ItemWarehouseSettings GI (SB401120) and splice it into
Customization/AesthetikContainers/project.xml.

This GI exposes INItemSite replenishment settings (reorder point, safety stock,
max qty, lead time, preferred vendor, ABC code) via OData.  It replaces the
broken StockItem entity API path that returns 500 KeyNotFoundException from
custom DAC fields.

Idempotent: refuses to run if the target DesignID already exists.
"""
import sys
import re
from pathlib import Path

PROJ = Path("/Users/kevin/dev/acumatica-ci-cd/Customization/AesthetikContainers/project.xml")

# UUIDs generated 2026-04-14
DESIGN = "6e77b05f-ef4d-49e7-90ac-4c703006880d"
NODE   = "3e124ece-6462-4be9-acc7-6372d6da32ef"
ROW = {
    "InventoryCD":          "5cbd9931-6bc5-4c98-868b-61aeb474664e",
    "SiteCD":               "6e902077-a0b8-44e6-b569-ea12bc1242e4",
    "BaseUnit":             "06d931cc-52c8-45f6-9c42-0cab8b665a26",
    "SafetyStock":          "30357e10-590f-48d6-9bc9-4533b4353300",
    "MinQty":               "1fd0bf01-6062-412f-848c-7cc803aaf88a",
    "MaxQty":               "a7483a20-c13d-458f-b167-39c4d6733fd3",
    "MinOrdQty":            "0d734a9c-4fb0-4a15-aba3-ef6d1bcc2fbf",
    "ReplenishmentSource":  "e01b5ea1-7dd7-4be8-a983-e3a17b7a2f41",
    "OverrideInvtSettings": "aee7e44e-7ade-43a0-8485-4b6e0a1fb4bd",
    "PreferredVendorID":    "7405ecbc-7ff1-4474-aa32-2a777ae48c23",
    "LeadTime":             "9a03d998-4f58-48e8-8a0a-41a3ba3305ef",
    "ABCCodeID":            "def1c599-a2ff-4b18-ab0c-6358c8c5430a",
}

# Shared workspace identifiers (Container Tracking / DRP folder)
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


def sitemap_row(position, title, design_id, screen_id, node_id, order_num):
    return (f'          <SiteMap linkname="toDesignById">\n'
            f'            <row Position="{position}" Title="{title}" '
            f'Url="~/GenericInquiry/GenericInquiry.aspx?id={design_id}" '
            f'Expanded="0" IsFolder="0" ScreenID="{screen_id}" '
            f'NodeID="{node_id}" ParentID="{PARENT_ID}">\n'
            f'              <MUIScreen IsPortal="0" WorkspaceID="{WORKSPACE_ID}" '
            f'Order="{order_num}" SubcategoryID="{SUBCAT_ID}" />\n'
            f'              <RolesInGraph Rolename="Administrator" ApplicationName="/" Accessrights="4" />\n'
            f'              <RolesInGraph Rolename="*" ApplicationName="/" Accessrights="4" />\n'
            f'            </row>\n'
            f'          </SiteMap>')


# ===========================================================================
# DRP_ItemWarehouseSettings — INItemSite × InventoryItem × INSite
# ===========================================================================
# Base: INItemSite (warehouse-level replenishment settings)
# Join L: InventoryItem on InventoryID for InventoryCD, BaseUnit
# Join L: INSite on SiteID for SiteCD

item_site_relations = [
    girelation(1, "InventoryItem", [("InventoryID", "InventoryID")]),
    girelation(2, "INSite", [("SiteID", "SiteID")]),
]

# Results from InventoryItem (joined)
inv_results = [
    gir(1,  1, "InventoryCD",  120, "Inventory ID",  ROW["InventoryCD"], default_nav=1),
    gir(3, 3, "BaseUnit",      60, "Base Unit",      ROW["BaseUnit"]),
]

# Results from INSite (joined)
site_results = [
    gir(2,  2, "SiteCD",        80, "Warehouse",     ROW["SiteCD"]),
]

# Results from INItemSite (main table)
item_site_results = [
    gir(4,  4, "SafetyStock",          100, "Safety Stock",          ROW["SafetyStock"]),
    gir(5,  5, "MinQty",               100, "Reorder Point",         ROW["MinQty"]),
    gir(6,  6, "MaxQty",               100, "Max Qty",               ROW["MaxQty"]),
    gir(7,  7, "MinOrdQty",            100, "Min Order Qty",         ROW["MinOrdQty"]),
    gir(8,  8, "ReplenishmentSource",  120, "Replenishment Source",  ROW["ReplenishmentSource"]),
    gir(9,  9, "OverrideInvtSettings", 100, "Override Settings",     ROW["OverrideInvtSettings"]),
    gir(10, 10, "PreferredVendorID",   120, "Preferred Vendor",      ROW["PreferredVendorID"]),
    gir(11, 11, "LeadTime",            80,  "Lead Time (Days)",      ROW["LeadTime"]),
    gir(12, 12, "ABCCodeID",           60,  "ABC Code",              ROW["ABCCodeID"]),
]

GIDESIGN = f'''        <row DesignID="{DESIGN}" Name="DRP_ItemWarehouseSettings" ScreenID="SB401120" FilterColCount="3" PageSize="0" ExportTop="0" NewRecordCreationEnabled="0" MassDeleteEnabled="0" AutoConfirmDelete="0" MassRecordsUpdateEnabled="0" MassActionsOnRecordsEnabled="0" ExposeViaOData="1" ExposeViaMobile="0">
{gitable("INItemSite", "PX.Objects.IN.INItemSite", item_site_relations + item_site_results)}
{gitable("InventoryItem", "PX.Objects.IN.InventoryItem", inv_results)}
{gitable("INSite", "PX.Objects.IN.INSite", site_results)}
          <GIWhere LineNbr="1" IsActive="1" DataFieldName="InventoryItem.StkItem" Condition="E " IsExpression="0" Value1="True" Operation="A" />
          <GIWhere LineNbr="2" OpenBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="AC" Operation="O" />
          <GIWhere LineNbr="3" CloseBrackets="1" IsActive="1" DataFieldName="InventoryItem.ItemStatus" Condition="E " IsExpression="0" Value1="NS" Operation="A" />
          <GISort LineNbr="1" IsActive="1" DataFieldName="InventoryItem.InventoryCD" SortOrder="A" />
          <GISort LineNbr="2" IsActive="1" DataFieldName="INSite.SiteCD" SortOrder="A" />
{sitemap_row(1190, "DRP Item Warehouse Settings", DESIGN, "SB401120", NODE, 2100)}

        </row>'''


def main():
    if not PROJ.exists():
        print(f"ERROR: {PROJ} not found", file=sys.stderr)
        sys.exit(1)

    xml = PROJ.read_text()

    if DESIGN in xml:
        print(f"SKIP: DesignID {DESIGN} already present in project.xml")
        sys.exit(0)

    # Add to the OData registration SQL (co_publish_enable_odata)
    odata_pattern = r"(  '89912975-c6ed-41ad-b514-a0f775a89362'   -- DRP_OpenPOLines)"
    odata_replacement = (
        r"\1\n"
        f"  ,'{DESIGN}'  -- DRP_ItemWarehouseSettings"
    )
    xml_new = re.sub(odata_pattern, odata_replacement, xml)
    if xml_new == xml:
        print("WARNING: Could not find OData registration block — adding GI without OData SQL update")
        xml_new = xml

    # Splice the GI block after the last DRP GI (DRP_OpenPOLines)
    # Find the end of the DRP_OpenPOLines row (</row>) and insert after it
    splice_pattern = r'(        </row>)(\s*</data-set>)'
    # Actually, let me find the end of the last GI row block before </data-set>
    # The GI rows end with </row> before the dataset structure closes

    # Simpler approach: find the DRP_OpenPOLines closing </row> and insert after
    # DRP_OpenPOLines DesignID is 89912975-...
    po_lines_end = xml_new.find('Name="DRP_OpenPOLines"')
    if po_lines_end < 0:
        print("ERROR: DRP_OpenPOLines not found in project.xml", file=sys.stderr)
        sys.exit(1)

    # Find the closing </row> for DRP_OpenPOLines
    # Starting from the DRP_OpenPOLines position, find the next "        </row>"
    search_start = po_lines_end
    row_end = xml_new.find("\n        </row>", search_start)
    if row_end < 0:
        print("ERROR: Could not find closing </row> for DRP_OpenPOLines", file=sys.stderr)
        sys.exit(1)

    # Insert after "        </row>\n"
    insert_pos = row_end + len("\n        </row>")
    xml_final = xml_new[:insert_pos] + "\n" + GIDESIGN + xml_new[insert_pos:]

    PROJ.write_text(xml_final)
    print(f"OK: DRP_ItemWarehouseSettings (DesignID={DESIGN}) spliced into project.xml")
    print(f"    ScreenID: SB401120")
    print(f"    Tables: INItemSite (main) × InventoryItem × INSite")
    print(f"    Fields: InventoryCD, SiteCD, BaseUnit, SafetyStock, MinQty (ROP),")
    print(f"            MaxQty, MinOrdQty, ReplenishmentSource, OverrideInvtSettings,")
    print(f"            PreferredVendorID, LeadTime, ABCCodeID")
    print(f"    OData: enabled (ExposeViaOData=1)")


if __name__ == "__main__":
    main()
