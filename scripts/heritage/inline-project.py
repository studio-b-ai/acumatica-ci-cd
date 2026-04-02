#!/usr/bin/env python3
"""
Inline external .cs file references into CDATA blocks in project.xml.

Acumatica's Customization API import only supports inline CDATA format.
The developer-friendly format uses Source="Code\DAC\*.cs" file references.
This script converts file references to inline CDATA for deployment.

Usage:
    python inline-project.py Customization/AesthetikWMS/project.xml
    python inline-project.py Customization/AesthetikWMS/project.xml --output dist/project.xml
"""

import re
import sys
from pathlib import Path


def inline_project(project_xml_path: str, output_path: str | None = None) -> str:
    """Read project.xml, inline external .cs files as CDATA, write result."""

    project_file = Path(project_xml_path)
    if not project_file.exists():
        print(f"ERROR: {project_xml_path} not found", file=sys.stderr)
        sys.exit(1)

    project_dir = project_file.parent
    xml = project_file.read_text(encoding="utf-8")

    # Strip XML comments (Acumatica import crashes on them)
    xml = re.sub(r"<!--.*?-->", "", xml, flags=re.DOTALL)

    # Find self-closing <Graph> elements with Source="*.cs"
    # Pattern: <Graph ClassName="X" Source="Code\Path\File.cs" IsNew="True" FileType="NewFile" />
    def replace_graph(match: re.Match) -> str:
        full_match = match.group(0)
        class_name = re.search(r'ClassName="([^"]+)"', full_match)
        source = re.search(r'Source="([^"]+\.cs)"', full_match)

        if not class_name or not source:
            return full_match  # Leave non-.cs references unchanged

        cn = class_name.group(1)
        src_path = source.group(1).replace("\\", "/")
        cs_file = project_dir / src_path

        if not cs_file.exists():
            print(f"  WARNING: {src_path} not found for {cn}", file=sys.stderr)
            return full_match

        code = cs_file.read_text(encoding="utf-8")
        print(f"  Inlined {cn} from {src_path} ({len(code)} chars)")

        # Build inline CDATA element
        return (
            f'    <Graph ClassName="{cn}" Source="#CDATA" IsNew="True" FileType="NewFile">\n'
            f"        <CDATA name=\"Source\"><![CDATA[{code}]]></CDATA>\n"
            f"    </Graph>"
        )

    # Match self-closing <Graph ... /> elements
    inlined_xml = re.sub(
        r"<Graph\s+[^>]*Source=\"[^\"]+\.cs\"[^>]*/\s*>",
        replace_graph,
        xml,
    )

    # Clean up blank lines
    inlined_xml = re.sub(r"\n\s*\n\s*\n", "\n\n", inlined_xml)

    # Write output
    out = Path(output_path) if output_path else project_file
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(inlined_xml, encoding="utf-8")

    # Count inlined vs remaining external
    inlined_count = inlined_xml.count('Source="#CDATA"')
    external_count = len(re.findall(r'Source="[^"]+\.cs"', inlined_xml))
    print(f"  Result: {inlined_count} inlined, {external_count} external remaining")

    return str(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: inline-project.py <project.xml> [--output <path>]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    print(f"Inlining external .cs files in {input_path}...")
    result = inline_project(input_path, output_path)
    print(f"Output: {result}")
