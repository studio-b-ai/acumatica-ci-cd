"""
Field parsing for Acumatica audit trail data.

The StudioBAuditTrail GI returns data with null-byte (\x00) delimiters:
- CombinedKey: null-byte separated key segments (e.g., "CO\x00S000201\x001")
- ModifiedFields: alternating field-name/value pairs (e.g., "Qty\x0010\x00UOM\x00CUT")
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from .models import AuditRecord


# ── Screen ID mapping ────────────────────────────────────────────────────────

SCREEN_NAMES: dict[str, str] = {
    "SO301000": "Sales Orders",
    "SO302000": "Shipments",
    "SO303000": "Invoices",
    "SO301010": "Sales Order Entry (Quick)",
    "PO301000": "Purchase Orders",
    "PO302000": "Purchase Receipts",
    "AR301000": "Invoices and Memos",
    "AR303000": "Customers",
    "AR302000": "Payments and Applications",
    "AP301000": "Bills and Adjustments",
    "AP303000": "Vendors",
    "AP302000": "Checks and Payments",
    "IN202500": "Stock Items",
    "IN301000": "Inventory Receipts",
    "IN302000": "Inventory Issues",
    "IN304000": "Inventory Transfers",
    "CS205000": "Business Accounts",
    "CR301000": "Cases",
    "CR302000": "Opportunities",
    "GL301000": "Journal Transactions",
    "SM201010": "Users",
    "SM208000": "Generic Inquiries",
}


def screen_name(screen_id: str) -> str:
    """Human-readable name for a screen ID."""
    return SCREEN_NAMES.get(screen_id, screen_id)


# ── Field parsing ────────────────────────────────────────────────────────────

def parse_combined_key(raw: str) -> list[str]:
    """Parse null-byte-delimited combined key into segments.

    Example: "CO\\x00S000201\\x001" -> ["CO", "S000201", "1"]
    """
    if not raw:
        return []
    return [s for s in raw.split("\x00") if s]


def parse_modified_fields(raw: str) -> dict[str, str]:
    """Parse null-byte-delimited alternating field/value pairs.

    Example: "Qty\\x0010\\x00UOM\\x00CUT" -> {"Qty": "10", "UOM": "CUT"}

    Acumatica stores ModifiedFields as alternating pairs:
    FieldName1, Value1, FieldName2, Value2, ...
    """
    if not raw:
        return {}
    parts = raw.split("\x00")
    result = {}
    i = 0
    while i < len(parts) - 1:
        field_name = parts[i].strip()
        value = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if field_name:
            result[field_name] = value
        i += 2
    return result


# ── Record parsing ───────────────────────────────────────────────────────────

def parse_odata_record(row: dict) -> AuditRecord:
    """Parse a single OData JSON row into an AuditRecord.

    Expected fields from StudioBAuditTrail GI:
    BatchID, ChangeID, ScreenID, Operation, ChangeDate, TableName,
    CombinedKey, ModifiedFields, (optional) Username
    """
    # ChangeDate comes as ISO-ish string, e.g. "2025-08-07T18:17:11.943"
    change_date_str = row.get("ChangeDate", "")
    try:
        change_date = datetime.fromisoformat(change_date_str)
    except (ValueError, TypeError):
        change_date = datetime.min

    return AuditRecord(
        batch_id=int(row.get("BatchID", 0)),
        change_id=int(row.get("ChangeID", 0)),
        screen_id=row.get("ScreenID", "").strip(),
        operation=row.get("Operation", "").strip(),
        change_date=change_date,
        table_name=row.get("TableName", "").strip(),
        combined_key=parse_combined_key(row.get("CombinedKey", "")),
        modified_fields=parse_modified_fields(row.get("ModifiedFields", "")),
        username=row.get("Username") or row.get("UserName") or None,
    )


def parse_odata_response(data: list[dict]) -> list[AuditRecord]:
    """Parse a list of OData rows into AuditRecords."""
    return [parse_odata_record(row) for row in data]
