"""
Test Case Generator — produces pytest fixtures from audit-derived patterns.

Generates two outputs:
1. JSON fixtures with real field combinations per entity (for parameterized pytest)
2. Suggested e2e_probes for publish-manifest.json (screens in audit but not in manifest)
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Optional

from .models import AuditRecord, PatternEntry
from .parser import screen_name


# ── Table-to-entity mapping for REST API ─────────────────────────────────────

TABLE_TO_REST_ENTITY: dict[str, str] = {
    "SOOrder": "SalesOrder",
    "SOLine": "SalesOrder",
    "SOLineSplit": "SalesOrder",
    "POOrder": "PurchaseOrder",
    "POLine": "PurchaseOrder",
    "POReceipt": "PurchaseReceipt",
    "POReceiptLine": "PurchaseReceipt",
    "ARInvoice": "Invoice",
    "ARTran": "Invoice",
    "ARPayment": "Payment",
    "APInvoice": "Bill",
    "APTran": "Bill",
    "APPayment": "Check",
    "BAccount": "BusinessAccount",
    "Customer": "Customer",
    "Vendor": "Vendor",
    "InventoryItem": "StockItem",
    "INRegister": "InventoryReceipt",
    "INTran": "InventoryReceipt",
    "INItemSite": "StockItem",
    "SOShipment": "Shipment",
    "SOShipLine": "Shipment",
}


def _extract_field_combinations(
    records: list[AuditRecord],
    min_occurrences: int = 2,
) -> dict[str, dict]:
    """Extract real field combinations from audit records, grouped by entity.

    Returns:
        {
            "SalesOrder": {
                "fields_observed": ["OrderType", "Status", "CustomerID", ...],
                "custom_fields": ["UsrHubSpotDealId", ...],
                "field_value_examples": {"OrderType": ["SO", "CO"], ...},
                "record_count": 150,
                "screen_ids": ["SO301000"],
            },
            ...
        }
    """
    entity_fields: dict[str, Counter] = defaultdict(Counter)
    entity_values: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    entity_screens: dict[str, set] = defaultdict(set)
    entity_count: dict[str, int] = defaultdict(int)

    for r in records:
        entity = TABLE_TO_REST_ENTITY.get(r.table_name)
        if not entity:
            continue

        entity_count[entity] += 1
        entity_screens[entity].add(r.screen_id)

        for field_name, value in r.modified_fields.items():
            # Skip internal/calculated fields
            if field_name in ("NoteID", "tstamp", "CompanyID", "CreatedByID",
                              "CreatedDateTime", "LastModifiedByID",
                              "LastModifiedDateTime", "DeletedDatabaseRecord"):
                continue
            entity_fields[entity][field_name] += 1
            if value:
                entity_values[entity][field_name][value] += 1

    result = {}
    for entity in sorted(entity_fields.keys()):
        fields = entity_fields[entity]
        # Only include fields seen at least min_occurrences times
        observed = [f for f, c in fields.most_common() if c >= min_occurrences]
        custom = [f for f in observed if f.startswith("Usr")]
        # Top 3 example values per field
        value_examples = {}
        for field_name in observed[:20]:  # limit to top 20 fields
            top_vals = entity_values[entity][field_name].most_common(3)
            if top_vals:
                value_examples[field_name] = [v for v, _ in top_vals]

        result[entity] = {
            "fields_observed": observed,
            "custom_fields": custom,
            "field_value_examples": value_examples,
            "record_count": entity_count[entity],
            "screen_ids": sorted(entity_screens[entity]),
        }

    return result


def generate_fixtures(
    records: list[AuditRecord],
    output_dir: str = "tests/fixtures/audit_derived",
    min_occurrences: int = 2,
) -> list[str]:
    """Generate JSON fixture files from audit records.

    Creates one fixture file per entity with real field combinations.

    Returns:
        List of generated fixture file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    combinations = _extract_field_combinations(records, min_occurrences)
    generated = []

    for entity, data in combinations.items():
        filepath = os.path.join(output_dir, f"{entity}.json")
        fixture = {
            "_generated": True,
            "_source": "StudioBAuditTrail",
            "_description": (
                f"Real field combinations for {entity}, derived from "
                f"{data['record_count']} audit records. Used by "
                f"test_audit_derived.py for regression testing."
            ),
            "entity": entity,
            "screen_ids": data["screen_ids"],
            "fields_observed": data["fields_observed"],
            "custom_fields": data["custom_fields"],
            "field_value_examples": data["field_value_examples"],
            "record_count": data["record_count"],
        }
        with open(filepath, "w") as f:
            json.dump(fixture, f, indent=2)
        generated.append(filepath)

    return generated


def suggest_manifest_updates(
    records: list[AuditRecord],
    manifest_path: str = "publish-manifest.json",
) -> dict:
    """Compare audit-observed screens/entities against publish-manifest.json.

    Returns suggested additions to e2e_probes.
    """
    # Load current manifest
    manifest_entities = set()
    manifest_probes = set()
    if os.path.exists(manifest_path):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        for entity in manifest.get("entities", {}):
            manifest_entities.add(entity)
        for probe in manifest.get("e2e_probes", []):
            manifest_probes.add(probe.get("entity", ""))

    # Entities seen in audit but not in manifest
    audit_entities = set()
    for r in records:
        entity = TABLE_TO_REST_ENTITY.get(r.table_name)
        if entity:
            audit_entities.add(entity)

    missing_entities = audit_entities - manifest_entities - manifest_probes
    suggestions = []
    for entity in sorted(missing_entities):
        # Find custom fields for this entity
        custom_fields = set()
        for r in records:
            if TABLE_TO_REST_ENTITY.get(r.table_name) == entity:
                for field in r.modified_fields:
                    if field.startswith("Usr"):
                        custom_fields.add(field)

        if custom_fields:
            suggestions.append({
                "entity": entity,
                "select_fields": sorted(custom_fields),
                "note": "Auto-suggested from audit trail — custom fields observed in production",
            })

    return {
        "entities_in_audit": sorted(audit_entities),
        "entities_in_manifest": sorted(manifest_entities),
        "missing_from_manifest": sorted(missing_entities),
        "suggested_probes": suggestions,
    }
