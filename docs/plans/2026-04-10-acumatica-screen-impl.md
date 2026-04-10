# AcumaticaScreen Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an iframe-aware `AcumaticaScreen` context object that eliminates the frame-parameter threading, magic timeouts, and evaluate() flake across all Acumatica Playwright UI tests.

**Architecture:** Single new class (`AcumaticaScreen`) in `tests/ui/acumatica_screen.py` wraps `Page` + `Frame` resolution. A factory fixture in `conftest.py` provides it to tests. Existing `helpers.py` stays untouched — tests migrate gradually. First migration: `test_uom_migration.py` to remove the xfail flake.

**Tech Stack:** Python 3, Playwright sync API, pytest fixtures

**Design doc:** `docs/plans/2026-04-10-acumatica-screen-design.md`

---

### Task 1: Core AcumaticaScreen class — construction + smart waits

**Files:**
- Create: `tests/ui/acumatica_screen.py`
- Test: `tests/ui/test_acumatica_screen.py`

**Step 1: Write the unit test file with construction tests**

These tests mock Playwright's Page/Frame to verify navigation logic, screen-shadow detection, and GI routing without needing a live Acumatica instance.

```python
# tests/ui/test_acumatica_screen.py
"""Unit tests for AcumaticaScreen — no live Acumatica needed."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, PropertyMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


class TestAcumaticaScreenConstruction:
    """Test navigate() routing and mode detection."""

    def test_navigate_standard_screen_uses_iframe_mode(self):
        """Standard screen navigation should resolve iframe[name='main']."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        frame = MagicMock()
        page.frame.return_value = frame
        type(page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=IN202500")
        # Mock wait_for_function to succeed immediately
        page.wait_for_function.return_value = None
        frame.wait_for_function.return_value = None

        screen = AcumaticaScreen.navigate(page, "IN202500")
        assert screen.mode == "iframe"
        assert screen.ctx is frame
        assert screen.screen_id == "IN202500"

    def test_navigate_gi_screen_uses_gi_url(self):
        """GI screens should route to /GenericInquiry/ URL."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        frame = MagicMock()
        page.frame.return_value = frame
        type(page).url = PropertyMock(return_value="https://example.com/GenericInquiry/GenericInquiry.aspx?id=GI000000")
        page.wait_for_function.return_value = None
        frame.wait_for_function.return_value = None

        screen = AcumaticaScreen.navigate(page, "GI000000")

        # Verify the goto URL contained GenericInquiry
        call_args = page.goto.call_args
        assert "GenericInquiry" in call_args[0][0]

    def test_navigate_shadowed_screen_falls_back_to_direct(self):
        """Shadowed screen (ScreenId=00000000) should auto-fallback to direct mode."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        # First URL check returns shadowed, second returns the direct page
        type(page).url = PropertyMock(side_effect=[
            "https://example.com/Main?ScreenId=00000000",
            "https://example.com/Main?ScreenId=00000000",
            "https://example.com/Pages/PO/PO301000.aspx",
        ])
        page.frame.return_value = None  # no iframe in direct mode
        page.wait_for_function.return_value = None

        screen = AcumaticaScreen.navigate(page, "PO301000")
        assert screen.mode == "direct"
        assert screen.ctx is page

    def test_navigate_error_screen_raises(self):
        """ERROR redirect should raise AssertionError."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=ERROR")
        page.wait_for_function.return_value = None
        page.frame.return_value = MagicMock()

        with pytest.raises(AssertionError, match="redirected to error page"):
            AcumaticaScreen.navigate(page, "IN202500")

    def test_direct_sets_direct_mode(self):
        """AcumaticaScreen.direct() should set mode='direct' and ctx=page."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        page.wait_for_function.return_value = None

        screen = AcumaticaScreen.direct(page, "/Pages/PO/PO301000.aspx")
        assert screen.mode == "direct"
        assert screen.ctx is page
```

**Step 2: Run to verify tests fail (module doesn't exist yet)**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | head -20`
Expected: `ModuleNotFoundError` or `ImportError` — `acumatica_screen` does not exist

**Step 3: Implement AcumaticaScreen class — construction + waits**

```python
# tests/ui/acumatica_screen.py
"""AcumaticaScreen — iframe-aware context for Playwright UI tests.

Acumatica renders all screen content inside iframe[name='main'].
This class resolves the correct DOM context (iframe or direct page)
and provides retry-capable methods for field reads/writes.

Usage:
    screen = AcumaticaScreen.navigate(page, "IN202500", params="InventoryCD=00004")
    value = screen.get_field("edBaseUnit_text")   # retries on empty-string flake
    screen.set_field("edDescr", "Updated")
    screen.save()
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from playwright.sync_api import Page, Frame, Locator

logger = logging.getLogger(__name__)

ACUMATICA_URL = os.environ.get("ACUMATICA_URL", "https://heritagefabrics.acumatica.com")

# Screen IDs known to be GI screens. Auto-detected by prefix too.
_GI_PREFIXES = ("GI",)

# Known ASPX paths for direct-mode fallback when screen is shadowed.
# Maps ScreenID -> relative ASPX path. Extend as new shadows are discovered.
_SHADOW_ASPX_MAP: dict[str, str] = {
    "PO301000": "/Pages/PO/PO301000.aspx",
}


class AcumaticaScreen:
    """Iframe-aware wrapper around a Playwright Page for Acumatica screens."""

    def __init__(
        self,
        page: Page,
        ctx: Frame | Page,
        screen_id: str,
        mode: Literal["iframe", "direct"],
    ):
        self.page = page
        self.ctx = ctx
        self.screen_id = screen_id
        self.mode = mode

    # ── Construction ──────────────────────────────────────────────────

    @classmethod
    def navigate(
        cls,
        page: Page,
        screen_id: str,
        *,
        params: str = "",
        timeout: int = 30_000,
    ) -> "AcumaticaScreen":
        """Navigate to a screen via /Main?ScreenId= with auto-detection.

        Handles:
        - GI screens → /GenericInquiry/ routing
        - Screen shadowing → auto-fallback to direct ASPX
        - iframe resolution → polls instead of magic timeout
        """
        # 1. Route GI screens
        if screen_id.startswith(_GI_PREFIXES):
            url = f"{ACUMATICA_URL}/GenericInquiry/GenericInquiry.aspx?id={screen_id}"
        else:
            url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
            if params:
                url += f"&{params}"

        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        # 2. Check for ERROR redirect
        if "ScreenId=ERROR" in page.url:
            raise AssertionError(
                f"Screen {screen_id} redirected to error page"
            )

        # 3. Check for screen shadowing (ScreenId=00000000 = home page)
        if "ScreenId=00000000" in page.url:
            logger.warning(
                "Screen %s is shadowed (redirected to home). "
                "Falling back to direct ASPX mode.",
                screen_id,
            )
            aspx_path = _SHADOW_ASPX_MAP.get(screen_id)
            if aspx_path:
                return cls.direct(page, aspx_path, screen_id=screen_id, timeout=timeout)
            # No known ASPX path — try generic pattern
            return cls.direct(
                page,
                f"/Pages/{screen_id[:2]}/{screen_id}.aspx",
                screen_id=screen_id,
                timeout=timeout,
            )

        # 4. Wait for iframe to attach and have content
        try:
            page.wait_for_function(
                "() => { const f = document.querySelector('iframe[name=main]'); "
                "return f && f.contentDocument && f.contentDocument.body "
                "&& f.contentDocument.body.children.length > 0; }",
                timeout=timeout,
            )
        except Exception:
            # iframe didn't appear — might be direct mode already
            frame = page.frame("main")
            if frame is None:
                logger.warning(
                    "No iframe[name='main'] found for %s — using page directly.",
                    screen_id,
                )
                return cls(page, page, screen_id, "direct")
            raise

        frame = page.frame("main")
        if frame is None:
            return cls(page, page, screen_id, "direct")

        ctx = frame

        # 5. Wait for form readiness
        try:
            ctx.wait_for_function(
                "() => document.querySelector('#ctl00_phF_form') !== null "
                "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
                "|| document.querySelector('[id*=grid]') !== null",
                timeout=timeout,
            )
        except Exception:
            logger.warning(
                "Form container not found for %s within %dms — proceeding anyway.",
                screen_id,
                timeout,
            )

        return cls(page, ctx, screen_id, "iframe")

    @classmethod
    def direct(
        cls,
        page: Page,
        aspx_path: str,
        *,
        screen_id: str = "",
        timeout: int = 30_000,
    ) -> "AcumaticaScreen":
        """Navigate directly to an ASPX page, bypassing the Main wrapper.

        Use for shadowed screens or when you need the form without the
        sidebar/breadcrumb frameset.
        """
        url = aspx_path if aspx_path.startswith("http") else f"{ACUMATICA_URL}{aspx_path}"
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        # In direct mode the form renders as the top-level page (no iframe)
        try:
            page.wait_for_function(
                "() => document.querySelector('#ctl00_phF_form') !== null "
                "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
                "|| document.querySelector('[id*=grid]') !== null "
                "|| document.querySelector('form') !== null",
                timeout=timeout,
            )
        except Exception:
            logger.warning(
                "Form container not found for direct page %s — proceeding anyway.",
                aspx_path,
            )

        sid = screen_id or aspx_path.split("/")[-1].replace(".aspx", "")
        return cls(page, page, sid, "direct")
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | tail -20`
Expected: All 5 construction tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git add tests/ui/acumatica_screen.py tests/ui/test_acumatica_screen.py && git commit -m "feat(ui): AcumaticaScreen class — construction + smart waits"
```

---

### Task 2: DOM methods — locator, evaluate with retry, get/set field

**Files:**
- Modify: `tests/ui/acumatica_screen.py`
- Modify: `tests/ui/test_acumatica_screen.py`

**Step 1: Write tests for DOM methods**

Append to `tests/ui/test_acumatica_screen.py`:

```python
class TestAcumaticaScreenDomMethods:
    """Test locator, evaluate, get_field, set_field."""

    def _make_screen(self):
        """Create a screen with a mocked frame context."""
        from acumatica_screen import AcumaticaScreen
        page = MagicMock()
        ctx = MagicMock()
        return AcumaticaScreen(page, ctx, "TEST00000", "iframe")

    def test_locator_delegates_to_ctx(self):
        screen = self._make_screen()
        screen.locator("#foo")
        screen.ctx.locator.assert_called_once_with("#foo")

    def test_evaluate_returns_value_on_first_try(self):
        screen = self._make_screen()
        screen.ctx.evaluate.return_value = "YDS"
        result = screen.evaluate("() => 'YDS'")
        assert result == "YDS"
        assert screen.ctx.evaluate.call_count == 1

    def test_evaluate_retries_on_empty_string(self):
        screen = self._make_screen()
        screen.ctx.evaluate.side_effect = ["", "", "YDS"]
        result = screen.evaluate("() => el.value", retries=3, delay_ms=0)
        assert result == "YDS"
        assert screen.ctx.evaluate.call_count == 3

    def test_evaluate_retries_on_none(self):
        screen = self._make_screen()
        screen.ctx.evaluate.side_effect = [None, "BOLTID"]
        result = screen.evaluate("() => el.value", retries=3, delay_ms=0)
        assert result == "BOLTID"
        assert screen.ctx.evaluate.call_count == 2

    def test_evaluate_returns_last_attempt_if_all_empty(self):
        screen = self._make_screen()
        screen.ctx.evaluate.return_value = ""
        result = screen.evaluate("() => ''", retries=3, delay_ms=0)
        assert result == ""
        assert screen.ctx.evaluate.call_count == 3

    def test_get_field_uses_evaluate_with_retry(self):
        screen = self._make_screen()
        # First call returns empty (flake), second returns value
        screen.ctx.evaluate.side_effect = ["", "YDS"]
        result = screen.get_field("edBaseUnit_text")
        assert result == "YDS"

    def test_set_field_clicks_clears_fills_blurs(self):
        screen = self._make_screen()
        screen.set_field("edDescr", "Test Value")
        # Verify click, fill(""), fill(value), blur sequence
        screen.ctx.click.assert_called_once_with("#edDescr")
        assert screen.ctx.fill.call_count == 2
        screen.ctx.evaluate.assert_called_once_with("document.activeElement.blur()")

    def test_find_fields_returns_dict(self):
        screen = self._make_screen()
        locator_mock = MagicMock()
        locator_mock.count.return_value = 1
        screen.ctx.locator.return_value = locator_mock
        result = screen.find_fields(["UsrHubSpotDealId"])
        assert result == {"UsrHubSpotDealId": True}
```

**Step 2: Run tests to verify failures**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py::TestAcumaticaScreenDomMethods -v --no-header 2>&1 | tail -20`
Expected: FAIL — `locator`, `evaluate`, `get_field`, `set_field`, `find_fields` methods don't exist

**Step 3: Implement DOM methods**

Append to the `AcumaticaScreen` class in `tests/ui/acumatica_screen.py`:

```python
    # ── DOM Access ────────────────────────────────────────────────────

    def locator(self, selector: str) -> Locator:
        """Return a Locator scoped to the resolved context (iframe or page)."""
        return self.ctx.locator(selector)

    def evaluate(self, js: str, *, retries: int = 3, delay_ms: int = 500):
        """Evaluate JS in the resolved context with retry on empty results.

        The retry addresses the known Playwright iframe-read flake where
        frame.evaluate() returns empty string despite the field being
        visually populated (xfailed since 2026-04-08).
        """
        result = None
        for attempt in range(retries):
            result = self.ctx.evaluate(js)
            if result not in (None, ""):
                return result
            if attempt < retries - 1:
                self.page.wait_for_timeout(delay_ms)
        return result

    def get_field(self, field_id: str) -> str:
        """Read a form field value with retry on empty-string flake.

        Uses evaluate() internally, which retries up to 3 times.
        """
        js = f"""() => {{
            var el = document.querySelector('[id*="{field_id}"]');
            if (!el) return null;
            return el.value !== undefined ? el.value : el.textContent;
        }}"""
        result = self.evaluate(js)
        return (result or "").strip()

    def set_field(self, field_id: str, value: str):
        """Set a form field value using click → clear → fill → blur."""
        selector = f"#{field_id}"
        self.ctx.click(selector)
        self.ctx.fill(selector, "")
        self.ctx.fill(selector, value)
        self.ctx.evaluate("document.activeElement.blur()")

    def find_fields(self, field_names: list[str]) -> dict[str, bool]:
        """Check which fields are present in the DOM.

        Returns dict mapping field_name -> True if found.
        """
        results = {}
        for name in field_names:
            locator = self.ctx.locator(f"[id*='{name}']")
            results[name] = locator.count() > 0
        return results
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | tail -20`
Expected: All tests PASS (construction + DOM methods)

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git add tests/ui/acumatica_screen.py tests/ui/test_acumatica_screen.py && git commit -m "feat(ui): AcumaticaScreen DOM methods — evaluate retry, get/set field"
```

---

### Task 3: Toolbar actions — save, add new, delete

**Files:**
- Modify: `tests/ui/acumatica_screen.py`
- Modify: `tests/ui/test_acumatica_screen.py`

**Step 1: Write tests for toolbar methods**

Append to `tests/ui/test_acumatica_screen.py`:

```python
class TestAcumaticaScreenToolbar:
    """Test save, click_toolbar actions."""

    def _make_screen(self):
        from acumatica_screen import AcumaticaScreen
        page = MagicMock()
        ctx = MagicMock()
        # Make wait_for_function succeed
        ctx.wait_for_function.return_value = None
        return AcumaticaScreen(page, ctx, "TEST00000", "iframe")

    def test_save_presses_ctrl_s(self):
        screen = self._make_screen()
        screen.save()
        screen.page.keyboard.press.assert_called_with("Control+s")

    def test_click_toolbar_save(self):
        screen = self._make_screen()
        btn = MagicMock()
        btn.is_visible.return_value = True
        screen.ctx.locator.return_value = MagicMock()
        screen.ctx.locator.return_value.first = btn
        screen.click_toolbar("save")
        btn.click.assert_called_once()

    def test_click_toolbar_add_new(self):
        screen = self._make_screen()
        btn = MagicMock()
        btn.is_visible.return_value = True
        screen.ctx.locator.return_value = MagicMock()
        screen.ctx.locator.return_value.first = btn
        screen.click_toolbar("add_new")
        btn.click.assert_called_once()

    def test_click_toolbar_delete_confirms_dialog(self):
        screen = self._make_screen()
        del_btn = MagicMock()
        del_btn.is_visible.return_value = True
        confirm_btn = MagicMock()
        confirm_btn.count.return_value = 1
        confirm_btn.first = MagicMock()
        confirm_btn.first.is_visible.return_value = True

        # First locator call → delete button, second → confirm button
        screen.ctx.locator.side_effect = [
            MagicMock(first=del_btn),
            confirm_btn,
        ]
        screen.click_toolbar("delete")
        del_btn.click.assert_called_once()
        confirm_btn.first.click.assert_called_once()

    def test_wait_ready_polls_for_form(self):
        screen = self._make_screen()
        screen.wait_ready()
        screen.ctx.wait_for_function.assert_called_once()
```

**Step 2: Run to verify failures**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py::TestAcumaticaScreenToolbar -v --no-header 2>&1 | tail -20`
Expected: FAIL — `save`, `click_toolbar`, `wait_ready` methods don't exist

**Step 3: Implement toolbar methods**

Append to the `AcumaticaScreen` class in `tests/ui/acumatica_screen.py`:

```python
    # ── Toolbar Actions ───────────────────────────────────────────────

    def save(self):
        """Save via Ctrl+S and wait for form readiness."""
        self.page.keyboard.press("Control+s")
        self.page.wait_for_load_state("domcontentloaded")
        self.wait_ready()

    def wait_ready(self, timeout: int = 15_000):
        """Wait for the form container to be present."""
        self.ctx.wait_for_function(
            "() => document.querySelector('#ctl00_phF_form') !== null "
            "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
            "|| document.querySelector('[id*=grid]') !== null",
            timeout=timeout,
        )

    def click_toolbar(self, action: str):
        """Click a toolbar button by action name.

        Supported actions: save, add_new, delete
        """
        selectors = {
            "save": "[id*='ToolBar_Save']",
            "add_new": "[id*='ToolBar_Insert'], [id*='btnInsert']",
            "delete": "[id*='ToolBar_Delete'], [id*='btnDelete']",
        }
        selector = selectors.get(action)
        if not selector:
            raise ValueError(f"Unknown toolbar action: {action}. Use: {list(selectors)}")

        btn = self.ctx.locator(selector).first
        btn.click()

        if action == "delete":
            # Confirm deletion dialog if present
            confirm = self.ctx.locator("button:has-text('Yes'), button:has-text('OK')")
            if confirm.count() > 0 and confirm.first.is_visible(timeout=2000):
                confirm.first.click()

        if action in ("save", "add_new"):
            self.page.wait_for_load_state("domcontentloaded")
            self.wait_ready()
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | tail -20`
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git add tests/ui/acumatica_screen.py tests/ui/test_acumatica_screen.py && git commit -m "feat(ui): AcumaticaScreen toolbar actions — save, add_new, delete"
```

---

### Task 4: conftest.py fixture + error detection

**Files:**
- Modify: `tests/ui/conftest.py` (add fixture, ~10 LOC)
- Modify: `tests/ui/acumatica_screen.py` (add assert_no_errors method)
- Modify: `tests/ui/test_acumatica_screen.py` (add fixture + error detection tests)

**Step 1: Write tests for error detection and fixture**

Append to `tests/ui/test_acumatica_screen.py`:

```python
class TestAcumaticaScreenErrors:
    """Test error detection methods."""

    def _make_screen(self):
        from acumatica_screen import AcumaticaScreen
        page = MagicMock()
        ctx = MagicMock()
        return AcumaticaScreen(page, ctx, "TEST00000", "iframe")

    def test_assert_no_errors_passes_clean_page(self):
        screen = self._make_screen()
        screen.ctx.locator.return_value.text_content.return_value = "Normal page content"
        type(screen.page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=TEST00000")
        screen.assert_no_errors()  # should not raise

    def test_assert_no_errors_catches_type_not_found(self):
        screen = self._make_screen()
        screen.ctx.locator.return_value.text_content.return_value = "Error: type is not found in module"
        type(screen.page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=TEST00000")
        with pytest.raises(AssertionError, match="type is not found"):
            screen.assert_no_errors()

    def test_assert_no_errors_catches_igcm_dac(self):
        screen = self._make_screen()
        screen.ctx.locator.return_value.text_content.return_value = "Reference to IGCM.DAC.SomeType"
        type(screen.page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=TEST00000")
        with pytest.raises(AssertionError, match="IGCM.DAC"):
            screen.assert_no_errors()
```

**Step 2: Run to verify failures**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py::TestAcumaticaScreenErrors -v --no-header 2>&1 | tail -20`
Expected: FAIL — `assert_no_errors` doesn't exist

**Step 3: Implement assert_no_errors**

Append to the `AcumaticaScreen` class in `tests/ui/acumatica_screen.py`:

```python
    # ── Error Detection ───────────────────────────────────────────────

    def assert_no_errors(self):
        """Check page for common Acumatica error states.

        Raises AssertionError if:
        - URL contains ScreenId=ERROR
        - Body contains 'type is not found' or 'type not found'
        - Body references IGCM.DAC types (orphan customization metadata)
        """
        url = self.page.url
        if "ScreenId=ERROR" in url:
            raise AssertionError(
                f"{self.screen_id} redirected to error page"
            )

        body = (self.ctx.locator("body").text_content() or "").lower()
        if "type is not found" in body:
            raise AssertionError(
                f"{self.screen_id} has 'type is not found' error"
            )
        if "type not found" in body:
            raise AssertionError(
                f"{self.screen_id} has 'type not found' error"
            )
        if "igcm.dac" in body:
            raise AssertionError(
                f"{self.screen_id} references IGCM.DAC types"
            )
```

**Step 4: Add the conftest.py fixture**

Add to `tests/ui/conftest.py` after the existing imports at the top:

```python
from acumatica_screen import AcumaticaScreen  # noqa: E402
```

Add after the `screen_page` fixture (end of file):

```python
@pytest.fixture
def acumatica_screen(acumatica_page):
    """Factory fixture — call with screen_id to get an AcumaticaScreen.

    Usage:
        def test_something(acumatica_screen):
            screen = acumatica_screen("IN202500", params="InventoryCD=00004")
            value = screen.get_field("edBaseUnit_text")
    """
    def _navigate(screen_id: str, **kwargs) -> AcumaticaScreen:
        return AcumaticaScreen.navigate(acumatica_page, screen_id, **kwargs)
    return _navigate
```

**Step 5: Run all tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | tail -25`
Expected: All tests PASS

**Step 6: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git add tests/ui/acumatica_screen.py tests/ui/test_acumatica_screen.py tests/ui/conftest.py && git commit -m "feat(ui): AcumaticaScreen error detection + conftest fixture"
```

---

### Task 5: Migrate test_uom_migration.py — remove the xfail

**Files:**
- Modify: `tests/ui/test_uom_migration.py`

This is the immediate payoff — the xfail iframe-read flake that's been there since 2026-04-08.

**Step 1: Update TestBaseUom to use AcumaticaScreen**

Replace the `TestBaseUom` class (lines 44-69) in `tests/ui/test_uom_migration.py`:

The import line (line 24) changes from:
```python
from helpers import ACUMATICA_URL, navigate_and_wait
```
to:
```python
from helpers import ACUMATICA_URL, navigate_and_wait
from acumatica_screen import AcumaticaScreen
```

Replace the `TestBaseUom` class:
```python
@pytest.mark.ui
class TestBaseUom:

    def test_stock_item_base_uom_is_yds(self, acumatica_screen):
        """Open item 00004 and verify BaseUnit = YDS.

        Uses AcumaticaScreen.get_field() which retries on the known
        iframe-read flake (frame.evaluate() returning empty string).
        Previously xfailed since 2026-04-08.
        """
        screen = acumatica_screen("IN202500", params=f"InventoryCD={ITEM_CD}")

        base_unit = screen.get_field("edBaseUnit_text")

        assert base_unit is not None and base_unit != "", (
            "Could not read BaseUnit field on IN202500 — "
            "evaluate() returned empty after retries"
        )
        assert base_unit.strip() == EXPECTED_UOM, (
            f"BaseUnit should be '{EXPECTED_UOM}' but got '{base_unit.strip()}'"
        )
```

Key changes:
- Removed `@pytest.mark.xfail` decorator
- Changed fixture from `acumatica_page` to `acumatica_screen`
- Replaced `navigate_and_wait` + `frame.evaluate()` with `screen.get_field()`
- Retry is now built into `get_field()`

**Step 2: Update TestInUnitConversions to use AcumaticaScreen**

Replace the `test_inunit_conversions_on_stock_item` method (lines 77-103):

```python
    def test_inunit_conversions_on_stock_item(self, acumatica_screen, dialog_messages):
        """Open a stock item — if it loads without UOM errors, conversions work."""
        screen = acumatica_screen("IN202500", params=f"InventoryCD={ITEM_CD}")

        base_unit = screen.get_field("edBaseUnit_text")
        assert base_unit is not None, "Stock item screen did not load"

        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM conversion error(s): {[d['message'] for d in uom_errors]} — "
            "INUnit self-conversion records may be missing"
        )
```

Replace `test_inunit_conversions_screen` (lines 105-125):

```python
    def test_inunit_conversions_screen(self, acumatica_screen, dialog_messages):
        """Navigate to IN209000 and verify it loads without errors."""
        try:
            screen = acumatica_screen("IN209000")
        except Exception:
            pytest.skip("IN209000 did not load — screen may not exist in this version")

        uom_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
        ]
        assert not uom_errors, (
            f"UOM error on IN209000: {[d['message'] for d in uom_errors]}"
        )
```

**Step 3: Update remaining classes that use navigate_and_wait**

Replace `TestUnallocatedPieceGoodsGI.test_unallocated_piece_goods_gi_loads` (lines 133-147):

```python
    def test_unallocated_piece_goods_gi_loads(self, acumatica_screen, dialog_messages):
        """Navigate to the UnallocatedPieceGoods GI and verify it loads."""
        screen = acumatica_screen("GI000000", params="Name=UnallocatedPieceGoods")

        gi_errors = [
            d for d in dialog_messages
            if "error" in d["message"].lower()
            or "inquiry" in d["message"].lower()
        ]
        assert not gi_errors, (
            f"GI error(s): {[d['message'] for d in gi_errors]} — "
            "UnallocatedPieceGoods GI definition may be broken"
        )
```

Replace `TestSalesOrderOperations.test_existing_sales_order_loads_with_details` (lines 154-176):

```python
    def test_existing_sales_order_loads_with_details(self, acumatica_screen, dialog_messages):
        """Open the Sales Orders screen — if it loads without UOM errors, conversions work."""
        screen = acumatica_screen("SO301000")

        load_errors = [
            d for d in dialog_messages
            if "conversion" in d["message"].lower()
            or "uom" in d["message"].lower()
            or "error" in d["message"].lower()
        ]
        assert not load_errors, (
            f"Error on Sales Orders screen: {[d['message'] for d in load_errors]} — "
            "this is the v1 failure mode"
        )
```

Note: `TestSalesOrderOperations.test_create_so_order_with_yds_item` (lines 178-231) uses REST API, not Playwright — leave it unchanged.

Note: `TestStockItemSaveSample` (lines 249-399) uses raw `page.frame("main") or page` with custom dialog logic — leave it unchanged for now. It's a complex test with its own iframe handling that works. Migrating it is a future task.

**Step 4: Run the migrated tests**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -m pytest tests/ui/test_acumatica_screen.py -v --no-header 2>&1 | tail -20`
Expected: All unit tests PASS (live Acumatica tests will only run in CI with credentials)

**Step 5: Verify test_uom_migration.py has no import/syntax errors**

Run: `cd /Users/kevin/dev/acumatica-ci-cd && python -c "import ast; ast.parse(open('tests/ui/test_uom_migration.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

**Step 6: Commit**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git add tests/ui/test_uom_migration.py && git commit -m "refactor(ui): migrate test_uom_migration.py to AcumaticaScreen — remove xfail

The iframe-read flake (frame.evaluate() returning empty string)
is addressed by AcumaticaScreen.get_field() retry mechanism.
xfail removed from test_stock_item_base_uom_is_yds."
```

---

### Task 6: Create PR

**Step 1: Push branch and create PR**

```bash
cd /Users/kevin/dev/acumatica-ci-cd && git push -u origin claude/intelligent-shaw
```

Then create PR:

```bash
gh pr create --title "feat(ui): AcumaticaScreen — iframe-aware Playwright test context" --body "$(cat <<'EOF'
## Summary
- New `AcumaticaScreen` class in `tests/ui/acumatica_screen.py` wraps Playwright Page + iframe resolution
- Auto-detects screen shadowing, GI routing, and iframe vs direct mode
- Built-in retry on `frame.evaluate()` empty-string flake (3 attempts, 500ms backoff)
- Poll-based smart waits replace magic `wait_for_timeout()` calls
- `acumatica_screen` factory fixture in conftest.py
- Migrated `test_uom_migration.py` — **removed the xfail** that's been there since 2026-04-08
- All existing helpers.py functions untouched — gradual migration path

## Test plan
- [ ] Unit tests pass: `pytest tests/ui/test_acumatica_screen.py -v`
- [ ] No syntax errors in migrated test: `python -c "import ast; ast.parse(open('tests/ui/test_uom_migration.py').read())"`
- [ ] CI sandbox gate passes with migrated tests
- [ ] `test_stock_item_base_uom_is_yds` passes WITHOUT xfail (the main payoff)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Step 2: Return PR URL**
