"""Tests for TUI panel widgets, DevicesView, and the _kv helper.

Textual widgets are instantiated directly (no running app required for
unit tests); `self.update()` is replaced with a MagicMock so we can
assert on the rendered markup without spinning up the full terminal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from orbitui import (
    DeviceSummaryPanel,
    DevicesView,
    RouterData,
    RouterInfoPanel,
    ThroughputPanel,
    WiFiBandsPanel,
    _kv,
)

# ── _kv helper ────────────────────────────────────────────────────────────────


class TestKv:
    def test_formats_label_and_value(self):
        result = _kv("Model", "RBR750")
        assert "Model" in result
        assert "RBR750" in result

    def test_label_padded_to_default_width(self):
        # Default width=14; "IP" should be padded to 14 chars
        result = _kv("IP", "1.2.3.4")
        assert "IP" + " " * 12 in result  # 2 chars + 12 spaces = 14

    def test_custom_label_width(self):
        result = _kv("X", "val", label_width=5)
        assert "X" + " " * 4 in result  # 1 char + 4 spaces = 5

    def test_dim_markup_present(self):
        assert "[dim]" in _kv("key", "value")

    def test_closing_markup_present(self):
        assert "[/]" in _kv("key", "value")


# ── RouterInfoPanel ───────────────────────────────────────────────────────────


def _make_full_data() -> RouterData:
    """RouterData with every field populated."""
    d = RouterData()
    d.settings = {
        "Model": "RBR750",
        "InternetConnectionStatus": "Up",
        "Firmware": "V7.2.6.21_5.0.20",
    }
    d.info = {
        "Firmware Version": "V7.2.6.21_5.0.20",
        "Operation Mode": "AP",
        "MAC Address": "80:CC:9C:25:D6:55",
        "Gateway IP Address": "192.168.0.1",
        "Domain Name Server": "1.1.1.1",
        "Name (SSID)": "fredsdeadnet",
        "IP Address": "192.168.0.44",
    }
    d.devices = [
        {
            "ip": "192.168.0.1",
            "name": "",
            "mac": "AA:BB:CC:DD:EE:01",
            "conn": "eth0",
            "band": "Wired",
        },
        {
            "ip": "192.168.0.10",
            "name": "TV",
            "mac": "AA:BB:CC:DD:EE:02",
            "conn": "ath1",
            "band": "5 GHz",
        },
        {
            "ip": "192.168.0.20",
            "name": "",
            "mac": "AA:BB:CC:DD:EE:03",
            "conn": "2.4G",
            "band": "2.4 GHz",
        },
    ]
    return d


class TestRouterInfoPanel:
    def _render(self, d: RouterData) -> str:
        panel = RouterInfoPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(d)
        assert panel.update.called, "update() was never called"
        return panel.update.call_args[0][0]

    def test_shows_model(self):
        assert "RBR750" in self._render(_make_full_data())

    def test_shows_firmware(self):
        text = self._render(_make_full_data())
        assert "V7.2.6.21" in text

    def test_shows_ssid(self):
        assert "fredsdeadnet" in self._render(_make_full_data())

    def test_shows_gateway(self):
        assert "192.168.0.1" in self._render(_make_full_data())

    def test_shows_dns(self):
        assert "1.1.1.1" in self._render(_make_full_data())

    def test_internet_up_green(self):
        text = self._render(_make_full_data())
        assert "bright_green" in text
        assert "UP" in text

    def test_internet_down_red(self):
        d = _make_full_data()
        d.settings["InternetConnectionStatus"] = "Down"
        text = self._render(d)
        assert "bright_red" in text
        assert "DOWN" in text

    def test_ap_mode_label(self):
        assert "Access Point" in self._render(_make_full_data())

    def test_called_exactly_once(self):
        panel = RouterInfoPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(_make_full_data())
        panel.update.assert_called_once()


# ── WiFiBandsPanel ────────────────────────────────────────────────────────────


class TestWiFiBandsPanel:
    def _render(self, d: RouterData) -> str:
        panel = WiFiBandsPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(d)
        assert panel.update.called
        return panel.update.call_args[0][0]

    def test_shows_24ghz_band(self):
        assert "2.4 GHz" in self._render(_make_full_data())

    def test_shows_5ghz_band(self):
        assert "5 GHz" in self._render(_make_full_data())

    def test_shows_speed_mbps(self):
        d = _make_full_data()
        d.info["2.4 GHz Wireless mode:"] = "Up to 573.5 Mbps"
        assert "573" in self._render(d)

    def test_shows_channel(self):
        d = _make_full_data()
        d.info["2.4 GHz Channel"] = "Auto (6)"
        assert "Auto (6)" in self._render(d)

    def test_full_bar_for_high_speed(self):
        d = _make_full_data()
        d.info["5 GHz Wireless mode:"] = "Up to 2402 Mbps"
        text = self._render(d)
        assert "█" in text

    def test_empty_bar_when_no_speed(self):
        d = _make_full_data()
        d.info.pop("2.4 GHz Wireless mode:", None)
        assert "░" in self._render(d)

    def test_device_count_shown(self):
        d = _make_full_data()  # 1 wired, 1 5GHz, 1 2.4GHz
        text = self._render(d)
        assert "dev" in text

    def test_missing_channel_shows_question_mark(self):
        d = _make_full_data()
        d.info.pop("6 GHz Channel", None)
        assert "?" in self._render(d)


# ── DeviceSummaryPanel ────────────────────────────────────────────────────────


class TestDeviceSummaryPanel:
    def _render(self, d: RouterData) -> str:
        panel = DeviceSummaryPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(d)
        assert panel.update.called
        return panel.update.call_args[0][0]

    def test_shows_total_count(self):
        d = _make_full_data()
        assert "3" in self._render(d)  # 3 devices in _make_full_data

    def test_shows_wired_band(self):
        assert "Wired" in self._render(_make_full_data())

    def test_shows_5ghz_band(self):
        assert "5 GHz" in self._render(_make_full_data())

    def test_shows_24ghz_band(self):
        assert "2.4 GHz" in self._render(_make_full_data())

    def test_shows_bar_characters(self):
        assert "▪" in self._render(_make_full_data())

    def test_error_shown_when_present(self):
        d = _make_full_data()
        d.error = "Connection refused"
        text = self._render(d)
        assert "Connection refused" in text

    def test_no_error_section_when_clean(self):
        text = self._render(_make_full_data())
        assert "Error" not in text

    def test_empty_devices(self):
        d = RouterData()
        text = self._render(d)
        assert "0" in text

    def test_band_with_many_devices_caps_bar_at_30(self):
        d = RouterData()
        d.devices = [
            {
                "ip": f"192.168.0.{i}",
                "name": "",
                "mac": f"AA:BB:CC:DD:EE:{i:02X}",
                "conn": "ath1",
                "band": "5 GHz",
            }
            for i in range(40)
        ]
        text = self._render(d)
        # bar is capped at 30 ▪ characters regardless of device count
        assert "▪" * 30 in text
        assert "▪" * 31 not in text


# ── DevicesView ───────────────────────────────────────────────────────────────


def _make_mock_table():
    tbl = MagicMock()
    tbl.clear = MagicMock()
    tbl.add_row = MagicMock()
    tbl.add_columns = MagicMock()
    return tbl


def _make_devices_view_with_mock_table():
    """Return (DevicesView instance, mock DataTable) with query_one patched."""
    mock_tbl = _make_mock_table()
    view = DevicesView()
    view.query_one = MagicMock(return_value=mock_tbl)
    return view, mock_tbl


_SAMPLE_DEVICES = [
    {"ip": "192.168.0.1", "name": "", "mac": "AA:BB:CC:DD:EE:01", "conn": "eth0", "band": "Wired"},
    {
        "ip": "192.168.0.10",
        "name": "TV",
        "mac": "AA:BB:CC:DD:EE:02",
        "conn": "ath1",
        "band": "5 GHz",
    },
    {
        "ip": "192.168.0.20",
        "name": "",
        "mac": "AA:BB:CC:DD:EE:03",
        "conn": "2.4G",
        "band": "2.4 GHz",
    },
]


class TestDevicesView:
    def test_on_mount_adds_columns(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.on_mount()
        mock_tbl.add_columns.assert_called_once()
        cols = mock_tbl.add_columns.call_args[0]
        assert "IP Address" in cols
        assert "MAC Address" in cols

    def test_update_devices_stores_and_renders(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        assert mock_tbl.clear.called
        assert mock_tbl.add_row.call_count == 3

    def test_apply_filter_no_query_shows_all(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        mock_tbl.add_row.reset_mock()
        view.filter_text = ""
        view._apply_filter()
        assert mock_tbl.add_row.call_count == 3

    def test_apply_filter_matches_ip(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        mock_tbl.add_row.reset_mock()
        view.filter_text = "192.168.0.1"
        view._apply_filter()
        # only the exact .1 device matches (not .10 or .20 for this specific prefix)
        assert mock_tbl.add_row.call_count >= 1

    def test_apply_filter_matches_name(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        mock_tbl.add_row.reset_mock()
        view.filter_text = "tv"
        view._apply_filter()
        assert mock_tbl.add_row.call_count == 1

    def test_apply_filter_matches_band(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        mock_tbl.add_row.reset_mock()
        view.filter_text = "wired"
        view._apply_filter()
        assert mock_tbl.add_row.call_count == 1

    def test_apply_filter_no_match_shows_none(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        mock_tbl.add_row.reset_mock()
        view.filter_text = "zzznomatch"
        view._apply_filter()
        assert mock_tbl.add_row.call_count == 0

    def test_unnamed_device_shows_dim_dash(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        # The wired device has no name — should render [dim]—[/]
        rows = [call[0] for call in mock_tbl.add_row.call_args_list]
        wired_row = next(r for r in rows if r[0] == "192.168.0.1")
        assert "[dim]" in wired_row[1]

    def test_named_device_shown_as_is(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        rows = [call[0] for call in mock_tbl.add_row.call_args_list]
        tv_row = next(r for r in rows if r[0] == "192.168.0.10")
        assert tv_row[1] == "TV"

    def test_band_colour_applied(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices(_SAMPLE_DEVICES)
        rows = [call[0] for call in mock_tbl.add_row.call_args_list]
        five_row = next(r for r in rows if r[0] == "192.168.0.10")
        assert "bright_green" in five_row[3]

    def test_empty_devices_clears_table(self):
        view, mock_tbl = _make_devices_view_with_mock_table()
        view.update_devices([])
        assert mock_tbl.clear.called
        assert mock_tbl.add_row.call_count == 0


# ── ThroughputPanel ───────────────────────────────────────────────────────────

_IFACE_STATS = [
    {"port": "WAN", "status": "1000M/Full", "tx_bps": 10240, "rx_bps": 20480},
    {"port": "2.4 GHz WLAN b/g/n/ax", "status": "573.5M", "tx_bps": 5120, "rx_bps": 6144},
    {"port": "5 GHz WLAN a/n/ac/ax/be", "status": "1201M", "tx_bps": 8192, "rx_bps": 4096},
]


def _make_throughput_data(iface_stats=None) -> RouterData:
    d = _make_full_data()
    d.iface_stats = iface_stats if iface_stats is not None else list(_IFACE_STATS)
    return d


class TestThroughputPanel:
    def _render(self, d: RouterData, panel: ThroughputPanel | None = None) -> str:
        if panel is None:
            panel = ThroughputPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(d)
        assert panel.update.called
        return panel.update.call_args[0][0]

    def test_shows_bandwidth_heading(self):
        assert "Bandwidth" in self._render(_make_throughput_data())

    def test_shows_wan_label(self):
        assert "WAN" in self._render(_make_throughput_data())

    def test_shows_upload_rate(self):
        text = self._render(_make_throughput_data())
        assert "10.0 KB/s" in text

    def test_shows_download_rate(self):
        text = self._render(_make_throughput_data())
        assert "20.0 KB/s" in text

    def test_shows_sparkline_after_first_poll(self):
        panel = ThroughputPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        panel.update_data(_make_throughput_data())
        text = panel.update.call_args[0][0]
        spark_chars = set("▁▂▃▄▅▆▇█")
        assert any(c in text for c in spark_chars)

    def test_collecting_message_before_first_data(self):
        d = _make_throughput_data(iface_stats=[])
        assert "Collecting" in self._render(d)

    def test_shows_24ghz_band(self):
        assert "2.4 GHz" in self._render(_make_throughput_data())

    def test_shows_5ghz_band(self):
        assert "5 GHz" in self._render(_make_throughput_data())

    def test_history_accumulates_across_calls(self):
        panel = ThroughputPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        for _ in range(5):
            panel.update_data(_make_throughput_data())
        assert len(panel._wan_tx) == 5
        assert len(panel._wan_rx) == 5

    def test_history_capped_at_max(self):
        panel = ThroughputPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        for i in range(ThroughputPanel.MAX_HISTORY + 10):
            d = _make_throughput_data()
            d.iface_stats = [{"port": "WAN", "status": "1000M", "tx_bps": i, "rx_bps": i}]
            panel.update_data(d)
        assert len(panel._wan_tx) == ThroughputPanel.MAX_HISTORY

    def test_fmt_bytes(self):
        panel = ThroughputPanel()
        assert panel._fmt(512) == "512 B/s"
        assert panel._fmt(1024) == "1.0 KB/s"
        assert panel._fmt(1_048_576) == "1.0 MB/s"

    def test_no_band_rows_when_iface_stats_empty(self):
        d = _make_full_data()
        d.iface_stats = []
        panel = ThroughputPanel()
        panel.update = MagicMock()  # type: ignore[method-assign]
        # should not raise; should show collecting message
        panel.update_data(d)
        assert panel.update.called

    def test_error_shown_when_present(self):
        d = _make_throughput_data()
        d.error = "connection refused"
        assert "connection refused" in self._render(d)

    def test_no_error_section_when_clean(self):
        assert "Error" not in self._render(_make_throughput_data())
