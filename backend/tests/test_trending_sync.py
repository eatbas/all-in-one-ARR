"""Tests for the scheduled trending refresh (core.trending_sync)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, call

from core import trending_sync
from core.trending import SEER_TRENDING_SYNC_PAGES, TRENDING_ITEM_LIMIT
from core.trending_sync import (
    _PREWARM_TASKS,
    _prewarm_targets,
    _trending_sync,
    _trending_sync_job,
    prewarm_posters,
    refresh_trending_store,
    start_trending_sync,
)
from tests.conftest import make_ctx


def _row(tmdb: int, media_type: str = "movie") -> dict:
    return {"media_type": media_type, "tmdb": tmdb, "title": "X", "year": 2021}


class _StubPosterCache:
    """Minimal stand-in for :class:`PosterCache` for pre-warm tests."""

    def __init__(self) -> None:
        self.get_poster = AsyncMock(return_value=None)


async def test_refresh_fills_every_feed_and_stamps_sync(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(1)]
    ctx.trakt.get_popular.return_value = [_row(2)]
    ctx.tmdb.get_trending.return_value = [_row(3)]
    ctx.tmdb.get_popular.return_value = [_row(4, media_type="show")]
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": [_row(5)],
        "show": [_row(6, media_type="show")],
    }
    ctx.seer.discover_popular.return_value = [_row(7)]

    await refresh_trending_store(ctx)

    store = ctx.trending_store
    assert store.last_synced_at() is not None
    assert store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(1)]
    assert store.get(
        source="tmdb", media="show", category="popular", window="week"
    ) == [_row(4, media_type="show")]
    # Seer trending mixes types; each feed is filtered to its requested media type.
    assert store.get(
        source="seer", media="movie", category="trending", window="week"
    ) == [_row(5)]
    # The scheduled fetch asks for a deeper grid than a live call.
    assert (
        ctx.tmdb.get_trending.await_args.kwargs["pages"]
        == trending_sync.TRENDING_SYNC_PAGES
    )
    assert ctx.trakt.get_trending.await_args.kwargs["limit"] == TRENDING_ITEM_LIMIT
    ctx.seer.discover_popular.assert_has_awaits(
        [
            call(
                media_type="movie",
                limit=TRENDING_ITEM_LIMIT,
                pages=trending_sync.TRENDING_SYNC_PAGES,
            ),
            call(
                media_type="show",
                limit=TRENDING_ITEM_LIMIT,
                pages=trending_sync.TRENDING_SYNC_PAGES,
            ),
        ],
        any_order=True,
    )


async def test_refresh_keeps_previous_snapshot_when_a_feed_fails(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(99)],
    )
    ctx.trakt.get_trending.side_effect = RuntimeError("trakt down")
    ctx.trakt.get_popular.return_value = [_row(2)]

    await refresh_trending_store(ctx)

    # The failed feed retains its prior snapshot; healthy feeds still refresh.
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(99)]
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="popular", window="week"
    ) == [_row(2)]
    assert ctx.trending_store.last_synced_at() is not None


async def test_seer_trending_is_fetched_once_and_split_by_media(db) -> None:
    # Seer's mixed trending feed is fetched through the bucket helper once per cycle,
    # rather than fetched separately for movies and shows.
    ctx = make_ctx(db=db)
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": [_row(5)],
        "show": [_row(6, media_type="show")],
    }
    await refresh_trending_store(ctx)
    ctx.seer.discover_trending_buckets.assert_awaited_once_with(
        limit_per_media=TRENDING_ITEM_LIMIT,
        pages=SEER_TRENDING_SYNC_PAGES,
    )
    assert ctx.trending_store.get(
        source="seer", media="movie", category="trending", window="week"
    ) == [_row(5)]
    assert ctx.trending_store.get(
        source="seer", media="show", category="trending", window="week"
    ) == [_row(6, media_type="show")]


async def test_seer_trending_stores_filled_buckets(db) -> None:
    ctx = make_ctx(db=db)
    movies = [_row(index) for index in range(1, 41)]
    shows = [_row(index, media_type="show") for index in range(101, 141)]
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": movies,
        "show": shows,
    }

    await refresh_trending_store(ctx)

    assert (
        ctx.trending_store.get(
            source="seer", media="movie", category="trending", window="week"
        )
        == movies
    )
    assert (
        ctx.trending_store.get(
            source="seer", media="show", category="trending", window="week"
        )
        == shows
    )


async def test_seer_trending_stores_exhausted_short_bucket(db) -> None:
    ctx = make_ctx(db=db)
    movies = [_row(index) for index in range(1, 41)]
    shows = [_row(index, media_type="show") for index in range(101, 121)]
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": movies,
        "show": shows,
    }

    await refresh_trending_store(ctx)

    assert (
        len(
            ctx.trending_store.get(
                source="seer", media="movie", category="trending", window="week"
            )
        )
        == 40
    )
    assert (
        ctx.trending_store.get(
            source="seer", media="show", category="trending", window="week"
        )
        == shows
    )


async def test_refresh_keeps_seer_trending_snapshot_when_it_fails(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trending_store.set(
        source="seer",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(42)],
    )
    ctx.seer.discover_trending_buckets.side_effect = RuntimeError("seer down")
    ctx.seer.discover_popular.return_value = [_row(7)]

    await refresh_trending_store(ctx)

    # Seer trending keeps its prior snapshot; the (independent) seer popular refreshes.
    assert ctx.trending_store.get(
        source="seer", media="movie", category="trending", window="week"
    ) == [_row(42)]
    assert ctx.trending_store.get(
        source="seer", media="movie", category="popular", window="week"
    ) == [_row(7)]
    assert ctx.trending_store.last_synced_at() is not None


async def test_job_invokes_refresh_when_ctx_set(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    seen: dict = {}

    async def fake_refresh(passed_ctx) -> None:
        seen["ctx"] = passed_ctx

    monkeypatch.setattr(trending_sync, "refresh_trending_store", fake_refresh)
    monkeypatch.setattr(_trending_sync, "ctx", ctx)
    await _trending_sync_job()
    assert seen["ctx"] is ctx


async def test_start_schedules_job_primes_store_and_reschedules(
    db, monkeypatch
) -> None:
    ctx = make_ctx(db=db)  # scheduler is an AsyncMock
    ctx.trakt.get_trending.return_value = [_row(1)]
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)

    # The interval job is registered under the trending id at the configured interval.
    ctx.scheduler.add_interval.assert_awaited_once()
    add_call = ctx.scheduler.add_interval.await_args
    assert add_call.kwargs["id"] == "trending_sync"
    assert add_call.kwargs["minutes"] == 60
    # The store is primed immediately so a cold boot is not empty.
    assert ctx.trending_store.last_synced_at() is not None
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(1)]
    # The reschedule hook re-points the same job id.
    assert ctx.reschedule_trending is not None
    await ctx.reschedule_trending(30)
    ctx.scheduler.reschedule_interval.assert_awaited_once()
    reschedule_call = ctx.scheduler.reschedule_interval.await_args
    assert reschedule_call.kwargs["id"] == "trending_sync"
    assert reschedule_call.kwargs["minutes"] == 30


# ---- poster pre-warm ----


def test_prewarm_targets_dedups_and_keeps_first_imdb() -> None:
    rows = [
        {"media_type": "movie", "tmdb": 1, "imdb": None},  # TMDB row: no imdb yet
        {"media_type": "movie", "tmdb": 1, "imdb": "tt1"},  # dup: upgrade to carry imdb
        {"media_type": "movie", "tmdb": 1, "imdb": "tt9"},  # dup: keep the first imdb
        {"media_type": "show", "tmdb": 2, "imdb": "tt2"},
        {"media_type": "movie", "tmdb": None},  # skipped: no tmdb
        {"media_type": "person", "tmdb": 5},  # skipped: not movie/show
    ]
    assert sorted(_prewarm_targets(rows)) == [("movie", 1, "tt1"), ("show", 2, "tt2")]


async def test_prewarm_posters_fetches_each_unique_target(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = _StubPosterCache()
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}],
    )
    ctx.trending_store.set(
        source="tmdb",
        media="movie",
        category="popular",
        window="week",
        rows=[{"media_type": "movie", "tmdb": 1}, {"media_type": "movie", "tmdb": 2}],
    )
    await prewarm_posters(ctx)
    # tmdb 1 appears in two feeds but is fetched once; tmdb 2 once.
    assert ctx.poster_cache.get_poster.await_count == 2
    fetched = {
        (call.kwargs["media_type"], call.kwargs["tmdb_id"])
        for call in ctx.poster_cache.get_poster.await_args_list
    }
    assert fetched == {("movie", 1), ("movie", 2)}


async def test_prewarm_posters_noop_without_cache(db) -> None:
    ctx = make_ctx(db=db)  # poster_cache defaults to None
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[{"media_type": "movie", "tmdb": 1}],
    )
    await prewarm_posters(ctx)  # must not raise
    assert ctx.poster_cache is None


async def test_prewarm_posters_noop_when_no_targets(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = _StubPosterCache()
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[{"media_type": "movie", "tmdb": None}],  # no usable id
    )
    await prewarm_posters(ctx)
    ctx.poster_cache.get_poster.assert_not_awaited()


async def test_prewarm_posters_swallows_fetch_failures(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = _StubPosterCache()
    ctx.poster_cache.get_poster.side_effect = RuntimeError("tmdb down")
    ctx.trending_store.set(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}],
    )
    await prewarm_posters(ctx)  # failure is swallowed, no raise
    ctx.poster_cache.get_poster.assert_awaited_once()


async def test_job_spawns_detached_poster_prewarm(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = _StubPosterCache()
    ctx.trakt.get_trending.return_value = [_row(1)]
    monkeypatch.setattr(_trending_sync, "ctx", ctx)

    await _trending_sync_job()
    # The pre-warm runs detached; drain the retained tasks to observe it.
    await asyncio.gather(*list(_PREWARM_TASKS))

    ctx.poster_cache.get_poster.assert_awaited()
