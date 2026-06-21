"""Tests for core.clients.jellyseerr."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.jellyseerr import AVAILABLE, JellyseerrClient, JellyseerrError

_BASE = "http://js:5055"


def make_client(*, dry_run=False):
    return JellyseerrClient(
        base_url=_BASE + "/", api_key="key", dry_run_provider=lambda: dry_run
    )


@respx.mock
async def test_get_status_available() -> None:
    respx.get(f"{_BASE}/api/v1/movie/100").mock(
        return_value=httpx.Response(200, json={"mediaInfo": {"status": AVAILABLE}})
    )
    client = make_client()
    assert await client.get_status(media_type="movie", tmdb_id=100) == AVAILABLE


@respx.mock
async def test_get_status_no_media_info() -> None:
    respx.get(f"{_BASE}/api/v1/tv/200").mock(
        return_value=httpx.Response(200, json={"mediaInfo": None})
    )
    client = make_client()
    assert await client.get_status(media_type="tv", tmdb_id=200) is None


@respx.mock
async def test_get_status_404_returns_none() -> None:
    respx.get(f"{_BASE}/api/v1/movie/300").mock(return_value=httpx.Response(404))
    client = make_client()
    assert await client.get_status(media_type="movie", tmdb_id=300) is None


@respx.mock
async def test_get_status_other_error_raises() -> None:
    respx.get(f"{_BASE}/api/v1/movie/400").mock(return_value=httpx.Response(500))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.get_status(media_type="movie", tmdb_id=400)


@respx.mock
async def test_get_status_network_error_raises() -> None:
    respx.get(f"{_BASE}/api/v1/movie/500").mock(side_effect=httpx.ConnectError("boom"))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.get_status(media_type="movie", tmdb_id=500)


async def test_create_request_dry_run_returns_none() -> None:
    client = make_client(dry_run=True)
    assert await client.create_request(media_type="movie", tmdb_id=100) is None


@respx.mock
async def test_create_request_movie() -> None:
    route = respx.post(f"{_BASE}/api/v1/request").mock(
        return_value=httpx.Response(201, json={"id": 7})
    )
    client = make_client()
    assert await client.create_request(media_type="movie", tmdb_id=100) == 7
    assert json_body(route)["mediaType"] == "movie"
    assert "seasons" not in json_body(route)


@respx.mock
async def test_create_request_tv_includes_seasons() -> None:
    route = respx.post(f"{_BASE}/api/v1/request").mock(
        return_value=httpx.Response(200, json={"id": 8})
    )
    client = make_client()
    assert await client.create_request(media_type="tv", tmdb_id=200) == 8
    assert json_body(route)["seasons"] == "all"


@respx.mock
async def test_create_request_error_status_raises() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(return_value=httpx.Response(409))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.create_request(media_type="movie", tmdb_id=100)


@respx.mock
async def test_create_request_network_error_raises() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(side_effect=httpx.ConnectError("x"))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.create_request(media_type="movie", tmdb_id=100)


async def test_aclose() -> None:
    await make_client().aclose()


def json_body(route):
    import json

    return json.loads(route.calls.last.request.content)
