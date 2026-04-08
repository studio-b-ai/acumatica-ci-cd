#!/usr/bin/env python3
"""
sync-aspx-cdata.py — Regenerate ASPX CDATA blocks in project.xml from physical files.

## Why

Every `Customization/*/project.xml` can contain `<File AppRelativePath="Pages\...\Foo.aspx"
Source="#CDATA">` entries with the ASPX source inlined as `<![CDATA[...]]>`. Developers
edit the physical `.aspx` file on disk with normal editor support, but the CDATA body
in project.xml has to be manually kept in sync. Drift is silent, easy to introduce, and
hard to review.

Acumatica's customization import API (`isReplaceIfExists=true`) is documented in the
studiob-knowledge base to *ignore* the CDATA body for ASPX files — only the physical
.aspx shipped in the ZIP overwrites the on-instance copy. So the CDATA is not
load-bearing for a working deploy, but:

- Diff readers and reviewers see the CDATA in PRs and assume it's the deployed content.
- Tools that parse project.xml (Acumatica's UI, manual imports, this repo's validators)
  will misreport state when the CDATA is wrong.
- Stale CDATA has bitten this repo twice already (SB501000 TabView.master incident on
  2026-04-05; Phase A/B drift discovered on 2026-04-08).

This script is the source-of-truth sync. Run it after editing any .aspx or .aspx.cs
file in a Customization project. The companion pytest in `tests/test_aspx_cdata_sync.py`
verifies the invariant in CI.

## Usage

    # Default: sync all project.xml under Customization/
    python3 scripts/sync-aspx-cdata.py

    # Explicit targets
    python3 scripts/sync-aspx-cdata.py Customization/AesthetikContainers/project.xml

    # Check-only (exit non-zero if drift found, no writes)
    python3 scripts/sync-aspx-cdata.py --check

## Scope

Only handles `<File AppRelativePath="...\*.aspx*" Source="#CDATA">` entries. Does not
touch `.cs` Graph/DAC CDATA (that's `scripts/heritage/inline-sources.py`), does not
touch bare `<File>` entries without CDATA, does not touch non-ASPX files.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# Matches the full <File AppRelativePath="...\Foo.aspx[.cs]" Source="#CDATA">
#   <CDATA name="Source"><![CDATA[<body>]]></CDATA>
# </File>
# block. Captures the relative path (group 1) and the CDATA body (group 2).
# Greedy-then-non-greedy to handle nested square brackets in ASPX as long as no
# literal `]]>` appears in the source (ASPX forbids `]]>` inside ASP.NET pages).
_ASPX_FILE_RE = re.compile(
    r'(<File AppRelativePath="[^"]*\.aspx[^"]*" Source="#CDATA">\s*'
    r'<CDATA name="Source"><!\[CDATA\[)'
    r'(.*?)'
    r'(\]\]></CDATA>\s*</File>)',
    re.DOTALL,
)

_PATH_ATTR_RE = re.compile(r'AppRelativePath="([^"]+)"')


@dataclass
class SyncResult:
    project_xml: Path
    entries_found: int
    entries_synced: int
    drift_paths: list[str]

    @property
    def had_drift(self) -> bool:
        return len(self.drift_paths) > 0


def _resolve_physical(project_xml: Path, rel_path: str) -> Path:
    """Translate a Windows-style AppRelativePath to a real path next to project.xml."""
    posix_rel = rel_path.replace("\\", "/")
    return project_xml.parent / posix_rel


def sync_project_xml(project_xml: Path, *, check_only: bool) -> SyncResult:
    """Scan one project.xml, replace each ASPX CDATA body with the physical file.

    When `check_only=True` the file is not rewritten; instead the result lists every
    drifted AppRelativePath so the caller can exit non-zero.
    """
    content = project_xml.read_text(encoding="utf-8")
    found = 0
    drift_paths: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        nonlocal found
        found += 1
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)
        path_match = _PATH_ATTR_RE.search(prefix)
        if not path_match:  # pragma: no cover — structurally impossible
            return match.group(0)
        rel = path_match.group(1)
        phys = _resolve_physical(project_xml, rel)
        if not phys.is_file():
            print(
                f"  WARNING: physical file not found for {rel} "
                f"(looked at {phys}); leaving CDATA as-is",
                file=sys.stderr,
            )
            return match.group(0)
        phys_body = phys.read_text(encoding="utf-8")
        if phys_body == body:
            return match.group(0)
        drift_paths.append(rel)
        return f"{prefix}{phys_body}{suffix}"

    new_content = _ASPX_FILE_RE.sub(_replace, content)

    if not check_only and new_content != content:
        project_xml.write_text(new_content, encoding="utf-8")

    return SyncResult(
        project_xml=project_xml,
        entries_found=found,
        entries_synced=0 if check_only else len(drift_paths),
        drift_paths=drift_paths,
    )


def find_default_project_xmls(repo_root: Path) -> list[Path]:
    """Return every Customization/*/project.xml we can find."""
    return sorted((repo_root / "Customization").glob("*/project.xml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "project_xml",
        nargs="*",
        type=Path,
        help="One or more project.xml files. Defaults to Customization/*/project.xml.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report drift but do not modify files. Exits 1 if any drift found.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    targets = args.project_xml or find_default_project_xmls(repo_root)
    if not targets:
        print("No project.xml files found.", file=sys.stderr)
        return 1

    any_drift = False
    for target in targets:
        if not target.is_file():
            print(f"  SKIP: {target} (not found)", file=sys.stderr)
            continue
        result = sync_project_xml(target, check_only=args.check)
        rel = target.relative_to(repo_root) if target.is_absolute() else target
        if result.had_drift:
            any_drift = True
            verb = "would sync" if args.check else "synced"
            print(f"  {rel}: {result.entries_found} ASPX entries, {verb} {len(result.drift_paths)}:")
            for p in result.drift_paths:
                print(f"    - {p}")
        else:
            print(f"  {rel}: {result.entries_found} ASPX entries, all in sync")

    if args.check and any_drift:
        print(
            "\nDrift detected. Run `python3 scripts/sync-aspx-cdata.py` to fix.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
