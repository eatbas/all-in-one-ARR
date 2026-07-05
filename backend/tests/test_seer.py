"""Tests for core.clients.seer."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.seer import AVAILABLE, SeerClient, SeerError, SeerUnavailableError

_BASE = "http://js:5055"


def make_client():
    return SeerClient(base_url=_BASE + "/", api_key="key")


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
    with pytest.raises(SeerError):
        await client.get_status(media_type="movie", tmdb_id=400)


@respx.mock
async def test_get_status_network_error_raises() -> None:
    respx.get(f"{_BASE}/api/v1/movie/500").mock(side_effect=httpx.ConnectError("boom"))
    client = make_client()
    with pytest.raises(SeerError):
        await client.get_status(media_type="movie", tmdb_id=500)


@respx.mock
async def test_get_status_connect_error_raises_unavailable() -> None:
    # A connection-level failure means Seer was never reached: it is classified as
    # SeerUnavailableError so loops can stop hammering a dead host for the cycle.
    respx.get(f"{_BASE}/api/v1/movie/500").mock(side_effect=httpx.ConnectError("down"))
    client = make_client()
    with pytest.raises(SeerUnavailableError):
        await client.get_status(media_type="movie", tmdb_id=500)


@respx.mock
async def test_get_status_connect_timeout_raises_unavailable() -> None:
    respx.get(f"{_BASE}/api/v1/movie/500").mock(
        side_effect=httpx.ConnectTimeout("too slow")
    )
    client = make_client()
    with pytest.raises(SeerUnavailableError):
        await client.get_status(media_type="movie", tmdb_id=500)


@respx.mock
async def test_get_status_read_timeout_is_not_unavailable() -> None:
    # A read timeout means Seer WAS reached but responded slowly: a plain SeerError,
    # so callers keep treating it as a per-item failure rather than an outage.
    respx.get(f"{_BASE}/api/v1/movie/500").mock(side_effect=httpx.ReadTimeout("slow"))
    client = make_client()
    with pytest.raises(SeerError) as excinfo:
        await client.get_status(media_type="movie", tmdb_id=500)
    assert not isinstance(excinfo.value, SeerUnavailableError)


def test_default_client_has_tight_connect_timeout() -> None:
    # The OS-level connect retry to a dead host can take 20+ seconds; the default
    # client must bound the connect phase well below that.
    client = make_client()
    assert client._client.timeout.connect == 5.0


@respx.mock
async def test_get_request_ids_returns_ids() -> None:
    # Request entries without an id are skipped; the rest are returned in order.
    respx.get(f"{_BASE}/api/v1/movie/100").mock(
        return_value=httpx.Response(
            200,
            json={"mediaInfo": {"requests": [{"id": 371}, {"id": None}, {"id": 5}]}},
        )
    )
    client = make_client()
    assert await client.get_request_ids(media_type="movie", tmdb_id=100) == [371, 5]


@respx.mock
async def test_get_request_ids_empty_when_no_media_info() -> None:
    respx.get(f"{_BASE}/api/v1/tv/200").mock(return_value=httpx.Response(404))
    client = make_client()
    assert await client.get_request_ids(media_type="tv", tmdb_id=200) == []


@respx.mock
async def test_get_request_ids_network_error_raises() -> None:
    respx.get(f"{_BASE}/api/v1/movie/100").mock(side_effect=httpx.ConnectError("x"))
    client = make_client()
    with pytest.raises(SeerError):
        await client.get_request_ids(media_type="movie", tmdb_id=100)


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
async def test_create_request_accepts_accepted_response() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(
        return_value=httpx.Response(202, json={"id": 9})
    )
    client = make_client()
    assert await client.create_request(media_type="movie", tmdb_id=100) == 9


@respx.mock
async def test_create_request_accepted_without_body_returns_none() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(return_value=httpx.Response(202))
    client = make_client()
    assert await client.create_request(media_type="movie", tmdb_id=100) is None


@respx.mock
async def test_create_request_error_status_raises() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(return_value=httpx.Response(409))
    client = make_client()
    with pytest.raises(SeerError):
        await client.create_request(media_type="movie", tmdb_id=100)


@respx.mock
async def test_create_request_network_error_raises() -> None:
    respx.post(f"{_BASE}/api/v1/request").mock(side_effect=httpx.ConnectError("x"))
    client = make_client()
    with pytest.raises(SeerError):
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
    with pytest.raises(SeerError):
        await client.delete_request(request_id=7)


@respx.mock
async def test_delete_request_network_error_raises() -> None:
    respx.delete(f"{_BASE}/api/v1/request/7").mock(side_effect=httpx.ConnectError("x"))
    client = make_client()
    with pytest.raises(SeerError):
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


@respx.mock
async def test_discover_trending_filters_people_and_maps_status() -> None:
    respx.get(f"{_BASE}/api/v1/discover/trending").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 603,
                        "mediaType": "movie",
                        "title": "The Matrix",
                        "releaseDate": "1999-03-31",
                        "mediaInfo": {"status": AVAILABLE},
                    },
                    {
                        "id": 1399,
                        "mediaType": "tv",
                        "name": "Game of Thrones",
                        "firstAirDate": "2011-04-17",
                    },
                    {"id": 5, "mediaType": "person", "name": "Keanu Reeves"},  # dropped
                ]
            },
        )
    )
    rows = await make_client().discover_trending(limit=10)
    assert rows == [
        {
            "media_type": "movie",
            "tmdb": 603,
            "title": "The Matrix",
            "year": 1999,
            "seer_status": AVAILABLE,
        },
        {
            "media_type": "show",
            "tmdb": 1399,
            "title": "Game of Thrones",
            "year": 2011,
            "seer_status": None,
        },
    ]


@respx.mock
async def test_discover_popular_movies_uses_default_media_type() -> None:
    route = respx.get(f"{_BASE}/api/v1/discover/movies").mock(
        return_value=httpx.Response(
            200,
            # No mediaType on the result; the type-specific endpoint supplies the default.
            json={"results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-31"}]},
        )
    )
    rows = await make_client().discover_popular(media_type="movie", limit=10)
    assert rows == [
        {"media_type": "movie", "tmdb": 603, "title": "The Matrix", "year": 1999, "seer_status": None}
    ]
    assert route.calls.last.request.url.params["sortBy"] == "popularity.desc"


@respx.mock
async def test_discover_popular_tv_endpoint_and_cap() -> None:
    respx.get(f"{_BASE}/api/v1/discover/tv").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 1, "name": "A", "firstAirDate": "2020-01-01"},
                    {"id": 2, "name": "B", "firstAirDate": "2021-01-01"},
                ]
            },
        )
    )
    rows = await make_client().discover_popular(media_type="show", limit=1)
    assert [row["tmdb"] for row in rows] == [1]


@respx.mock
async def test_discover_popular_concatenates_pages_and_stops_when_empty() -> None:
    respx.get(f"{_BASE}/api/v1/discover/movies").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"results": [{"id": 1, "title": "A", "release_date": "2020-01-01"}]},
            ),
            httpx.Response(
                200,
                json={"results": [{"id": 2, "title": "B", "release_date": "2021-01-01"}]},
            ),
            httpx.Response(200, json={"results": []}),
        ]
    )
    rows = await make_client().discover_popular(media_type="movie", limit=40, pages=3)
    assert [row["tmdb"] for row in rows] == [1, 2]


@respx.mock
async def test_discover_trending_stops_on_empty_page() -> None:
    respx.get(f"{_BASE}/api/v1/discover/trending").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": 1,
                            "mediaType": "movie",
                            "title": "A",
                            "releaseDate": "2020-01-01",
                        }
                    ]
                },
            ),
            httpx.Response(200, json={"results": []}),
        ]
    )
    rows = await make_client().discover_trending(limit=40, pages=3)
    assert [row["tmdb"] for row in rows] == [1]


@respx.mock
async def test_discover_non_200_raises() -> None:
    respx.get(f"{_BASE}/api/v1/discover/trending").mock(return_value=httpx.Response(500))
    with pytest.raises(SeerError):
        await make_client().discover_trending()


@respx.mock
async def test_discover_network_error_raises() -> None:
    respx.get(f"{_BASE}/api/v1/discover/trending").mock(
        side_effect=httpx.ConnectError("down")
    )
    with pytest.raises(SeerError):
        await make_client().discover_trending()


async def test_aclose() -> None:
    await make_client().aclose()


def json_body(route):
    import json

    return json.loads(route.calls.last.request.content)
