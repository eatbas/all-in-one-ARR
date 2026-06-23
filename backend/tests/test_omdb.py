"""Tests for core.clients.omdb (OMDb connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.omdb import OmdbClient

_URL = "https://www.omdbapi.com"


@respx.mock
async def test_valid_key_succeeds() -> None:
    route = respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "x"})
    )
    result = await OmdbClient(api_key="ok").test_connection()
    assert result == {"ok": True, "detail": "Connected to OMDb"}
    assert route.calls.last.request.url.params["apikey"] == "ok"


@respx.mock
async def test_invalid_key_reports_error_body() -> None:
    # OMDb answers a bad key with HTTP 200 and the reason in the body.
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"Response": "False", "Error": "Invalid API key!"}
        )
    )
    result = await OmdbClient(api_key="bad").test_connection()
    assert result == {"ok": False, "detail": "Invalid API key!"}


@respx.mock
async def test_non_200_reports_http_status() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(401, json={}))
    result = await OmdbClient(api_key="bad").test_connection()
    assert result["ok"] is False
    assert "401" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    result = await OmdbClient(api_key="x").test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_non_json_body_is_handled() -> None:
    # A 200 whose body is not JSON must degrade gracefully, not raise.
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    result = await OmdbClient(api_key="x").test_connection()
    assert result == {"ok": False, "detail": "Unexpected response from OMDb"}


@respx.mock
async def test_update_credentials_changes_key() -> None:
    route = respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"Response": "True"})
    )
    client = OmdbClient(api_key="old")
    client.update_credentials(api_key="new")
    await client.test_connection()
    assert route.calls.last.request.url.params["apikey"] == "new"


async def test_aclose() -> None:
    await OmdbClient(api_key="x").aclose()
