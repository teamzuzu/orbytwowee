#!/usr/bin/env python3
"""Generate SVG screenshots of every tab using sanitised mock data."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import orbitui
from orbitui import RouterData

# ── sanitised mock data ───────────────────────────────────────────────────────

MOCK_SETTINGS = {
    "Model": "RBR750",
    "Firmware": "V7.2.6.21_5.0.20",
    "InternetConnectionStatus": "Up",
    "Region": "ww",
    "DeviceMode": "1",
}

MOCK_INFO = {
    "Firmware Version": "V7.2.6.21_5.0.20",
    "Operation Mode": "AP",
    "MAC Address": "AA:BB:CC:DD:EE:00",
    "Gateway IP Address": "192.168.1.1",
    "Domain Name Server": "1.1.1.1",
    "Name (SSID)": "HomeNetwork",
    "IP Address": "192.168.1.2",
    "2.4 GHz Wireless mode:": "Up to 573.5 Mbps",
    "2.4 GHz Channel": "Auto (6)",
    "5 GHz Wireless mode:": "Up to 1201 Mbps",
    "5 GHz Channel": "Auto (36)",
    "6 GHz Wireless mode:": "",
    "6 GHz Channel": "",
}

MOCK_DEVICES = [
    {"ip": "192.168.1.10",  "name": "iPhone",        "mac": "AA:BB:CC:11:22:33", "conn": "ath1",  "band": "5 GHz"},
    {"ip": "192.168.1.11",  "name": "MacBook",        "mac": "AA:BB:CC:11:22:44", "conn": "ath1",  "band": "5 GHz"},
    {"ip": "192.168.1.12",  "name": "SmartTV",        "mac": "AA:BB:CC:11:22:55", "conn": "ath1",  "band": "5 GHz"},
    {"ip": "192.168.1.13",  "name": "PlayStation",    "mac": "AA:BB:CC:11:22:66", "conn": "ath1",  "band": "5 GHz"},
    {"ip": "192.168.1.20",  "name": "Thermostat",     "mac": "AA:BB:CC:33:44:11", "conn": "2.4G",  "band": "2.4 GHz"},
    {"ip": "192.168.1.21",  "name": "DoorCam",        "mac": "AA:BB:CC:33:44:22", "conn": "2.4G",  "band": "2.4 GHz"},
    {"ip": "192.168.1.22",  "name": "SmartPlug",      "mac": "AA:BB:CC:33:44:33", "conn": "2.4G",  "band": "2.4 GHz"},
    {"ip": "192.168.1.23",  "name": "Tablet",         "mac": "AA:BB:CC:33:44:44", "conn": "2.4G",  "band": "2.4 GHz"},
    {"ip": "192.168.1.24",  "name": "Printer",        "mac": "AA:BB:CC:33:44:55", "conn": "2.4G",  "band": "2.4 GHz"},
    {"ip": "192.168.1.30",  "name": "NAS",            "mac": "AA:BB:CC:55:66:11", "conn": "eth0",  "band": "Wired"},
    {"ip": "192.168.1.31",  "name": "Desktop",        "mac": "AA:BB:CC:55:66:22", "conn": "eth0",  "band": "Wired"},
    {"ip": "192.168.1.32",  "name": "",               "mac": "AA:BB:CC:55:66:33", "conn": "eth0",  "band": "Wired"},
]

MOCK_IFACE_STATS = [
    {"port": "WAN",                       "status": "1000M/Full", "tx_bps": 18432,  "rx_bps": 52428},
    {"port": "2.4 GHz WLAN b/g/n/ax",    "status": "573.5M",    "tx_bps": 9216,   "rx_bps": 12288},
    {"port": "5 GHz WLAN a/n/ac/ax/be",  "status": "1201M",     "tx_bps": 36864,  "rx_bps": 102400},
    {"port": "WLAN Backhaul",             "status": "2402M",     "tx_bps": 0,      "rx_bps": 0},
]


def _make_mock_data() -> RouterData:
    d = RouterData()
    d.settings = MOCK_SETTINGS
    d.info = MOCK_INFO
    d.devices = MOCK_DEVICES
    d.iface_stats = MOCK_IFACE_STATS
    d.last_updated = datetime(2024, 1, 15, 14, 32, 7)
    d.error = None
    return d


# ── screenshot driver ─────────────────────────────────────────────────────────

SCREENSHOT_DIR = Path("docs/screenshots")


async def take_screenshots() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    mock_data = _make_mock_data()

    # Patch fetch so the app never hits the network
    def fake_fetch(self: RouterData) -> None:
        self.settings = mock_data.settings
        self.info = mock_data.info
        self.devices = mock_data.devices
        self.iface_stats = mock_data.iface_stats
        self.last_updated = mock_data.last_updated
        self.error = None

    with patch.object(RouterData, "fetch_all", fake_fetch):
        app = orbitui.OrbiApp()
        async with app.run_test(size=(120, 40)) as pilot:
            # Wait for initial data load
            await pilot.pause(0.5)

            # Overview tab (default)
            await pilot.pause(0.1)
            app.save_screenshot(filename="overview.svg", path=str(SCREENSHOT_DIR))
            print("  saved overview.svg")

            # Devices tab
            await pilot.click("Tab#--content-tab-devices")
            await pilot.pause(0.1)
            app.save_screenshot(filename="devices.svg", path=str(SCREENSHOT_DIR))
            print("  saved devices.svg")

            # Bandwidth tab — seed a few history samples so sparkline shows
            await pilot.click("Tab#--content-tab-bandwidth")
            await pilot.pause(0.1)
            throughput = app.query_one("#throughput", orbitui.ThroughputPanel)
            for tx, rx in [
                (8192, 40960), (10240, 45056), (12288, 49152),
                (15360, 51200), (18432, 52428),
            ]:
                d = _make_mock_data()
                d.iface_stats = [
                    {"port": "WAN",                      "status": "1000M/Full", "tx_bps": tx,    "rx_bps": rx},
                    {"port": "2.4 GHz WLAN b/g/n/ax",   "status": "573.5M",    "tx_bps": tx//2, "rx_bps": rx//4},
                    {"port": "5 GHz WLAN a/n/ac/ax/be",  "status": "1201M",     "tx_bps": tx,    "rx_bps": rx//2},
                ]
                throughput.update_data(d)
            await pilot.pause(0.1)
            app.save_screenshot(filename="bandwidth.svg", path=str(SCREENSHOT_DIR))
            print("  saved bandwidth.svg")


if __name__ == "__main__":
    print("Taking screenshots…")
    asyncio.run(take_screenshots())
    print(f"Done — saved to {SCREENSHOT_DIR}/")
