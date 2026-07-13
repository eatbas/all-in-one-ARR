"""Tests for core.anime_ids (Fribb mapping cache and row enrichment)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from core import anime_ids as anime_ids_mod
from core.anime_ids import AnimeIdMap, MappedIds, _build_indexes, _mapped_ids

_SOURCE_URL = (
    "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-mini.json"
)

# Mirrors the verified source shapes: imdb_id is a list, themoviedb_id is an
# object whose values may be an int or a list of ints.
_ENTRIES = [
    {
        "type": "TV",
        "anilist_id": 290,
        "mal_id": 290,
        "imdb_id": ["tt0286390"],
        "themoviedb_id": {"tv": 26209},
        "tvdb_id": 72025,
    },
    {
        "type": "MOVIE",
        "anilist_id": 164,
        "mal_id": 164,
        "imdb_id": ["tt0119698"],
        "themoviedb_id": {"movie": [128]},
    },
    # MAL-only entry: reachable through the mal_id fallback.
    {"type": "TV", "mal_id": 500, "tvdb_id": 999},
    # Maps to no known id space: must not occupy the index.
    {"type": "TV", "anilist_id": 777},
    # AniList-only entry (no MAL id), only in the anilist index.
    {"type": "TV", "anilist_id": 888, "tvdb_id": 111},
]


def _write_mapping(path: Path, entries: list[dict] | None = None) -> None:
    path.write_text(json.dumps(entries if entries is not None else _ENTRIES), "utf-8")


def _make_map(path: Path) -> AnimeIdMap:
    return AnimeIdMap(path=str(path))


@pytest.fixture
def mapping_path(tmp_path: Path) -> Path:
    return tmp_path / "anime_ids.json"


async def test_enrich_fills_show_ids_from_fresh_file(mapping_path) -> None:
    _write_mapping(mapping_path)
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "show", "anilist": 290, "mal": 290}]
    enriched = await id_map.enrich(rows)
    assert enriched[0]["tmdb"] == 26209
    assert enriched[0]["tvdb"] == 72025
    assert enriched[0]["imdb"] == "tt0286390"
    await id_map.aclose()


async def test_enrich_movie_uses_movie_tmdb_and_skips_tvdb(mapping_path) -> None:
    _write_mapping(mapping_path)
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "movie", "anilist": 164, "mal": None}]
    enriched = await id_map.enrich(rows)
    # The one-element list unwraps to its first int; movies never get a tvdb.
    assert enriched[0]["tmdb"] == 128
    assert "tvdb" not in enriched[0]
    assert enriched[0]["imdb"] == "tt0119698"
    await id_map.aclose()


async def test_enrich_falls_back_to_mal_id(mapping_path) -> None:
    _write_mapping(mapping_path)
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "show", "anilist": None, "mal": 500}]
    enriched = await id_map.enrich(rows)
    assert enriched[0]["tvdb"] == 999
    await id_map.aclose()


async def test_enrich_leaves_unmapped_and_existing_ids_untouched(mapping_path) -> None:
    _write_mapping(mapping_path)
    id_map = _make_map(mapping_path)
    rows = [
        # Indexed nowhere (its entry maps to no id space).
        {"media_type": "show", "anilist": 777, "mal": None},
        # Already carries a tmdb: enrichment must not overwrite it.
        {"media_type": "show", "anilist": 290, "mal": None, "tmdb": 1},
    ]
    enriched = await id_map.enrich(rows)
    assert enriched[0].get("tmdb") is None
    assert enriched[1]["tmdb"] == 1
    assert enriched[1]["tvdb"] == 72025
    await id_map.aclose()


async def test_enrich_keeps_an_existing_imdb_id(mapping_path) -> None:
    _write_mapping(mapping_path)
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "show", "anilist": 290, "imdb": "tt-existing"}]
    enriched = await id_map.enrich(rows)
    assert enriched[0]["imdb"] == "tt-existing"
    assert enriched[0]["tvdb"] == 72025
    await id_map.aclose()


@respx.mock
async def test_stale_file_is_refreshed_from_upstream(mapping_path, monkeypatch) -> None:
    _write_mapping(mapping_path, [])
    route = respx.get(_SOURCE_URL).mock(
        return_value=httpx.Response(200, content=json.dumps(_ENTRIES).encode())
    )
    # A clock far past the file's mtime makes the on-disk copy stale.
    monkeypatch.setattr(
        anime_ids_mod, "_now", lambda: mapping_path.stat().st_mtime + 8 * 24 * 3600
    )
    id_map = _make_map(mapping_path)
    enriched = await id_map.enrich([{"media_type": "show", "anilist": 290}])
    assert route.called
    assert enriched[0]["tvdb"] == 72025
    await id_map.aclose()


@respx.mock
async def test_ensure_fresh_downloads_a_missing_mapping(mapping_path) -> None:
    # The public boot/scheduled entry point performs the same check-and-
    # download as the lazy enrich() path, without needing any rows.
    route = respx.get(_SOURCE_URL).mock(
        return_value=httpx.Response(200, content=json.dumps(_ENTRIES).encode())
    )
    id_map = _make_map(mapping_path)
    await id_map.ensure_fresh()
    assert route.call_count == 1
    assert mapping_path.exists()
    # A fresh file makes the next check a stat-only no-op: no second download.
    await id_map.ensure_fresh()
    assert route.call_count == 1
    await id_map.aclose()


@respx.mock
async def test_download_failure_falls_back_to_stale_file(
    mapping_path, monkeypatch
) -> None:
    _write_mapping(mapping_path)
    respx.get(_SOURCE_URL).mock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr(
        anime_ids_mod, "_now", lambda: mapping_path.stat().st_mtime + 8 * 24 * 3600
    )
    id_map = _make_map(mapping_path)
    enriched = await id_map.enrich([{"media_type": "show", "anilist": 290}])
    assert enriched[0]["tvdb"] == 72025
    await id_map.aclose()


@respx.mock
async def test_no_file_and_dead_upstream_passes_rows_through(
    mapping_path,
) -> None:
    route = respx.get(_SOURCE_URL).mock(side_effect=httpx.ConnectError("down"))
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "show", "anilist": 290}]
    enriched = await id_map.enrich(rows)
    assert enriched[0].get("tmdb") is None
    # The failure arms the retry guard: an immediate second call must not
    # hammer the dead upstream again.
    await id_map.enrich(rows)
    assert route.call_count == 1
    await id_map.aclose()


def test_helper_parsers_cover_source_shape_quirks() -> None:
    # A list with no usable int degrades to None; leading junk is skipped.
    assert _mapped_ids({"themoviedb_id": {"tv": ["x"]}, "tvdb_id": 5}) == MappedIds(
        tvdb=5
    )
    assert _mapped_ids({"themoviedb_id": {"tv": [None, 7]}}) == MappedIds(tmdb_tv=7)
    # imdb_id as a plain string (defensive) and as a list with empty leading
    # entries both resolve to the first non-empty string.
    assert _mapped_ids({"imdb_id": "tt1"}) == MappedIds(imdb="tt1")
    assert _mapped_ids({"imdb_id": ["", "tt2"]}) == MappedIds(imdb="tt2")


def test_build_indexes_tolerates_unexpected_top_level_shapes() -> None:
    # A non-list document and non-dict entries yield empty/partial indexes
    # rather than raising.
    assert _build_indexes('{"not": "a list"}') == ({}, {})
    by_anilist, by_mal = _build_indexes(
        json.dumps([42, {"anilist_id": 1, "tvdb_id": 2}])
    )
    assert by_anilist == {1: MappedIds(tvdb=2)}
    assert by_mal == {}


@respx.mock
async def test_refresh_days_bounds_staleness(mapping_path, monkeypatch) -> None:
    # A two-day-old file is fresh at the default 3-day cadence but stale at 1.
    _write_mapping(mapping_path)
    route = respx.get(_SOURCE_URL).mock(
        return_value=httpx.Response(200, content=json.dumps(_ENTRIES).encode())
    )
    monkeypatch.setattr(
        anime_ids_mod, "_now", lambda: mapping_path.stat().st_mtime + 2 * 24 * 3600
    )

    default_map = _make_map(mapping_path)
    await default_map.enrich([{"media_type": "show", "anilist": 290}])
    assert not route.called
    await default_map.aclose()

    daily_map = AnimeIdMap(path=str(mapping_path), refresh_days=1)
    await daily_map.enrich([{"media_type": "show", "anilist": 290}])
    assert route.called
    await daily_map.aclose()


@respx.mock
async def test_update_refresh_days_applies_to_next_check(
    mapping_path, monkeypatch
) -> None:
    _write_mapping(mapping_path)
    route = respx.get(_SOURCE_URL).mock(
        return_value=httpx.Response(200, content=json.dumps(_ENTRIES).encode())
    )
    monkeypatch.setattr(
        anime_ids_mod, "_now", lambda: mapping_path.stat().st_mtime + 2 * 24 * 3600
    )
    id_map = _make_map(mapping_path)
    await id_map.enrich([{"media_type": "show", "anilist": 290}])
    assert not route.called

    # Tightening the cadence at runtime makes the same file stale on the next
    # enrich; an out-of-range value normalises back to the 3-day default.
    id_map.update_refresh_days(1)
    await id_map.enrich([{"media_type": "show", "anilist": 290}])
    assert route.called

    id_map.update_refresh_days(9)
    assert id_map._refresh_ttl_seconds == 3 * 24 * 3600
    await id_map.aclose()


def test_mapped_ids_handles_bare_int_tmdb_by_type() -> None:
    # Defensive branch: a bare-int themoviedb_id is assigned per the entry type.
    assert _mapped_ids({"type": "MOVIE", "themoviedb_id": 128}) == MappedIds(
        tmdb_movie=128
    )
    assert _mapped_ids({"type": "TV", "themoviedb_id": 26209}) == MappedIds(
        tmdb_tv=26209
    )
    # Booleans are ints in Python but never ids; entries without any usable id
    # yield None so they never occupy the index.
    assert _mapped_ids({"themoviedb_id": True}) is None
    assert _mapped_ids({"imdb_id": [], "tvdb_id": "nope"}) is None


async def test_malformed_file_yields_empty_indexes(mapping_path) -> None:
    mapping_path.write_text("{not json", "utf-8")
    id_map = _make_map(mapping_path)
    rows = [{"media_type": "show", "anilist": 290}]
    enriched = await id_map.enrich(rows)
    assert enriched[0].get("tmdb") is None
    await id_map.aclose()


def test_mapped_ids_drops_ambiguous_multi_id_fields() -> None:
    # Franchise entries list several films under one AniList id; an arbitrary
    # first pick mis-rates the card or adds the wrong title, so two or more
    # valid ids in one field yield None while the unambiguous fields survive.
    mapped = _mapped_ids(
        {
            "type": "MOVIE",
            "imdb_id": ["tt1920940", "tt0089206"],
            "themoviedb_id": {"movie": 37585},
        }
    )
    assert mapped == MappedIds(tmdb_movie=37585)

    # A multi-valued tmdb list is equally ambiguous; a one-element list is not.
    assert _mapped_ids({"themoviedb_id": {"movie": [1, 2]}}) is None
    assert _mapped_ids({"themoviedb_id": {"movie": [9]}}) == MappedIds(tmdb_movie=9)

    # An entry ambiguous in every field maps to nothing at all.
    assert (
        _mapped_ids(
            {
                "imdb_id": ["tt1", "tt2"],
                "themoviedb_id": {"movie": [1, 2], "tv": [3, 4]},
                "tvdb_id": [5, 6],
            }
        )
        is None
    )


async def test_enrich_leaves_imdb_unset_for_ambiguous_mapping(
    mapping_path,
) -> None:
    # End to end: the ambiguous imdb is dropped, the single tmdb survives, and
    # the row leaves enrichment ready for the tmdb-based rating/add fallbacks.
    _write_mapping(
        mapping_path,
        [
            {
                "type": "MOVIE",
                "anilist_id": 1441,
                "imdb_id": ["tt1920940", "tt0089206"],
                "themoviedb_id": {"movie": 37585},
            }
        ],
    )
    rows = [{"media_type": "movie", "anilist": 1441}]
    await _make_map(mapping_path).enrich(rows)
    assert rows[0]["tmdb"] == 37585
    assert rows[0].get("imdb") is None


def test_build_indexes_logs_ambiguous_field_count(caplog) -> None:
    import logging

    with caplog.at_level(logging.DEBUG, logger="aio_arr.anime_ids"):
        _build_indexes(
            json.dumps(
                [
                    {"anilist_id": 1, "imdb_id": ["tt1", "tt2"], "tvdb_id": 9},
                    {"anilist_id": 2, "themoviedb_id": {"tv": [3, 4]}, "tvdb_id": 8},
                ]
            )
        )
    assert "2 ambiguous multi-id fields ignored" in caplog.text
