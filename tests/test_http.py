"""Tests for the HTTP session layer — XSRF handshake, retries, error handling.

Uses `responses` to intercept requests without touching the network.
The module-level `_session` global is reset before every test by the
`reset_orbi_session` autouse fixture in conftest.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests as req
import responses as rsps
from responses import GET

import orbitui

ROUTER_URL = f"http://{orbitui.ROUTER_HOST}"
PRIME_URL = f"{ROUTER_URL}/ADVANCED_home2.htm"
XSRF_COOKIE = {"Set-Cookie": "XSRF_TOKEN=testtoken123; Path=/"}


def _prime_response(status: int = 401) -> None:
    """Register the XSRF-priming response for ADVANCED_home2.htm."""
    rsps.add(GET, PRIME_URL, status=status, headers=XSRF_COOKIE)


# ── _make_session ──────────────────────────────────────────────────────────────


class TestMakeSession:
    @rsps.activate
    def test_sends_priming_request(self):
        _prime_response()
        orbitui._make_session()
        assert len(rsps.calls) == 1
        assert "ADVANCED_home2.htm" in rsps.calls[0].request.url

    @rsps.activate
    def test_returns_requests_session(self):
        _prime_response()
        s = orbitui._make_session()
        assert isinstance(s, req.Session)

    @rsps.activate
    def test_sets_mozilla_user_agent(self):
        _prime_response()
        orbitui._make_session()
        ua = rsps.calls[0].request.headers.get("User-Agent", "")
        assert "Mozilla/5.0" in ua

    @rsps.activate
    def test_session_carries_basic_auth(self):
        _prime_response()
        s = orbitui._make_session()
        assert s.auth == orbitui.AUTH

    @rsps.activate
    def test_xsrf_cookie_is_stored(self):
        _prime_response()
        s = orbitui._make_session()
        # The 401 response plants the XSRF_TOKEN cookie in the session jar
        assert "XSRF_TOKEN" in s.cookies


# ── _get ──────────────────────────────────────────────────────────────────────


class TestGet:
    @rsps.activate
    def test_returns_body_on_200(self):
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/page.htm", status=200, body="<p>hello</p>")
        assert orbitui._get("page.htm") == "<p>hello</p>"

    @rsps.activate
    def test_creates_session_on_first_call(self):
        assert orbitui._session is None
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/page.htm", status=200, body="ok")
        orbitui._get("page.htm")
        assert orbitui._session is not None

    @rsps.activate
    def test_reuses_existing_session(self):
        _prime_response()  # priming
        rsps.add(GET, f"{ROUTER_URL}/a.htm", status=200, body="a")
        rsps.add(GET, f"{ROUTER_URL}/b.htm", status=200, body="b")

        orbitui._get("a.htm")
        orbitui._get("b.htm")

        # Only one priming call; two data calls = 3 total
        assert len(rsps.calls) == 3

    @rsps.activate
    def test_returns_empty_on_404(self):
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/missing.htm", status=404)
        assert orbitui._get("missing.htm") == ""

    @rsps.activate
    def test_returns_empty_on_500(self):
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/broken.htm", status=500)
        assert orbitui._get("broken.htm") == ""

    @rsps.activate
    def test_retries_after_401_on_live_request(self):
        """Session exists but the router cookie expired mid-session."""
        # 1. Initial priming (session creation)
        _prime_response()
        # 2. First real call returns 401 (expired)
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=401)
        # 3. Re-priming
        _prime_response()
        # 4. Retry succeeds
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=200, body="refreshed")

        result = orbitui._get("data.htm")
        assert result == "refreshed"

    @rsps.activate
    def test_raises_permission_error_if_retry_also_401(self):
        """Persistent 401 after re-priming means wrong credentials — raise PermissionError."""
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=401)
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=401)

        import pytest

        with pytest.raises(PermissionError, match="401"):
            orbitui._get("data.htm")

    @rsps.activate
    def test_session_cleared_after_persistent_401(self):
        """Session must be reset so the next call creates a fresh one."""
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=401)
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/data.htm", status=401)

        import pytest

        with pytest.raises(PermissionError):
            orbitui._get("data.htm")
        assert orbitui._session is None

    def test_returns_empty_on_connection_error(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = req.exceptions.ConnectionError("timeout")
        orbitui._session = mock_session

        assert orbitui._get("page.htm") == ""

    def test_resets_session_on_connection_error(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = req.exceptions.ConnectionError("gone")
        orbitui._session = mock_session

        orbitui._get("page.htm")
        assert orbitui._session is None

    def test_returns_empty_on_timeout(self):
        mock_session = MagicMock()
        mock_session.get.side_effect = req.exceptions.Timeout("timed out")
        orbitui._session = mock_session

        assert orbitui._get("page.htm") == ""

    @rsps.activate
    def test_correct_url_constructed(self):
        _prime_response()
        rsps.add(GET, f"{ROUTER_URL}/currentsetting.htm", status=200, body="ok")
        orbitui._get("currentsetting.htm")
        last_url = rsps.calls[-1].request.url
        assert last_url == f"{ROUTER_URL}/currentsetting.htm"

    def test_make_session_called_once_for_multiple_gets(self):
        """_make_session should only be invoked when _session is None."""
        mock_session = MagicMock()
        mock_session.get.return_value = MagicMock(status_code=200, text="data", ok=True)

        with patch("orbitui._make_session", return_value=mock_session) as mock_make:
            orbitui._get("a.htm")
            orbitui._get("b.htm")
            orbitui._get("c.htm")

        assert mock_make.call_count == 1
