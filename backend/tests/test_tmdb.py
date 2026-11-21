"""Tests for core.clients.tmdb (TMDB connection test)."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.tmdb import TmdbClient, TmdbRequestError

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


_SEARCH_MOVIE = "https://api.themoviedb.org/3/search/movie"
_SEARCH_TV = "https://api.themoviedb.org/3/search/tv"


@respx.mock
async def test_search_movie_sends_query_and_normalises() -> None:
    route = respx.get(_SEARCH_MOVIE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 603, "title": "The Matrix", "release_date": "1999-03-31"}
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").search(
        media_type="movie", query="matrix", limit=5
    )
    assert rows == [
        {"media_type": "movie", "tmdb": 603, "title": "The Matrix", "year": 1999}
    ]
    params = route.calls.last.request.url.params
    assert params["query"] == "matrix"
    assert params["include_adult"] == "false"


@respx.mock
async def test_search_tv_uses_search_endpoint() -> None:
    respx.get(_SEARCH_TV).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 1399, "name": "Game of Thrones", "first_air_date": "2011"}
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").search(
        media_type="show", query="thrones", limit=5
    )
    assert [row["tmdb"] for row in rows] == [1399]


@respx.mock
async def test_search_anime_keeps_only_japanese_animation() -> None:
    route = respx.get(_SEARCH_TV).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 240411,
                        "name": "Dan Da Dan",
                        "first_air_date": "2024-10-04",
                        "genre_ids": [16, 35],
                        "original_language": "ja",
                    },
                    {
                        # Animation but not Japanese: dropped.
                        "id": 1,
                        "name": "Western Cartoon",
                        "genre_ids": [16],
                        "original_language": "en",
                    },
                    {
                        # Japanese but not Animation: dropped.
                        "id": 2,
                        "name": "Live Action Drama",
                        "genre_ids": [18],
                        "original_language": "ja",
                    },
                    {
                        # No genre metadata at all: dropped.
                        "id": 3,
                        "name": "Bare Result",
                    },
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").search_anime(
        media_type="show", query="dan da dan", limit=5
    )
    assert [row["tmdb"] for row in rows] == [240411]
    assert route.calls.last.request.url.params["query"] == "dan da dan"


@respx.mock
async def test_search_anime_pages_past_an_all_filtered_page() -> None:
    respx.get(_SEARCH_MOVIE).mock(
        side_effect=[
            # Every result filtered out, but the response page itself is
            # non-empty, so paging continues to the next page.
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "title": "A", "genre_ids": [28]},
                    ]
                },
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 129,
                            "title": "Spirited Away",
                            "release_date": "2001-07-20",
                            "genre_ids": [16],
                            "original_language": "ja",
                        }
                    ]
                },
            ),
        ]
    )
    rows = await TmdbClient(api_key="v3key").search_anime(
        media_type="movie", query="spirited", limit=5, pages=2
    )
    assert [row["tmdb"] for row in rows] == [129]


@respx.mock
async def test_get_animation_trending_show_uses_genre_only_discover() -> None:
    route = respx.get(_DISCOVER_TV).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 60625,
                        "name": "Rick and Morty",
                        "first_air_date": "2013-12-02",
                        "original_language": "en",
                    },
                    {
                        # Japanese-language animation is anime: dropped.
                        "id": 240411,
                        "name": "Dan Da Dan",
                        "first_air_date": "2024-10-04",
                        "original_language": "ja",
                    },
                    {
                        # No language at all: the feed is already genre
                        # filtered, so the row is kept.
                        "id": 94605,
                        "name": "Arcane",
                        "first_air_date": "2021-11-06",
                    },
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_animation_trending(
        media_type="show", limit=5
    )
    assert rows == [
        {"media_type": "show", "tmdb": 60625, "title": "Rick and Morty", "year": 2013},
        {"media_type": "show", "tmdb": 94605, "title": "Arcane", "year": 2021},
    ]
    params = route.calls.last.request.url.params
    assert params["with_genres"] == "16"
    assert "with_origin_country" not in params
    assert params["sort_by"] == "popularity.desc"


@respx.mock
async def test_get_animation_popular_movie_sorts_by_vote_count() -> None:
    route = respx.get(_DISCOVER_MOVIE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 862,
                        "title": "Toy Story",
                        "release_date": "1995-11-22",
                        "original_language": "en",
                    },
                    {
                        "id": 129,
                        "title": "Spirited Away",
                        "release_date": "2001-07-20",
                        "original_language": "ja",
                    },
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").get_animation_popular(
        media_type="movie", limit=5
    )
    assert rows == [
        {"media_type": "movie", "tmdb": 862, "title": "Toy Story", "year": 1995}
    ]
    params = route.calls.last.request.url.params
    assert params["with_genres"] == "16"
    assert "with_origin_country" not in params
    assert params["sort_by"] == "vote_count.desc"


@respx.mock
async def test_get_animation_trending_pages_past_an_all_filtered_page() -> None:
    respx.get(_DISCOVER_MOVIE).mock(
        side_effect=[
            # Every result is anime, but the response page is non-empty, so
            # paging continues to the next page.
            httpx.Response(
                200,
                json={"results": [{"id": 1, "title": "A", "original_language": "ja"}]},
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 2, "title": "B", "original_language": "en"},
                        {"id": 3, "title": "C", "original_language": "fr"},
                        {"id": 4, "title": "D", "original_language": "en"},
                    ]
                },
            ),
            httpx.Response(200, json={"results": []}),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_animation_trending(
        media_type="movie", limit=2, pages=5
    )
    # Pages concatenate past the filtered page, then the limit caps the result.
    assert [row["tmdb"] for row in rows] == [2, 3]


@respx.mock
async def test_get_animation_trending_stops_once_kept_results_fill_the_limit() -> None:
    route = respx.get(_DISCOVER_TV).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 1, "name": "A", "original_language": "ja"},
                        {"id": 2, "name": "B", "original_language": "en"},
                    ]
                },
            ),
            httpx.Response(
                200,
                json={"results": [{"id": 3, "name": "C", "original_language": "en"}]},
            ),
            # The limit is already met after the filter, so this failure must
            # never be requested.
            httpx.Response(503),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_animation_trending(
        media_type="show", limit=2, pages=10
    )
    assert [row["tmdb"] for row in rows] == [2, 3]
    assert route.call_count == 2


@respx.mock
async def test_get_popular_stops_once_the_limit_is_met() -> None:
    route = respx.get(_POPULAR_MOVIE).mock(
        side_effect=[
            httpx.Response(200, json={"results": [{"id": 1}, {"id": 2}]}),
            httpx.Response(503),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_popular(
        media_type="movie", limit=2, pages=5
    )
    assert [row["tmdb"] for row in rows] == [1, 2]
    assert route.call_count == 1


_SECRET_KEY = "synthetic-v3-secret-key"


@respx.mock
async def test_discovery_http_error_omits_the_api_key() -> None:
    respx.get(_DISCOVER_MOVIE).mock(return_value=httpx.Response(503))
    with pytest.raises(TmdbRequestError) as caught:
        await TmdbClient(api_key=_SECRET_KEY).get_animation_popular(
            media_type="movie", limit=5, pages=2
        )
    message = str(caught.value)
    assert message == "TMDB /3/discover/movie returned HTTP 503"
    assert _SECRET_KEY not in message
    # The keyed httpx error is not chained, so a logged traceback cannot
    # print it either.
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


@respx.mock
async def test_search_transport_error_omits_the_api_key() -> None:
    respx.get(_SEARCH_TV).mock(
        side_effect=httpx.ConnectError(f"failed for ?api_key={_SECRET_KEY}")
    )
    with pytest.raises(TmdbRequestError) as caught:
        await TmdbClient(api_key=_SECRET_KEY).search_animation(
            media_type="show", query="x"
        )
    assert str(caught.value) == "TMDB /3/search/tv request failed: ConnectError"
    assert caught.value.__suppress_context__ is True


@respx.mock
async def test_get_animation_popular_stops_on_empty_page() -> None:
    route = respx.get(_DISCOVER_TV).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"results": [{"id": 1, "name": "A", "original_language": "en"}]},
            ),
            httpx.Response(200, json={"results": []}),
        ]
    )
    rows = await TmdbClient(api_key="v3key").get_animation_popular(
        media_type="show", limit=40, pages=10
    )
    assert [row["tmdb"] for row in rows] == [1]
    assert route.call_count == 2


@respx.mock
async def test_search_animation_keeps_only_non_anime_animation() -> None:
    route = respx.get(_SEARCH_MOVIE).mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 808,
                        "title": "Shrek",
                        "release_date": "2001-05-18",
                        "genre_ids": [16, 35],
                        "original_language": "en",
                    },
                    {
                        # Animation but Japanese: anime, dropped.
                        "id": 129,
                        "title": "Spirited Away",
                        "genre_ids": [16],
                        "original_language": "ja",
                    },
                    {
                        # Not Animation: dropped.
                        "id": 2,
                        "title": "Shrek the Musical",
                        "genre_ids": [10402],
                        "original_language": "en",
                    },
                    {
                        # No genre metadata: search applies no server-side
                        # genre filter, so the row is dropped.
                        "id": 3,
                        "title": "Bare Result",
                        "original_language": "en",
                    },
                    {
                        # Animation with no language: kept.
                        "id": 10192,
                        "title": "Shrek Forever After",
                        "release_date": "2010-05-16",
                        "genre_ids": [16],
                    },
                ]
            },
        )
    )
    rows = await TmdbClient(api_key="v3key").search_animation(
        media_type="movie", query="shrek", limit=5
    )
    assert [row["tmdb"] for row in rows] == [808, 10192]
    params = route.calls.last.request.url.params
    assert params["query"] == "shrek"
    assert params["include_adult"] == "false"


@respx.mock
async def test_search_animation_pages_and_caps() -> None:
    respx.get(_SEARCH_TV).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"results": [{"id": 1, "name": "A", "genre_ids": [18]}]},
            ),
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": 2, "name": "B", "genre_ids": [16]},
                        {"id": 3, "name": "C", "genre_ids": [16]},
                    ]
                },
            ),
        ]
    )
    rows = await TmdbClient(api_key="v3key").search_animation(
        media_type="show", query="b", limit=1, pages=2
    )
    assert [row["tmdb"] for row in rows] == [2]


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
