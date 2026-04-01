"""
SOP Generator — produces DOCX Standard Operating Procedures from workflow patterns.

Each SOP documents a real workflow observed in production audit data,
written in human-readable, followable language.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from typing import Optional

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

from .models import PatternEntry, AuditRecord, Operation
from .parser import screen_name


def _operation_verb(op_type: str) -> str:
    """Convert operation type to human-readable verb."""
    return {
        "Created": "Create",
        "Modified": "Update",
        "Deleted": "Delete",
    }.get(op_type, op_type)


def _table_to_entity(table_name: str) -> str:
    """Convert Acumatica table name to human-readable entity.

    Examples: SOOrder -> Sales Order, SOLine -> Sales Order Line,
    SOLineSplit -> Line Allocation, POOrder -> Purchase Order
    """
    mapping = {
        "SOOrder": "Sales Order header",
        "SOLine": "Sales Order line",
        "SOLineSplit": "line allocation",
        "SOShipment": "Shipment",
        "SOShipLine": "Shipment line",
        "SOPackageDetail": "package detail",
        "POOrder": "Purchase Order header",
        "POLine": "Purchase Order line",
        "POReceipt": "Purchase Receipt header",
        "POReceiptLine": "Purchase Receipt line",
        "ARInvoice": "Invoice header",
        "ARTran": "Invoice line",
        "ARPayment": "Payment",
        "APInvoice": "Bill header",
        "APTran": "Bill line",
        "APPayment": "Check/Payment",
        "INRegister": "Inventory transaction",
        "INTran": "Inventory transaction line",
        "BAccount": "Business Account",
        "Customer": "Customer",
        "Vendor": "Vendor",
        "InventoryItem": "Stock Item",
        "INItemSite": "Warehouse detail",
    }
    return mapping.get(table_name, table_name)


def _key_fields_summary(records: list[AuditRecord], max_fields: int = 8) -> list[str]:
    """Extract the most commonly modified fields across records.

    Returns human-readable field descriptions.
    """
    field_counts: Counter = Counter()
    field_values: dict[str, Counter] = {}

    for r in records:
        for field_name, value in r.modified_fields.items():
            # Skip internal/calculated fields
            if field_name.startswith("Cury") or field_name.startswith("Base"):
                continue
            if field_name in ("LineCntr", "NoteID", "tstamp", "CreatedByID",
                              "CreatedDateTime", "LastModifiedByID",
                              "LastModifiedDateTime", "CompanyID"):
                continue
            field_counts[field_name] += 1
            if field_name not in field_values:
                field_values[field_name] = Counter()
            if value:
                field_values[field_name][value] += 1

    result = []
    for field_name, count in field_counts.most_common(max_fields):
        desc = field_name
        top_values = field_values.get(field_name, Counter()).most_common(3)
        if top_values:
            examples = ", ".join(f'"{v}"' for v, _ in top_values)
            desc += f" (e.g., {examples})"
        result.append(desc)

    return result


def generate_sop(
    pattern: PatternEntry,
    all_records: Optional[list[AuditRecord]] = None,
    output_dir: str = "docs/sops",
) -> str:
    """Generate a DOCX SOP from a pattern entry.

    Args:
        pattern: The pattern to document
        all_records: Optional full record set for field-level detail
        output_dir: Directory to write the DOCX file

    Returns:
        Path to the generated DOCX file
    """
    os.makedirs(output_dir, exist_ok=True)

    doc = Document()

    # ── Styles ────────────────────────────────────────────────────────────
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ── Title ─────────────────────────────────────────────────────────────
    screen = pattern.screen_id
    screen_label = screen_name(screen)

    # Derive process name from the pattern's operation types
    step_ops = []
    for sig in pattern.step_signatures:
        parts = sig.split(" -> ")
        for part in parts:
            segments = part.split(":")
            if len(segments) >= 2:
                op = segments[1]
                if op not in step_ops:
                    step_ops.append(op)

    process_verb = _operation_verb(step_ops[0]) if step_ops else "Process"
    title = f"{process_verb} {screen_label}"

    heading = doc.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # ── Metadata ──────────────────────────────────────────────────────────
    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(6)
    run = meta.add_run(f"Screen: {screen} ({screen_label})")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    meta.add_run("\n")
    run = meta.add_run(f"Observations: {pattern.count} occurrences")
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    if pattern.first_seen and pattern.last_seen:
        meta.add_run("\n")
        run = meta.add_run(f"Period: {pattern.first_seen[:10]} to {pattern.last_seen[:10]}")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    # ── Purpose ───────────────────────────────────────────────────────────
    doc.add_heading("Purpose", level=2)
    doc.add_paragraph(
        f"This procedure documents the workflow for {process_verb.lower().rstrip('e')}ing "
        f"records on the {screen_label} screen ({screen}), "
        f"based on {pattern.count} observed occurrences in production."
    )

    # ── Steps ─────────────────────────────────────────────────────────────
    doc.add_heading("Procedure", level=2)

    step_num = 0
    for sig in pattern.step_signatures:
        # Each step signature may contain multiple sub-steps (joined by " -> ")
        parts = sig.split(" -> ")
        for part in parts:
            segments = part.split(":")
            if len(segments) < 3:
                continue

            step_screen, op_type, table = segments[0], segments[1], segments[2]
            step_num += 1

            verb = _operation_verb(op_type)
            entity = _table_to_entity(table)
            step_label = screen_name(step_screen)

            # Main step
            p = doc.add_paragraph(style="List Number")
            run = p.add_run(f"{verb} the {entity}")
            run.bold = True
            p.add_run(f"\nNavigate to {step_label} ({step_screen}).")

            if op_type == "Created":
                p.add_run(f"\nClick the \"+\" button or use Add New to create a new {entity}.")
            elif op_type == "Modified":
                p.add_run(f"\nOpen the existing {entity} and make the required changes.")
            elif op_type == "Deleted":
                p.add_run(f"\nSelect the {entity} row and click Delete.")

            # Field details (if we have records)
            if all_records:
                matching = [
                    r for r in all_records
                    if r.screen_id == step_screen
                    and r.operation == op_type
                    and r.table_name == table
                ]
                if matching:
                    fields = _key_fields_summary(matching)
                    if fields:
                        p.add_run("\nKey fields to set:")
                        for field_desc in fields:
                            sub = doc.add_paragraph(style="List Bullet")
                            sub.add_run(field_desc)

    if step_num == 0:
        doc.add_paragraph("(No detailed steps could be extracted from the pattern signature.)")

    # ── Save ──────────────────────────────────────────────────────────────
    p = doc.add_paragraph()
    step_num += 1
    run = p.add_run(f"{step_num}. Save the record")
    run.bold = True
    p.add_run("\nClick Save (Ctrl+S) to persist all changes.")

    # ── Footer ────────────────────────────────────────────────────────────
    doc.add_paragraph()  # spacer
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = footer.add_run(
        f"Auto-generated on {datetime.now().strftime('%Y-%m-%d')} "
        f"by Workflow Extractor | Studio B AI"
    )
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.italic = True

    # ── Write file ────────────────────────────────────────────────────────
    # Include hash of signature to ensure unique filenames per pattern
    import hashlib
    sig_hash = hashlib.sha256(pattern.signature.encode()).hexdigest()[:6]
    safe_name = f"{screen}_{process_verb.lower()}_{screen_label.replace(' ', '_').lower()}_{sig_hash}"
    filename = f"{safe_name}.docx"
    filepath = os.path.join(output_dir, filename)
    doc.save(filepath)

    return filepath
