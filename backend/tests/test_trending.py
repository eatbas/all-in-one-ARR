"""Tests for core.trending (normalisation + IMDb-rating cache)."""

from __future__ import annotations

from core import trending as trending_mod
from core.trending import (
    LibraryCache,
    LibraryIndex,
    RatingCache,
    TrendingStore,
    build_library_index,
    to_trending_items,
)


def test_to_trending_items_tags_source_and_tracked() -> None:
    rows = [
        {
            "media_type": "movie",
            "tmdb": 100,
            "imdb": "tt1",
            "tvdb": None,
            "trakt": 1,
            "slug": "dune-2021",
            "title": "Dune",
            "year": 2021,
        },
        # No tmdb -> never marked tracked; a Seer-style row carries seer_status.
        {"media_type": "show", "tmdb": None, "title": "Mystery", "seer_status": 5},
    ]
    items = to_trending_items(rows, source="trakt", tracked_tmdbs={100})
    assert items[0] == {
        "source": "trakt",
        "media_type": "movie",
        "tmdb": 100,
        "imdb": "tt1",
        "tvdb": None,
        "trakt": 1,
        "slug": "dune-2021",
        "title": "Dune",
        "year": 2021,
        "anilist": None,
        "poster_url": None,
        "seer_status": None,
        "already_tracked": True,
        "in_library": False,
        "in_library_available": False,
    }
    assert items[1]["already_tracked"] is False
    assert items[1]["seer_status"] == 5
    assert items[1]["imdb"] is None
    assert items[1]["in_library"] is False
    assert items[1]["in_library_available"] is False


def test_to_trending_items_passes_anilist_fields_through() -> None:
    # AniList rows carry an anilist id and cover-art URL; both must survive the
    # mapping so unmapped rows can still render and deep-link.
    rows = [
        {
            "media_type": "show",
            "anilist": 195600,
            "poster_url": "https://img.example/cover.jpg",
            "title": "Yomi no Tsugai",
            "year": 2026,
        }
    ]
    items = to_trending_items(rows, source="anilist", tracked_tmdbs=set())
    assert items[0]["anilist"] == 195600
    assert items[0]["poster_url"] == "https://img.example/cover.jpg"
    assert items[0]["tmdb"] is None
    assert items[0]["already_tracked"] is False


def test_to_trending_items_untracked_tmdb() -> None:
    rows = [{"media_type": "movie", "tmdb": 200, "title": "X"}]
    items = to_trending_items(rows, source="tmdb", tracked_tmdbs={100})
    assert items[0]["already_tracked"] is False


def test_to_trending_items_flags_in_library() -> None:
    rows = [
        {"media_type": "movie", "tmdb": 603},  # in Radarr by tmdb
        {"media_type": "movie", "tmdb": 999},  # not in Radarr
        {"media_type": "show", "tmdb": 1, "tvdb": 121361},  # in Sonarr by tvdb
        {"media_type": "show", "tmdb": 1399, "tvdb": None},  # in Sonarr by tmdb
        {"media_type": "show", "tmdb": 7, "tvdb": 8},  # not in Sonarr
    ]
    library = LibraryIndex(
        radarr_tmdb=frozenset({603}),
        sonarr_tvdb=frozenset({121361}),
        sonarr_tmdb=frozenset({1399}),
    )
    flags = [
        item["in_library"]
        for item in to_trending_items(
            rows, source="trakt", tracked_tmdbs=set(), library=library
        )
    ]
    assert flags == [True, False, True, True, False]


def test_to_trending_items_flags_in_library_available() -> None:
    rows = [
        {"media_type": "movie", "tmdb": 603},  # downloaded in Radarr
        {"media_type": "movie", "tmdb": 604},  # in Radarr, no file yet
        {"media_type": "show", "tmdb": 1, "tvdb": 121361},  # downloaded in Sonarr
        {"media_type": "show", "tmdb": 7, "tvdb": 8},  # in Sonarr, no episodes yet
    ]
    library = LibraryIndex(
        radarr_tmdb=frozenset({603, 604}),
        sonarr_tvdb=frozenset({121361, 8}),
        radarr_available_tmdb=frozenset({603}),
        sonarr_available_tvdb=frozenset({121361}),
    )
    items = to_trending_items(
        rows, source="trakt", tracked_tmdbs=set(), library=library
    )
    assert [item["in_library"] for item in items] == [True, True, True, True]
    assert [item["in_library_available"] for item in items] == [
        True,
        False,
        True,
        False,
    ]


def test_is_available_defaults_false_without_library() -> None:
    # A row with no library passed in is never "available".
    items = to_trending_items(
        [{"media_type": "movie", "tmdb": 1}], source="tmdb", tracked_tmdbs=set()
    )
    assert items[0]["in_library_available"] is False


def test_build_library_index_collects_int_ids() -> None:
    index = build_library_index(
        radarr_items=[{"tmdbId": 603}, {"tmdbId": None}, {"title": "no id"}],
        sonarr_items=[{"tvdbId": 1, "tmdbId": 2}, {"tvdbId": "bad"}],
    )
    assert index.radarr_tmdb == frozenset({603})
    assert index.sonarr_tvdb == frozenset({1})
    assert index.sonarr_tmdb == frozenset({2})


def test_build_library_index_collects_available_ids() -> None:
    # hasFile / episodeFileCount drive the available subsets; absent or zero excludes.
    index = build_library_index(
        radarr_items=[
            {"tmdbId": 603, "hasFile": True},
            {"tmdbId": 604, "hasFile": False},
            {"tmdbId": 605},  # no hasFile key
        ],
        sonarr_items=[
            {"tvdbId": 1, "tmdbId": 11, "statistics": {"episodeFileCount": 4}},
            {"tvdbId": 2, "tmdbId": 12, "statistics": {"episodeFileCount": 0}},
            {"tvdbId": 3, "tmdbId": 13},  # no statistics
        ],
    )
    assert index.radarr_tmdb == frozenset({603, 604, 605})
    assert index.radarr_available_tmdb == frozenset({603})
    assert index.sonarr_available_tvdb == frozenset({1})
    assert index.sonarr_available_tmdb == frozenset({11})


def test_rating_cache_miss_then_hit() -> None:
    cache = RatingCache(ttl_seconds=100, max_entries=10)
    assert cache.get("tt1") is None
    cache.set("tt1", {"imdb_rating": 8.6, "imdb_votes": 10})
    assert cache.get("tt1") == {"imdb_rating": 8.6, "imdb_votes": 10}


def test_rating_cache_expiry(monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(trending_mod, "_now", lambda: clock["now"])
    cache = RatingCache(ttl_seconds=50, max_entries=10)
    cache.set("tt1", {"imdb_rating": 7.0, "imdb_votes": 1})
    clock["now"] = 1049.0
    assert cache.get("tt1") == {"imdb_rating": 7.0, "imdb_votes": 1}
    clock["now"] = 1051.0  # past the TTL
    assert cache.get("tt1") is None
    # A second read after eviction still returns None (entry already removed).
    assert cache.get("tt1") is None


def test_rating_cache_evicts_oldest_when_full() -> None:
    cache = RatingCache(ttl_seconds=1000, max_entries=2)
    cache.set("tt1", {"imdb_rating": 1.0, "imdb_votes": 1})
    cache.set("tt2", {"imdb_rating": 2.0, "imdb_votes": 2})
    cache.set("tt3", {"imdb_rating": 3.0, "imdb_votes": 3})  # evicts tt1
    assert cache.get("tt1") is None
    assert cache.get("tt2") is not None
    assert cache.get("tt3") is not None
    # Updating an existing key does not trigger eviction.
    cache.set("tt2", {"imdb_rating": 9.0, "imdb_votes": 9})
    assert cache.get("tt2") == {"imdb_rating": 9.0, "imdb_votes": 9}


def test_trending_store_all_rows_flattens_every_feed() -> None:
    store = TrendingStore()
    assert store.all_rows() == []
    store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[{"tmdb": 1}],
    )
    store.set(
        source="tmdb",
        media="show",
        category="popular",
        window="week",
        rows=[{"tmdb": 2}, {"tmdb": 3}],
    )
    assert sorted(row["tmdb"] for row in store.all_rows()) == [1, 2, 3]


def test_library_cache_miss_set_and_ttl(monkeypatch) -> None:
    clock = {"now": 1000.0}
    monkeypatch.setattr(trending_mod, "_now", lambda: clock["now"])
    cache = LibraryCache(ttl_seconds=60)
    assert cache.get() is None  # nothing cached yet
    index = LibraryIndex(radarr_tmdb=frozenset({603}))
    cache.set(index)
    assert cache.get() is index
    clock["now"] = 1059.0
    assert cache.get() is index  # still fresh
    clock["now"] = 1061.0  # past the TTL
    assert cache.get() is None
    assert cache.peek() is index
