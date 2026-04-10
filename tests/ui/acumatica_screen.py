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

_GI_PREFIXES = ("GI",)

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

    @classmethod
    def navigate(
        cls,
        page: Page,
        screen_id: str,
        *,
        params: str = "",
        timeout: int = 30_000,
    ) -> "AcumaticaScreen":
        """Navigate to a screen via /Main?ScreenId= with auto-detection."""
        if screen_id.startswith(_GI_PREFIXES):
            url = f"{ACUMATICA_URL}/GenericInquiry/GenericInquiry.aspx?id={screen_id}"
        else:
            url = f"{ACUMATICA_URL}/Main?ScreenId={screen_id}"
            if params:
                url += f"&{params}"

        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        if "ScreenId=ERROR" in page.url:
            raise AssertionError(f"Screen {screen_id} redirected to error page")

        if "ScreenId=00000000" in page.url:
            logger.warning("Screen %s is shadowed. Falling back to direct ASPX.", screen_id)
            aspx_path = _SHADOW_ASPX_MAP.get(screen_id)
            if aspx_path:
                return cls.direct(page, aspx_path, screen_id=screen_id, timeout=timeout)
            return cls.direct(page, f"/Pages/{screen_id[:2]}/{screen_id}.aspx", screen_id=screen_id, timeout=timeout)

        try:
            page.wait_for_function(
                "() => { const f = document.querySelector('iframe[name=main]'); "
                "return f && f.contentDocument && f.contentDocument.body "
                "&& f.contentDocument.body.children.length > 0; }",
                timeout=timeout,
            )
        except Exception:
            frame = page.frame("main")
            if frame is None:
                logger.warning("No iframe[name='main'] found for %s — using page directly.", screen_id)
                return cls(page, page, screen_id, "direct")
            raise

        frame = page.frame("main")
        if frame is None:
            return cls(page, page, screen_id, "direct")

        try:
            frame.wait_for_function(
                "() => document.querySelector('#ctl00_phF_form') !== null "
                "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
                "|| document.querySelector('[id*=grid]') !== null",
                timeout=timeout,
            )
        except Exception:
            logger.warning("Form container not found for %s within %dms — proceeding.", screen_id, timeout)

        return cls(page, frame, screen_id, "iframe")

    @classmethod
    def direct(
        cls,
        page: Page,
        aspx_path: str,
        *,
        screen_id: str = "",
        timeout: int = 30_000,
    ) -> "AcumaticaScreen":
        """Navigate directly to an ASPX page, bypassing the Main wrapper."""
        url = aspx_path if aspx_path.startswith("http") else f"{ACUMATICA_URL}{aspx_path}"
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        try:
            page.wait_for_function(
                "() => document.querySelector('#ctl00_phF_form') !== null "
                "|| document.querySelector('#ctl00_phF_frmFilter') !== null "
                "|| document.querySelector('[id*=grid]') !== null "
                "|| document.querySelector('form') !== null",
                timeout=timeout,
            )
        except Exception:
            logger.warning("Form container not found for direct page %s — proceeding.", aspx_path)

        sid = screen_id or aspx_path.split("/")[-1].replace(".aspx", "")
        return cls(page, page, sid, "direct")

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
        """Read a form field value with retry on empty-string flake."""
        js = f"""() => {{
            var el = document.querySelector('[id*="{field_id}"]');
            if (!el) return null;
            return el.value !== undefined ? el.value : el.textContent;
        }}"""
        result = self.evaluate(js)
        return (result or "").strip()

    def set_field(self, field_id: str, value: str):
        """Set a form field value using click -> clear -> fill -> blur."""
        selector = f"#{field_id}"
        self.ctx.click(selector)
        self.ctx.fill(selector, "")
        self.ctx.fill(selector, value)
        self.ctx.evaluate("document.activeElement.blur()")

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
            confirm = self.ctx.locator("button:has-text('Yes'), button:has-text('OK')")
            if confirm.count() > 0 and confirm.first.is_visible(timeout=2000):
                confirm.first.click()

        if action in ("save", "add_new"):
            self.page.wait_for_load_state("domcontentloaded")
            self.wait_ready()

    # ── Error Detection ───────────────────────────────────────────────

    def assert_no_errors(self):
        """Check page for common Acumatica error states."""
        url = self.page.url
        if "ScreenId=ERROR" in url:
            raise AssertionError(f"{self.screen_id} redirected to error page")

        body = (self.ctx.locator("body").text_content() or "").lower()
        if "type is not found" in body:
            raise AssertionError(f"{self.screen_id} has 'type is not found' error")
        if "type not found" in body:
            raise AssertionError(f"{self.screen_id} has 'type not found' error")
        if "igcm.dac" in body:
            raise AssertionError(f"{self.screen_id} references IGCM.DAC types")

    def find_fields(self, field_names: list[str]) -> dict[str, bool]:
        """Check which fields are present in the DOM."""
        results = {}
        for name in field_names:
            locator = self.ctx.locator(f"[id*='{name}']")
            results[name] = locator.count() > 0
        return results
