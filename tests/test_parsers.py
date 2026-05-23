"""Unit tests for every parsing function in orbitui.py.

All tests here are pure (no network, no I/O) — they operate directly on
HTML strings, either from the fixture files or inline snippets.
"""

from __future__ import annotations

import pytest

from orbitui import (
    _MAC_RE,
    _band_label,
    _ip_key,
    _parse_current_settings,
    _parse_devices,
    _parse_router_info,
    _strip,
)

# ── _strip ────────────────────────────────────────────────────────────────────


class TestStrip:
    def test_removes_tags(self):
        assert _strip("<b>hello</b>") == "hello"

    def test_removes_nested_tags(self):
        assert _strip("<td class='x'><span>text</span></td>") == "text"

    def test_plain_text_unchanged(self):
        assert _strip("no tags here") == "no tags here"

    def test_empty_string(self):
        assert _strip("") == ""

    def test_strips_surrounding_whitespace(self):
        assert _strip("  <p>  hi  </p>  ") == "hi"

    def test_tag_only_gives_empty(self):
        assert _strip("<br/>") == ""


# ── _MAC_RE ───────────────────────────────────────────────────────────────────


class TestMacRe:
    @pytest.mark.parametrize(
        "mac",
        [
            "AA:BB:CC:DD:EE:FF",
            "00:00:00:00:00:00",
            "E8:48:B8:C7:40:EA",
            "aa:bb:cc:dd:ee:ff",
            "0a:1b:2c:3d:4e:5f",
        ],
    )
    def test_valid_macs(self, mac):
        assert _MAC_RE.match(mac), f"{mac!r} should match"

    @pytest.mark.parametrize(
        "value",
        [
            "eth0",
            "ath1",
            "2.4G",
            "5G",
            "",
            "AA:BB:CC:DD:EE",  # too short
            "AA:BB:CC:DD:EE:FF:00",  # too long
            "GG:BB:CC:DD:EE:FF",  # invalid hex
            "192.168.0.1",
        ],
    )
    def test_non_macs(self, value):
        assert not _MAC_RE.match(value), f"{value!r} should not match"


# ── _ip_key ───────────────────────────────────────────────────────────────────


class TestIpKey:
    def test_standard_ip(self):
        assert _ip_key("192.168.0.1") == (192, 168, 0, 1)

    def test_sorts_numerically_not_lexically(self):
        ips = ["192.168.0.10", "192.168.0.9", "192.168.0.100"]
        assert sorted(ips, key=_ip_key) == ["192.168.0.9", "192.168.0.10", "192.168.0.100"]

    def test_sorts_across_subnets(self):
        ips = ["192.168.6.1", "10.0.0.1", "192.168.0.1"]
        assert sorted(ips, key=_ip_key) == ["10.0.0.1", "192.168.0.1", "192.168.6.1"]

    def test_malformed_returns_fallback(self):
        assert _ip_key("not-an-ip") == (999,)

    def test_empty_string_returns_fallback(self):
        assert _ip_key("") == (999,)

    def test_partial_ip_parses_what_it_can(self):
        # "192.168" splits fine; _ip_key returns a shorter tuple (not (999,))
        result = _ip_key("192.168")
        assert result == (192, 168)


# ── _band_label ───────────────────────────────────────────────────────────────


class TestBandLabel:
    @pytest.mark.parametrize(
        "conn,expected",
        [
            # Wired
            ("eth0", "Wired"),
            ("eth1", "Wired"),
            ("ETH0", "Wired"),  # case-insensitive
            # 2.4 GHz
            ("ath0", "2.4 GHz"),
            ("2.4G", "2.4 GHz"),
            ("2.4GHz", "2.4 GHz"),
            ("2.4g", "2.4 GHz"),
            # 5 GHz backhaul — matched before plain 5G
            ("ath2", "5 GHz BH"),
            ("5G-2", "5 GHz BH"),
            ("5g-2", "5 GHz BH"),
            # 5 GHz
            ("ath1", "5 GHz"),
            ("5G", "5 GHz"),
            ("5GHz", "5 GHz"),
            ("5g", "5 GHz"),
            # 6 GHz
            ("ath3", "6 GHz"),
            ("6G", "6 GHz"),
            ("6GHz", "6 GHz"),
            # Unknown / pass-through
            ("wlan0", "wlan0"),
            ("", "—"),
        ],
    )
    def test_all_cases(self, conn, expected):
        assert _band_label(conn) == expected

    def test_5g_backhaul_matched_before_5g(self):
        # "5G-2" contains "5G" but must map to backhaul, not plain 5 GHz
        assert _band_label("5G-2") == "5 GHz BH"
        assert _band_label("ath2") == "5 GHz BH"


# ── _parse_current_settings ───────────────────────────────────────────────────


class TestParseCurrentSettings:
    def test_full_fixture(self, currentsetting_html):
        data = _parse_current_settings(currentsetting_html)
        assert data["Model"] == "RBR750"
        assert data["Firmware"] == "V7.2.6.21_5.0.20"
        assert data["InternetConnectionStatus"] == "Up"
        assert data["Region"] == "ww"
        assert data["DeviceMode"] == "1"

    def test_all_expected_keys_present(self, currentsetting_html):
        data = _parse_current_settings(currentsetting_html)
        for key in (
            "Firmware",
            "Model",
            "InternetConnectionStatus",
            "SOAPVersion",
            "LoginMethod",
            "DeviceMode",
            "isBlankState",
        ):
            assert key in data, f"Missing key: {key}"

    def test_empty_html_returns_empty_dict(self):
        assert _parse_current_settings("") == {}

    def test_no_tag_returns_empty_dict(self):
        assert _parse_current_settings("<html><body>nothing</body></html>") == {}

    def test_ignores_lines_without_equals(self):
        html = '<p id="currentsetting">\nmodel_line_no_equals\nModel=RBR750\n</p>'
        data = _parse_current_settings(html)
        assert "model_line_no_equals" not in data
        assert data["Model"] == "RBR750"

    def test_value_containing_equals_sign(self):
        html = '<p id="currentsetting">\nKey=first=second\n</p>'
        assert _parse_current_settings(html)["Key"] == "first=second"

    def test_whitespace_around_keys_trimmed(self):
        html = '<p id="currentsetting">\n  Model  =  RBR750  \n</p>'
        assert _parse_current_settings(html)["Model"] == "RBR750"

    def test_internet_down(self):
        html = '<p id="currentsetting">\nInternetConnectionStatus=Down\n</p>'
        assert _parse_current_settings(html)["InternetConnectionStatus"] == "Down"


# ── _parse_router_info ────────────────────────────────────────────────────────


class TestParseRouterInfo:
    def test_firmware_version(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["Firmware Version"] == "V7.2.6.21_5.0.20"

    def test_operation_mode(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["Operation Mode"] == "AP"

    def test_lan_mac_address(self, advanced_home_html):
        # First MAC entry (LAN) should win over the second (WAN)
        assert _parse_router_info(advanced_home_html)["MAC Address"] == "80:CC:9C:25:D6:55"

    def test_gateway(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["Gateway IP Address"] == "192.168.0.1"

    def test_dns(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["Domain Name Server"] == "1.1.1.1"

    def test_ssid_main_network(self, advanced_home_html):
        # First Name (SSID) entry should win over the guest network entry
        assert _parse_router_info(advanced_home_html)["Name (SSID)"] == "fredsdeadnet"

    def test_ssid_does_not_overwrite_with_guest(self, advanced_home_html):
        result = _parse_router_info(advanced_home_html)
        assert result["Name (SSID)"] != "NETGEAR-Guest"

    def test_band_24ghz_channel(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["2.4 GHz Channel"] == "Auto (3)"

    def test_band_24ghz_speed(self, advanced_home_html):
        assert (
            _parse_router_info(advanced_home_html)["2.4 GHz Wireless mode:"] == "Up to 573.5 Mbps"
        )

    def test_band_5ghz_channel(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["5 GHz Channel"] == "36 + 40(P) + 44 + 48"

    def test_band_5ghz_speed(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["5 GHz Wireless mode:"] == "Up to 1201 Mbps"

    def test_commented_5g2_not_parsed(self, advanced_home_html):
        result = _parse_router_info(advanced_home_html)
        # 5G-2 rows are inside HTML comments — must be ignored
        assert "5G-2 Channel" not in result or result.get("5G-2 Channel") == ""
        assert "5G-2 Mode:" not in result or result.get("5G-2 Mode:") == ""

    def test_hidden_input_wan_status(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["wan_status"] == "up"

    def test_hidden_input_enable_apmode(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["enable_apmode"] == "1"

    def test_hidden_input_wantype(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["wantype"] == "dhcp"

    def test_ip_address_empty_in_ap_mode(self, advanced_home_html):
        # In AP mode the LAN IP row exists but the content td is empty
        result = _parse_router_info(advanced_home_html)
        assert result.get("IP Address", "") == ""

    def test_empty_html_returns_empty_dict(self):
        assert _parse_router_info("") == {}

    def test_first_duplicate_key_wins(self):
        html = """
        <tr class="basic-text">
          <td class="basic-text-menu">MAC Address</td>
          <td class="basic-text-content">AA:BB:CC:DD:EE:01</td>
        </tr>
        <tr class="basic-text">
          <td class="basic-text-menu">MAC Address</td>
          <td class="basic-text-content">AA:BB:CC:DD:EE:02</td>
        </tr>
        """
        assert _parse_router_info(html)["MAC Address"] == "AA:BB:CC:DD:EE:01"

    def test_comment_stripping_prevents_false_matches(self):
        html = """
        <!-- <tr class="basic-text">
          <td class="basic-text-menu">Secret Key</td>
          <td class="basic-text-content">should not appear</td>
        </tr> -->
        <tr class="basic-text">
          <td class="basic-text-menu">Real Key</td>
          <td class="basic-text-content">real value</td>
        </tr>
        """
        result = _parse_router_info(html)
        assert "Secret Key" not in result
        assert result["Real Key"] == "real value"

    def test_hidden_input_does_not_overwrite_existing_key(self):
        # setdefault: HTML form inputs should NOT overwrite td-parsed values
        html = """
        <tr class="basic-text">
          <td class="basic-text-menu">Operation Mode</td>
          <td class="basic-text-content">AP</td>
        </tr>
        <input type="hidden" name="Operation Mode" value="Router">
        """
        assert _parse_router_info(html)["Operation Mode"] == "AP"

    def test_hardware_version(self, advanced_home_html):
        assert _parse_router_info(advanced_home_html)["Hardware Version"] == "RBR750"


# ── _parse_devices ────────────────────────────────────────────────────────────


class TestParseDevices:
    def test_correct_device_count(self, devices_html):
        # Fixture has 12 unique devices in the first table;
        # second table (intruders) should be fully skipped.
        devices = _parse_devices(devices_html)
        assert len(devices) == 12

    def test_all_required_fields_present(self, devices_html):
        for d in _parse_devices(devices_html):
            assert "ip" in d
            assert "name" in d
            assert "mac" in d
            assert "conn" in d
            assert "band" in d

    def test_no_mac_in_conn_field(self, devices_html):
        # Wireless-intruders section puts MAC in col4 — must all be skipped
        for d in _parse_devices(devices_html):
            assert not _MAC_RE.match(d["conn"]), (
                f"Device {d['mac']} has a MAC address as its conn field"
            )

    def test_no_duplicate_macs(self, devices_html):
        devices = _parse_devices(devices_html)
        macs = [d["mac"] for d in devices]
        assert len(macs) == len(set(macs)), "Duplicate MACs in device list"

    def test_sorted_by_ip(self, devices_html):
        devices = _parse_devices(devices_html)
        keys = [_ip_key(d["ip"]) for d in devices]
        assert keys == sorted(keys)

    def test_wired_devices_classified_correctly(self, devices_html):
        devices = _parse_devices(devices_html)
        wired = [d for d in devices if d["band"] == "Wired"]
        assert len(wired) == 3  # gateway + QNAP + BABYCHONG

    def test_5ghz_devices_classified_correctly(self, devices_html):
        devices = _parse_devices(devices_html)
        five = [d for d in devices if d["band"] == "5 GHz"]
        assert len(five) == 4  # ath1 devices

    def test_24ghz_devices_classified_correctly(self, devices_html):
        devices = _parse_devices(devices_html)
        two4 = [d for d in devices if d["band"] == "2.4 GHz"]
        assert len(two4) == 5  # 2.4G devices

    def test_dash_name_becomes_empty_string(self, devices_html):
        devices = _parse_devices(devices_html)
        # IP 192.168.0.1 has "--" as name
        gw = next(d for d in devices if d["ip"] == "192.168.0.1")
        assert gw["name"] == ""

    def test_named_device_keeps_name(self, devices_html):
        devices = _parse_devices(devices_html)
        qnap = next(d for d in devices if d["ip"] == "192.168.0.248")
        assert qnap["name"] == "QNAP"

    def test_conn_field_preserved(self, devices_html):
        devices = _parse_devices(devices_html)
        tapo = next(d for d in devices if d["mac"] == "E8:48:B8:C7:40:EA")
        assert tapo["conn"] == "ath1"

    def test_mac_repeated_in_col4_fully_excluded(self, devices_html):
        # Device AA:BB:CC:DD:EE:FF only appears in the wireless-intruders section
        # (col4 = MAC). It must not appear in the parsed output.
        devices = _parse_devices(devices_html)
        macs = {d["mac"] for d in devices}
        assert "AA:BB:CC:DD:EE:FF" not in macs

    def test_empty_html_returns_empty_list(self):
        assert _parse_devices("") == []

    def test_skips_non_ip_rows(self):
        # Rows where column 0 is not an IP address are silently ignored
        # (covers header rows and any non-device rows)
        html = """
        <tr><td>IP Address</td><td>Device Name</td><td>MAC Address</td><td>Band</td></tr>
        <tr><td>192.168.0.5</td><td>test</td><td>AA:BB:CC:DD:EE:01</td><td>eth0</td></tr>
        """
        devices = _parse_devices(html)
        assert len(devices) == 1
        assert devices[0]["ip"] == "192.168.0.5"

    def test_inline_single_device(self):
        html = """<tr>
          <td>192.168.0.10</td><td>TestDevice</td>
          <td>AA:BB:CC:DD:EE:FF</td><td>ath1</td>
        </tr>"""
        devices = _parse_devices(html)
        assert len(devices) == 1
        d = devices[0]
        assert d["ip"] == "192.168.0.10"
        assert d["name"] == "TestDevice"
        assert d["mac"] == "AA:BB:CC:DD:EE:FF"
        assert d["conn"] == "ath1"
        assert d["band"] == "5 GHz"

    def test_inline_wired_device(self):
        html = """<tr>
          <td>192.168.0.1</td><td>gateway</td>
          <td>11:22:33:44:55:66</td><td>eth0</td>
        </tr>"""
        devices = _parse_devices(html)
        assert devices[0]["band"] == "Wired"

    def test_nbsp_rows_ignored(self):
        html = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>"
        assert _parse_devices(html) == []

    def test_duplicate_mac_in_connected_table_deduped(self):
        # Two rows with the same MAC but valid (non-MAC) conn — second is skipped (line 122)
        html = """
        <tr><td>192.168.0.5</td><td>DevA</td><td>AA:BB:CC:DD:EE:01</td><td>ath1</td></tr>
        <tr><td>192.168.0.6</td><td>DevA-dup</td><td>AA:BB:CC:DD:EE:01</td><td>ath1</td></tr>
        """
        devices = _parse_devices(html)
        assert len(devices) == 1
        assert devices[0]["ip"] == "192.168.0.5"
