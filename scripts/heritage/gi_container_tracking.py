"""Generate Container Tracking GI SQL using the GI Builder Engine.

Produces transactional SQL for 4 Generic Inquiries that replace the IIG
Container Management ISV with native Acumatica GI screens:

  SB401000 — PO Containers
  SB401010 — SO Containers
  SB401020 — Container Events
  SB401030 — Custom Classification

Usage:
    python scripts/heritage/gi_container_tracking.py [--output-dir data/container-tracking] [--company-id 2] [--gi SB401000]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from gi_builder import GIDefinition, GIBuilder
from gi_schema import GISchemaMap


# Mock schema based on known GI table structures from the 2026-03-29 investigation.
# This will be replaced with real INFORMATION_SCHEMA data once schema discovery runs.
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
        "QuickFilter": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "FastFilter": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
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
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
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
        "IsActive": {"data_type": "bit", "nullable": "YES", "max_length": None, "default": None},
        "DataFieldName": {"data_type": "nvarchar", "nullable": "NO", "max_length": 256, "default": None},
        "SortOrder": {"data_type": "nvarchar", "nullable": "YES", "max_length": 1, "default": None},
        "CompanyID": {"data_type": "int", "nullable": "NO", "max_length": None, "default": None},
    },
}

# Template audit column values — these would come from a real existing GI
# in production. For the POC, use placeholder values.
TEMPLATE_ROW = {
    "CreatedByID": "B5344897-037E-4D58-B5C3-1BDFD0F47BF4",  # admin user GUID
    "CreatedByScreenID": "SM208000",
    # NoteID intentionally omitted — auto-generated as UUID per row by GIBuilder
}


# ---------------------------------------------------------------------------
# GI Specifications
# ---------------------------------------------------------------------------

GI_REGISTRY: dict[str, callable] = {}


def _register(screen_id: str):
    """Decorator to register a GI spec builder function by screen ID."""
    def decorator(fn):
        GI_REGISTRY[screen_id] = fn
        return fn
    return decorator


@_register("SB401000")
def build_po_containers() -> GIDefinition:
    """PO Containers — master list of inbound containers."""
    return GIDefinition(
        name="POContainers",
        screen_id="SB401000",
        tables=[
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container ID", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "CarrierCode", "caption": "Carrier", "width": 100},
            {"field": "VesselName", "caption": "Vessel", "width": 150},
            {"field": "PortOfLoading", "caption": "Port of Loading", "width": 120},
            {"field": "PortOfDischarge", "caption": "Port of Discharge", "width": 120},
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


@_register("SB401010")
def build_so_containers() -> GIDefinition:
    """SO Containers — shipments linked to containers."""
    return GIDefinition(
        name="SOContainers",
        screen_id="SB401010",
        tables=[
            {"dac": "PX.Objects.SO.SOShipment", "alias": "Shipment"},
        ],
        results=[
            {"field": "ShipmentNbr", "caption": "Shipment Nbr", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "CustomerID", "caption": "Customer", "width": 120},
            {"field": "ShipDate", "caption": "Ship Date", "width": 100},
            {"field": "UsrContainerID", "caption": "Container ID", "width": 120},
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


@_register("SB401020")
def build_container_events() -> GIDefinition:
    """Container Events — tracking events joined to containers."""
    return GIDefinition(
        name="ContainerEvents",
        screen_id="SB401020",
        tables=[
            {"dac": "StudioB.Containers.UsrContainerEvent", "alias": "Event"},
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container ID", "width": 120},
            {"field": "EventDateTime", "caption": "Event Date/Time", "width": 150},
            {"field": "NormalizedEventCode", "caption": "Event Code", "width": 120},
            {"field": "EventClassifier", "caption": "Classifier", "width": 80},
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


@_register("SB401030")
def build_custom_classification() -> GIDefinition:
    """Custom Classification — inventory items with tariff/duty fields."""
    return GIDefinition(
        name="CustomClassification",
        screen_id="SB401030",
        tables=[
            {"dac": "PX.Objects.IN.InventoryItem", "alias": "Item"},
        ],
        results=[
            {"field": "InventoryCD", "caption": "Inventory ID", "width": 120},
            {"field": "Descr", "caption": "Description", "width": 200},
            {"field": "ItemClassID", "caption": "Item Class", "width": 120},
            {"field": "UsrFiberContent", "caption": "Fiber Content", "width": 150},
            {"field": "UsrDutyRate", "caption": "Duty Rate", "width": 100},
            {"field": "UsrPreferentialTariff", "caption": "Preferential Tariff", "width": 100},
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


@_register("SB401040")
def build_po_container_lines() -> GIDefinition:
    """PO Container Lines — detail view of PO lines on containers."""
    return GIDefinition(
        name="POContainerLines",
        screen_id="SB401040",
        tables=[
            {"dac": "StudioB.Containers.UsrContainerPOLink", "alias": "Link"},
            {"dac": "StudioB.Containers.UsrContainer", "alias": "Container"},
            {"dac": "PX.Objects.PO.POOrder", "alias": "PO"},
            {"dac": "PX.Objects.PO.POLine", "alias": "Line"},
        ],
        results=[
            {"field": "ContainerCD", "caption": "Container", "width": 120},
            {"field": "Status", "caption": "Status", "width": 100},
            {"field": "ETA", "caption": "ETA", "width": 100},
            {"field": "OrderType", "caption": "Type", "width": 60},
            {"field": "OrderNbr", "caption": "PO Nbr", "width": 120},
            {"field": "LineNbr", "caption": "Line", "width": 60},
            {"field": "InventoryID", "caption": "Item", "width": 120},
            {"field": "OrderQty", "caption": "Qty", "width": 80},
            {"field": "CuryUnitCost", "caption": "Price", "width": 80},
        ],
        filters=[
            {"name": "ContainerFilter", "display_name": "Container", "data_type": 6},
            {"name": "POFilter", "display_name": "PO Nbr", "data_type": 6},
        ],
        where=[
            {"field": "Container.ContainerCD", "condition": "E ", "value": "@ContainerFilter", "operation": "A"},
            {"field": "Link.OrderNbr", "condition": "E ", "value": "@POFilter", "operation": "A"},
        ],
        sort=[
            {"field": "Container.ContainerCD", "order": "A"},
            {"field": "Link.OrderNbr", "order": "A"},
        ],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def generate_gi(screen_id: str, schema: GISchemaMap, company_id: int, output_dir: Path) -> Path:
    """Generate SQL for a single GI and write to output_dir."""
    spec_fn = GI_REGISTRY[screen_id]
    spec = spec_fn()
    builder = GIBuilder(schema, template_row=TEMPLATE_ROW, company_id=company_id)
    sql = builder.build_sql(spec)

    filename = f"{spec.name}.sql"
    output_path = output_dir / filename
    output_path.write_text(sql)
    print(f"  {screen_id} ({spec.name}): {len(sql):,} bytes -> {output_path}")
    print(f"    {len(spec.tables)} tables, {len(spec.results)} results, "
          f"{len(spec.filters)} filters, {len(spec.where)} conditions, {len(spec.sort)} sorts")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Container Tracking GI SQL (4 screens)")
    parser.add_argument("--schema-file", help="Path to cached schema JSON (from Phase 1)")
    parser.add_argument("--output-dir", default="data/container-tracking", help="Output directory for SQL files")
    parser.add_argument("--company-id", type=int, default=2, help="Acumatica CompanyID")
    parser.add_argument("--gi", choices=list(GI_REGISTRY.keys()), help="Generate only one specific GI")
    args = parser.parse_args()

    if args.schema_file:
        schema = GISchemaMap.load(Path(args.schema_file))
    else:
        schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    targets = [args.gi] if args.gi else list(GI_REGISTRY.keys())
    print(f"Generating {len(targets)} GI SQL file(s) to {output_dir}/\n")

    generated = []
    for screen_id in targets:
        path = generate_gi(screen_id, schema, args.company_id, output_dir)
        generated.append(path)

    print(f"\nDone. {len(generated)} file(s) generated.")
