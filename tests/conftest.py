"""Shared fixtures for the orbitui test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# ── HTML fixture strings ───────────────────────────────────────────────────────


@pytest.fixture
def currentsetting_html() -> str:
    return (FIXTURES / "currentsetting.htm").read_text()


@pytest.fixture
def advanced_home_html() -> str:
    return (FIXTURES / "ADVANCED_home2.htm").read_text()


@pytest.fixture
def devices_html() -> str:
    return (FIXTURES / "DEV_device.htm").read_text()


# ── session isolation ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_orbi_session():
    """Reset the module-level HTTP session before and after every test
    so tests never leak state to each other."""
    import orbitui

    orbitui._session = None
    yield
    orbitui._session = None
