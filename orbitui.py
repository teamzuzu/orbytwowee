#!/usr/bin/env python3
"""orbitui.py — Netgear Orbi RBR750 TUI monitor"""

from __future__ import annotations

import re
from collections import deque
from datetime import datetime

import requests
from requests.auth import HTTPBasicAuth
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Header, Input, Static, TabbedContent, TabPane

# ── config ──────────────────────────────────────────────────────────────────

ROUTER_HOST = "192.168.0.44"
AUTH = HTTPBasicAuth("admin", "netgearpassword")
REFRESH_SECS = 30

# ── session ──────────────────────────────────────────────────────────────────
# Netgear Orbi requires a two-step handshake: the first request to a protected
# endpoint returns 401 + Set-Cookie: XSRF_TOKEN; subsequent requests carrying
# that cookie (plus Basic Auth) return 200.  We keep a persistent session so
# the cookie survives across calls.

_session: requests.Session | None = None


def _make_session() -> requests.Session:
    s = requests.Session()
    s.auth = AUTH
    s.headers["User-Agent"] = "Mozilla/5.0"
    # Prime: triggers the 401 that plants the XSRF_TOKEN cookie
    s.get(f"http://{ROUTER_HOST}/ADVANCED_home2.htm", timeout=10)
    return s


def _get(path: str) -> str:
    global _session
    try:
        if _session is None:
            _session = _make_session()
        r = _session.get(f"http://{ROUTER_HOST}/{path}", timeout=10)
        if r.status_code == 401:
            _session = _make_session()
            r = _session.get(f"http://{ROUTER_HOST}/{path}", timeout=10)
            if r.status_code == 401:
                _session = None
                raise PermissionError("Authentication failed (HTTP 401) — check AUTH credentials")
        return r.text if r.ok else ""
    except PermissionError:
        raise
    except Exception:
        _session = None
        return ""


def _strip(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _parse_current_settings(html: str) -> dict[str, str]:
    data: dict[str, str] = {}
    m = re.search(r'<p id="currentsetting">(.*?)</p>', html, re.DOTALL)
    if m:
        for line in m.group(1).strip().splitlines():
            if "=" in line:
                k, _, v = line.strip().partition("=")
                data[k.strip()] = v.strip()
    return data


_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def _parse_router_info(html: str) -> dict[str, str]:
    # Strip HTML comments so we don't pick up commented-out sections (e.g. 5G-2)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

    result: dict[str, str] = {}

    # Parse structured label→value rows via their CSS classes
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        menu = re.search(r'<td[^>]*class="basic-text-menu[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL)
        content = re.search(
            r'<td[^>]*class="basic-text-content[^"]*"[^>]*>(.*?)</td>', row, re.DOTALL
        )
        if menu and content:
            k = _strip(menu.group(1))
            v = _strip(content.group(1))
            if k and k not in result:
                result[k] = v

    # Form hidden inputs carry wan_status, wantype, enable_apmode, etc.
    for m in re.finditer(r'name="(\w+)"[^>]+value="([^"]*)"', html):
        result.setdefault(m.group(1), m.group(2))

    return result


def _parse_devices(html: str) -> list[dict]:
    devices: list[dict] = []
    seen: set[str] = set()

    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = [_strip(c) for c in re.findall(r"<td[^>]*>\s*(.*?)\s*</td>", row, re.DOTALL)]
        cells = [c for c in cells if c and "&nbsp;" not in c]

        if len(cells) < 3 or not re.match(r"\d+\.\d+\.\d+", cells[0]):
            continue

        ip = cells[0]
        name = cells[1] if cells[1] != "--" else ""
        mac = cells[2]
        conn = cells[3] if len(cells) > 3 else ""

        # The "Wireless Devices (intruders)" section repeats the MAC in column 4 —
        # detect and skip those rows to avoid duplicate/mislabelled entries.
        if _MAC_RE.match(conn):
            continue

        if mac in seen:
            continue
        seen.add(mac)

        devices.append(
            {"ip": ip, "name": name, "mac": mac, "conn": conn, "band": _band_label(conn)}
        )

    return sorted(devices, key=lambda d: _ip_key(d["ip"]))


def _ip_key(ip: str) -> tuple:
    try:
        return tuple(int(x) for x in ip.split("."))
    except Exception:
        return (999,)


def _band_label(conn: str) -> str:
    c = conn.lower()
    if c in ("eth0", "eth1", "eth"):
        return "Wired"
    if "2.4g" in c or c == "ath0":
        return "2.4 GHz"
    if "5g-2" in c or c == "ath2":
        return "5 GHz BH"
    if "5g" in c or c == "ath1":
        return "5 GHz"
    if "6g" in c or c == "ath3":
        return "6 GHz"
    return conn or "—"


def _parse_iface_stats(html: str) -> list[dict]:
    """Parse RST_stattbl.htm → [{port, status, tx_bps, rx_bps}, ...]."""
    result = []
    for row_html in re.findall(r"<tr.*?</tr>", html, re.DOTALL):
        cells = re.findall(r'<span class="(?:thead|ttext)">(.*?)</span>', row_html, re.DOTALL)
        cells = [_strip(c) for c in cells]
        if len(cells) < 8 or cells[0] in ("Port", ""):
            continue
        port, status = cells[0], cells[1]
        try:
            tx_bps = max(0, int(cells[5]))
            rx_bps = max(0, int(cells[6]))
        except (ValueError, IndexError):
            tx_bps = rx_bps = 0
        result.append({"port": port, "status": status, "tx_bps": tx_bps, "rx_bps": rx_bps})
    return result


# ── data model ────────────────────────────────────────────────────────────────


class RouterData:
    def __init__(self) -> None:
        self.settings: dict[str, str] = {}
        self.info: dict[str, str] = {}
        self.devices: list[dict] = []
        self.iface_stats: list[dict] = []
        self.last_updated: datetime | None = None
        self.error: str | None = None

    def fetch_all(self) -> None:
        try:
            self.settings = _parse_current_settings(_get("currentsetting.htm"))
            self.info = _parse_router_info(_get("ADVANCED_home2.htm"))
            self.devices = _parse_devices(_get("DEV_device.htm"))
            self.iface_stats = _parse_iface_stats(_get("RST_stattbl.htm"))
            self.last_updated = datetime.now()
            self.error = None
        except Exception as e:
            self.error = str(e)

    @property
    def model(self) -> str:
        return self.settings.get("Model", "—")

    @property
    def firmware(self) -> str:
        fw = self.info.get("Firmware Version", self.settings.get("Firmware", "—"))
        return fw.split("_")[0]  # trim the build suffix

    @property
    def internet_up(self) -> bool:
        return self.settings.get("InternetConnectionStatus", "").lower() == "up"

    @property
    def lan_ip(self) -> str:
        # The router serves on ROUTER_HOST; the HTML field may be empty in AP mode
        return self.info.get("IP Address") or ROUTER_HOST

    @property
    def lan_mac(self) -> str:
        return self.info.get("MAC Address", "—")

    @property
    def gateway(self) -> str:
        return self.info.get("Gateway IP Address", "—")

    @property
    def dns(self) -> str:
        return self.info.get("Domain Name Server", "—") or "—"

    @property
    def ssid(self) -> str:
        return self.info.get("Name (SSID)", "—")

    @property
    def mode(self) -> str:
        raw = self.info.get("Operation Mode") or self.info.get("enable_apmode", "")
        if raw in ("1", "AP"):
            return "Access Point"
        if raw in ("0", "Router"):
            return "Router"
        return raw or "—"

    def band_rows(self) -> list[tuple[str, str, str]]:
        return [
            (
                "2.4 GHz",
                self.info.get("2.4 GHz Channel", "?"),
                self.info.get("2.4 GHz Wireless mode:", "—"),
            ),
            (
                "5 GHz",
                self.info.get("5 GHz Channel", "?"),
                self.info.get("5 GHz Wireless mode:", "—"),
            ),
            ("5 GHz BH", self.info.get("5G-2 Channel", "?"), self.info.get("5G-2 Mode:", "—")),
            (
                "6 GHz",
                self.info.get("6 GHz Channel", "?"),
                self.info.get("6 GHz Wireless mode:", "—"),
            ),
        ]

    def band_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.devices:
            counts[d["band"]] = counts.get(d["band"], 0) + 1
        return counts


# ── panel widgets ─────────────────────────────────────────────────────────────


def _kv(label: str, value: str, label_width: int = 14) -> str:
    return f"  [dim]{label:<{label_width}}[/]  {value}"


class RouterInfoPanel(Static):
    def update_data(self, d: RouterData) -> None:
        status_color = "bright_green" if d.internet_up else "bright_red"
        status_text = "UP" if d.internet_up else "DOWN"

        lines = [
            "[bold cyan]● Router Info[/]",
            "",
            _kv("Model", f"[bold]{d.model}[/]"),
            _kv("Firmware", d.firmware),
            _kv("Mode", d.mode),
            "",
            _kv("Internet", f"[{status_color}]● {status_text}[/]"),
            _kv("LAN IP", d.lan_ip),
            _kv("LAN MAC", d.lan_mac),
            _kv("Gateway", d.gateway),
            _kv("DNS", d.dns),
            "",
            _kv("SSID", f"[bright_yellow]{d.ssid}[/]"),
        ]
        self.update("\n".join(lines))


class WiFiBandsPanel(Static):
    BAND_COLORS = {
        "2.4 GHz": "bright_yellow",
        "5 GHz": "bright_green",
        "5 GHz BH": "cyan",
        "6 GHz": "bright_magenta",
    }
    MBPS_THRESHOLDS = [200, 400, 600, 800, 1000, 1500, 2000, 3000]

    def update_data(self, d: RouterData) -> None:
        counts = d.band_counts()
        lines = ["[bold cyan]◈ WiFi Bands[/]", ""]

        for band, channel, speed_raw in d.band_rows():
            color = self.BAND_COLORS.get(band, "white")
            ch_str = f"ch {channel:>4}" if channel and channel != "?" else "ch    ?"
            n_devs = counts.get(band, 0)
            devs_str = f"{n_devs:>2} dev" if n_devs else " — dev"

            mbps_m = re.search(r"([\d.]+)\s*Mbps", speed_raw)
            if mbps_m:
                mbps = float(mbps_m.group(1))
                filled = sum(1 for t in self.MBPS_THRESHOLDS if mbps >= t)
                bar = "█" * filled + "░" * (8 - filled)
                speed_str = f"{int(mbps):>5} Mbps"
            else:
                bar = "░" * 8
                speed_str = "    — Mbps"

            lines.append(
                f"  [{color}]{band:<10}[/]  {ch_str}  [{color}]{bar}[/]"
                f"  {speed_str}  [dim]{devs_str}[/]"
            )

        self.update("\n".join(lines))


class DeviceSummaryPanel(Static):
    BAND_COLORS = {
        "Wired": "bright_cyan",
        "2.4 GHz": "bright_yellow",
        "5 GHz": "bright_green",
        "5 GHz BH": "cyan",
        "6 GHz": "bright_magenta",
    }

    def update_data(self, d: RouterData) -> None:
        counts = d.band_counts()
        total = len(d.devices)
        lines = [f"[bold cyan]◉ Devices  [bright_white]{total} total[/][/]", ""]

        for band in ("Wired", "2.4 GHz", "5 GHz", "5 GHz BH", "6 GHz"):
            n = counts.get(band, 0)
            if not n:
                continue
            c = self.BAND_COLORS.get(band, "white")
            bar = "▪" * min(n, 30)
            lines.append(f"  [{c}]{band:<10}[/]  {bar} [dim]{n}[/]")

        if d.error:
            lines += ["", f"  [bright_red]Error: {d.error[:50]}[/]"]

        self.update("\n".join(lines))


# ── throughput panel ─────────────────────────────────────────────────────────


class ThroughputPanel(Static):
    """Rolling WAN sparkline + per-interface Tx/Rx rates."""

    MAX_HISTORY = 60
    SPARK = "▁▂▃▄▅▆▇█"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._wan_tx: deque[int] = deque(maxlen=self.MAX_HISTORY)
        self._wan_rx: deque[int] = deque(maxlen=self.MAX_HISTORY)

    @staticmethod
    def _fmt(bps: int) -> str:
        if bps >= 1_048_576:
            return f"{bps / 1_048_576:.1f} MB/s"
        if bps >= 1024:
            return f"{bps / 1024:.1f} KB/s"
        return f"{bps} B/s"

    def _sparkline(self, values: deque[int], colour: str) -> str:
        recent = list(values)[-48:]
        if not recent:
            return "[dim]—[/]"
        peak = max(recent) or 1
        chars = "".join(self.SPARK[min(7, int(v / peak * 7))] for v in recent)
        return f"[{colour}]{chars}[/]"

    def update_data(self, d: RouterData) -> None:
        wan = next((r for r in d.iface_stats if r["port"] == "WAN"), None)
        if wan:
            self._wan_tx.append(wan["tx_bps"])
            self._wan_rx.append(wan["rx_bps"])

        lines: list[str] = ["[bold cyan]● Bandwidth[/]", ""]

        # WAN summary + sparklines
        if self._wan_tx:
            tx_now = self._fmt(self._wan_tx[-1])
            rx_now = self._fmt(self._wan_rx[-1])
            n = len(self._wan_tx)
            secs = n * REFRESH_SECS
            history_label = f"{secs // 60}m" if secs >= 60 else f"{secs}s"
            lines += [
                f"  WAN  [bold bright_yellow]↑ {tx_now:<12}[/]  [bold bright_green]↓ {rx_now}[/]",
                "",
                f"  {self._sparkline(self._wan_tx, 'bright_yellow')}  [dim]↑ upload[/]",
                f"  {self._sparkline(self._wan_rx, 'bright_green')}  [dim]↓ download[/]",
                f"  [dim]{n} polls · last {history_label}[/]",
            ]
        else:
            lines.append("  [dim]Collecting data…[/]")

        # Per-interface current rates
        IFACE_LABELS = [
            ("2.4 GHz WLAN", "2.4 GHz", "bright_yellow"),
            ("5 GHz WLAN", "5 GHz  ", "bright_green"),
            ("6 GHz WLAN", "6 GHz  ", "bright_magenta"),
            ("WLAN Backhaul", "BH     ", "cyan"),
        ]
        rows = []
        for prefix, label, colour in IFACE_LABELS:
            iface = next((r for r in d.iface_stats if r["port"].startswith(prefix)), None)
            if iface and (iface["tx_bps"] or iface["rx_bps"]):
                rows.append((label, colour, iface["tx_bps"], iface["rx_bps"]))

        if rows:
            peak = max(max(tx, rx) for _, _, tx, rx in rows) or 1
            lines += ["", "  [bold]Band         ↑ Tx/s          ↓ Rx/s[/]"]
            for label, colour, tx, rx in rows:
                BAR = 6
                tx_bar = "█" * max(1, round(tx / peak * BAR))
                rx_bar = "█" * max(1, round(rx / peak * BAR))
                lines.append(
                    f"  [{colour}]{label}[/]  "
                    f"[bright_yellow]{tx_bar:<{BAR}}[/] {self._fmt(tx):<12}  "
                    f"[bright_green]{rx_bar:<{BAR}}[/] {self._fmt(rx)}"
                )

        if d.error:
            lines += ["", f"  [bright_red]Error: {d.error[:50]}[/]"]

        self.update("\n".join(lines))


# ── devices tab ───────────────────────────────────────────────────────────────


class DevicesView(Widget):
    filter_text: reactive[str] = reactive("")

    BAND_COLORS = {
        "Wired": "bright_cyan",
        "2.4 GHz": "bright_yellow",
        "5 GHz": "bright_green",
        "5 GHz BH": "cyan",
        "6 GHz": "bright_magenta",
    }

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter by IP, name, MAC or band…", id="filter-input")
        yield DataTable(id="device-table", zebra_stripes=True, cursor_type="row")

    def on_mount(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.add_columns("IP Address", "Hostname", "MAC Address", "Band", "Interface")

    def update_devices(self, devices: list[dict]) -> None:
        self._all_devices = list(devices)
        self._apply_filter()

    def _apply_filter(self) -> None:
        tbl = self.query_one(DataTable)
        tbl.clear()
        q = self.filter_text.lower()

        for d in getattr(self, "_all_devices", []):
            if q and not any(q in d[k].lower() for k in ("ip", "name", "mac", "band", "conn")):
                continue
            bc = self.BAND_COLORS.get(d["band"], "white")
            name = d["name"] if d["name"] else "[dim]—[/]"
            tbl.add_row(
                d["ip"],
                name,
                d["mac"],
                f"[{bc}]{d['band']}[/]",
                f"[dim]{d['conn']}[/]",
            )

    @on(Input.Changed, "#filter-input")
    def _on_filter(self, event: Input.Changed) -> None:
        self.filter_text = event.value
        self._apply_filter()


# ── app ───────────────────────────────────────────────────────────────────────


class OrbiApp(App):
    CSS = """
    Screen { background: $surface; }

    TabbedContent { height: 1fr; }
    TabPane       { padding: 1 2; }

    #overview-tab { padding: 0; }
    #left-col     { width: 42; margin: 0 0 0 0; }
    #right-col    { width: 1fr; }

    RouterInfoPanel, WiFiBandsPanel, DeviceSummaryPanel {
        border: round $primary-darken-2;
        padding: 1 2;
        margin: 0 1 1 0;
        height: auto;
        min-width: 38;
    }

    ThroughputPanel {
        border: round $primary-darken-2;
        padding: 1 2;
        height: 1fr;
    }

    DevicesView   { height: 1fr; }
    #filter-input { margin: 0 0 1 0; }
    #device-table { height: 1fr; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("f5", "refresh", "Refresh", show=False),
        Binding("f", "focus_filter", "Filter", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._data = RouterData()
        self._countdown = REFRESH_SECS

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                with Horizontal(id="overview-tab"):
                    with Vertical(id="left-col"):
                        yield RouterInfoPanel(id="router-info")
                        yield DeviceSummaryPanel(id="device-summary")
                    with Vertical(id="right-col"):
                        yield WiFiBandsPanel(id="wifi-bands")
            with TabPane("Devices", id="devices"):
                yield DevicesView(id="devices-view")
            with TabPane("Bandwidth", id="bandwidth"):
                yield ThroughputPanel(id="throughput")
        yield Footer()

    def on_mount(self) -> None:
        self.title = f"Orbi Monitor  ·  {ROUTER_HOST}"
        self.sub_title = "Loading…"
        self._do_fetch()
        self.set_interval(1.0, self._tick)

    # ── refresh timer ──────────────────────────────────────────────────────

    def _tick(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown = REFRESH_SECS
            self._do_fetch()
        self._refresh_subtitle()

    def _refresh_subtitle(self) -> None:
        d = self._data
        if d.error:
            self.sub_title = f"[red]Error: {d.error[:60]}[/]  ⟳ {self._countdown}s"
            return
        status = "● UP" if d.internet_up else "○ DOWN"
        last = d.last_updated.strftime("%H:%M:%S") if d.last_updated else "—"
        self.sub_title = (
            f"Internet {status}  |  {len(d.devices)} devices  "
            f"|  updated {last}  |  ⟳ {self._countdown}s"
        )

    # ── data fetch ─────────────────────────────────────────────────────────

    @work(thread=True)
    def _do_fetch(self) -> None:
        self._data.fetch_all()
        self.call_from_thread(self._update_ui)

    def _update_ui(self) -> None:
        d = self._data
        self.query_one("#router-info", RouterInfoPanel).update_data(d)
        self.query_one("#wifi-bands", WiFiBandsPanel).update_data(d)
        self.query_one("#device-summary", DeviceSummaryPanel).update_data(d)
        self.query_one("#devices-view", DevicesView).update_devices(d.devices)
        self.query_one("#throughput", ThroughputPanel).update_data(d)
        self._refresh_subtitle()

    # ── actions ────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._countdown = REFRESH_SECS
        self._do_fetch()

    def action_focus_filter(self) -> None:
        try:
            self.query_one("#filter-input", Input).focus()
        except Exception:
            pass


if __name__ == "__main__":
    OrbiApp().run()
