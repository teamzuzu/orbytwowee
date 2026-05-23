"""Tests for the RouterData model — properties, fetch_all, band helpers.

All HTTP calls are patched out so these tests never hit the network.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import orbitui
from orbitui import RouterData

FIXTURES = Path(__file__).parent / "fixtures"

# Pre-load HTML fixtures as module-level constants so individual tests can
# call _parse_* directly or inject them via the mock.
CURRENTSETTING_HTML = (FIXTURES / "currentsetting.htm").read_text()
ADVANCED_HOME_HTML  = (FIXTURES / "ADVANCED_home2.htm").read_text()
DEVICES_HTML        = (FIXTURES / "DEV_device.htm").read_text()


def _html_for(path: str) -> str:
    mapping = {
        "currentsetting.htm":  CURRENTSETTING_HTML,
        "ADVANCED_home2.htm":  ADVANCED_HOME_HTML,
        "DEV_device.htm":      DEVICES_HTML,
    }
    return mapping.get(path, "")


@pytest.fixture
def loaded_data() -> RouterData:
    """RouterData fully populated from fixtures (no network)."""
    d = RouterData()
    with patch("orbitui._get", side_effect=_html_for):
        d.fetch_all()
    return d


@pytest.fixture
def empty_data() -> RouterData:
    """RouterData after fetch that returns empty strings for everything."""
    d = RouterData()
    with patch("orbitui._get", return_value=""):
        d.fetch_all()
    return d


# ── fetch_all ─────────────────────────────────────────────────────────────────

class TestFetchAll:
    def test_populates_settings(self, loaded_data):
        assert loaded_data.settings != {}

    def test_populates_info(self, loaded_data):
        assert loaded_data.info != {}

    def test_populates_devices(self, loaded_data):
        assert len(loaded_data.devices) > 0

    def test_sets_last_updated(self, loaded_data):
        assert loaded_data.last_updated is not None

    def test_clears_error_on_success(self, loaded_data):
        assert loaded_data.error is None

    def test_captures_exception_in_error(self):
        d = RouterData()
        with patch("orbitui._get", side_effect=RuntimeError("network dead")):
            d.fetch_all()
        assert d.error is not None
        assert "network dead" in d.error

    def test_last_updated_none_after_error(self):
        d = RouterData()
        with patch("orbitui._get", side_effect=RuntimeError("boom")):
            d.fetch_all()
        assert d.last_updated is None

    def test_fetch_calls_all_three_endpoints(self):
        called = []
        def track(path):
            called.append(path)
            return _html_for(path)
        d = RouterData()
        with patch("orbitui._get", side_effect=track):
            d.fetch_all()
        assert "currentsetting.htm" in called
        assert "ADVANCED_home2.htm" in called
        assert "DEV_device.htm" in called


# ── RouterData properties ─────────────────────────────────────────────────────

class TestRouterDataProperties:
    def test_model(self, loaded_data):
        assert loaded_data.model == "RBR750"

    def test_firmware_strips_build_suffix(self, loaded_data):
        assert loaded_data.firmware == "V7.2.6.21"
        assert "_" not in loaded_data.firmware

    def test_internet_up_true(self, loaded_data):
        assert loaded_data.internet_up is True

    def test_internet_up_false(self):
        d = RouterData()
        d.settings = {"InternetConnectionStatus": "Down"}
        assert d.internet_up is False

    def test_internet_up_missing_is_false(self):
        assert RouterData().internet_up is False

    def test_lan_ip_from_info(self, loaded_data):
        # Fixture has empty IP Address; falls back to ROUTER_HOST
        assert loaded_data.lan_ip == orbitui.ROUTER_HOST

    def test_lan_ip_from_info_when_present(self):
        d = RouterData()
        d.info = {"IP Address": "192.168.1.1"}
        assert d.lan_ip == "192.168.1.1"

    def test_lan_ip_falls_back_to_router_host_when_empty(self):
        d = RouterData()
        d.info = {"IP Address": ""}
        assert d.lan_ip == orbitui.ROUTER_HOST

    def test_lan_mac(self, loaded_data):
        assert loaded_data.lan_mac == "80:CC:9C:25:D6:55"

    def test_lan_mac_fallback(self):
        assert RouterData().lan_mac == "—"

    def test_gateway(self, loaded_data):
        assert loaded_data.gateway == "192.168.0.1"

    def test_gateway_fallback(self):
        assert RouterData().gateway == "—"

    def test_dns(self, loaded_data):
        assert loaded_data.dns == "1.1.1.1"

    def test_dns_fallback(self):
        assert RouterData().dns == "—"

    def test_dns_empty_string_returns_dash(self):
        d = RouterData()
        d.info = {"Domain Name Server": ""}
        assert d.dns == "—"

    def test_ssid(self, loaded_data):
        assert loaded_data.ssid == "fredsdeadnet"

    def test_ssid_fallback(self):
        assert RouterData().ssid == "—"

    def test_mode_ap_from_operation_mode(self, loaded_data):
        assert loaded_data.mode == "Access Point"

    def test_mode_ap_from_enable_apmode_flag(self):
        d = RouterData()
        d.info = {"enable_apmode": "1"}
        assert d.mode == "Access Point"

    def test_mode_router(self):
        d = RouterData()
        d.info = {"Operation Mode": "0"}
        assert d.mode == "Router"

    def test_mode_fallback(self):
        assert RouterData().mode == "—"

    def test_model_fallback(self):
        assert RouterData().model == "RBR750"  # hardcoded default


# ── band_rows ─────────────────────────────────────────────────────────────────

class TestBandRows:
    def test_returns_four_bands(self, loaded_data):
        rows = loaded_data.band_rows()
        assert len(rows) == 4

    def test_band_names(self, loaded_data):
        names = [r[0] for r in loaded_data.band_rows()]
        assert names == ["2.4 GHz", "5 GHz", "5 GHz BH", "6 GHz"]

    def test_24ghz_channel(self, loaded_data):
        row = loaded_data.band_rows()[0]
        assert row[1] == "Auto (3)"

    def test_24ghz_speed(self, loaded_data):
        row = loaded_data.band_rows()[0]
        assert "573.5 Mbps" in row[2]

    def test_5ghz_channel(self, loaded_data):
        row = loaded_data.band_rows()[1]
        assert "36" in row[1]

    def test_5ghz_speed(self, loaded_data):
        row = loaded_data.band_rows()[1]
        assert "1201 Mbps" in row[2]

    def test_missing_band_falls_back_gracefully(self, empty_data):
        for name, ch, speed in empty_data.band_rows():
            assert ch == "?"
            assert speed == "—"


# ── band_counts ───────────────────────────────────────────────────────────────

class TestBandCounts:
    def test_returns_dict(self, loaded_data):
        assert isinstance(loaded_data.band_counts(), dict)

    def test_wired_count(self, loaded_data):
        assert loaded_data.band_counts()["Wired"] == 3

    def test_5ghz_count(self, loaded_data):
        assert loaded_data.band_counts()["5 GHz"] == 4

    def test_24ghz_count(self, loaded_data):
        assert loaded_data.band_counts()["2.4 GHz"] == 5

    def test_total_matches_devices(self, loaded_data):
        total_from_counts = sum(loaded_data.band_counts().values())
        assert total_from_counts == len(loaded_data.devices)

    def test_empty_when_no_devices(self):
        d = RouterData()
        assert d.band_counts() == {}
