"""Tests for the scheduled trending refresh (core.trending_sync)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, call

import pytest

from core import trending_sync
from core.db import utcnow_iso
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


async def test_refresh_covers_anime_sources(db) -> None:
    # The anime variants and AniList are full members of the scheduled matrix,
    # so the Anime tab is served from the same warmed snapshot.
    ctx = make_ctx(db=db)
    ctx.anilist.get_trending.return_value = [
        {"media_type": "show", "anilist": 1, "title": "A", "year": 2026}
    ]

    await refresh_trending_store(ctx)

    store = ctx.trending_store
    for source in ("trakt-anime", "tmdb-anime", "anilist"):
        for media in ("movie", "show"):
            for category in ("trending", "popular"):
                assert (
                    store.get(
                        source=source, media=media, category=category, window="week"
                    )
                    is not None
                ), (source, media, category)
    assert store.get(
        source="anilist", media="show", category="trending", window="week"
    ) == [{"media_type": "show", "anilist": 1, "title": "A", "year": 2026}]
    # The trakt-anime feeds go through the same client with the genre filter.
    assert ctx.trakt.get_trending.await_args.kwargs.get("genres") == "anime"
    ctx.tmdb.get_anime_trending.assert_awaited()
    ctx.tmdb.get_anime_popular.assert_awaited()


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
    # Partial cycles do not stamp the store or the persistent cycle timestamp.
    assert ctx.trending_store.last_synced_at() is None
    assert db.trending_cycle_last_synced() is None


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
    # Partial cycles do not stamp the store or the persistent cycle timestamp.
    assert ctx.trending_store.last_synced_at() is None
    assert db.trending_cycle_last_synced() is None


async def test_job_invokes_refresh_when_ctx_set(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    seen: dict = {}

    async def fake_refresh(passed_ctx) -> None:
        seen["ctx"] = passed_ctx

    monkeypatch.setattr(trending_sync, "refresh_trending_store", fake_refresh)
    monkeypatch.setattr(_trending_sync, "ctx", ctx)
    await _trending_sync_job()
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))
    assert seen["ctx"] is ctx


async def test_start_schedules_job_primes_store_and_reschedules(
    db, monkeypatch
) -> None:
    ctx = make_ctx(db=db)  # scheduler is an AsyncMock
    ctx.trakt.get_trending.return_value = [_row(1)]
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    # The interval job is registered under the trending id at the configured interval.
    add_call = next(
        call
        for call in ctx.scheduler.add_interval.await_args_list
        if call.kwargs["id"] == "trending_sync"
    )
    assert add_call.kwargs["id"] == "trending_sync"
    assert add_call.kwargs["minutes"] == 1440
    # The immediate APScheduler-4 first fire is deferred: the boot path below
    # already primes or restores the store.
    assert add_call.kwargs["defer_first_run"] is True
    # The daily rating-backfill cron is registered alongside the interval job.
    # The hourly backfill interval is registered alongside, first run deferred
    # (the boot path already spawns one).
    backfill_call = next(
        call
        for call in ctx.scheduler.add_interval.await_args_list
        if call.kwargs["id"] == "trending_rating_backfill"
    )
    assert backfill_call.kwargs["minutes"] == 60
    assert backfill_call.kwargs["defer_first_run"] is True
    # Nothing persisted yet: the store is primed live so a cold boot is not empty.
    assert ctx.trending_store.last_synced_at() is not None
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(1)]
    # The reschedule hook re-points the same job id, keeping the deferred
    # first fire; the snapshot was refreshed moments ago so no catch-up
    # refresh is kicked.
    assert ctx.reschedule_trending is not None
    await ctx.reschedule_trending(2880)
    ctx.scheduler.reschedule_interval.assert_awaited_once()
    reschedule_call = ctx.scheduler.reschedule_interval.await_args
    assert reschedule_call.kwargs["id"] == "trending_sync"
    assert reschedule_call.kwargs["minutes"] == 2880
    assert reschedule_call.kwargs["defer_first_run"] is True
    assert not trending_sync._REFRESH_TASKS


async def test_start_restores_fresh_snapshot_without_refetching(
    db, monkeypatch
) -> None:
    # A snapshot persisted moments ago (well inside the 1-day interval) is
    # restored from the database; no provider is called at boot. The cycle
    # timestamp must also be present for the snapshot to be considered complete.
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced()
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(1)]
    assert ctx.trending_store.last_synced_at() == db.trending_cycle_last_synced()
    ctx.trakt.get_trending.assert_not_awaited()
    ctx.tmdb.get_trending.assert_not_awaited()


async def test_start_refreshes_when_snapshot_is_stale(db, monkeypatch) -> None:
    # Backdate the persisted snapshot beyond the configured interval: boot must
    # refresh live rather than serve week-old feeds.
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced("2020-01-01T00:00:00+00:00")
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(2)]
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(2)]
    ctx.trakt.get_trending.assert_awaited()


async def test_start_refreshes_when_snapshot_stamp_is_unparseable(
    db, monkeypatch
) -> None:
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced("not-a-timestamp")
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(2)]
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    ctx.trakt.get_trending.assert_awaited()


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
    # The pre-warm and backfill run detached; drain the retained tasks.
    await asyncio.gather(*list(_PREWARM_TASKS))
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    ctx.poster_cache.get_poster.assert_awaited()


# ---- IMDb-rating backfill ----


def _feed(ctx, rows: list[dict]) -> None:
    """Put rows into one warmed feed so the backfill sees them."""
    ctx.trending_store.set(
        source="trakt", media="movie", category="trending", window="week", rows=rows
    )


def test_rating_targets_dedupes_by_key_and_skips_unusable_rows() -> None:
    rows = [
        {"media_type": "movie", "tmdb": 1, "imdb": "tt1"},
        {"media_type": "movie", "tmdb": 1, "imdb": "tt1"},  # duplicate key
        {"media_type": "movie", "tmdb": 2},  # alias key
        {"media_type": "movie", "tmdb": None, "imdb": None},  # no usable id
        {"media_type": "person", "tmdb": 5},  # not movie/show
    ]
    targets = trending_sync._rating_targets(rows)
    assert sorted(target.canonical for target in targets) == ["movie:2", "tt1"]


def test_rating_targets_groups_mixed_imdb_and_alias() -> None:
    # A title represented by both an IMDb id in one feed and a TMDB-only alias
    # in another must become a single lookup target, preserving both aliases.
    rows = [
        {"media_type": "movie", "tmdb": 42, "imdb": "tt42"},
        {"media_type": "movie", "tmdb": 42},  # alias-only duplicate
        {"media_type": "show", "tmdb": 99, "imdb": "tt99"},
    ]
    targets = {
        target.canonical: target for target in trending_sync._rating_targets(rows)
    }
    assert set(targets) == {"tt42", "tt99"}
    assert targets["tt42"].imdb == "tt42"
    assert targets["tt42"].aliases == {"tt42", "movie:42"}
    assert targets["tt99"].aliases == {"tt99"}


async def test_backfill_fetches_missing_and_stores_ratings(db) -> None:
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.6, "imdb_votes": 100}
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])

    await trending_sync.backfill_ratings(ctx)

    stored = db.trending_ratings_get_many(["tt1"])["tt1"]
    assert stored["imdb_rating"] == 8.6
    assert stored["imdb_votes"] == 100
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 1


async def test_backfill_resolves_alias_and_stores_both_keys(db) -> None:
    ctx = make_ctx(db=db)
    ctx.tmdb.fetch_external_ids.return_value = "tt2"
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 7.1, "imdb_votes": 5}
    _feed(ctx, [{"media_type": "movie", "tmdb": 603}])

    await trending_sync.backfill_ratings(ctx)

    stored = db.trending_ratings_get_many(["movie:603", "tt2"])
    assert stored["movie:603"]["imdb_rating"] == 7.1
    assert stored["tt2"]["imdb_rating"] == 7.1


async def test_backfill_upserts_every_alias_for_mixed_identity(db) -> None:
    # One title appears as both an IMDb row and a TMDB-only alias: the backfill
    # must perform exactly one OMDb lookup and store the rating under both keys.
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.1, "imdb_votes": 50}
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": 42, "imdb": "tt42"},
            {"media_type": "movie", "tmdb": 42},
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_awaited_once_with(imdb_id="tt42")
    stored = db.trending_ratings_get_many(["tt42", "movie:42"])
    assert stored["tt42"]["imdb_rating"] == 8.1
    assert stored["movie:42"]["imdb_rating"] == 8.1


async def test_backfill_leaves_unresolved_alias_missing(db) -> None:
    # A failed/absent TMDB->IMDb resolution costs no OMDb budget and stores
    # nothing, so a later run retries it.
    ctx = make_ctx(db=db)
    ctx.tmdb.fetch_external_ids.return_value = None
    _feed(ctx, [{"media_type": "movie", "tmdb": 603}])

    await trending_sync.backfill_ratings(ctx)

    assert db.trending_ratings_get_many(["movie:603"]) == {}
    ctx.omdb.fetch_rating.assert_not_awaited()
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 0


async def test_backfill_skips_fresh_and_refetches_stale_entries(db) -> None:
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 9.0, "imdb_votes": 1}
    db.trending_ratings_upsert(key="tt-fresh", imdb_rating=8.0, imdb_votes=1)
    db.trending_ratings_upsert(
        key="tt-stale",
        imdb_rating=5.0,
        imdb_votes=1,
        fetched_at="2020-01-01T00:00:00+00:00",
    )
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": 1, "imdb": "tt-fresh"},
            {"media_type": "movie", "tmdb": 2, "imdb": "tt-stale"},
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_awaited_once_with(imdb_id="tt-stale")
    assert db.trending_ratings_get_many(["tt-stale"])["tt-stale"]["imdb_rating"] == 9.0
    assert db.trending_ratings_get_many(["tt-fresh"])["tt-fresh"]["imdb_rating"] == 8.0


async def test_backfill_respects_remaining_daily_budget(db) -> None:
    # Two pending titles but budget for one: the second waits for the next run.
    from tests.conftest import StubSettingsStore

    ctx = make_ctx(
        db=db, settings_store=StubSettingsStore(omdb_daily_budget_per_key=100)
    )
    db.omdb_usage_add(utcnow_iso()[:10], 99)  # one request left today
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 6.0, "imdb_votes": 2}
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": 1, "imdb": "tt1"},
            {"media_type": "movie", "tmdb": 2, "imdb": "tt2"},
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    assert ctx.omdb.fetch_rating.await_count == 1
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 100
    # The next day (usage reset) picks the leftover up.
    with db._lock:
        db._conn.execute("DELETE FROM omdb_usage")
        db._conn.commit()
    await trending_sync.backfill_ratings(ctx)
    assert ctx.omdb.fetch_rating.await_count == 2
    assert len(db.trending_ratings_get_many(["tt1", "tt2"])) == 2


async def test_backfill_noop_when_budget_already_spent(db) -> None:
    ctx = make_ctx(db=db)
    db.omdb_usage_add(utcnow_iso()[:10], 800)  # the stub store's default budget
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_not_awaited()


async def test_backfill_noop_without_targets_or_pending(db) -> None:
    ctx = make_ctx(db=db)
    await trending_sync.backfill_ratings(ctx)  # empty store: no targets
    ctx.omdb.fetch_rating.assert_not_awaited()

    db.trending_ratings_upsert(key="tt1", imdb_rating=8.0, imdb_votes=1)
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])
    await trending_sync.backfill_ratings(ctx)  # everything fresh: nothing pending
    ctx.omdb.fetch_rating.assert_not_awaited()


async def test_backfill_swallows_per_item_failures(db) -> None:
    # A store write blowing up must not abort the batch (gather return_exceptions).
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.side_effect = RuntimeError("boom")
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])

    await trending_sync.backfill_ratings(ctx)  # must not raise

    assert db.trending_ratings_get_many(["tt1"]) == {}


async def test_backfill_job_invokes_backfill_when_ctx_set(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    seen: dict = {}

    async def fake_backfill(passed_ctx) -> None:
        seen["ctx"] = passed_ctx

    monkeypatch.setattr(trending_sync, "backfill_ratings", fake_backfill)
    monkeypatch.setattr(_trending_sync, "ctx", ctx)
    await trending_sync._rating_backfill_job()
    assert seen["ctx"] is ctx


async def test_job_spawns_detached_rating_backfill(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [
        {"media_type": "movie", "tmdb": 1, "imdb": "tt1"}
    ]
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.0, "imdb_votes": 3}
    monkeypatch.setattr(_trending_sync, "ctx", ctx)

    await _trending_sync_job()
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    ctx.omdb.fetch_rating.assert_awaited()
    assert db.trending_ratings_get_many(["tt1"])["tt1"]["imdb_rating"] == 8.0


async def test_refresh_persists_feeds_for_restart(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(1)]
    ctx.seer.discover_trending_buckets.return_value = {
        "movie": [_row(5)],
        "show": [_row(6, media_type="show")],
    }

    await refresh_trending_store(ctx)

    persisted = {
        (feed["source"], feed["media"], feed["category"]): feed["rows"]
        for feed in db.trending_feeds_load()
    }
    assert persisted[("trakt", "movie", "trending")] == [_row(1)]
    assert persisted[("seer", "show", "trending")] == [_row(6, media_type="show")]
    assert db.trending_cycle_last_synced() is not None


async def test_refresh_does_not_update_cycle_timestamp_on_partial_failure(
    db,
) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.side_effect = RuntimeError("trakt down")

    await refresh_trending_store(ctx)

    # The failed feed's own row is still persisted, but the cycle timestamp
    # must stay absent so the next restart knows the snapshot is incomplete.
    assert db.trending_feeds_load()
    assert db.trending_cycle_last_synced() is None


async def test_start_refreshes_after_partial_failure_restart(db, monkeypatch) -> None:
    # A persisted feed with no cycle timestamp means the last cycle was partial;
    # boot must refresh instead of trusting the partial snapshot.
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    ctx = make_ctx(db=db)
    ctx.trakt.get_trending.return_value = [_row(2)]
    monkeypatch.setattr(_trending_sync, "ctx", None)

    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    ctx.trakt.get_trending.assert_awaited()
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(2)]
    # A successful full cycle now stamps the cycle timestamp.
    assert db.trending_cycle_last_synced() is not None


# ---- backfill concurrency guard and reschedule catch-up ----


def test_is_fresh_treats_naive_timestamp_as_stale() -> None:
    # A naive stamp parses but cannot be subtracted from aware now (TypeError);
    # it must degrade to "stale" exactly like an unparseable one.
    assert (
        trending_sync._is_fresh("2020-01-01T00:00:00", interval_minutes=1440) is False
    )


async def test_spawn_backfill_skips_while_one_is_in_flight(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    release = asyncio.Event()
    calls = {"count": 0}

    async def slow_backfill(_ctx) -> None:
        calls["count"] += 1
        await release.wait()

    monkeypatch.setattr(trending_sync, "backfill_ratings", slow_backfill)
    first = trending_sync._spawn_rating_backfill(ctx)
    assert first is not None
    # A duplicate trigger while the first run is in flight is a no-op, so two
    # runs can never spend the daily OMDb budget twice.
    assert trending_sync._spawn_rating_backfill(ctx) is None
    assert calls["count"] <= 1
    release.set()
    await first
    # Once the run finishes (done-callback cleared the slot), triggers spawn again.
    await asyncio.sleep(0)
    second = trending_sync._spawn_rating_backfill(ctx)
    assert second is not None
    await second
    assert calls["count"] == 2


async def test_cron_backfill_job_skips_when_backfill_in_flight(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    release = asyncio.Event()
    started = asyncio.Event()
    calls = {"count": 0}

    async def slow_backfill(_ctx) -> None:
        calls["count"] += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(trending_sync, "backfill_ratings", slow_backfill)
    monkeypatch.setattr(_trending_sync, "ctx", ctx)
    in_flight = trending_sync._spawn_rating_backfill(ctx)
    assert in_flight is not None
    # Wait for the spawned run to actually start before asserting the call count.
    await started.wait()
    assert calls["count"] == 1
    # The daily cron finds a run in flight and returns without starting another.
    await trending_sync._rating_backfill_job()
    assert calls["count"] == 1
    release.set()
    await in_flight


async def test_reschedule_kicks_refresh_when_snapshot_stale_for_new_interval(
    db, monkeypatch
) -> None:
    # Boot restores a fresh snapshot (no live fetch). Backdating it two days and
    # switching to a 1-day cadence must catch up immediately: defer_first_run
    # pushes the next scheduled fire a full new interval out, so without the
    # kick the stale snapshot would survive another day.
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced()
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_trending_sync, "ctx", None)
    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))
    ctx.trakt.get_trending.assert_not_awaited()

    stale = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    db.trending_cycle_mark_synced(stale)
    ctx.trakt.get_trending.return_value = [_row(2)]

    await ctx.reschedule_trending(1440)
    await asyncio.gather(*list(trending_sync._REFRESH_TASKS))
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    ctx.trakt.get_trending.assert_awaited()
    assert ctx.trending_store.get(
        source="trakt", media="movie", category="trending", window="week"
    ) == [_row(2)]


async def test_reschedule_refresh_cycle_is_exclusive(db, monkeypatch) -> None:
    # Repeated stale reschedules must not spawn concurrent refresh cycles.
    trending_sync._REFRESH_ACTIVE = False
    trending_sync._REFRESH_TASKS.clear()
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced()
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_trending_sync, "ctx", None)
    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    release = asyncio.Event()
    started = asyncio.Event()
    calls = {"count": 0}

    async def slow_refresh_store(passed_ctx) -> None:
        calls["count"] += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(trending_sync, "refresh_trending_store", slow_refresh_store)

    # Make the existing cycle state stale so rescheduling spawns a catch-up.
    stale = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    db.trending_cycle_mark_synced(stale)
    await ctx.reschedule_trending(1440)
    await started.wait()
    # Fire more reschedule calls while the first cycle is still active.
    await ctx.reschedule_trending(1440)
    await ctx.reschedule_trending(1440)
    await asyncio.sleep(0)

    assert calls["count"] == 1
    release.set()
    await asyncio.gather(*list(trending_sync._REFRESH_TASKS))
    assert calls["count"] == 1
    assert not trending_sync._REFRESH_ACTIVE


async def test_scheduled_job_skips_when_refresh_cycle_active(db, monkeypatch) -> None:
    # Scheduler overlap with an active reschedule cycle must not run a second
    # provider sweep.
    trending_sync._REFRESH_ACTIVE = False
    trending_sync._REFRESH_TASKS.clear()
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced()
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_trending_sync, "ctx", None)
    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    release = asyncio.Event()
    started = asyncio.Event()
    calls = {"count": 0}

    async def slow_refresh_store(passed_ctx) -> None:
        calls["count"] += 1
        started.set()
        await release.wait()

    monkeypatch.setattr(trending_sync, "refresh_trending_store", slow_refresh_store)

    stale = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    db.trending_cycle_mark_synced(stale)
    await ctx.reschedule_trending(1440)
    await started.wait()
    assert calls["count"] == 1

    # The scheduled job sees the active cycle and returns immediately.
    await _trending_sync_job()
    assert calls["count"] == 1

    release.set()
    await asyncio.gather(*list(trending_sync._REFRESH_TASKS))
    assert not trending_sync._REFRESH_ACTIVE


async def test_reschedule_refresh_cycle_logs_detached_exception(
    db, monkeypatch
) -> None:
    # A detached refresh cycle that raises must be supervised and logged rather
    # than dropped by the asyncio runtime.
    trending_sync._REFRESH_ACTIVE = False
    trending_sync._REFRESH_TASKS.clear()
    db.trending_feeds_save(
        source="trakt",
        media="movie",
        category="trending",
        window="week",
        rows=[_row(1)],
    )
    db.trending_cycle_mark_synced()
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_trending_sync, "ctx", None)
    await start_trending_sync(ctx)
    await asyncio.gather(*list(trending_sync._BACKFILL_TASKS))

    async def failing_refresh_store(passed_ctx) -> None:
        raise RuntimeError("detached boom")

    monkeypatch.setattr(trending_sync, "refresh_trending_store", failing_refresh_store)

    stale = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    db.trending_cycle_mark_synced(stale)
    await ctx.reschedule_trending(1440)

    with pytest.raises(RuntimeError, match="detached boom"):
        await asyncio.gather(*list(trending_sync._REFRESH_TASKS))

    assert not trending_sync._REFRESH_ACTIVE


async def test_backfill_reuses_fresh_imdb_rating_for_resolved_alias(db) -> None:
    # A TMDB-only alias resolving to a title already rated under its IMDb key
    # copies the stored rating instead of spending a second OMDb request.
    ctx = make_ctx(db=db)
    db.trending_ratings_upsert(key="tt2", imdb_rating=7.1, imdb_votes=5)
    ctx.tmdb.fetch_external_ids.return_value = "tt2"
    _feed(ctx, [{"media_type": "movie", "tmdb": 603}])

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_not_awaited()
    stored = db.trending_ratings_get_many(["movie:603"])["movie:603"]
    assert stored["imdb_rating"] == 7.1
    assert stored["imdb_votes"] == 5


async def test_backfill_refetches_when_resolved_alias_rating_is_stale(db) -> None:
    # A stale rating under the resolved IMDb key is not reused: the title is
    # re-fetched and both key forms end up refreshed.
    ctx = make_ctx(db=db)
    db.trending_ratings_upsert(
        key="tt2",
        imdb_rating=5.0,
        imdb_votes=1,
        fetched_at="2020-01-01T00:00:00+00:00",
    )
    ctx.tmdb.fetch_external_ids.return_value = "tt2"
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.1, "imdb_votes": 900}
    _feed(ctx, [{"media_type": "movie", "tmdb": 603}])

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_awaited_once_with(imdb_id="tt2")
    assert (
        db.trending_ratings_get_many(["movie:603"])["movie:603"]["imdb_rating"] == 8.1
    )
    assert db.trending_ratings_get_many(["tt2"])["tt2"]["imdb_rating"] == 8.1


async def test_backfill_honours_configured_rating_window(db) -> None:
    # A rating fetched six days ago is stale under a 5-day window but fresh
    # under the default 7 days.
    from tests.conftest import StubSettingsStore

    six_days_ago = (datetime.now(UTC) - timedelta(days=6)).isoformat()

    short_ctx = make_ctx(db=db, settings_store=StubSettingsStore(rating_ttl_days=5))
    short_ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.0, "imdb_votes": 1}
    db.trending_ratings_upsert(
        key="tt1", imdb_rating=5.0, imdb_votes=1, fetched_at=six_days_ago
    )
    _feed(short_ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])
    await trending_sync.backfill_ratings(short_ctx)
    short_ctx.omdb.fetch_rating.assert_awaited_once_with(imdb_id="tt1")

    default_ctx = make_ctx(db=db)  # stub store defaults to 7 days
    db.trending_ratings_upsert(
        key="tt2", imdb_rating=6.0, imdb_votes=1, fetched_at=six_days_ago
    )
    _feed(default_ctx, [{"media_type": "movie", "tmdb": 2, "imdb": "tt2"}])
    await trending_sync.backfill_ratings(default_ctx)
    default_ctx.omdb.fetch_rating.assert_not_awaited()


async def test_backfill_budget_scales_with_omdb_key_count(db) -> None:
    # Two configured keys double the per-key budget: with per-key 1, a
    # three-title backlog fetches exactly two and leaves one for later.
    from tests.conftest import StubSettingsStore

    ctx = make_ctx(
        db=db, settings_store=StubSettingsStore(omdb_daily_budget_per_key=100)
    )
    db.omdb_usage_add(utcnow_iso()[:10], 198)  # 2x100 budget, two requests left
    ctx.omdb.key_count.return_value = 2
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 6.0, "imdb_votes": 2}
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": 1, "imdb": "tt1"},
            {"media_type": "movie", "tmdb": 2, "imdb": "tt2"},
            {"media_type": "movie", "tmdb": 3, "imdb": "tt3"},
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    assert ctx.omdb.fetch_rating.await_count == 2
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 200


async def test_backfill_skips_cleanly_without_any_omdb_key(db) -> None:
    # No configured key means no budget: the run logs a clear skip instead of
    # a misleading "budget exhausted" and never touches the usage counter.
    ctx = make_ctx(db=db)
    ctx.omdb.key_count.return_value = 0
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])

    await trending_sync.backfill_ratings(ctx)

    ctx.omdb.fetch_rating.assert_not_awaited()
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 0


async def test_backfill_retries_failed_lookups_instead_of_caching_nulls(db) -> None:
    # A failed lookup (all keys rejected, network down) stores nothing and
    # charges nothing, so the next run picks the title up again — unlike a
    # definitive OMDb "N/A", which is stored and not re-fetched.
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.return_value = None
    _feed(ctx, [{"media_type": "movie", "tmdb": 1, "imdb": "tt1"}])

    await trending_sync.backfill_ratings(ctx)

    assert db.trending_ratings_get_many(["tt1"]) == {}
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 0

    # The next run retries and a definitive answer lands normally.
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.2, "imdb_votes": 42}
    await trending_sync.backfill_ratings(ctx)
    assert ctx.omdb.fetch_rating.await_count == 2
    assert db.trending_ratings_get_many(["tt1"])["tt1"]["imdb_rating"] == 8.2
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 1


async def test_backfill_circuit_breaks_after_consecutive_failures(db) -> None:
    # With OMDb unavailable for every attempt (all keys dead), the run stops
    # probing after the breaker threshold instead of walking the whole backlog
    # on every hourly run; the deferred titles stay pending for later.
    ctx = make_ctx(db=db)
    ctx.omdb.fetch_rating.return_value = None
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": index, "imdb": f"tt{index}"}
            for index in range(1, 41)
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    breaker = trending_sync._BACKFILL_FAILURE_BREAKER
    concurrency = trending_sync._BACKFILL_CONCURRENCY
    assert ctx.omdb.fetch_rating.await_count >= breaker
    # In-flight tasks may overshoot by up to the concurrency window, but the
    # remaining ~30 titles are deferred without a single probe.
    assert ctx.omdb.fetch_rating.await_count <= breaker + concurrency
    assert db.trending_ratings_get_many([f"tt{i}" for i in range(1, 41)]) == {}
    assert db.omdb_usage_count(utcnow_iso()[:10]) == 0


async def test_backfill_failure_streak_resets_on_success(db) -> None:
    # Scattered failures below the threshold never trip the breaker: a
    # definitive answer resets the streak and the whole batch is attempted.
    ctx = make_ctx(db=db)
    answers = []
    for index in range(20):
        if index % 3 == 2:
            answers.append({"imdb_rating": 7.0, "imdb_votes": 1})
        else:
            answers.append(None)
    ctx.omdb.fetch_rating.side_effect = answers
    _feed(
        ctx,
        [
            {"media_type": "movie", "tmdb": index, "imdb": f"tt{index}"}
            for index in range(1, 21)
        ],
    )

    await trending_sync.backfill_ratings(ctx)

    assert ctx.omdb.fetch_rating.await_count == 20


async def test_ambiguous_anime_mapping_resolves_rating_via_tmdb(db) -> None:
    # An anime show whose Fribb imdb mapping was ambiguous arrives from
    # enrichment with only its tv-space tmdb id. The backfill resolves the
    # authoritative IMDb id via TMDB and stores the rating under both key
    # forms, so the feed row's alias key surfaces the correct rating.
    ctx = make_ctx(db=db)
    ctx.tmdb.fetch_external_ids.return_value = "tt-right"
    ctx.omdb.fetch_rating.return_value = {"imdb_rating": 8.4, "imdb_votes": 900}
    _feed(ctx, [{"media_type": "show", "tmdb": 42828, "anilist": 1719}])

    await trending_sync.backfill_ratings(ctx)

    ctx.tmdb.fetch_external_ids.assert_awaited_once_with(
        media_type="show", tmdb_id=42828
    )
    stored = db.trending_ratings_get_many(["show:42828", "tt-right"])
    assert stored["show:42828"]["imdb_rating"] == 8.4
    assert stored["tt-right"]["imdb_rating"] == 8.4
