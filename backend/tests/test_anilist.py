"""Tests for core.clients.anilist (keyless GraphQL discovery)."""

from __future__ import annotations

import json

import httpx
import respx

from core.clients.anilist import AnilistClient

_URL = "https://graphql.anilist.co"


def _page(media: list[dict]) -> httpx.Response:
    return httpx.Response(200, json={"data": {"Page": {"media": media}}})


def _media(
    anilist_id: int,
    *,
    mal_id: int | None = None,
    english: str | None = "English Title",
    romaji: str = "Romaji Title",
    season_year: int | None = 2026,
    start_year: int | None = 2025,
    cover: str | None = "https://img.anili.st/cover.jpg",
) -> dict:
    return {
        "id": anilist_id,
        "idMal": mal_id,
        "title": {"romaji": romaji, "english": english},
        "format": "TV",
        "seasonYear": season_year,
        "startDate": {"year": start_year},
        "coverImage": {"large": cover},
    }


def _variables(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content)["variables"]


@respx.mock
async def test_get_trending_show_sends_sort_and_formats() -> None:
    route = respx.post(_URL).mock(
        side_effect=[_page([_media(1, mal_id=10)]), _page([])]
    )
    rows = await AnilistClient().get_trending(media_type="show", limit=5)
    assert rows == [
        {
            "media_type": "show",
            "anilist": 1,
            "mal": 10,
            "title": "English Title",
            "year": 2026,
            "poster_url": "https://img.anili.st/cover.jpg",
        }
    ]
    variables = json.loads(route.calls[0].request.content)["variables"]
    assert variables["sort"] == ["TRENDING_DESC"]
    assert variables["formats"] == ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"]
    assert variables["perPage"] == 50


@respx.mock
async def test_get_popular_movie_sends_popularity_sort() -> None:
    route = respx.post(_URL).mock(side_effect=[_page([_media(2)]), _page([])])
    rows = await AnilistClient().get_popular(media_type="movie", limit=5)
    assert rows[0]["media_type"] == "movie"
    variables = json.loads(route.calls[0].request.content)["variables"]
    assert variables["sort"] == ["POPULARITY_DESC"]
    assert variables["formats"] == ["MOVIE"]


@respx.mock
async def test_title_falls_back_to_romaji_and_year_to_start_date() -> None:
    respx.post(_URL).mock(
        side_effect=[_page([_media(3, english=None, season_year=None)]), _page([])]
    )
    rows = await AnilistClient().get_trending(media_type="show", limit=5)
    assert rows[0]["title"] == "Romaji Title"
    assert rows[0]["year"] == 2025


@respx.mock
async def test_paging_concatenates_until_limit_and_caps() -> None:
    first = [_media(anilist_id) for anilist_id in range(1, 51)]
    second = [_media(anilist_id) for anilist_id in range(51, 101)]
    route = respx.post(_URL).mock(side_effect=[_page(first), _page(second)])
    rows = await AnilistClient().get_trending(media_type="show", limit=60)
    assert len(rows) == 60
    assert route.call_count == 2
    assert _variables(route)["page"] == 2


@respx.mock
async def test_paging_stops_on_empty_page() -> None:
    route = respx.post(_URL).mock(side_effect=[_page([_media(1)]), _page([])])
    rows = await AnilistClient().get_trending(media_type="show", limit=60)
    assert [row["anilist"] for row in rows] == [1]
    assert route.call_count == 2


async def test_aclose_closes_the_http_client() -> None:
    client = AnilistClient()
    await client.aclose()


@respx.mock
async def test_missing_optional_fields_normalise_to_none() -> None:
    respx.post(_URL).mock(
        side_effect=[
            _page([{"id": 4, "idMal": None, "title": None, "startDate": None}]),
            _page([]),
        ]
    )
    rows = await AnilistClient().get_trending(media_type="show", limit=5)
    assert rows == [
        {
            "media_type": "show",
            "anilist": 4,
            "mal": None,
            "title": None,
            "year": None,
            "poster_url": None,
        }
    ]
