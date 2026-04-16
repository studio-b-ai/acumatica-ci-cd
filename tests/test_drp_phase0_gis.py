"""Static assertions for the DRP Phase 0 Stream A GIs.

These GIs are installed via the C# CustomizationPlugin
(AesthetikContainersInstall.cs → EnsureDRPGenericInquiries).
This test locks in:
  - DRP_VelocityHistory
  - DRP_OpenSOCommitments
  - DRP_InventoryBySite
  - DRP_OpenPOLines
  - DRP_ItemWarehouseSettings

Each GI must be present in the C# plugin with the correct name,
ExposeViaOData=1, expected table aliases, expected result fields,
and NO ScreenID (which would trigger SiteMap access checks on OData).

This is deliberately an offline contract test — it runs fast, has no
live Acumatica dependency, and catches silent drift from later edits
to AesthetikContainersInstall.cs.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

CSHARP_FILE = (
    Path(__file__).parent.parent
    / "src"
    / "StudioB.Containers"
    / "Graphs"
    / "AesthetikContainersInstall.cs"
)

PROJECT_XML = (
    Path(__file__).parent.parent
    / "Customization"
    / "AesthetikContainers"
    / "project.xml"
)


# Expected GI metadata: Name → (table_aliases, required_result_fields)
EXPECTED_GIS = {
    "DRP_VelocityHistory": (
        {"SOShipLine", "SOShipment", "SOLine"},
        {"InventoryID", "ShippedQty", "ShipDate", "OrigOrderType", "OrigOrderNbr",
         "CustomerID", "SiteID", "UOM"},
    ),
    "DRP_OpenSOCommitments": (
        {"SOOrder", "SOLine"},
        {"InventoryID", "OrderType", "OrderNbr", "LineNbr", "OrderQty", "ShippedQty",
         "OpenQty", "RequestDate", "CustomerID", "SiteID", "UOM"},
    ),
    "DRP_OpenPOLines": (
        {"POOrder", "Line", "ContainerLink", "Container"},
        {"OrderType", "OrderNbr", "LineNbr", "InventoryID", "VendorID", "OrderQty",
         "ReceivedQty", "OpenQty", "PromisedDate",
         "UsrAcknowledgedDate", "UsrFactoryReadyDate", "ContainerCD"},
    ),
    "DRP_InventoryBySite": (
        {"InventoryItem", "INSiteStatus"},
        {"InventoryCD", "Descr", "ItemStatus", "ItemClassID", "SiteID", "QtyOnHand",
         "QtyAvail", "QtyHardAvail", "QtyAllocated"},
    ),
    "DRP_ItemWarehouseSettings": (
        {"INItemSite", "InventoryItem", "INSite", "POVendorInventory"},
        {"InventoryCD", "SiteCD", "BaseUnit", "SafetyStock", "MinQty", "MaxQty",
         "MinOrdQty", "ReplenishmentSource", "ReplenishmentPolicyOverride",
         "PreferredVendorID", "VLeadTime", "ABCCodeID", "AddLeadTimeDays"},
    ),
}


@pytest.fixture(scope="module")
def csharp_source():
    """Read the C# plugin source for analysis."""
    assert CSHARP_FILE.is_file(), f"{CSHARP_FILE} not found"
    return CSHARP_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gi_sql_blocks(csharp_source):
    """Extract per-GI SQL blocks from InstallDRPGI calls.

    Each call looks like:
        InstallDRPGI(conn, companyId, "DRP_FooBar", @"...sql...");

    Returns dict of GI name → SQL text.
    """
    out: dict[str, str] = {}
    # Match: InstallDRPGI(conn, companyId, "GI_NAME", @"...SQL...")
    pattern = r'InstallDRPGI\s*\(\s*conn\s*,\s*companyId\s*,\s*"([^"]+)"\s*,\s*@"((?:[^"]|"")*)"'
    for m in re.finditer(pattern, csharp_source, re.DOTALL):
        gi_name = m.group(1)
        sql = m.group(2).replace('""', '"')  # un-escape C# verbatim strings
        out[gi_name] = sql
    return out


def test_ensure_drp_method_exists(csharp_source):
    """The C# plugin has an EnsureDRPGenericInquiries method."""
    assert "EnsureDRPGenericInquiries" in csharp_source, (
        "AesthetikContainersInstall.cs missing EnsureDRPGenericInquiries method"
    )


def test_ensure_drp_called_from_update_database(csharp_source):
    """EnsureDRPGenericInquiries is called from the per-company loop."""
    assert "EnsureDRPGenericInquiries(conn, companyId)" in csharp_source, (
        "EnsureDRPGenericInquiries not called from per-company processing loop"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_exists_in_plugin(gi_sql_blocks, gi_name):
    """Every DRP GI has an InstallDRPGI call in the C# plugin."""
    assert gi_name in gi_sql_blocks, (
        f"Missing InstallDRPGI call for {gi_name} in {CSHARP_FILE}."
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_exposes_via_odata(gi_sql_blocks, gi_name):
    """Every DRP GI must set ExposeViaOData=1 in the GIDesign INSERT."""
    sql = gi_sql_blocks.get(gi_name, "")
    assert "ExposeViaOData" in sql, (
        f"{gi_name} SQL missing ExposeViaOData in GIDesign INSERT"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_no_screenid(gi_sql_blocks, gi_name):
    """DRP GIs must NOT have ScreenID — this is what makes OData work without 403."""
    sql = gi_sql_blocks.get(gi_name, "")
    gi_design_match = re.search(
        r"INSERT\s+INTO\s+GIDesign\s*\(([^)]+)\)", sql, re.IGNORECASE
    )
    assert gi_design_match, f"{gi_name} SQL missing INSERT INTO GIDesign"
    columns = gi_design_match.group(1)
    assert "ScreenID" not in columns, (
        f"{gi_name} SQL has ScreenID in GIDesign INSERT columns — "
        f"this will trigger SiteMap access checks and break OData"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_tables(gi_sql_blocks, gi_name):
    """Every DRP GI SQL references the expected table aliases."""
    expected_aliases, _ = EXPECTED_GIS[gi_name]
    sql = gi_sql_blocks.get(gi_name, "")
    for alias in expected_aliases:
        assert f"'{alias}'" in sql, (
            f"{gi_name} SQL missing table alias '{alias}'"
        )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_required_result_fields(gi_sql_blocks, gi_name):
    """Every DRP GI SQL includes the required result fields."""
    _, required_fields = EXPECTED_GIS[gi_name]
    sql = gi_sql_blocks.get(gi_name, "")
    missing = set()
    for field in required_fields:
        if f"'{field}'" not in sql:
            missing.add(field)
    assert not missing, (
        f"{gi_name} SQL missing required result fields: {sorted(missing)}"
    )


def test_drp_gi_xml_blocks_removed():
    """No DRP GIs should remain as XML GenericInquiryScreen blocks."""
    content = PROJECT_XML.read_text(encoding="utf-8")
    cleaned = re.sub(r"<%--.*?--%>", "", content, flags=re.DOTALL)
    root = ET.fromstring(cleaned)

    drp_names_in_xml = []
    for row in root.iter("row"):
        name = row.get("Name", "")
        if name.startswith("DRP_") and row.get("DesignID"):
            drp_names_in_xml.append(name)

    assert not drp_names_in_xml, (
        f"DRP GIs still defined as XML blocks (should be C# plugin only): "
        f"{drp_names_in_xml}"
    )


def test_drp_gi_sql_blocks_removed():
    """No DRP GI <Sql> installer blocks should remain in project.xml."""
    content = PROJECT_XML.read_text(encoding="utf-8")
    cleaned = re.sub(r"<%--.*?--%>", "", content, flags=re.DOTALL)
    root = ET.fromstring(cleaned)

    drp_sql_names = []
    for sql_el in root.findall("Sql"):
        name = sql_el.get("Name", "")
        if name.startswith("InstallDRP_"):
            drp_sql_names.append(name)

    assert not drp_sql_names, (
        f"DRP GI <Sql> blocks still in project.xml (should be in C# plugin): "
        f"{drp_sql_names}"
    )


def test_probe_gis_include_drp_phase0():
    """validate_publish_gi.PROBE_GIS covers all 5 DRP GIs so post-deploy
    verification catches regressions automatically."""
    import sys
    import os
    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "scripts", "heritage")
    )
    from validate_publish_gi import PROBE_GIS  # type: ignore

    expected_names = set(EXPECTED_GIS.keys())
    missing = expected_names - set(PROBE_GIS)
    assert not missing, (
        f"DRP Phase 0 GIs missing from PROBE_GIS: {sorted(missing)}. "
        f"Add them to scripts/heritage/validate_publish_gi.py."
    )
