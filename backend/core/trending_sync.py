"""Scheduled trending/popular refresh.

The Trending page is served from an in-process snapshot (``ctx.trending_store``)
rather than calling the Trakt/TMDB/Seer providers on every request. A scheduled
job refreshes that snapshot on the configured interval; this module owns the
refresh routine, the APScheduler-compatible module-level job, the holder the job
reads (APScheduler 4 cannot serialise a closure — this mirrors
``core.app._poster_churn``), and the start/reschedule wiring.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.app_metrics import observe_scheduler_job
from core.db import utcnow_iso
from core.logging import get_logger
from core.trending import SCHEDULED_TRENDING_LIMIT, TRENDING_SYNC_PAGES
from core.trending_api import fetch_feed, fetch_seer_trending_buckets

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

# The job id under which the interval schedule is registered (and rescheduled).
_JOB_ID = "trending_sync"
_log = get_logger("trending_sync")

# Poster pre-warm bounds: how many posters to fetch concurrently, and how long any
# single fetch may take before it is abandoned (so one hung upstream cannot stall the
# batch). Pre-warm is best-effort and detached, so it never delays the refresh or boot.
_PREWARM_CONCURRENCY = 8
_PREWARM_TIMEOUT_SECONDS = 20
# Strong references to in-flight pre-warm tasks so they are not garbage-collected
# before completion (per the asyncio docs); cleared by a done-callback.
_PREWARM_TASKS: set[asyncio.Task] = set()

# The feed matrix refreshed each cycle. TMDB trending uses the weekly window — the
# only window the dashboard ever requests — so it is the only one kept warm.
_SOURCES = ("trakt", "tmdb", "seer")
_MEDIA = ("movie", "show")
_CATEGORIES = ("trending", "popular")
SYNC_WINDOW = "week"


async def _store_feed(
    ctx: "AppContext", *, source: str, media: str, category: str
) -> None:
    """Refresh one ``(source, media, category)`` feed into the store.

    A provider failure is logged and leaves the previous snapshot for that feed
    intact rather than blanking it.
    """
    try:
        rows = await fetch_feed(
            ctx,
            source=source,
            media=media,
            category=category,
            window=SYNC_WINDOW,
            limit=SCHEDULED_TRENDING_LIMIT,
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
        return
    ctx.trending_store.set(
        source=source, media=media, category=category, window=SYNC_WINDOW, rows=rows
    )


async def _store_seer_trending(ctx: "AppContext") -> None:
    """Refresh both Seer trending feeds from a single mixed-type fetch.

    Seer's trending endpoint returns movies and shows on one page, so it is fetched
    as bounded mixed pages and split by media type — rather than fetched separately
    for each type. A failure is logged and leaves the previous snapshots intact.
    """
    try:
        buckets = await fetch_seer_trending_buckets(
            ctx, limit=SCHEDULED_TRENDING_LIMIT, pages=TRENDING_SYNC_PAGES
        )
    except Exception as exc:  # noqa: BLE001 - a dead feed must not abort the cycle
        _log.warning("trending refresh failed (source=seer category=trending): %s", exc)
        return
    for media in _MEDIA:
        ctx.trending_store.set(
            source="seer",
            media=media,
            category="trending",
            window=SYNC_WINDOW,
            rows=buckets[media],
        )


async def refresh_trending_store(ctx: "AppContext") -> None:
    """Refresh every trending/popular feed into ``ctx.trending_store``.

    Each feed is fetched independently so one dead provider does not abort the cycle.
    Seer's mixed trending feed is fetched once and split by media type (see
    :func:`_store_seer_trending`); every other feed is per media type. The store's
    last-synced timestamp is stamped once the cycle finishes.
    """
    for source in _SOURCES:
        for category in _CATEGORIES:
            if source == "seer" and category == "trending":
                await _store_seer_trending(ctx)
                continue
            for media in _MEDIA:
                await _store_feed(ctx, source=source, media=media, category=category)
    ctx.trending_store.mark_synced(utcnow_iso())
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


async def prewarm_posters(ctx: "AppContext") -> None:
    """Fetch posters for the currently-stored trending rows into the disk cache.

    Best-effort: bounded by :data:`_PREWARM_CONCURRENCY`, each fetch capped by
    :data:`_PREWARM_TIMEOUT_SECONDS`, and every failure swallowed so a dead poster
    source never affects the rest. A no-op when no poster cache is configured.
    """
    if ctx.poster_cache is None:
        return
    targets = _prewarm_targets(ctx.trending_store.all_rows())
    if not targets:
        return
    semaphore = asyncio.Semaphore(_PREWARM_CONCURRENCY)

    async def _one(media_type: str, tmdb: int, imdb: str | None) -> None:
        async with semaphore:
            await asyncio.wait_for(
                ctx.poster_cache.get_poster(
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


def _spawn_prewarm(ctx: "AppContext") -> None:
    """Fire poster pre-warming as a detached task so it never blocks the caller.

    A no-op when no poster cache is configured, so callers in tests without a cache
    do not leave a pending task behind.
    """
    if ctx.poster_cache is None:
        return
    task = asyncio.create_task(prewarm_posters(ctx))
    _PREWARM_TASKS.add(task)
    task.add_done_callback(_PREWARM_TASKS.discard)


@dataclass
class _TrendingSync:
    """Holds the context the module-level job reads (APScheduler-4 constraint)."""

    ctx: "AppContext | None" = None


_trending_sync = _TrendingSync()


async def _trending_sync_job() -> None:
    """Scheduled entrypoint: refresh the trending snapshot, then pre-warm posters."""
    ctx = _trending_sync.ctx
    if ctx is None:  # pragma: no cover - ctx is set before the job is scheduled
        return
    async def refresh_and_prewarm() -> None:
        await refresh_trending_store(ctx)
        _spawn_prewarm(ctx)

    await observe_scheduler_job(_JOB_ID, refresh_and_prewarm)


async def start_trending_sync(ctx: "AppContext") -> None:
    """Schedule the periodic trending refresh and prime the store immediately.

    An interval trigger only fires after the first interval elapses, so the store is
    refreshed once at start-up to avoid serving an empty grid on a cold boot. Also
    exposes ``ctx.reschedule_trending`` so a settings change re-points the job
    (mirrors ``reschedule_sync`` / ``findarr_reschedule``).
    """
    _trending_sync.ctx = ctx
    await ctx.scheduler.add_interval(
        _trending_sync_job,
        minutes=ctx.settings_store.trending_sync_interval_minutes(),
        id=_JOB_ID,
    )
    ctx.reschedule_trending = lambda minutes: ctx.scheduler.reschedule_interval(
        _trending_sync_job, minutes=minutes, id=_JOB_ID
    )
    await refresh_trending_store(ctx)
    _spawn_prewarm(ctx)
