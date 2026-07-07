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


_POSTER_URL = "https://m.media-amazon.com/images/poster.jpg"


@respx.mock
async def test_fetch_poster_downloads_image() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200, json={"Response": "True", "Poster": _POSTER_URL}
        )
    )
    respx.get(_POSTER_URL).mock(return_value=httpx.Response(200, content=b"OMDBJPEG"))
    data = await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1")
    assert data == b"OMDBJPEG"


@respx.mock
async def test_fetch_poster_na_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": "N/A"}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_missing_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Title": "x"}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_lookup_non_200_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500, json={}))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_lookup_network_error_returns_none() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_non_json_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_image_non_200_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": _POSTER_URL}))
    respx.get(_POSTER_URL).mock(return_value=httpx.Response(404))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_poster_image_network_error_returns_none() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"Poster": _POSTER_URL}))
    respx.get(_POSTER_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="ok").fetch_poster(imdb_id="tt1") is None


@respx.mock
async def test_fetch_rating_parses_rating_and_votes() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "imdbRating": "8.6", "imdbVotes": "1,234,567"},
        )
    )
    result = await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1")
    assert result == {"imdb_rating": 8.6, "imdb_votes": 1234567}


@respx.mock
async def test_fetch_rating_na_values_become_none() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"imdbRating": "N/A", "imdbVotes": "N/A"})
    )
    assert await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_unparseable_values_become_none() -> None:
    respx.get(_URL).mock(
        return_value=httpx.Response(200, json={"imdbRating": "bad", "imdbVotes": "x"})
    )
    assert await OmdbClient(api_key="ok").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_non_200_returns_empty() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(500, json={}))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_network_error_returns_empty() -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("down"))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


@respx.mock
async def test_fetch_rating_non_json_returns_empty() -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>"))
    assert await OmdbClient(api_key="x").fetch_rating(imdb_id="tt1") == {
        "imdb_rating": None,
        "imdb_votes": None,
    }


async def test_aclose() -> None:
    await OmdbClient(api_key="x").aclose()
