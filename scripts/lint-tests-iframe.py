#!/usr/bin/env python3
"""Lint: block `screen.page.locator(...)` anti-pattern in tests/ui/.

Acumatica renders all screen content inside `iframe[name='main']`.
`screen.page.locator(...)` only sees the top-level frame and returns
`count() == 0` for any element inside the iframe, even when the element
is visibly rendered. Use `screen.locator(...)` which is iframe-aware
(see `AcumaticaScreen.locator()` in tests/ui/acumatica_screen.py).

Incidents this guard prevents:
  - 2026-04-15 PCC: ~1 hour burned proposing a C# fix for what was a
    test-locator bug (CLAUDE.md rule #20).
  - 2026-04-17 container tracking: `skip_sandbox_gate=OVERRIDE` required
    because `test_container_tracking_button_exists` returned 0 despite
    the button being present on sandbox (fixed in PR #456).

Exception marker
----------------
Tests that legitimately target the top frame (sidebar links, post-logout
redirect pages, global nav) can add `# noqa: iframe-locator` at the end
of the offending line to document the intent. The lint skips any line
carrying that marker.

Uses Python AST so docstring/comment mentions of the pattern do not
trigger the guard — only actual Call nodes count.

Exit codes:
    0 — clean
    1 — one or more unannotated violations found
"""
from __future__ import annotations

import ast
import pathlib
import sys


def _find_violations(py_file: pathlib.Path) -> list[tuple[int, str]]:
    """Return [(line_no, source_line), ...] for un-noqa'd anti-pattern calls."""
    try:
        source = py_file.read_text()
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "locator"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "page"
        ):
            continue

        line_no = node.lineno
        if line_no < 1 or line_no > len(source_lines):
            continue
        line = source_lines[line_no - 1]
        if "noqa: iframe-locator" in line:
            continue
        hits.append((line_no, line))

    return hits


def main(argv: list[str]) -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    test_roots = [repo_root / "tests"]

    if len(argv) > 1:
        test_roots = [pathlib.Path(p).resolve() for p in argv[1:]]

    all_violations: list[tuple[pathlib.Path, int, str]] = []
    scanned = 0
    for root in test_roots:
        if not root.exists():
            continue
        for py_file in sorted(root.rglob("*.py")):
            if "__pycache__" in py_file.parts:
                continue
            scanned += 1
            for line_no, line in _find_violations(py_file):
                try:
                    rel = py_file.relative_to(repo_root)
                except ValueError:
                    rel = py_file
                all_violations.append((rel, line_no, line))

    if not all_violations:
        print(f"lint-tests-iframe: clean ({scanned} file(s) scanned)")
        return 0

    print("::error::iframe-locator anti-pattern detected in tests/ui/")
    print()
    print("Acumatica renders screen content inside iframe[name='main'].")
    print("  screen.locator(...)       ← iframe-aware   ✓")
    print("  screen.page.locator(...)  ← top-frame only ✗")
    print()
    print(f"{len(all_violations)} violation(s):")
    for rel, line_no, line in all_violations:
        print(f"  {rel}:{line_no}")
        print(f"    {line.strip()}")
    print()
    print("Fixes:")
    print("  1. Replace screen.page.locator(...) with screen.locator(...)")
    print("  2. For tests that legitimately target the top frame (sidebar,")
    print("     top-nav, post-logout page), add this comment on the same line:")
    print("       # noqa: iframe-locator — <reason>")
    print()
    print("Reference: CLAUDE.md rule #20 (2026-04-15 incident),")
    print("           PR #456 (2026-04-17 container tracking fix).")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
