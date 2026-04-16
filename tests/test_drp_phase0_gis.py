"""Static SQL-level assertions for the DRP Phase 0 Stream A GIs.

These GIs are installed via SQL <Sql> blocks inside
Customization/AesthetikContainers/project.xml. This test locks in:
  - DRP_VelocityHistory
  - DRP_OpenSOCommitments
  - DRP_InventoryBySite
  - DRP_OpenPOLines
  - DRP_ItemWarehouseSettings

Each GI must have a SQL installer script with the correct name,
ExposeViaOData=1, expected table aliases, expected result fields,
and NO ScreenID (which would trigger SiteMap access checks on OData).

This is deliberately an offline contract test — it runs fast, has no
live Acumatica dependency, and catches silent drift from later edits
to project.xml.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

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
def sql_scripts():
    """Parse project.xml and return dict of GI name → SQL script text."""
    assert PROJECT_XML.is_file(), f"{PROJECT_XML} not found"
    # Strip ASP.NET comments that break standard XML parsing
    content = PROJECT_XML.read_text(encoding="utf-8")
    cleaned = re.sub(r"<%--.*?--%>", "", content, flags=re.DOTALL)
    root = ET.fromstring(cleaned)

    out: dict[str, str] = {}
    for sql_el in root.findall("Sql"):
        name = sql_el.get("Name", "")
        if name.startswith("InstallDRP_") and name.endswith("GI"):
            # Extract GI name from script name: InstallDRP_FooGI → DRP_Foo
            gi_name = name[len("Install"):-len("GI")]
            cdata = sql_el.find("CDATA")
            if cdata is not None and cdata.text:
                out[gi_name] = cdata.text
    return out


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_script_exists(sql_scripts, gi_name):
    """Every DRP GI has a SQL installer script in project.xml."""
    assert gi_name in sql_scripts, (
        f"Missing SQL installer script for {gi_name} in {PROJECT_XML}. "
        f"Expected <Sql Name=\"Install{gi_name}GI\">."
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_has_review_marker(sql_scripts, gi_name):
    """Every DRP GI SQL script has the gi-sql-safe review marker."""
    sql = sql_scripts.get(gi_name, "")
    assert "-- REVIEWED: gi-sql-safe" in sql, (
        f"{gi_name} SQL script missing '-- REVIEWED: gi-sql-safe' marker"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_exposes_via_odata(sql_scripts, gi_name):
    """Every DRP GI must set ExposeViaOData=1 in the GIDesign INSERT."""
    sql = sql_scripts.get(gi_name, "")
    assert "ExposeViaOData" in sql, (
        f"{gi_name} SQL script missing ExposeViaOData in GIDesign INSERT"
    )
    # Verify the INSERT INTO GIDesign line contains the GI name
    assert f"'{gi_name}'" in sql, (
        f"{gi_name} SQL script doesn't reference its own name in GIDesign INSERT"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_has_no_screenid(sql_scripts, gi_name):
    """DRP GIs must NOT have ScreenID — this is what makes OData work without 403."""
    sql = sql_scripts.get(gi_name, "")
    # Check the GIDesign INSERT specifically — ScreenID should not appear as a column
    gi_design_match = re.search(
        r"INSERT\s+INTO\s+GIDesign\s*\(([^)]+)\)", sql, re.IGNORECASE
    )
    assert gi_design_match, f"{gi_name} SQL script missing INSERT INTO GIDesign"
    columns = gi_design_match.group(1)
    assert "ScreenID" not in columns, (
        f"{gi_name} SQL script has ScreenID in GIDesign INSERT columns — "
        f"this will trigger SiteMap access checks and break OData"
    )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_has_tables(sql_scripts, gi_name):
    """Every DRP GI SQL script references the expected table aliases."""
    expected_aliases, _ = EXPECTED_GIS[gi_name]
    sql = sql_scripts.get(gi_name, "")
    for alias in expected_aliases:
        assert f"'{alias}'" in sql, (
            f"{gi_name} SQL script missing table alias '{alias}'"
        )


@pytest.mark.parametrize("gi_name", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_sql_has_required_result_fields(sql_scripts, gi_name):
    """Every DRP GI SQL script includes the required result fields."""
    _, required_fields = EXPECTED_GIS[gi_name]
    sql = sql_scripts.get(gi_name, "")
    missing = set()
    for field in required_fields:
        if f"'{field}'" not in sql:
            missing.add(field)
    assert not missing, (
        f"{gi_name} SQL script missing required result fields: {sorted(missing)}"
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
        f"DRP GIs still defined as XML blocks (should be SQL-only): "
        f"{drp_names_in_xml}"
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
