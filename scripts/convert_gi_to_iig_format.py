#!/usr/bin/env python3
"""Convert legacy <GenericInquiryScreen> blocks in AesthetikContainers/project.xml
to the modern IIG-format that Acumatica's publish engine accepts for fresh GI
registration.

Background: PR #461 + tonight's three publishes confirmed the legacy format
silently fails to register new GIs (11/12 missing from prod OData catalog after
3 publishes). Hypothesis was tested on ArrivingThisWeek by hand — converting
to the IIG format made it register on sandbox (200 OData response) within one
publish. This script applies the same transformation to the remaining 10
failing GI blocks.

Transformations (per IIG-CM[24.204] reference and KB
"Acumatica Generic Inquiry — XML Import Format (Definitive Guide)"):

1. GIDesign row: rename `ScreenID="X"` → `PrimaryScreenIDNew="X"` and append
   the 5 attrs Acumatica 24.208 expects on the new column set:
   `ShowDeletedRecords="0" ShowArchivedRecords="0"
    NotesAndFilesTable="$<None>" MLDetectionEnabled="0" SkipEmptyGroups="0"`.

2. GITable: add `Type="0"` (root data source type marker; IIG always sets it).

3. SiteMap row: drop legacy display attrs `Position`/`Expanded`/`IsFolder`,
   rebind ParentID to the zero GUID (the to-design-by-id link is for the
   GI itself, not a workspace child), add `SelectedUI="E"`, lowercase the
   `~/genericinquiry/genericinquiry.aspx?id=...` URL to match IIG.

4. MUIScreen: nest `<MUIPinnedScreen IsPortal="0" Username="" IsPinned="1" />`
   so the catalog's pinned-screen registration is satisfied.

Skip list:
- LandedCostSummary  — works on prod via legacy format (registered manually
                      long before this format issue surfaced). Re-publishing
                      it in modern format could orphan child rows.
- ArrivingThisWeek   — already converted by hand as the POC.

Idempotency: the script detects already-converted blocks (presence of
`PrimaryScreenIDNew=` on the GIDesign row) and skips them.

Usage:
    python3 scripts/convert_gi_to_iig_format.py --check   # dry run
    python3 scripts/convert_gi_to_iig_format.py           # apply in place
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_XML = Path(__file__).resolve().parents[1] / "Customization" / "AesthetikContainers" / "project.xml"

# Skip these GI Names — leave their existing XML blocks untouched.
SKIP = {
    "LandedCostSummary",  # works on prod via legacy format
    "ArrivingThisWeek",   # POC — already converted by hand
}

# 5 new GIDesign attrs Acumatica 24.208 expects (per IIG-CM reference).
NEW_GIDESIGN_ATTRS = (
    'ShowDeletedRecords="0" ShowArchivedRecords="0" '
    'NotesAndFilesTable="$&lt;None&gt;" '
    'MLDetectionEnabled="0" SkipEmptyGroups="0"'
)

ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def convert_block(block: str, gi_name: str) -> tuple[str, list[str]]:
    """Apply the four transformations to a single <GenericInquiryScreen> block.

    Returns (new_block_text, list_of_changes_applied).
    """
    changes: list[str] = []
    text = block

    # 1. GIDesign row: rename ScreenID -> PrimaryScreenIDNew, append new attrs.
    #    Match the row tag of the GIDesign and rewrite ScreenID + suffix attrs.
    def gidesign_repl(m: re.Match) -> str:
        attrs = m.group(1)
        if "PrimaryScreenIDNew=" in attrs:
            return m.group(0)  # already modern format

        new_attrs = re.sub(
            r'ScreenID="([^"]+)"',
            r'PrimaryScreenIDNew="\1"',
            attrs,
            count=1,
        )
        # Move PrimaryScreenIDNew to between ExportTop and NewRecordCreationEnabled
        # to match IIG layout exactly. If the rename happened, reorder.
        m_psn = re.search(r'PrimaryScreenIDNew="[^"]+"', new_attrs)
        if m_psn:
            psn = m_psn.group(0)
            new_attrs = new_attrs.replace(" " + psn, "")
            new_attrs = new_attrs.replace(psn + " ", "")
            new_attrs = re.sub(
                r'(ExportTop="[^"]+")(\s+)(NewRecordCreationEnabled=)',
                rf'\1 {psn}\2\3',
                new_attrs,
                count=1,
            )
        # Append new GIDesign attrs at the end of attrs (before closing >).
        new_attrs = new_attrs.rstrip() + " " + NEW_GIDESIGN_ATTRS
        changes.append("GIDesign attrs: ScreenID->PrimaryScreenIDNew, +5 new attrs")
        return f"<row{new_attrs}>"

    text = re.sub(
        r"<row(\s+DesignID=\"[^\"]+\"\s+Name=\"" + re.escape(gi_name) + r"\"[^>]*?)>",
        gidesign_repl,
        text,
        count=1,
        flags=re.DOTALL,
    )

    # 2. GITable: add Type="0" to every <GITable ...> opening tag in the block
    #    that doesn't already have it.
    def gitable_repl(m: re.Match) -> str:
        if 'Type=' in m.group(0):
            return m.group(0)
        return m.group(0)[:-1] + ' Type="0">'
    new_text, ntables = re.subn(r'<GITable\s[^>]*>', gitable_repl, text)
    if ntables:
        text = new_text
        changes.append(f"GITable: +Type=\"0\" on {ntables} tables")

    # 3. SiteMap row: rewrite the row attrs.
    #    Find <row ...> inside <SiteMap linkname="toDesignById"> blocks.
    def sitemap_row_repl(m: re.Match) -> str:
        before, attrs, after = m.group(1), m.group(2), m.group(3)
        if 'SelectedUI=' in attrs:
            return m.group(0)  # already modern format

        # Strip Position, Expanded, IsFolder.
        new_attrs = re.sub(r'\s*Position="[^"]*"', "", attrs)
        new_attrs = re.sub(r'\s*Expanded="[^"]*"', "", new_attrs)
        new_attrs = re.sub(r'\s*IsFolder="[^"]*"', "", new_attrs)

        # Lowercase URL path: ~/GenericInquiry/GenericInquiry.aspx -> lowercase.
        new_attrs = re.sub(
            r'(Url=")~/GenericInquiry/GenericInquiry\.aspx',
            r'\1~/genericinquiry/genericinquiry.aspx',
            new_attrs,
        )

        # Set ParentID to zero GUID (link is for the GI itself, not workspace).
        new_attrs = re.sub(
            r'ParentID="[^"]+"',
            f'ParentID="{ZERO_GUID}"',
            new_attrs,
        )

        # Append SelectedUI="E" before the closing >.
        new_attrs = new_attrs.rstrip() + ' SelectedUI="E"'
        return f"{before}<row{new_attrs}>{after}"

    text, nsm = re.subn(
        r'(<SiteMap\s+linkname="toDesignById">\s*)<row(\s[^>]*?)>([\s\S]*?)',
        sitemap_row_repl,
        text,
    )
    if nsm:
        changes.append("SiteMap row: -Position/Expanded/IsFolder, +SelectedUI, ParentID=zero, lowercased URL")

    # 4. MUIScreen: nest <MUIPinnedScreen ...> if not already.
    def muiscreen_repl(m: re.Match) -> str:
        opening = m.group(0)
        # If already has nested MUIPinnedScreen via opening tag (not self-closing), skip.
        if '<MUIPinnedScreen' in opening:
            return opening
        # Convert self-closing <MUIScreen .../> into open-tag with nested
        # MUIPinnedScreen + closing </MUIScreen>.
        if opening.endswith("/>"):
            attrs = opening[len("<MUIScreen"):-2].rstrip()
            return (
                f"<MUIScreen{attrs}>\n"
                "                <MUIPinnedScreen IsPortal=\"0\" Username=\"\" IsPinned=\"1\" />\n"
                "              </MUIScreen>"
            )
        return opening
    text, nmu = re.subn(r'<MUIScreen\s[^>]*?/>', muiscreen_repl, text)
    if nmu:
        changes.append(f"MUIScreen: nested MUIPinnedScreen on {nmu}")

    return text, changes


def split_blocks(content: str) -> list[tuple[str, int, int]]:
    """Find each <GenericInquiryScreen>...</GenericInquiryScreen> block.

    Returns list of (block_text, start_offset, end_offset).
    """
    blocks = []
    open_tag = "<GenericInquiryScreen>"
    close_tag = "</GenericInquiryScreen>"
    pos = 0
    while True:
        start = content.find(open_tag, pos)
        if start < 0:
            break
        end = content.find(close_tag, start)
        if end < 0:
            print(f"ERROR: unmatched {open_tag} at offset {start}", file=sys.stderr)
            sys.exit(2)
        end += len(close_tag)
        blocks.append((content[start:end], start, end))
        pos = end
    return blocks


def gi_names_of_block(block: str) -> list[str]:
    """Pull all GI Names out of the GIDesign/row Name attributes.

    A single <GenericInquiryScreen> block may carry multiple GIs — the
    DRP_OpenPOLines + DRP_ItemWarehouseSettings block at line ~2525 has
    two GIDesign/row entries under one <GIDesign> parent.
    """
    return re.findall(r'<row\s+DesignID="[^"]+"\s+Name="([^"]+)"', block)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="Dry run — show changes, do not write file.")
    args = ap.parse_args()

    content = PROJECT_XML.read_text()
    blocks = split_blocks(content)
    print(f"Found {len(blocks)} <GenericInquiryScreen> blocks in {PROJECT_XML.relative_to(PROJECT_XML.parents[2])}")

    # Build the new content by walking blocks left-to-right.
    out = []
    cursor = 0
    converted = 0
    skipped = 0
    for block, start, end in blocks:
        out.append(content[cursor:start])
        gi_names = gi_names_of_block(block)
        if not gi_names:
            print(f"  WARN: block at offset {start} has no GIDesign/row Name — leaving unchanged")
            out.append(block)
        else:
            new_block = block
            block_changes: list[tuple[str, list[str]]] = []
            for gi_name in gi_names:
                if gi_name in SKIP:
                    print(f"  SKIP {gi_name} (in skip list)")
                    skipped += 1
                    continue
                new_block, changes = convert_block(new_block, gi_name)
                if changes:
                    block_changes.append((gi_name, changes))
                    converted += 1
                else:
                    print(f"  NOOP {gi_name} (no changes — likely already modern format)")
            for gi_name, changes in block_changes:
                print(f"  CONVERT {gi_name}:")
                for c in changes:
                    print(f"      - {c}")
            out.append(new_block)
        cursor = end
    out.append(content[cursor:])
    new_content = "".join(out)

    print(f"\nSummary: converted={converted}, skipped={skipped}, total_blocks={len(blocks)}")

    if args.check:
        print("(--check mode: not writing file)")
        return 0

    if new_content == content:
        print("No changes to write.")
        return 0

    PROJECT_XML.write_text(new_content)
    print(f"Wrote {PROJECT_XML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
