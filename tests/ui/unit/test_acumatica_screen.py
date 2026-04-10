"""Unit tests for AcumaticaScreen — no live Acumatica needed."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, PropertyMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAcumaticaScreenConstruction:
    """Test navigate() routing and mode detection."""

    def test_navigate_standard_screen_uses_iframe_mode(self):
        """Standard screen navigation should resolve iframe[name='main']."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        frame = MagicMock()
        page.frame.return_value = frame
        type(page).url = PropertyMock(return_value="https://example.com/Main?ScreenId=IN202500")
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
        call_args = page.goto.call_args
        assert "GenericInquiry" in call_args[0][0]

    def test_navigate_shadowed_screen_falls_back_to_direct(self):
        """Shadowed screen (ScreenId=00000000) should auto-fallback to direct mode."""
        from acumatica_screen import AcumaticaScreen

        page = MagicMock()
        type(page).url = PropertyMock(side_effect=[
            "https://example.com/Main?ScreenId=00000000",
            "https://example.com/Main?ScreenId=00000000",
            "https://example.com/Pages/PO/PO301000.aspx",
        ])
        page.frame.return_value = None
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


class TestAcumaticaScreenDomMethods:
    """Test locator, evaluate, get_field, set_field."""

    def _make_screen(self):
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
        screen.ctx.evaluate.side_effect = ["", "YDS"]
        result = screen.get_field("edBaseUnit_text")
        assert result == "YDS"

    def test_set_field_clicks_clears_fills_blurs(self):
        screen = self._make_screen()
        screen.set_field("edDescr", "Test Value")
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


class TestAcumaticaScreenToolbar:
    """Test save, click_toolbar actions."""

    def _make_screen(self):
        from acumatica_screen import AcumaticaScreen
        page = MagicMock()
        ctx = MagicMock()
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
