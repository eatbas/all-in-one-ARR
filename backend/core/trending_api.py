"""Trending discovery JSON API.

Backs the dashboard's Trending page: per-source (Trakt / TMDB / Seer) trending and
popular feeds, a lazily-cached IMDb rating overlay (via OMDb), and an "add to an
owned Trakt list, then sync" action. The add never creates a Seer request directly
— it adds to Trakt and triggers the existing List-Syncarr sync, which requests the
item through the normal pipeline.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.context import SyncAlreadyRunning
from core.db import Database
from core.logging import get_logger
from core.timefmt import next_sync_at
from core.trending import (
    SEER_TRENDING_SYNC_PAGES,
    TRENDING_ITEM_LIMIT,
    LibraryCache,
    LibraryIndex,
    RatingCache,
    build_library_index,
    to_trending_items,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.settings_store import TrackedList


class TrendingItem(BaseModel):
    source: str
    media_type: str
    tmdb: int | None
    imdb: str | None
    tvdb: int | None
    trakt: int | None
    slug: str | None
    title: str | None
    year: int | None
    seer_status: int | None
    already_tracked: bool
    in_library: bool
    in_library_available: bool


class TrendingRating(BaseModel):
    imdb_rating: float | None
    imdb_votes: int | None


class TrendingStatus(BaseModel):
    # When the scheduled refresh last completed (ISO-8601), the configured interval,
    # and the derived next-refresh time. ``last_synced_at``/``next_sync_at`` are null
    # until the first refresh completes.
    last_synced_at: str | None
    interval_minutes: int
    next_sync_at: str | None


async def fetch_seer_trending_buckets(
    ctx: AppContext, *, limit: int, pages: int = 1
) -> dict[str, list[dict]]:
    """Fetch Seer trending with enough mixed pages to fill both media buckets."""
    return await ctx.seer.discover_trending_buckets(
        limit_per_media=limit,
        pages=max(pages, SEER_TRENDING_SYNC_PAGES),
    )


async def fetch_feed(
    ctx: AppContext,
    *,
    source: str,
    media: str,
    category: str,
    window: str,
    limit: int,
    pages: int = 1,
) -> list[dict]:
    """Fetch and normalise one ``(source, media, category)`` discovery feed.

    Shared by the live cold-feed fallback in the router (``pages=1``) and the
    scheduled refresh (deeper ``pages``/``limit``). The Seer trending feed mixes
    media types on one endpoint, so it is bucket-filled before returning the
    requested type.
    """
    if source == "trakt":
        if category == "trending":
            return await ctx.trakt.get_trending(media_type=media, limit=limit)
        return await ctx.trakt.get_popular(media_type=media, limit=limit)
    if source == "tmdb":
        if category == "trending":
            return await ctx.tmdb.get_trending(
                media_type=media, window=window, limit=limit, pages=pages
            )
        return await ctx.tmdb.get_popular(media_type=media, limit=limit, pages=pages)
    # source == "seer"
    if category == "trending":
        buckets = await fetch_seer_trending_buckets(ctx, limit=limit, pages=pages)
        return buckets[media]
    return await ctx.seer.discover_popular(media_type=media, limit=limit, pages=pages)


class TrendingAddRequest(BaseModel):
    media_type: Literal["movie", "show"]
    owner_user: str
    slug: str
    tmdb: int | None = None
    imdb: str | None = None
    trakt: int | None = None
    tvdb: int | None = None
    title: str | None = None


def _added_anything(summary: dict) -> bool:
    """Whether Trakt actually added (or already had) the requested item.

    Trakt returns ``201`` even when an item is unresolved (it lands in
    ``not_found``); ``added`` and ``existing`` carry the per-type counts that
    indicate real success.
    """
    total = 0
    for bucket in ("added", "existing"):
        counts = summary.get(bucket)
        if isinstance(counts, dict):
            total += sum(value for value in counts.values() if isinstance(value, int))
    return total > 0


class TrendingAddResponse(BaseModel):
    status: str


def _tracked_tmdbs(db: Database) -> set[int]:
    """Return the set of TMDB ids currently mirrored on a tracked list.

    Items with status ``removed`` are excluded: they are no longer on any list, so
    treating them as "tracked" would be misleading on a trending card.
    """
    tmdbs: set[int] = set()
    for row in db.list_items():
        tmdb = row.get("tmdb")
        if tmdb is not None and row.get("status") != "removed":
            tmdbs.add(tmdb)
    return tmdbs


def _addable_target(ctx: AppContext, owner_user: str, slug: str) -> TrackedList | None:
    """Return the tracked list to add to, or ``None`` if it is not addable.

    A destination is addable only when it is a tracked list the connected account
    owns (``owner_user == "me"``) and is not the watchlist (which uses a different
    Trakt endpoint). Official curated lists are excluded implicitly (their owner is
    never ``"me"``).
    """
    for tracked in ctx.settings_store.tracked_lists():
        if tracked.owner_user == owner_user and tracked.slug == slug:
            if tracked.owner_user == "me" and not tracked.is_watchlist:
                return tracked
            return None
    return None


def create_trending_router(ctx: AppContext) -> APIRouter:
    """Build the ``/api/trending`` router bound to a specific context."""
    router = APIRouter(prefix="/api/trending", tags=["trending"])
    log = get_logger("trending")
    rating_cache = RatingCache()
    library_cache = LibraryCache()
    library_refresh_task: asyncio.Task[LibraryIndex] | None = None

    async def _fetch_library_index(previous: LibraryIndex | None) -> LibraryIndex:
        """Fetch Radarr/Sonarr libraries in parallel, preserving failed sides."""
        # asyncio.gather with return_exceptions=True yields a dynamic union that
        # mypy cannot resolve through tuple unpacking; annotate explicitly. Each
        # result is either the library payload or the exception it raised.
        radarr_result: Any
        sonarr_result: Any
        radarr_result, sonarr_result = await asyncio.gather(
            ctx.radarr.library_items(),
            ctx.sonarr.library_items(),
            return_exceptions=True,
        )
        radarr_failed = isinstance(radarr_result, Exception)
        sonarr_failed = isinstance(sonarr_result, Exception)
        if radarr_failed:
            log.warning("trending radarr library lookup failed: %s", radarr_result)
        if sonarr_failed:
            log.warning("trending sonarr library lookup failed: %s", sonarr_result)
        fresh = build_library_index(
            radarr_items=[] if radarr_failed else radarr_result,
            sonarr_items=[] if sonarr_failed else sonarr_result,
        )
        if previous is None:
            return fresh
        return LibraryIndex(
            radarr_tmdb=previous.radarr_tmdb if radarr_failed else fresh.radarr_tmdb,
            sonarr_tvdb=previous.sonarr_tvdb if sonarr_failed else fresh.sonarr_tvdb,
            sonarr_tmdb=previous.sonarr_tmdb if sonarr_failed else fresh.sonarr_tmdb,
            radarr_available_tmdb=(
                previous.radarr_available_tmdb
                if radarr_failed
                else fresh.radarr_available_tmdb
            ),
            sonarr_available_tvdb=(
                previous.sonarr_available_tvdb
                if sonarr_failed
                else fresh.sonarr_available_tvdb
            ),
            sonarr_available_tmdb=(
                previous.sonarr_available_tmdb
                if sonarr_failed
                else fresh.sonarr_available_tmdb
            ),
        )

    async def _refresh_library_index() -> LibraryIndex:
        """Fetch and store a fresh library index, using any stale value as fallback."""
        index = await _fetch_library_index(library_cache.peek())
        library_cache.set(index)
        return index

    def _spawn_library_refresh() -> None:
        """Refresh the library overlay once in the background when stale."""
        nonlocal library_refresh_task
        if library_refresh_task is not None and not library_refresh_task.done():
            return  # pragma: no cover - only hit by concurrent duplicate requests
        task = asyncio.create_task(_refresh_library_index())
        library_refresh_task = task

        def _clear_task(done: asyncio.Task[LibraryIndex]) -> None:
            nonlocal library_refresh_task
            try:
                done.result()
            except Exception as exc:  # noqa: BLE001  # pragma: no cover - guard
                log.warning("trending library refresh failed: %s", exc)
            if (
                library_refresh_task is done
            ):  # pragma: no branch - defensive identity check
                library_refresh_task = None

        task.add_done_callback(_clear_task)

    async def _library_index() -> LibraryIndex:
        """Return the Radarr/Sonarr library index without blocking on stale refreshes."""
        cached = library_cache.get()
        if cached is not None:
            return cached
        stale = library_cache.peek()
        if stale is not None:
            _spawn_library_refresh()
            return stale
        return await _refresh_library_index()

    @router.get("", response_model=list[TrendingItem])
    async def get_trending(
        source: Literal["trakt", "tmdb", "seer"],
        media: Literal["movie", "show"] = "movie",
        category: Literal["trending", "popular"] = "trending",
        window: Literal["day", "week"] = "week",
    ) -> list[TrendingItem]:
        # Serve from the scheduler-warmed snapshot. A feed the scheduler does not keep
        # warm (e.g. the rarely-used "day" window) is absent from the store, so it is
        # fetched live once and cached; a dead source degrades to an empty grid.
        rows = ctx.trending_store.get(
            source=source, media=media, category=category, window=window
        )
        if rows is None:
            try:
                rows = await fetch_feed(
                    ctx,
                    source=source,
                    media=media,
                    category=category,
                    window=window,
                    limit=TRENDING_ITEM_LIMIT,
                )
            except Exception as exc:  # noqa: BLE001 - a dead source must not break the page
                log.warning(
                    "trending fetch failed (source=%s media=%s category=%s): %s",
                    source,
                    media,
                    category,
                    exc,
                )
                return []
            ctx.trending_store.set(
                source=source, media=media, category=category, window=window, rows=rows
            )
        # Overlay flags depend on fast-changing local state, so they are recomputed on
        # every read rather than cached alongside the rows.
        tracked = _tracked_tmdbs(ctx.db)
        library = await _library_index()
        return [
            TrendingItem(**item)
            for item in to_trending_items(
                rows, source=source, tracked_tmdbs=tracked, library=library
            )
        ]

    @router.get("/status", response_model=TrendingStatus)
    async def get_trending_status() -> TrendingStatus:
        """Return when the trending snapshot last refreshed and when it next will."""
        last = ctx.trending_store.last_synced_at()
        interval = ctx.settings_store.trending_sync_interval_minutes()
        return TrendingStatus(
            last_synced_at=last,
            interval_minutes=interval,
            next_sync_at=next_sync_at(last, interval),
        )

    @router.get("/rating", response_model=TrendingRating)
    async def get_rating(
        imdb: str | None = None,
        media: Literal["movie", "show"] | None = None,
        tmdb: int | None = None,
    ) -> TrendingRating:
        imdb_id = imdb
        if not imdb_id and media is not None and tmdb is not None:
            imdb_id = await ctx.tmdb.fetch_external_ids(media_type=media, tmdb_id=tmdb)
        if not imdb_id:
            return TrendingRating(imdb_rating=None, imdb_votes=None)
        cached = rating_cache.get(imdb_id)
        if cached is not None:
            return TrendingRating(**cached)
        rating = await ctx.omdb.fetch_rating(imdb_id=imdb_id)
        rating_cache.set(imdb_id, rating)
        return TrendingRating(**rating)

    @router.post("/add", response_model=TrendingAddResponse)
    async def post_add(
        body: TrendingAddRequest,
    ) -> JSONResponse | TrendingAddResponse:
        target = _addable_target(ctx, body.owner_user, body.slug)
        if target is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "List is not an owned, syncable Trakt list"},
            )
        ids: dict[str, int | str] = {}
        if body.trakt is not None:
            ids["trakt"] = body.trakt
        if body.imdb:
            ids["imdb"] = body.imdb
        if body.tvdb is not None:
            ids["tvdb"] = body.tvdb
        if body.tmdb is not None:
            ids["tmdb"] = body.tmdb
        # TMDB/Seer cards carry only a TMDB id, which Trakt's list-add resolves
        # unreliably (the title lands in not_found); resolve it to a Trakt id first
        # so the add lands deterministically.
        if "trakt" not in ids and body.tmdb is not None:
            try:
                resolved = await ctx.trakt.lookup_ids_by_tmdb(
                    media_type=body.media_type, tmdb_id=body.tmdb
                )
            except Exception as exc:  # noqa: BLE001 - a failed lookup degrades to a bare-tmdb add
                log.warning("trending tmdb lookup failed for %s: %s", body.tmdb, exc)
                resolved = None
            if resolved:
                ids = {
                    **resolved,
                    **ids,
                }  # add trakt/imdb/tvdb; keep explicit body values
        if not ids:
            return JSONResponse(
                status_code=422, content={"detail": "No usable media id supplied"}
            )
        movies = [ids] if body.media_type == "movie" else None
        shows = [ids] if body.media_type == "show" else None
        try:
            summary = await ctx.trakt.add_items(
                movies=movies,
                shows=shows,
                list_id=body.slug,
                owner_user=body.owner_user,
            )
        except Exception as exc:  # noqa: BLE001 - surface the upstream failure
            log.warning("trending add failed for list %s: %s", body.slug, exc)
            return JSONResponse(
                status_code=502, content={"detail": f"Trakt add failed: {exc}"}
            )
        if not _added_anything(summary):
            log.warning(
                "trending add resolved nothing for list %s (ids=%s, summary=%s)",
                body.slug,
                ids,
                summary,
            )
            return JSONResponse(
                status_code=502,
                content={"detail": "Trakt could not find this title to add"},
            )
        ctx.db.add_activity(
            "Trending add", f"Added {body.title or ids} to {target.name}"
        )
        # Trigger the existing sync so the new item is mirrored and requested in Seer
        # through the normal pipeline. If a sync is already running, the next poll
        # picks it up — the add still succeeds.
        if ctx.sync_now is None:
            return TrendingAddResponse(status="added")
        try:
            await ctx.sync_gate.try_run(ctx.sync_now)
        except SyncAlreadyRunning:
            return TrendingAddResponse(status="added_pending_sync")
        return TrendingAddResponse(status="added")

    return router
