"""
DAC/plugin schema drift detector — Python layer.

Parses src/StudioB.Containers/DACs/Usr*.cs for [PXDB*] attributes and
src/StudioB.Containers/Graphs/AesthetikContainersInstall.cs for EnsureTable
and EnsureColumn calls, then asserts every DAC field has matching plugin
coverage with exact type match.

Design: docs/plans/2026-04-08-dac-plugin-drift-design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DAC_DIR = REPO_ROOT / "src" / "StudioB.Containers" / "DACs"
PLUGIN_FILE = REPO_ROOT / "src" / "StudioB.Containers" / "Graphs" / "AesthetikContainersInstall.cs"


@dataclass(frozen=True)
class DacField:
    """A DAC field with a [PXDB*] attribute that requires plugin coverage."""
    table: str                # SQL table name (from [PXCacheName] or class name)
    file_path: str            # Source file path
    line_number: int          # Line where the field's region starts
    field_name: str           # SQL column name (e.g., "LCCodeShipping")
    attribute: str            # e.g., "PXDBString"
    args: str                 # e.g., "15, IsUnicode = true"
    is_key: bool
    has_default: bool
    default_value: Optional[str]
    expected_ddl: str         # computed SQL type (e.g., "nvarchar(15) NULL")


@dataclass(frozen=True)
class PluginColumn:
    """A column known to the install plugin via EnsureTable or EnsureColumn."""
    table: str
    column: str
    ddl: str                  # normalized type fragment
    source: str               # "EnsureColumn" or "EnsureTable"


@dataclass(frozen=True)
class DriftEntry:
    dac_field: DacField
    plugin_column: Optional[PluginColumn]
    reason: str               # "missing" | "type_mismatch"
    suggested_fix: str        # ready-to-paste EnsureColumn line


def find_drift(dac_fields: list[DacField],
               plugin_coverage: dict[str, dict[str, PluginColumn]]) -> list[DriftEntry]:
    """Compare DAC fields against plugin coverage. Returns drift entries."""
    drift: list[DriftEntry] = []
    for field in dac_fields:
        table_cols = plugin_coverage.get(field.table, {})
        plugin_col = table_cols.get(field.field_name)
        if plugin_col is None:
            drift.append(DriftEntry(
                dac_field=field,
                plugin_column=None,
                reason="missing",
                suggested_fix=f'EnsureColumn(conn, "{field.table}", "{field.field_name}", "{field.expected_ddl}");',
            ))
    return drift


# ─── Meta-tests ──────────────────────────────────────────────────────────

def test_detector_catches_missing_column():
    """DAC field exists but plugin has no EnsureColumn/EnsureTable coverage."""
    dac_field = DacField(
        table="UsrTestTable",
        file_path="fake.cs",
        line_number=10,
        field_name="TestField",
        attribute="PXDBString",
        args="20, IsUnicode = true",
        is_key=False,
        has_default=False,
        default_value=None,
        expected_ddl="nvarchar(20) NULL",
    )
    plugin_coverage: dict[str, dict[str, PluginColumn]] = {}
    drift = find_drift([dac_field], plugin_coverage)
    assert len(drift) == 1
    assert drift[0].reason == "missing"
    assert drift[0].dac_field.field_name == "TestField"
    assert 'EnsureColumn(conn, "UsrTestTable", "TestField", "nvarchar(20) NULL");' in drift[0].suggested_fix
