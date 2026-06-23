"""Tests for core.clients.sabnzbd (SABnzbd connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.sabnzbd import SabnzbdClient

_BASE = "http://sab:8080"
_API = f"{_BASE}/api"


@respx.mock
async def test_valid_key_succeeds() -> None:
    route = respx.get(_API).mock(
        return_value=httpx.Response(200, json={"queue": {"status": "Idle"}})
    )
    # Trailing slash in the base URL must be normalised away.
    result = await SabnzbdClient(base_url=_BASE + "/", api_key="zk").test_connection()
    assert result == {"ok": True, "detail": "Connected to SABnzbd"}
    assert route.calls.last.request.url.params["apikey"] == "zk"


@respx.mock
async def test_invalid_key_reports_error_body() -> None:
    # SABnzbd answers a bad key with HTTP 200 and the reason in the body.
    respx.get(_API).mock(
        return_value=httpx.Response(
            200, json={"status": False, "error": "API Key Incorrect"}
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="bad").test_connection()
    assert result == {"ok": False, "detail": "API Key Incorrect"}


@respx.mock
async def test_non_200_reports_http_status() -> None:
    respx.get(_API).mock(return_value=httpx.Response(500))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result["ok"] is False
    assert "500" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_API).mock(side_effect=httpx.ConnectError("down"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_non_json_body_is_handled() -> None:
    # A 200 whose body is not JSON must degrade gracefully, not raise.
    respx.get(_API).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result == {"ok": False, "detail": "Unexpected response from SABnzbd"}


@respx.mock
async def test_update_credentials_changes_target() -> None:
    new_api = "http://other:9090/api"
    route = respx.get(new_api).mock(
        return_value=httpx.Response(200, json={"queue": {}})
    )
    client = SabnzbdClient(base_url=_BASE, api_key="x")
    client.update_credentials(base_url="http://other:9090/", api_key="k2")
    result = await client.test_connection()
    assert result["ok"] is True
    assert route.calls.last.request.url.params["apikey"] == "k2"


async def test_aclose() -> None:
    await SabnzbdClient(base_url=_BASE, api_key="x").aclose()
