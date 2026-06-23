"""Tests for core.clients.tmdb (TMDB connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.tmdb import TmdbClient

_URL = "https://api.themoviedb.org/3/configuration"


@respx.mock
async def test_v3_key_uses_query_param_and_succeeds() -> None:
    route = respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"images": {}})
    )
    result = await TmdbClient(api_key="v3key").test_connection()
    assert result == {"ok": True, "detail": "Connected to TMDB"}
    # A v3 key is presented as the api_key query parameter.
    assert route.calls.last.request.url.params["api_key"] == "v3key"
    assert "Authorization" not in route.calls.last.request.headers


@respx.mock
async def test_v4_token_uses_bearer_header() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json={}))
    token = "eyJabc.def.ghi"  # JWT-shaped read-access token
    result = await TmdbClient(api_key=token).test_connection()
    assert result["ok"] is True
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {token}"
    assert "api_key" not in route.calls.last.request.url.params


@respx.mock
async def test_unauthorised_reports_http_status() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(401, json={}))
    result = await TmdbClient(api_key="bad").test_connection()
    assert result["ok"] is False
    assert "401" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    result = await TmdbClient(api_key="x").test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_update_credentials_changes_key() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json={}))
    client = TmdbClient(api_key="old")
    client.update_credentials(api_key="new")
    await client.test_connection()
    assert route.calls.last.request.url.params["api_key"] == "new"


_MOVIE_DETAILS = "https://api.themoviedb.org/3/movie/603"
_TV_DETAILS = "https://api.themoviedb.org/3/tv/1399"
_IMAGE = "https://image.tmdb.org/t/p/w342/poster.jpg"


@respx.mock
async def test_fetch_poster_movie_downloads_image() -> None:
    respx.get(_MOVIE_DETAILS).mock(
        return_value=httpx.Response(200, json={"poster_path": "/poster.jpg"})
    )
    respx.get(_IMAGE).mock(return_value=httpx.Response(200, content=b"JPEGDATA"))
    data = await TmdbClient(api_key="v3key").fetch_poster(
        media_type="movie", tmdb_id=603
    )
    assert data == b"JPEGDATA"


@respx.mock
async def test_fetch_poster_show_uses_tv_endpoint() -> None:
    route = respx.get(_TV_DETAILS).mock(
        return_value=httpx.Response(200, json={"poster_path": "/poster.jpg"})
    )
    respx.get(_IMAGE).mock(return_value=httpx.Response(200, content=b"X"))
    data = await TmdbClient(api_key="v3key").fetch_poster(
        media_type="show", tmdb_id=1399
    )
    assert data == b"X"
    assert route.called


@respx.mock
async def test_fetch_poster_missing_path_returns_none() -> None:
    respx.get(_MOVIE_DETAILS).mock(
        return_value=httpx.Response(200, json={"poster_path": None})
    )
    result = await TmdbClient(api_key="x").fetch_poster(media_type="movie", tmdb_id=603)
    assert result is None


@respx.mock
async def test_fetch_poster_details_non_200_returns_none() -> None:
    respx.get(_MOVIE_DETAILS).mock(return_value=httpx.Response(404, json={}))
    result = await TmdbClient(api_key="x").fetch_poster(media_type="movie", tmdb_id=603)
    assert result is None


@respx.mock
async def test_fetch_poster_details_network_error_returns_none() -> None:
    respx.get(_MOVIE_DETAILS).mock(side_effect=httpx.ConnectError("down"))
    result = await TmdbClient(api_key="x").fetch_poster(media_type="movie", tmdb_id=603)
    assert result is None


@respx.mock
async def test_fetch_poster_image_non_200_returns_none() -> None:
    respx.get(_MOVIE_DETAILS).mock(
        return_value=httpx.Response(200, json={"poster_path": "/poster.jpg"})
    )
    respx.get(_IMAGE).mock(return_value=httpx.Response(500))
    result = await TmdbClient(api_key="x").fetch_poster(media_type="movie", tmdb_id=603)
    assert result is None


@respx.mock
async def test_fetch_poster_image_network_error_returns_none() -> None:
    respx.get(_MOVIE_DETAILS).mock(
        return_value=httpx.Response(200, json={"poster_path": "/poster.jpg"})
    )
    respx.get(_IMAGE).mock(side_effect=httpx.ConnectError("down"))
    result = await TmdbClient(api_key="x").fetch_poster(media_type="movie", tmdb_id=603)
    assert result is None


async def test_aclose() -> None:
    await TmdbClient(api_key="x").aclose()
