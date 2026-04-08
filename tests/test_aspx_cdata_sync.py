"""
ASPX CDATA sync tripwire.

Asserts that every `<File AppRelativePath="*.aspx*" Source="#CDATA">` entry in
every `Customization/*/project.xml` has a CDATA body that matches the physical
file on disk.

## Why

Acumatica's CustomizationApi/Import ignores ASPX CDATA — only the physical
`.aspx` shipped in the ZIP overwrites the on-instance file. But the CDATA in
project.xml is still visible to code reviewers, the Acumatica UI, and any
project.xml parsers, so keeping it in sync is important for correctness of
tooling + reviewability.

This has bitten the repo twice:
- 2026-04-05: SB501000.aspx stuck on TabView.master across 3 deploys because
  the CDATA had FormDetail.master but the physical file had TabView.master.
- 2026-04-08: SB501000.aspx CDATA was stale Phase A/B content while the
  physical file had Phase E+F+G content; prod rendered fine but project.xml
  also carried literal Git merge conflict markers inside the CDATA block.

## Remediation

If this test fails, run:

    python3 scripts/sync-aspx-cdata.py

That script regenerates every ASPX CDATA body from its physical file. The
test then passes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CUSTOMIZATION_DIR = REPO_ROOT / "Customization"

# Mirrors the regex in scripts/sync-aspx-cdata.py. Kept in sync by convention;
# if either drifts, this test will surface the bug.
_ASPX_FILE_RE = re.compile(
    r'(<File AppRelativePath="[^"]*\.aspx[^"]*" Source="#CDATA">\s*'
    r'<CDATA name="Source"><!\[CDATA\[)'
    r'(.*?)'
    r'(\]\]></CDATA>\s*</File>)',
    re.DOTALL,
)
_PATH_ATTR_RE = re.compile(r'AppRelativePath="([^"]+)"')


@dataclass
class AspxEntry:
    project_xml: Path
    rel_path: str
    cdata_body: str

    @property
    def physical_path(self) -> Path:
        posix = self.rel_path.replace("\\", "/")
        return self.project_xml.parent / posix

    @property
    def display(self) -> str:
        return f"{self.project_xml.relative_to(REPO_ROOT)} → {self.rel_path}"


def _find_entries() -> list[AspxEntry]:
    entries: list[AspxEntry] = []
    if not CUSTOMIZATION_DIR.is_dir():
        return entries
    for project_xml in sorted(CUSTOMIZATION_DIR.glob("*/project.xml")):
        content = project_xml.read_text(encoding="utf-8")
        for match in _ASPX_FILE_RE.finditer(content):
            prefix = match.group(1)
            body = match.group(2)
            path_match = _PATH_ATTR_RE.search(prefix)
            if not path_match:
                continue
            entries.append(
                AspxEntry(
                    project_xml=project_xml,
                    rel_path=path_match.group(1),
                    cdata_body=body,
                )
            )
    return entries


_ENTRIES = _find_entries()


def test_customization_dir_exists():
    assert CUSTOMIZATION_DIR.is_dir(), (
        f"Customization/ directory missing at {CUSTOMIZATION_DIR} — cannot "
        "verify ASPX CDATA sync"
    )


def test_found_at_least_one_aspx_cdata_entry():
    """Sanity check that the regex is actually matching something.

    If this fires, either the regex broke or we migrated off CDATA entirely
    (in which case this entire test file can be deleted).
    """
    assert _ENTRIES, (
        "No ASPX CDATA entries found in any Customization/*/project.xml. "
        "Either the regex broke, or the project migrated to bare <File> "
        "entries — in which case delete this test file."
    )


@pytest.mark.parametrize(
    "entry",
    _ENTRIES,
    ids=lambda e: e.display,
)
def test_aspx_cdata_matches_physical(entry: AspxEntry):
    """For each CDATA entry, the body must equal the physical file verbatim."""
    assert entry.physical_path.is_file(), (
        f"{entry.display}: physical file not found at {entry.physical_path}. "
        "Either the physical file was deleted and the project.xml entry not "
        "cleaned up, or AppRelativePath is wrong."
    )
    physical_body = entry.physical_path.read_text(encoding="utf-8")
    if physical_body != entry.cdata_body:
        pytest.fail(
            f"{entry.display}: CDATA in project.xml does not match physical "
            f"file.\n"
            f"  physical: {len(physical_body)} chars, "
            f"{len(physical_body.splitlines())} lines\n"
            f"  CDATA:    {len(entry.cdata_body)} chars, "
            f"{len(entry.cdata_body.splitlines())} lines\n"
            f"\n"
            f"Fix by running: python3 scripts/sync-aspx-cdata.py\n"
        )
