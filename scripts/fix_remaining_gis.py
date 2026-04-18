#!/usr/bin/env python3
"""Apply targeted fixes for the 4 GIs that didn't register after the
convert_gi_to_iig_format.py pass:

1. DRP_ItemWarehouseSettings (was 403): split the dual <GenericInquiryScreen>
   block (which currently contains DRP_OpenPOLines + DRP_ItemWarehouseSettings)
   into two separate single-GI blocks. IIG one-block-per-GI convention; the
   publish engine appears to bind RolesInGraph to the first row's NodeID
   when multiple rows share a block.

2. InventoryQuantityDetail (was 404): change ScreenID GI007000 → SB401130.
   GI007000 is in Acumatica's system-reserved GI screen ID range and almost
   certainly conflicts with a built-in.

3. ContainerEvents (was 404): remove <GIFilter> + the two <GIWhere> rows
   that reference =[ContainerFilter] / =[EventCodeFilter]. The IIG packages
   never use <GIFilter>; the filter format may be wrong for 24.208 fresh
   registration. The remaining sort/structure keeps the GI listing all
   container events; users can re-add filters after.

4. POContainers (was 404): same treatment as ContainerEvents.

Idempotent: each fix only fires if the legacy state is still present.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_XML = Path(__file__).resolve().parents[1] / "Customization" / "AesthetikContainers" / "project.xml"


def split_dual_drp_block(content: str) -> tuple[str, str]:
    """Split the DRP_OpenPOLines + DRP_ItemWarehouseSettings dual block into
    two separate <GenericInquiryScreen> blocks. Both share the same
    <relations>/<layout> boilerplate, so we clone those into the new block."""

    # Find the dual block.
    open_tag = "<GenericInquiryScreen>"
    close_tag = "</GenericInquiryScreen>"
    pos = 0
    while True:
        b_start = content.find(open_tag, pos)
        if b_start < 0:
            return content, "no DRP dual block found (already split?)"
        b_end = content.find(close_tag, b_start)
        if b_end < 0:
            return content, "unterminated GenericInquiryScreen block"
        b_end += len(close_tag)
        block = content[b_start:b_end]
        if 'Name="DRP_OpenPOLines"' in block and 'Name="DRP_ItemWarehouseSettings"' in block:
            break
        pos = b_end

    # Extract <relations>...</relations> and <layout>...</layout> from the block.
    rel_m = re.search(r"<relations[\s\S]*?</relations>", block)
    layout_m = re.search(r"<layout[\s\S]*?</layout>", block)
    if not rel_m or not layout_m:
        return content, "dual block missing <relations> or <layout>"
    relations_xml = rel_m.group(0)
    layout_xml = layout_m.group(0)

    # Split out the second <row> (DRP_ItemWarehouseSettings) from the existing block.
    # Need to match the OUTER </row> closing the GIDesign row, not the inner
    # </row> closing the nested SiteMap row. Anchor on the </row> immediately
    # before </GIDesign> via a lookahead.
    second_row_m = re.search(
        r"(\s*<row\s+DesignID=\"[^\"]+\"\s+Name=\"DRP_ItemWarehouseSettings\"[\s\S]*?</row>\s*)(?=</GIDesign>)",
        block,
    )
    if not second_row_m:
        return content, "second DRP row not found"
    second_row_text = second_row_m.group(1)

    # Build the rewritten existing block (without the second row).
    existing_block_new = block.replace(second_row_text, "\n        ", 1)

    # Build the NEW <GenericInquiryScreen> block for DRP_ItemWarehouseSettings.
    # Mirror the indentation style of surrounding blocks (4 spaces leading).
    new_block = (
        "    <GenericInquiryScreen>\n"
        "  <data-set>\n"
        "                " + relations_xml + "\n"
        "            " + layout_xml + "\n"
        "    <data>\n"
        "      <GIDesign>"
        + second_row_text.rstrip()
        + "\n      </GIDesign>\n"
        "    </data>\n"
        "  </data-set>\n"
        "</GenericInquiryScreen>"
    )

    # Splice both back into content: existing_block_new replaces the original
    # block; the new_block follows it.
    new_content = content[:b_start] + existing_block_new + "\n" + new_block + content[b_end:]
    return new_content, "split: 1 dual block → 2 single-GI blocks"


def change_inv_qty_screenid(content: str) -> tuple[str, str]:
    """Change InventoryQuantityDetail ScreenID GI007000 → SB401130 wherever it
    appears in that GI's block. The DesignID and NodeID stay the same."""

    # Find InventoryQuantityDetail block boundaries.
    pos = content.find('Name="InventoryQuantityDetail"')
    if pos < 0:
        return content, "InventoryQuantityDetail not found"

    # Replace PrimaryScreenIDNew on the GIDesign row.
    new_content, n1 = re.subn(
        r'(Name="InventoryQuantityDetail"[^>]*?)PrimaryScreenIDNew="GI007000"',
        r'\1PrimaryScreenIDNew="SB401130"',
        content,
        count=1,
    )
    # Replace ScreenID on the SiteMap row (which references the same screen).
    new_content, n2 = re.subn(
        r'(Url="~/genericinquiry/genericinquiry\.aspx\?id=b7e3a1d4-92f6-4c8a-b5d1-1a2b3c4d5e6f"\s+)ScreenID="GI007000"',
        r'\1ScreenID="SB401130"',
        new_content,
        count=1,
    )
    if n1 == 0 and n2 == 0:
        return content, "InventoryQuantityDetail ScreenID already fixed (or not present)"
    return new_content, f"InventoryQuantityDetail ScreenID: GI007000 → SB401130 ({n1+n2} replacements)"


def remove_filters_from(gi_name: str, filter_names: list[str]) -> callable:
    """Returns a transform that strips <GIFilter> rows + <GIWhere> rows that
    reference the given filter parameter names from the named GI's block."""

    def fn(content: str) -> tuple[str, str]:
        # Locate the GI's block boundaries (<GenericInquiryScreen>...</GenericInquiryScreen>
        # that contains the named row).
        marker = f'Name="{gi_name}"'
        pos = content.find(marker)
        if pos < 0:
            return content, f"{gi_name} not found"
        # Walk back to <GenericInquiryScreen>
        b_start = content.rfind("<GenericInquiryScreen>", 0, pos)
        b_end = content.find("</GenericInquiryScreen>", pos) + len("</GenericInquiryScreen>")
        block = content[b_start:b_end]
        original = block

        # Remove every <GIFilter ... /> whose Name attribute is in filter_names.
        for fname in filter_names:
            block = re.sub(
                r'\s*<GIFilter\s[^>]*Name="' + re.escape(fname) + r'"[^>]*/>',
                "",
                block,
            )

        # Remove <GIWhere> elements whose Value1 references "=[<fname>]".
        for fname in filter_names:
            block = re.sub(
                r'\s*<GIWhere\s[^>]*Value1="=\[' + re.escape(fname) + r'\]"[^>]*/>',
                "",
                block,
            )

        if block == original:
            return content, f"{gi_name}: no GIFilter/GIWhere matches removed (already clean?)"
        new_content = content[:b_start] + block + content[b_end:]
        return new_content, f"{gi_name}: removed GIFilter/GIWhere for {', '.join(filter_names)}"

    return fn


def main() -> int:
    content = PROJECT_XML.read_text()
    transforms = [
        ("split_dual_drp_block", split_dual_drp_block),
        ("change_inv_qty_screenid", change_inv_qty_screenid),
        ("remove_container_filter", remove_filters_from(
            "ContainerEvents", ["ContainerFilter", "EventCodeFilter"]
        )),
        ("remove_pocontainers_filter", remove_filters_from(
            "POContainers", ["StatusFilter", "CarrierFilter"]
        )),
    ]

    for name, fn in transforms:
        new_content, msg = fn(content)
        print(f"  [{name}] {msg}")
        content = new_content

    if content == PROJECT_XML.read_text():
        print("No changes to write.")
        return 0
    PROJECT_XML.write_text(content)
    print(f"Wrote {PROJECT_XML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
