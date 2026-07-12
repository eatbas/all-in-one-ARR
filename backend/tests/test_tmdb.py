"""Tests for core.clients.tmdb (TMDB connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.tmdb import TmdbClient

_URL = "https://api.themoviedb.org/3/configuration"


@respx.mock
async def test_v3_key_uses_query_param_and_succeeds() -> None:
    route = respx.get(_URL).mock(return_value=httpx.Response(200, json={"images": {}}))
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


_TRENDING_MOVIE = "https://api.themoviedb.org/3/trending/movie/week"
_TRENDING_TV = "https://api.themoviedb.org/3/trending/tv/day"
_POPULAR_MOVIE = "https://api.themoviedb.org/3/movie/popular"
_EXTERNAL_IDS_MOVIE = "https://api.themoviedb.org/3/movie/603/external_ids"
_EXTERNAL_IDS_TV = "https://api.themoviedb.org/3/tv/1399/external_ids"


@respx.mock
async def test_get_trending_movie_normalises_and_caps() -> None:
    respx.get(_TRENDING_MOVIE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 603,
                        "title": "The Matrix",
                        "release_date": "1999-03-31",
                        "vote_average": 8.2,
                    },
                    {"id": 604, "title": "Extra", "release_date": "2003-05-15"},
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_trending(media_type="movie", limit=1)
    assert rows == [
        {"media_type": "movie", "tmdb": 603, "title": "The Matrix", "year": 1999}
    ]


@respx.mock
async def test_get_trending_tv_uses_name_and_day_window() -> None:
    respx.get(_TRENDING_TV).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 1399, "name": "Game of Thrones", "first_air_date": ""}
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_trending(
        media_type="show", window="day", limit=5
    )
    # A blank air date yields a null year.
    assert rows == [
        {"media_type": "show", "tmdb": 1399, "title": "Game of Thrones", "year": None}
    ]


@respx.mock
async def test_get_popular_movie_handles_missing_results() -> None:
    respx.get(_POPULAR_MOVIE).mock(return_value=httpx.Response(200, json={}))
    assert await TmdbClient(api_key="v3key").get_popular(media_type="movie") == []


@respx.mock
async def test_get_popular_fetches_and_concatenates_pages() -> None:
    respx.get(_POPULAR_MOVIE).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": 1, "title": "A", "release_date": "2020-01-01"}]
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [{"id": 2, "title": "B", "release_date": "2021-01-01"}]
                },
            ),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_popular(
        media_type="movie", limit=40, pages=2
    )
    assert [row["tmdb"] for row in rows] == [1, 2]


@respx.mock
async def test_get_trending_stops_on_empty_page() -> None:
    respx.get(_TRENDING_MOVIE).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": 1, "title": "A", "release_date": "2020-01-01"}]
                },
            ),
            httpx.Response(200, json={"results": []}),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_trending(
        media_type="movie", limit=40, pages=3
    )
    assert [row["tmdb"] for row in rows] == [1]


_DISCOVER_MOVIE = "https://api.themoviedb.org/3/discover/movie"
_DISCOVER_TV = "https://api.themoviedb.org/3/discover/tv"


@respx.mock
async def test_get_anime_trending_show_uses_discover_with_anime_filters() -> None:
    route = respx.get(_DISCOVER_TV).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 240411, "name": "Dan Da Dan", "first_air_date": "2024-10-04"}
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_anime_trending(
        media_type="show", limit=5
    )
    assert rows == [
        {"media_type": "show", "tmdb": 240411, "title": "Dan Da Dan", "year": 2024}
    ]
    params = route.calls.last.request.url.params
    assert params["with_genres"] == "16"
    assert params["with_origin_country"] == "JP"
    assert params["sort_by"] == "popularity.desc"


@respx.mock
async def test_get_anime_popular_movie_sorts_by_vote_count() -> None:
    route = respx.get(_DISCOVER_MOVIE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 129, "title": "Spirited Away", "release_date": "2001-07-20"}
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_anime_popular(
        media_type="movie", limit=5
    )
    assert rows == [
        {"media_type": "movie", "tmdb": 129, "title": "Spirited Away", "year": 2001}
    ]
    params = route.calls.last.request.url.params
    assert params["with_genres"] == "16"
    assert params["with_origin_country"] == "JP"
    assert params["sort_by"] == "vote_count.desc"


@respx.mock
async def test_get_anime_trending_pages_and_caps_like_discover() -> None:
    respx.get(_DISCOVER_MOVIE).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [{"id": 1, "title": "A", "release_date": "2020-01-01"}]
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 2, "title": "B", "release_date": "2021-01-01"},
                        {"id": 3, "title": "C", "release_date": "2022-01-01"},
                    ]
                },
            ),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_anime_trending(
        media_type="movie", limit=2, pages=2
    )
    # Pages concatenate before the limit cap, like every other discovery feed.
    assert [row["tmdb"] for row in rows] == [1, 2]


@respx.mock
async def test_fetch_external_ids_returns_imdb_id() -> None:
    respx.get(_EXTERNAL_IDS_MOVIE).mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0133093"})
    )
    imdb = await TmdbClient(api_key="v3key").fetch_external_ids(
        media_type="movie", tmdb_id=603
    )
    assert imdb == "tt0133093"


@respx.mock
async def test_fetch_external_ids_tv_blank_returns_none() -> None:
    respx.get(_EXTERNAL_IDS_TV).mock(
        return_value=httpx.Response(200, json={"imdb_id": ""})
    )
    imdb = await TmdbClient(api_key="v3key").fetch_external_ids(
        media_type="show", tmdb_id=1399
    )
    assert imdb is None


@respx.mock
async def test_fetch_external_ids_non_200_returns_none() -> None:
    respx.get(_EXTERNAL_IDS_MOVIE).mock(return_value=httpx.Response(404, json={}))
    assert (
        await TmdbClient(api_key="x").fetch_external_ids(
            media_type="movie", tmdb_id=603
        )
        is None
    )


@respx.mock
async def test_fetch_external_ids_network_error_returns_none() -> None:
    respx.get(_EXTERNAL_IDS_MOVIE).mock(side_effect=httpx.ConnectError("down"))
    assert (
        await TmdbClient(api_key="x").fetch_external_ids(
            media_type="movie", tmdb_id=603
        )
        is None
    )


async def test_aclose() -> None:
    await TmdbClient(api_key="x").aclose()
