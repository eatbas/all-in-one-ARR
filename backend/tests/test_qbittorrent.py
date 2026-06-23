"""Tests for core.clients.qbittorrent (qBittorrent WebUI login test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.qbittorrent import QbittorrentClient

_BASE = "http://qb:8080"
_LOGIN = f"{_BASE}/api/v2/auth/login"
_VERSION = f"{_BASE}/api/v2/app/version"


def make_client(*, base_url=_BASE, username="admin", password="pw"):
    return QbittorrentClient(base_url=base_url, username=username, password=password)


@respx.mock
async def test_login_ok_with_version() -> None:
    login = respx.post(_LOGIN).mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v4.6.0"))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v4.6.0"}
    # The login carries the matching Referer for CSRF protection.
    assert login.calls.last.request.headers["Referer"] == _BASE


@respx.mock
async def test_login_ok_version_unavailable_falls_back() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(_VERSION).mock(return_value=httpx.Response(403))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent"}


@respx.mock
async def test_login_ok_204_no_content_succeeds() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(204))
    respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v5.0.0"))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.0.0"}


@respx.mock
async def test_login_ok_version_network_error_falls_back() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(_VERSION).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent"}


@respx.mock
async def test_login_fails_reports_invalid_credentials() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(200, text="Fails."))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "Invalid username or password"}


@respx.mock
async def test_login_forbidden_reports_403() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(403))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "403" in result["detail"]


@respx.mock
async def test_login_other_status_reports_http() -> None:
    respx.post(_LOGIN).mock(return_value=httpx.Response(500))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "500" in result["detail"]


@respx.mock
async def test_login_network_error_is_reported() -> None:
    respx.post(_LOGIN).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_update_credentials_changes_target() -> None:
    new_login = "http://other:9090/api/v2/auth/login"
    new_version = "http://other:9090/api/v2/app/version"
    respx.post(new_login).mock(return_value=httpx.Response(200, text="Ok."))
    respx.get(new_version).mock(return_value=httpx.Response(200, text="v5"))
    client = make_client()
    client.update_credentials(base_url="http://other:9090/", username="u", password="p")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5"}


async def test_aclose() -> None:
    await make_client().aclose()
