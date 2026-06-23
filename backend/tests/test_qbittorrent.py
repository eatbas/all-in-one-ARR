"""Tests for core.clients.qbittorrent (qBittorrent WebUI API-key test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.qbittorrent import QbittorrentClient

_BASE = "http://qb:8080"
_VERSION = f"{_BASE}/api/v2/app/version"
_KEY = "qbt_0123456789abcdefghijklmnop"


def make_client(*, base_url=_BASE, api_key=_KEY):
    return QbittorrentClient(base_url=base_url, api_key=api_key)


@respx.mock
async def test_connection_ok_with_version() -> None:
    version = respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v5.2.0"))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.2.0"}
    # The key is sent as a Bearer token; a matching Referer is sent defensively.
    request = version.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    assert request.headers["Referer"] == _BASE


@respx.mock
async def test_connection_ok_empty_version_falls_back() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(200, text=""))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent"}


@respx.mock
async def test_invalid_key_401_reports_rejected() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(401))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "qBittorrent rejected the API key"}


@respx.mock
async def test_invalid_key_403_reports_rejected() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(403))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "qBittorrent rejected the API key"}


@respx.mock
async def test_other_status_reports_http() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(500))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "500" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_VERSION).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_update_credentials_changes_target() -> None:
    new_version = "http://other:9090/api/v2/app/version"
    route = respx.get(new_version).mock(return_value=httpx.Response(200, text="v5.2.1"))
    client = make_client()
    client.update_credentials(base_url="http://other:9090/", api_key="qbt_new")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.2.1"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer qbt_new"


async def test_aclose() -> None:
    await make_client().aclose()
