#!/usr/bin/env python3
"""
inline-sources.py — Convert Acumatica project.xml external file references to inline CDATA.

Converts:
    <Graph ClassName="Foo" Source="Code\\DAC\\Foo.cs" IsNew="True" FileType="NewFile" />

To:
    <Graph ClassName="Foo" Source="#CDATA" IsNew="True" FileType="NewFile">
        <CDATA name="Source"><![CDATA[<file content>]]></CDATA>
    </Graph>

Usage:
    python3 inline-sources.py path/to/project.xml
"""

import re
import sys
import os


def inline_sources(project_xml_path: str) -> None:
    project_xml_path = os.path.abspath(project_xml_path)
    project_dir = os.path.dirname(project_xml_path)

    with open(project_xml_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match self-closing <Graph ... Source="something.cs" ... /> tags
    # Include leading whitespace for proper indentation detection
    pattern = re.compile(
        r'^([ \t]*)'                  # Leading whitespace (indent)
        r'<Graph\s+'                  # Opening <Graph + whitespace
        r'[^>]*?'                     # Attributes before Source
        r'Source="([^"]+\.cs)"'       # Source attribute with .cs path
        r'[^>]*?'                     # Attributes after Source
        r'\s*/>',                     # Self-closing />
        re.MULTILINE
    )

    def replace_graph(match: re.Match) -> str:
        full_match = match.group(0)
        indent = match.group(1)         # Leading whitespace
        source_path = match.group(2)    # Source file path

        # Convert backslash paths to OS paths
        os_path = source_path.replace("\\", os.sep)
        file_path = os.path.join(project_dir, os_path)

        if not os.path.isfile(file_path):
            print(f"  WARNING: File not found: {file_path} — skipping")
            return full_match

        with open(file_path, "r", encoding="utf-8") as f:
            cs_content = f.read()

        # Replace Source="..." with Source="#CDATA" in the original tag
        new_tag = full_match.replace(f'Source="{source_path}"', 'Source="#CDATA"')
        # Change self-closing /> to opening >
        new_tag = re.sub(r'\s*/>\s*$', '>', new_tag)

        child_indent = indent + "    "

        # Build the expanded element
        result = (
            f'{new_tag}\n'
            f'{child_indent}<CDATA name="Source"><![CDATA[{cs_content}]]></CDATA>\n'
            f'{indent}</Graph>'
        )
        return result

    new_content = pattern.sub(replace_graph, content)

    with open(project_xml_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    # Count conversions
    original_count = len(pattern.findall(content))
    print(f"Converted {original_count} Graph element(s) in {project_xml_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 inline-sources.py <project.xml>")
        sys.exit(1)

    for path in sys.argv[1:]:
        if not os.path.isfile(path):
            print(f"ERROR: File not found: {path}")
            sys.exit(1)
        inline_sources(path)
