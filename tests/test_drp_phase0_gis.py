"""Static XML-level assertions for the DRP Phase 0 Stream A GIs.

These GIs live as inline <GenericInquiryScreen> blocks inside
Customization/AesthetikContainers/project.xml. This test locks in:
  - A.1 DRP_VelocityHistory   (ScreenID SB401080)
  - A.2 DRP_OpenSOCommitments (ScreenID SB401090)
  - A.4 DRP_InventoryBySite   (ScreenID SB401110)

Each GI must exist with the correct name / ScreenID, expected base tables,
and expected result columns. This is deliberately an XML contract test —
it runs fast, has no live Acumatica dependency, and catches silent drift
from later edits to project.xml. Post-deploy live verification happens via
scripts/heritage/validate_publish_gi.py and Playwright.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

PROJECT_XML = (
    Path(__file__).parent.parent
    / "Customization"
    / "AesthetikContainers"
    / "project.xml"
)


# Expected GI metadata: ScreenID → (Name, base_table_alias, required_result_fields)
EXPECTED_GIS = {
    "SB401080": (
        "DRP_VelocityHistory",
        "SOShipLine",
        {"InventoryID", "ShippedQty", "ShipDate", "OrigOrderType", "OrigOrderNbr",
         "CustomerID", "SiteID", "UOM"},
    ),
    "SB401090": (
        "DRP_OpenSOCommitments",
        "SOLine",
        {"InventoryID", "OrderType", "OrderNbr", "LineNbr", "OrderQty", "ShippedQty",
         "OpenQty", "RequestedDate", "CustomerID", "SiteID", "UOM"},
    ),
    "SB401100": (
        "DRP_OpenPOLines",
        "Line",
        {"OrderType", "OrderNbr", "LineNbr", "InventoryID", "VendorID", "OrderQty",
         "ReceivedQty", "OpenQty", "PromisedDate",
         "UsrAcknowledgedDate", "UsrFactoryReadyDate", "ContainerCD"},
    ),
    "SB401110": (
        "DRP_InventoryBySite",
        "InventoryItem",
        {"InventoryCD", "Descr", "ItemStatus", "ItemClassID", "SiteID", "QtyOnHand",
         "QtyAvail", "QtyHardAvail", "QtyAllocated"},
    ),
}


@pytest.fixture(scope="module")
def root():
    """Parse project.xml once per test module."""
    assert PROJECT_XML.is_file(), f"{PROJECT_XML} not found"
    return ET.parse(PROJECT_XML).getroot()


@pytest.fixture(scope="module")
def drp_gi_rows(root):
    """Return dict ScreenID → <GIDesign><row> element for the 3 DRP GIs.

    Filters on DesignID presence because <SiteMap><row> elements share the
    ScreenID attribute name but have NodeID instead of DesignID — and they'd
    shadow the real GI rows in a naive filter.
    """
    out: dict[str, ET.Element] = {}
    for row in root.findall(".//GIDesign/row"):
        sid = row.get("ScreenID")
        if sid in EXPECTED_GIS:
            out[sid] = row
    return out


@pytest.mark.parametrize("screen_id", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_exists(drp_gi_rows, screen_id):
    """Every DRP Phase 0 GI has a <GIDesign><row> with the expected name."""
    expected_name, _, _ = EXPECTED_GIS[screen_id]
    assert screen_id in drp_gi_rows, (
        f"Missing GI row for ScreenID {screen_id} ({expected_name}) "
        f"in {PROJECT_XML}"
    )
    row = drp_gi_rows[screen_id]
    assert row.get("Name") == expected_name, (
        f"ScreenID {screen_id} has Name={row.get('Name')!r}, expected {expected_name!r}"
    )
    design_id = row.get("DesignID")
    assert design_id, f"{screen_id} missing DesignID"
    # DesignID must be a well-formed UUID (36 chars with hyphens)
    assert len(design_id) == 36 and design_id.count("-") == 4, (
        f"{screen_id} DesignID {design_id!r} not UUID-shaped"
    )


@pytest.mark.parametrize("screen_id", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_exposes_via_odata(drp_gi_rows, screen_id):
    """Every DRP GI must be ExposeViaOData=1 (Wave 4 code consumes them)."""
    row = drp_gi_rows[screen_id]
    assert row.get("ExposeViaOData") == "1", (
        f"{screen_id} must have ExposeViaOData=1 so the DRP agent can read it"
    )


@pytest.mark.parametrize("screen_id", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_base_table(drp_gi_rows, screen_id):
    """Every DRP GI defines its expected base-table alias."""
    _, expected_alias, _ = EXPECTED_GIS[screen_id]
    row = drp_gi_rows[screen_id]
    aliases = {t.get("Alias") for t in row.findall("GITable")}
    assert expected_alias in aliases, (
        f"{screen_id} expected base alias {expected_alias!r}, got {aliases}"
    )


@pytest.mark.parametrize("screen_id", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_required_result_fields(drp_gi_rows, screen_id):
    """Every DRP GI surfaces the result fields Wave 4 code depends on."""
    _, _, required_fields = EXPECTED_GIS[screen_id]
    row = drp_gi_rows[screen_id]
    result_fields = {r.get("Field") for r in row.iter("GIResult")}
    missing = required_fields - result_fields
    assert not missing, (
        f"{screen_id} missing required result fields: {sorted(missing)}. "
        f"Present: {sorted(result_fields)}"
    )


@pytest.mark.parametrize("screen_id", sorted(EXPECTED_GIS.keys()))
def test_drp_gi_has_sitemap_entry(drp_gi_rows, screen_id):
    """Every DRP GI has a SiteMap row so it shows up in the Container Tracking workspace."""
    row = drp_gi_rows[screen_id]
    sitemap_rows = row.findall("./SiteMap/row")
    assert len(sitemap_rows) >= 1, f"{screen_id} missing <SiteMap> entry"
    sm_row = sitemap_rows[0]
    assert sm_row.get("ScreenID") == screen_id, (
        f"{screen_id} SiteMap row has ScreenID={sm_row.get('ScreenID')}"
    )
    # Parent should be the shared Container Tracking workspace folder
    assert sm_row.get("ParentID") == "9c89e3db-7c47-43c0-8554-5d2c9f2c0e87", (
        f"{screen_id} SiteMap ParentID mismatch — should match other SB401xxx GIs"
    )


def test_probe_gis_include_drp_phase0():
    """validate_publish_gi.PROBE_GIS covers the 3 new DRP GIs so post-deploy
    verification catches regressions automatically."""
    import sys
    import os
    sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "scripts", "heritage")
    )
    from validate_publish_gi import PROBE_GIS  # type: ignore

    expected_names = {name for name, _, _ in EXPECTED_GIS.values()}
    missing = expected_names - set(PROBE_GIS)
    assert not missing, (
        f"DRP Phase 0 GIs missing from PROBE_GIS: {sorted(missing)}. "
        f"Add them to scripts/heritage/validate_publish_gi.py."
    )
