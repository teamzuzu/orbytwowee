# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## Self-Maintenance Rule
After every major change update this CLAUDE.md file to reflect the current state.

## Running the TUI

```bash
# First-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run
.venv/bin/python orbitui.py
```

All development should use the `.venv` virtualenv — do not install packages globally.

## Configuration

At the top of `orbitui.py`, update these two constants before running:

```python
ROUTER_HOST = "192.168.0.44"   # your Orbi's IP
AUTH = HTTPBasicAuth("admin", "netgearpassword")  # your admin password
```

`REFRESH_SECS` (default 30) controls the auto-refresh interval.

## Architecture

Everything lives in a single file, `orbitui.py`, organised into four layers:

**1. HTTP / scraping layer** (`_get`, `_make_session`, `_parse_*` functions)  
The Orbi web UI requires a two-step XSRF handshake: the first request to a protected endpoint returns 401 and sets a `XSRF_TOKEN` cookie; the second request carrying that cookie succeeds. `_make_session()` handles this by sending a priming request, and `_get()` auto-resets the session on a subsequent 401.

Data is scraped from three pages:
- `currentsetting.htm` — firmware, model, internet status (plain `key=value` inside a `<p id="currentsetting">` tag)
- `ADVANCED_home2.htm` — router info, WiFi band details, SSID (parsed via `basic-text-menu` / `basic-text-content` CSS class pairs; HTML comments are stripped first since some sections like 5G-2 are commented out)
- `DEV_device.htm` — connected device list; the page has two tables — the first has a real band/interface in column 4, the second ("Wireless Devices") repeats the MAC there. Rows where column 4 matches `_MAC_RE` are skipped to avoid duplicates.

**2. Data model** (`RouterData`)  
A plain class that calls `fetch_all()` (blocking, intended to run in a thread) and exposes cleaned properties (`model`, `firmware`, `ssid`, `internet_up`, etc.). `band_rows()` returns the four radio bands; `band_counts()` counts devices per band label.

**3. Panel widgets** (`RouterInfoPanel`, `WiFiBandsPanel`, `DeviceSummaryPanel`)  
Stateless `Static` subclasses. Each has an `update_data(RouterData)` method that re-renders Rich markup into the widget. Layout and colours are inline; band speed bars are computed from `MBPS_THRESHOLDS`.

**4. App** (`OrbiApp`)  
A Textual `App` with two tabs: *Overview* (three panels in a two-column layout) and *Devices* (`DevicesView` — a `DataTable` with a live-filter `Input`). A 1-second `set_interval` drives a countdown; when it hits zero `_do_fetch()` is called via `@work(thread=True)` and `call_from_thread` marshals the UI update back to the main thread.

Key bindings: `r`/`F5` refresh · `f` focus filter · `q` quit.
