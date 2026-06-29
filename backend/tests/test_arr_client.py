"""Tests for core.clients.arr_client (Sonarr/Radarr outbound client)."""

from __future__ import annotations

import httpx
import respx

from core.clients.arr_client import ArrClient

_BASE = "http://sonarr:8989"


def make_client(*, name="sonarr", base_url=_BASE + "/", api_key="key"):
    return ArrClient(name=name, base_url=base_url, api_key=api_key)


@respx.mock
async def test_test_connection_ok_with_version() -> None:
    respx.get(f"{_BASE}/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"appName": "Sonarr", "version": "4.0.1"})
    )
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to Sonarr 4.0.1"}


@respx.mock
async def test_test_connection_ok_without_version() -> None:
    respx.get(f"{_BASE}/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={})
    )
    # appName falls back to the configured name; no version appended.
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to sonarr"}


@respx.mock
async def test_test_connection_unauthorised() -> None:
    respx.get(f"{_BASE}/api/v3/system/status").mock(return_value=httpx.Response(401))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "401" in result["detail"]


@respx.mock
async def test_test_connection_network_error() -> None:
    respx.get(f"{_BASE}/api/v3/system/status").mock(
        side_effect=httpx.ConnectError("down")
    )
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_update_credentials_changes_target() -> None:
    respx.get("http://radarr:7878/api/v3/system/status").mock(
        return_value=httpx.Response(200, json={"appName": "Radarr"})
    )
    client = make_client()
    client.update_credentials(base_url="http://radarr:7878/", api_key="k2")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to Radarr"}


_RADARR_BASE = "http://radarr:7878"


@respx.mock
async def test_library_items_sonarr_uses_series_endpoint() -> None:
    route = respx.get(f"{_BASE}/api/v3/series").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"tvdbId": 121361, "tmdbId": 1399, "title": "GoT"},
                "broken",  # non-dict entries are dropped
            ],
        )
    )
    items = await make_client(name="sonarr").library_items()
    assert items == [{"tvdbId": 121361, "tmdbId": 1399, "title": "GoT"}]
    assert route.called


@respx.mock
async def test_library_items_radarr_uses_movie_endpoint() -> None:
    respx.get(f"{_RADARR_BASE}/api/v3/movie").mock(
        return_value=httpx.Response(200, json=[{"tmdbId": 603, "title": "The Matrix"}])
    )
    items = await make_client(
        name="radarr", base_url=_RADARR_BASE + "/"
    ).library_items()
    assert items == [{"tmdbId": 603, "title": "The Matrix"}]


async def test_library_items_unconfigured_returns_empty() -> None:
    # No HTTP route registered: an unconfigured client must not even call out.
    client = make_client(base_url="", api_key="")
    assert await client.library_items() == []


@respx.mock
async def test_library_items_non_200_returns_empty() -> None:
    respx.get(f"{_BASE}/api/v3/series").mock(return_value=httpx.Response(500))
    assert await make_client(name="sonarr").library_items() == []


@respx.mock
async def test_library_items_network_error_returns_empty() -> None:
    respx.get(f"{_BASE}/api/v3/series").mock(side_effect=httpx.ConnectError("down"))
    assert await make_client(name="sonarr").library_items() == []


async def test_aclose() -> None:
    await make_client().aclose()


def test_connection_fields_returns_internal_copy() -> None:
    assert make_client().connection_fields() == {"base_url": _BASE, "api_key": "key"}
