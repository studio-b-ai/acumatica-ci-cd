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
