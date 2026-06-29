"""Tests for core.trending (normalisation + IMDb-rating cache)."""

from __future__ import annotations

from core import trending as trending_mod
from core.trending import (
    LibraryCache,
    LibraryIndex,
    RatingCache,
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
        "seer_status": None,
        "already_tracked": True,
        "in_library": False,
    }
    assert items[1]["already_tracked"] is False
    assert items[1]["seer_status"] == 5
    assert items[1]["imdb"] is None
    assert items[1]["in_library"] is False


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


def test_build_library_index_collects_int_ids() -> None:
    index = build_library_index(
        radarr_items=[{"tmdbId": 603}, {"tmdbId": None}, {"title": "no id"}],
        sonarr_items=[{"tvdbId": 1, "tmdbId": 2}, {"tvdbId": "bad"}],
    )
    assert index.radarr_tmdb == frozenset({603})
    assert index.sonarr_tvdb == frozenset({1})
    assert index.sonarr_tmdb == frozenset({2})


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
