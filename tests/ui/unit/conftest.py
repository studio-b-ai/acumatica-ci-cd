"""Conftest for unit tests — overrides autouse fixtures from parent conftest."""
import pytest


@pytest.fixture(autouse=True)
def cleanup_orders():
    """No-op override — unit tests don't use Acumatica."""
    yield


@pytest.fixture(autouse=True)
def capture_dialogs():
    """No-op override — unit tests don't use a browser."""
    yield
