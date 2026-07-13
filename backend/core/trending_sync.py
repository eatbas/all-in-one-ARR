"""Scheduled trending/popular refresh and the budgeted IMDb-rating backfill.

The Trending page is served from an in-process snapshot (``ctx.trending_store``)
rather than calling the Trakt/TMDB/Seer providers on every request. A scheduled
job refreshes that snapshot on the configured interval; this module owns the
refresh routine, the APScheduler-compatible module-level jobs, the holder the
jobs read (APScheduler 4 cannot serialise a closure — this mirrors
``core.app._poster_churn``), and the start/reschedule wiring.

The snapshot is mirrored into the database (``trending_feeds``) so a restart
within the configured interval reloads it instead of refetching every provider.
IMDb ratings are filled into ``trending_ratings`` by a background backfill that
spends at most the configured per-key budget (Settings -> OMDb tab, default
800) per configured API key per UTC day (tracked in ``omdb_usage``; the client
rotates keys on quota exhaustion); whatever does not fit is picked up by the next run — the
daily cron drains the backlog even on days the feed refresh does not fire.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from core.app_metrics import observe_scheduler_job
from core.db import utcnow_iso
from core.logging import get_logger
from core.tasks import spawn_supervised, spawn_tracked
from core.trending import (
    TRENDING_ITEM_LIMIT,
    TRENDING_SYNC_PAGES,
    trending_rating_key,
)
from core.trending_api import fetch_feed, fetch_seer_trending_buckets

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

# The job ids under which the schedules are registered (and rescheduled).
_JOB_ID = "trending_sync"
_BACKFILL_JOB_ID = "trending_rating_backfill"
# The backfill re-runs hourly (single-flight, cheap no-op when nothing is
# pending) so the backlog drains as soon as budget frees or new titles appear.
_BACKFILL_INTERVAL_MINUTES = 60
_log = get_logger("trending_sync")

# Poster pre-warm bounds: how many posters to fetch concurrently, and how long any
# single fetch may take before it is abandoned (so one hung upstream cannot stall the
# batch). Pre-warm is best-effort and detached, so it never delays the refresh or boot.
_PREWARM_CONCURRENCY = 8
_PREWARM_TIMEOUT_SECONDS = 20
# Strong references to in-flight pre-warm tasks so they are not garbage-collected
# before completion (per the asyncio docs); cleared by a done-callback.
_PREWARM_TASKS: set[asyncio.Task] = set()

# Rating backfill bounds. The per-key daily budget is user-configured
# (Settings -> OMDb tab, default 800 of OMDb's ~1000/day free tier, leaving
# headroom for the poster fallback and the compat rating route); the effective
# run budget scales with the number of configured keys (see
# ``backfill_ratings``). Stored ratings are refreshed once older than the
# configured window (Settings -> General: 5/7/10 days); missing ones come
# first so new titles gain a badge before old ratings are re-polled.
_BACKFILL_CONCURRENCY = 8
# Circuit breaker: when this many OMDb lookups fail in a row, the whole pool
# is evidently unavailable (all keys exhausted or rejected, or OMDb is down),
# so the run defers the rest of the backlog instead of probing every pending
# title once per hour for nothing.
_BACKFILL_FAILURE_BREAKER = 10
# Strong references to in-flight backfill tasks (same rationale as _PREWARM_TASKS).
# Also the concurrency guard: a non-empty set means a backfill is in flight, so
# duplicate triggers are skipped rather than double-spending the daily budget.
_BACKFILL_TASKS: set[asyncio.Task] = set()
# Strong references to a reschedule-triggered catch-up refresh (see
# ``start_trending_sync``'s reschedule hook).
_REFRESH_TASKS: set[asyncio.Task] = set()
# Guard refresh cycles so repeated reschedules or scheduler overlap cannot run
# multiple provider sweeps concurrently.
_REFRESH_LOCK = asyncio.Lock()
_REFRESH_ACTIVE = False


# The feed matrix refreshed each cycle. TMDB trending uses the weekly window — the
# only window the dashboard ever requests — so it is the only one kept warm. The
# anime variants and AniList are full members of the matrix so the Anime tab is
# served from the same warmed snapshot.
_SOURCES = ("trakt", "tmdb", "seer", "trakt-anime", "tmdb-anime", "anilist")
_MEDIA = ("movie", "show")
_CATEGORIES = ("trending", "popular")
SYNC_WINDOW = "week"


def _persist_feed(
    ctx: AppContext, *, source: str, media: str, category: str, rows: list[dict]
) -> None:
    """Write one feed into the in-process store and its database mirror.

    Kept as one helper so the snapshot a restart restores can never drift from
    what the running process serves.
    """
    ctx.trending_store.set(
        source=source, media=media, category=category, window=SYNC_WINDOW, rows=rows
    )
    ctx.db.trending_feeds_save(
        source=source, media=media, category=category, window=SYNC_WINDOW, rows=rows
    )


async def _store_feed(
    ctx: AppContext, *, source: str, media: str, category: str
) -> bool:
    """Refresh one ``(source, media, category)`` feed into the store.

    A provider failure is logged and leaves the previous snapshot for that feed
    intact rather than blanking it. Returns ``True`` when the feed was refreshed.
    """
    try:
        rows = await fetch_feed(
            ctx,
            source=source,
            media=media,
            category=category,
            window=SYNC_WINDOW,
            limit=TRENDING_ITEM_LIMIT,
            pages=TRENDING_SYNC_PAGES,
        )
    except Exception as exc:  # noqa: BLE001 - one dead feed must not abort the cycle
        _log.warning(
            "trending refresh failed (source=%s media=%s category=%s): %s",
            source,
            media,
            category,
            exc,
        )
        return False
    _persist_feed(ctx, source=source, media=media, category=category, rows=rows)
    return True


async def _store_seer_trending(ctx: AppContext) -> bool:
    """Refresh both Seer trending feeds from a single mixed-type fetch.

    Seer's trending endpoint returns movies and shows on one page, so it is fetched
    as bounded mixed pages and split by media type — rather than fetched separately
    for each type. A failure is logged and leaves the previous snapshots intact.
    Returns ``True`` when both feeds were refreshed.
    """
    try:
        buckets = await fetch_seer_trending_buckets(
            ctx, limit=TRENDING_ITEM_LIMIT, pages=TRENDING_SYNC_PAGES
        )
    except Exception as exc:  # noqa: BLE001 - a dead feed must not abort the cycle
        _log.warning("trending refresh failed (source=seer category=trending): %s", exc)
        return False
    for media in _MEDIA:
        _persist_feed(
            ctx, source="seer", media=media, category="trending", rows=buckets[media]
        )
    return True


async def refresh_trending_store(ctx: AppContext) -> None:
    """Refresh every trending/popular feed into ``ctx.trending_store``.

    Each feed is fetched independently so one dead provider does not abort the cycle.
    Seer's mixed trending feed is fetched once and split by media type (see
    :func:`_store_seer_trending`); every other feed is per media type. The store's
    last-synced timestamp is stamped only when every feed succeeds, so a partial
    cycle cannot make stale feeds appear fresh on restart.
    """
    any_failed = False
    for source in _SOURCES:
        for category in _CATEGORIES:
            if source == "seer" and category == "trending":
                if not await _store_seer_trending(ctx):
                    any_failed = True
                continue
            for media in _MEDIA:
                if not await _store_feed(
                    ctx, source=source, media=media, category=category
                ):
                    any_failed = True
    if any_failed:
        _log.warning("trending refresh cycle finished with one or more feed failures")
        return
    now = utcnow_iso()
    ctx.trending_store.mark_synced(now)
    ctx.db.trending_cycle_mark_synced(now)
    _log.info("trending store refreshed")


def _prewarm_targets(
    rows: list[dict],
) -> list[tuple[str, int, str | None]]:
    """Deduplicate stored rows into ``(media_type, tmdb, imdb)`` poster targets.

    Keyed by ``(media_type, tmdb)`` so a title appearing in several feeds is fetched
    once; rows without an integer ``tmdb`` are skipped. The first non-null ``imdb``
    seen for a key is kept so Trakt/Seer rows enable the OMDb fallback even when a
    TMDB-only row (no imdb) is encountered first.
    """
    seen: dict[tuple[str, int], str | None] = {}
    for row in rows:
        tmdb = row.get("tmdb")
        media_type = row.get("media_type")
        if not isinstance(tmdb, int) or media_type not in ("movie", "show"):
            continue
        key = (media_type, tmdb)
        imdb = row.get("imdb")
        if key not in seen:
            seen[key] = imdb
        elif seen[key] is None and imdb:
            seen[key] = imdb
    return [(media_type, tmdb, imdb) for (media_type, tmdb), imdb in seen.items()]


async def prewarm_posters(ctx: AppContext) -> None:
    """Fetch posters for the currently-stored trending rows into the disk cache.

    Best-effort: bounded by :data:`_PREWARM_CONCURRENCY`, each fetch capped by
    :data:`_PREWARM_TIMEOUT_SECONDS`, and every failure swallowed so a dead poster
    source never affects the rest. A no-op when no poster cache is configured.
    """
    if ctx.poster_cache is None:
        return
    poster_cache = ctx.poster_cache
    targets = _prewarm_targets(ctx.trending_store.all_rows())
    if not targets:
        return
    semaphore = asyncio.Semaphore(_PREWARM_CONCURRENCY)

    async def _one(media_type: str, tmdb: int, imdb: str | None) -> None:
        async with semaphore:
            await asyncio.wait_for(
                poster_cache.get_poster(
                    media_type=media_type, tmdb_id=tmdb, imdb_id=imdb
                ),
                _PREWARM_TIMEOUT_SECONDS,
            )

    results = await asyncio.gather(
        *(_one(media_type, tmdb, imdb) for media_type, tmdb, imdb in targets),
        return_exceptions=True,
    )
    failed = sum(1 for result in results if isinstance(result, Exception))
    _log.info("poster pre-warm: %d targets, %d failed", len(targets), failed)


def _spawn_prewarm(ctx: AppContext) -> None:
    """Fire poster pre-warming as a detached task so it never blocks the caller.

    A no-op when no poster cache is configured, so callers in tests without a cache
    do not leave a pending task behind.
    """
    if ctx.poster_cache is None:
        return
    spawn_tracked(_PREWARM_TASKS, prewarm_posters(ctx))


# ---- IMDb-rating backfill ----


@dataclass
class _RatingGroup:
    """One deduplicated title to rate, with every storage alias observed.

    ``canonical`` is the key used for freshness checks and TMDB->IMDb resolution:
    the IMDb id when known, otherwise the ``media_type:tmdb`` alias. ``aliases``
    holds every key under which the rating must be stored so rows keyed by
    either form all hit the cache.
    """

    canonical: str
    imdb: str | None
    media_type: str
    tmdb: int
    aliases: set[str]


def _rating_targets(rows: list[dict]) -> list[_RatingGroup]:
    """Group rows by title identity so each title is looked up once.

    Rows carrying both IMDb and TMDB ids merge with rows that only carry the
    matching TMDB alias, preventing the same title from consuming two OMDb
    requests. Rows without a usable id are skipped.
    """
    # First pass: build (media_type, tmdb) -> imdb for rows that expose both ids.
    alias_to_imdb: dict[tuple[str, int], str] = {}
    for row in rows:
        imdb = row.get("imdb")
        media_type = row.get("media_type")
        tmdb = row.get("tmdb")
        if imdb and media_type in ("movie", "show") and isinstance(tmdb, int):
            alias_to_imdb[(media_type, tmdb)] = imdb

    groups: dict[str, _RatingGroup] = {}
    for row in rows:
        imdb = row.get("imdb")
        media_type = row.get("media_type")
        tmdb = row.get("tmdb")
        alias = trending_rating_key(imdb=imdb, media_type=media_type, tmdb=tmdb)
        if alias is None:
            continue

        resolved_imdb = imdb
        if (
            not resolved_imdb
            and media_type in ("movie", "show")
            and isinstance(tmdb, int)
        ):
            resolved_imdb = alias_to_imdb.get((media_type, tmdb))

        canonical = resolved_imdb if resolved_imdb else alias

        if canonical not in groups:
            groups[canonical] = _RatingGroup(
                canonical=canonical,
                imdb=resolved_imdb,
                media_type=media_type or "",
                tmdb=tmdb if isinstance(tmdb, int) else 0,
                aliases=set(),
            )
        groups[canonical].aliases.add(alias)

    return list(groups.values())


async def backfill_ratings(ctx: AppContext) -> None:
    """Fill missing/stale IMDb ratings for the stored rows, within today's budget.

    Missing keys are fetched before stale ones so new titles gain a badge first.
    A TMDB-only target is resolved to an IMDb id first (a failed resolution is
    left missing so a later run retries — it costs no OMDb budget); a resolved
    rating is stored under every observed alias and the resolved IMDb key.
    ``fetch_rating`` never raises and reports "no rating" as nulls, which are
    stored too so a title known to lack a rating is not re-fetched daily.
    """
    targets = _rating_targets(ctx.trending_store.all_rows())
    if not targets:
        return
    stored = ctx.db.trending_ratings_get_many([target.canonical for target in targets])
    ttl_days = ctx.settings_store.rating_ttl_days()
    cutoff = (datetime.now(UTC) - timedelta(days=ttl_days)).isoformat()
    missing = [target for target in targets if target.canonical not in stored]
    stale = [
        target
        for target in targets
        if target.canonical in stored
        and stored[target.canonical]["fetched_at"] < cutoff
    ]
    pending = missing + stale
    if not pending:
        _log.info(
            "rating backfill: all %d stored titles rated; nothing pending",
            len(targets),
        )
        return
    key_count = ctx.omdb.key_count()
    if key_count == 0:
        _log.info("no OMDb API key configured; rating backfill skipped")
        return
    today = utcnow_iso()[:10]
    # The daily budget scales with the configured OMDb keys (the client rotates
    # to the next key when one hits its request limit); the per-key figure is
    # user-configured and read live so an edit applies on the next run.
    budget = ctx.settings_store.omdb_daily_budget_per_key() * key_count
    remaining = budget - ctx.db.omdb_usage_count(today)
    if remaining <= 0:
        _log.info(
            "rating backfill: %d pending, daily OMDb budget exhausted", len(pending)
        )
        return
    batch = pending[:remaining]
    semaphore = asyncio.Semaphore(_BACKFILL_CONCURRENCY)
    consecutive_failures = 0
    breaker_tripped = False

    async def _one(target: _RatingGroup) -> bool | None:
        nonlocal consecutive_failures, breaker_tripped
        async with semaphore:
            if breaker_tripped:
                return None  # deferred to a later run; not an attempt
            imdb_id = target.imdb
            if not imdb_id:
                imdb_id = await ctx.tmdb.fetch_external_ids(
                    media_type=target.media_type, tmdb_id=target.tmdb
                )
                if not imdb_id:
                    # Unresolved: leave every alias missing so a later run retries.
                    return False
                stored_imdb = ctx.db.trending_ratings_get_many([imdb_id]).get(imdb_id)
                if stored_imdb is not None and stored_imdb["fetched_at"] >= cutoff:
                    # Another feed already paid OMDb for this title under its
                    # IMDb key; copy the stored rating across the aliases
                    # instead of spending a second request on the same title.
                    for key in target.aliases:
                        ctx.db.trending_ratings_upsert(
                            key=key,
                            imdb_rating=stored_imdb["imdb_rating"],
                            imdb_votes=stored_imdb["imdb_votes"],
                        )
                    return True
            rating = await ctx.omdb.fetch_rating(imdb_id=imdb_id)
            if rating is None:
                # Failed lookup (keys exhausted/rejected, network): store
                # nothing and charge nothing so a later run retries — only a
                # definitive OMDb answer may be remembered. A long failure
                # streak trips the breaker and defers the rest of the batch.
                consecutive_failures += 1
                if consecutive_failures >= _BACKFILL_FAILURE_BREAKER:
                    breaker_tripped = True
                return False
            consecutive_failures = 0
            ctx.db.omdb_usage_add(today, 1)
            for key in target.aliases:
                ctx.db.trending_ratings_upsert(
                    key=key,
                    imdb_rating=rating["imdb_rating"],
                    imdb_votes=rating["imdb_votes"],
                )
            if imdb_id not in target.aliases:
                ctx.db.trending_ratings_upsert(
                    key=imdb_id,
                    imdb_rating=rating["imdb_rating"],
                    imdb_votes=rating["imdb_votes"],
                )
            return True

    results = await asyncio.gather(
        *(_one(target) for target in batch), return_exceptions=True
    )
    fetched = sum(1 for result in results if result is True)
    failed = sum(1 for result in results if isinstance(result, Exception))
    deferred = sum(1 for result in results if result is None)
    unresolved = len(batch) - fetched - failed - deferred
    if breaker_tripped:
        _log.warning(
            "rating backfill: %d consecutive OMDb failures — OMDb appears "
            "unavailable; deferring %d titles to a later run",
            _BACKFILL_FAILURE_BREAKER,
            deferred,
        )
    _log.info(
        "rating backfill: %d pending, %d fetched, %d unresolved, %d failed, "
        "%d left for a later run",
        len(pending),
        fetched,
        unresolved,
        failed,
        len(pending) - len(batch) + deferred,
    )


def _spawn_rating_backfill(ctx: AppContext) -> asyncio.Task | None:
    """Fire the rating backfill detached, unless one is already in flight.

    The guard keeps concurrent triggers (a refresh cycle and the daily cron
    landing together) from running two backfills that would each spend the full
    daily budget — double the OMDb quota. The in-flight run already scans the
    latest store state; anything it leaves is picked up by the next trigger.
    The check-then-spawn pair is atomic on the single event loop (no await
    between them), so two triggers cannot both pass the guard.
    """
    if _BACKFILL_TASKS:
        _log.info("rating backfill already in flight; skipping duplicate trigger")
        return None
    return spawn_tracked(_BACKFILL_TASKS, backfill_ratings(ctx))


@dataclass
class _TrendingSync:
    """Holds the context the module-level job reads (APScheduler-4 constraint)."""

    ctx: AppContext | None = None


_trending_sync = _TrendingSync()


async def _refresh_cycle(ctx: AppContext) -> None:
    """One full refresh pass: fetch every feed, then pre-warm posters and ratings.

    Guarded: overlapping calls (repeated reschedules or scheduler overlap) are
    skipped so only one cycle runs at a time.
    """
    global _REFRESH_ACTIVE
    async with _REFRESH_LOCK:
        if _REFRESH_ACTIVE:
            _log.info("refresh cycle already active; skipping")
            return
        _REFRESH_ACTIVE = True
    await _run_refresh_cycle(ctx)


async def _run_refresh_cycle(ctx: AppContext) -> None:
    """The actual refresh-cycle work, with guaranteed cleanup of the active flag."""
    global _REFRESH_ACTIVE
    try:
        await refresh_trending_store(ctx)
        _spawn_prewarm(ctx)
        _spawn_rating_backfill(ctx)
    except Exception:
        _log.exception("refresh cycle raised an exception")
        raise
    finally:
        async with _REFRESH_LOCK:
            _REFRESH_ACTIVE = False


async def _trending_sync_job() -> None:
    """Scheduled entrypoint: refresh the snapshot, then pre-warm posters and ratings."""
    ctx = _trending_sync.ctx
    if ctx is None:  # pragma: no cover - ctx is set before the job is scheduled
        return
    await observe_scheduler_job(_JOB_ID, lambda: _refresh_cycle(ctx))


async def _rating_backfill_job() -> None:
    """Scheduled entrypoint: drain the rating backlog within the daily budget.

    Runs hourly (a cheap no-op when nothing is pending) so failed lookups are
    retried promptly and the backlog resumes as soon as the day rolls over and
    budget frees. Skipped when another backfill is already in flight (see
    :func:`_spawn_rating_backfill`).
    """
    ctx = _trending_sync.ctx
    if ctx is None:  # pragma: no cover - ctx is set before the job is scheduled
        return

    async def run_exclusive() -> None:
        task = _spawn_rating_backfill(ctx)
        if task is not None:
            await task

    await observe_scheduler_job(_BACKFILL_JOB_ID, run_exclusive)


def _restore_trending_store(ctx: AppContext) -> str | None:
    """Load the persisted feed snapshot into the store; return its last sync time.

    Returns ``None`` when nothing was persisted (first boot, or a pre-persistence
    database), in which case the caller refreshes live as before.
    """
    feeds = ctx.db.trending_feeds_load()
    for feed in feeds:
        ctx.trending_store.set(
            source=feed["source"],
            media=feed["media"],
            category=feed["category"],
            window=feed["window"],
            rows=feed["rows"],
        )
    last = ctx.db.trending_cycle_last_synced()
    if last is not None:
        ctx.trending_store.mark_synced(last)
    return last


def _is_fresh(last_synced_at: str, *, interval_minutes: int) -> bool:
    """Whether a persisted snapshot is younger than the configured interval.

    An unparseable timestamp counts as stale so the boot path degrades to a
    normal live refresh rather than serving a snapshot of unknown age. A naive
    timestamp parses but cannot be compared against aware now (``TypeError``),
    so it is treated the same way.
    """
    try:
        last = datetime.fromisoformat(last_synced_at)
        return datetime.now(UTC) - last < timedelta(minutes=interval_minutes)
    except ValueError, TypeError:
        return False


async def start_trending_sync(ctx: AppContext) -> None:
    """Schedule the refresh and backfill jobs and prime the store.

    The persisted snapshot is restored first; a live refresh (and poster
    pre-warm) runs only when that snapshot is absent or older than the
    configured interval, so a restart inside the 1–3-day cadence serves
    instantly without a provider fetch burst. The rating backfill is spawned on
    every boot — it no-ops cheaply when nothing is pending. Also exposes
    ``ctx.reschedule_trending`` so a settings change re-points the job (mirrors
    ``reschedule_sync`` / ``findarr_reschedule``).
    """
    _trending_sync.ctx = ctx
    # defer_first_run: APScheduler 4's interval trigger fires immediately by
    # default, which would refetch every provider right after the boot path
    # below has already primed (or restored) the store.
    await ctx.scheduler.add_interval(
        _trending_sync_job,
        minutes=ctx.settings_store.trending_sync_interval_minutes(),
        id=_JOB_ID,
        defer_first_run=True,
    )

    async def _reschedule_trending(minutes: int) -> None:
        """Re-point the interval job; catch up once if the snapshot is now stale.

        ``defer_first_run`` pushes the next scheduled fire one full *new*
        interval out, so without this check a 3-day-old snapshot would survive
        a switch to a 1-day cadence for yet another day. A catch-up cycle is
        skipped when one is already active, and every detached cycle is
        supervised so exceptions are never lost.
        """
        global _REFRESH_ACTIVE
        await ctx.scheduler.reschedule_interval(
            _trending_sync_job, minutes=minutes, id=_JOB_ID, defer_first_run=True
        )
        last_synced = ctx.db.trending_cycle_last_synced()
        if last_synced is not None and _is_fresh(last_synced, interval_minutes=minutes):
            return
        async with _REFRESH_LOCK:
            if _REFRESH_ACTIVE:
                _log.info("refresh cycle already active; skipping duplicate catch-up")
                return
            _REFRESH_ACTIVE = True
        spawn_supervised(
            _REFRESH_TASKS,
            _run_refresh_cycle(ctx),
            log=_log,
            log_msg="reschedule-triggered refresh cycle raised an exception",
        )

    ctx.reschedule_trending = _reschedule_trending
    # defer_first_run: the boot path below already spawns a backfill; the
    # hourly re-run keeps draining the backlog afterwards.
    await ctx.scheduler.add_interval(
        _rating_backfill_job,
        minutes=_BACKFILL_INTERVAL_MINUTES,
        id=_BACKFILL_JOB_ID,
        defer_first_run=True,
    )
    last = _restore_trending_store(ctx)
    interval = ctx.settings_store.trending_sync_interval_minutes()
    if last is None or not _is_fresh(last, interval_minutes=interval):
        await _refresh_cycle(ctx)
    else:
        _log.info("trending store restored from database (last synced %s)", last)
        _spawn_rating_backfill(ctx)
