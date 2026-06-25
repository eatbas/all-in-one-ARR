"""Tests for core.clients.jellyseerr."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.jellyseerr import AVAILABLE, JellyseerrClient, JellyseerrError

_BASE = "http://js:5055"


def make_client():
    return JellyseerrClient(base_url=_BASE + "/", api_key="key")


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


@respx.mock
async def test_delete_request() -> None:
    route = respx.delete(f"{_BASE}/api/v1/request/7").mock(
        return_value=httpx.Response(204)
    )
    client = make_client()
    await client.delete_request(request_id=7)
    assert route.called


@respx.mock
async def test_delete_request_404_is_already_gone() -> None:
    respx.delete(f"{_BASE}/api/v1/request/7").mock(return_value=httpx.Response(404))
    client = make_client()
    await client.delete_request(request_id=7)


@respx.mock
async def test_delete_request_error_status_raises() -> None:
    respx.delete(f"{_BASE}/api/v1/request/7").mock(return_value=httpx.Response(500))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.delete_request(request_id=7)


@respx.mock
async def test_delete_request_network_error_raises() -> None:
    respx.delete(f"{_BASE}/api/v1/request/7").mock(side_effect=httpx.ConnectError("x"))
    client = make_client()
    with pytest.raises(JellyseerrError):
        await client.delete_request(request_id=7)


@respx.mock
async def test_test_connection_ok_with_user() -> None:
    respx.get(f"{_BASE}/api/v1/auth/me").mock(
        return_value=httpx.Response(200, json={"username": "erena"})
    )
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected as erena"}


@respx.mock
async def test_test_connection_ok_without_user() -> None:
    respx.get(f"{_BASE}/api/v1/auth/me").mock(
        return_value=httpx.Response(200, json={})
    )
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected"}


@respx.mock
async def test_test_connection_forbidden() -> None:
    respx.get(f"{_BASE}/api/v1/auth/me").mock(return_value=httpx.Response(403))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "403" in result["detail"]


@respx.mock
async def test_test_connection_network_error() -> None:
    respx.get(f"{_BASE}/api/v1/auth/me").mock(
        side_effect=httpx.ConnectError("boom")
    )
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "boom" in result["detail"]


@respx.mock
async def test_update_credentials_changes_target() -> None:
    respx.get("http://new:5055/api/v1/movie/100").mock(
        return_value=httpx.Response(200, json={"mediaInfo": {"status": AVAILABLE}})
    )
    client = make_client()
    client.update_credentials(base_url="http://new:5055/", api_key="key2")
    assert await client.get_status(media_type="movie", tmdb_id=100) == AVAILABLE


async def test_aclose() -> None:
    await make_client().aclose()


def json_body(route):
    import json

    return json.loads(route.calls.last.request.content)
