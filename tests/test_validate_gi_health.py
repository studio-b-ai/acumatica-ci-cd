"""Tests for GI health check."""
from unittest.mock import MagicMock
from scripts.validate_publish_gi import check_gi_health


def test_gi_probe_healthy():
    session = MagicMock()
    session.query_entity.return_value = (200, [])
    assert check_gi_health(session, "https://example.com") is True


def test_gi_probe_all_fail():
    session = MagicMock()
    session.query_entity.return_value = (500, "error")
    assert check_gi_health(session, "https://example.com") is False


def test_gi_probe_timeout():
    session = MagicMock()
    session.query_entity.side_effect = Exception("Connection timed out")
    assert check_gi_health(session, "https://example.com") is False


def test_gi_probe_partial_success():
    """At least one success = healthy."""
    session = MagicMock()
    session.query_entity.side_effect = [
        (500, "error"),   # First probe fails
        (200, []),        # Second probe succeeds
    ]
    assert check_gi_health(session, "https://example.com") is True


def test_gi_probe_requests_session_fallback():
    """When session lacks query_entity, falls back to .get()."""
    session = MagicMock(spec=["get"])  # No query_entity attribute
    resp = MagicMock(status_code=200)
    session.get.return_value = resp
    assert check_gi_health(session, "https://example.com") is True
    assert session.get.call_count == 2
