"""Dashboard JSON API.

These endpoints back the React dashboard. The Pydantic response models are the
authoritative contract that the frontend TypeScript types mirror.
"""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.app_metrics import record_sync_run
from core.context import SyncAlreadyRunning
from core.logging import get_logger
from core.timefmt import next_sync_at

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.status_checker import StatusResult

# Strong references to in-flight background sync tasks so they are not
# garbage-collected before completion (per the asyncio docs).
_SYNC_TASKS: set[asyncio.Task] = set()


def _on_sync_done(task: "asyncio.Task") -> None:
    """Discard a finished sync task and log any failure."""
    _SYNC_TASKS.discard(task)
    if not task.cancelled() and task.exception() is not None:
        get_logger("api").error("manual sync failed: %s", task.exception())


def _remember_task(task: "asyncio.Task") -> None:
    """Retain a background task and attach the completion callback."""
    _SYNC_TASKS.add(task)
    task.add_done_callback(_on_sync_done)


class Counts(BaseModel):
    synced: int
    requested: int
    available: int
    removed: int


class StatusResponse(BaseModel):
    trakt_connected: bool
    counts: Counts


class Item(BaseModel):
    trakt_id: int
    type: str
    title: str | None
    year: int | None
    tmdb: int | None
    tvdb: int | None
    imdb: str | None
    list_id: str
    seer_request_id: int | None
    status: str
    created_at: str
    updated_at: str


class ActivityEntry(BaseModel):
    id: int
    ts: str
    action: str
    detail: str


class ListSummary(BaseModel):
    owner_user: str
    slug: str
    name: str
    item_count: int
    # Number of ``removed`` items; ``item_count - removed_count`` is the active count.
    removed_count: int
    last_synced_at: str | None
    next_sync_at: str | None
    interval_minutes: int


class SyncResponse(BaseModel):
    status: str


class ServiceStatus(BaseModel):
    ok: bool
    detail: str
    checked_at: str


class ServicesStatusResponse(BaseModel):
    interval_seconds: int
    last_check_at: str | None
    services: dict[str, ServiceStatus]


class GeneralSettingsRequest(BaseModel):
    # All optional so the UI can change one without re-sending the others; a
    # ``None`` field is left unchanged.
    interval_seconds: int | None = None
    sync_interval_minutes: int | None = None
    trending_sync_interval_minutes: int | None = None
    auto_remove_when_available: bool | None = None


class GeneralSettingsResponse(BaseModel):
    interval_seconds: int
    sync_interval_minutes: int
    trending_sync_interval_minutes: int
    auto_remove_when_available: bool


class DatabaseStatsResponse(BaseModel):
    db_size_bytes: int
    poster_cache_bytes: int
    item_count: int
    activity_count: int
    list_state_count: int


def _services_status_response(snapshot: "StatusResult") -> ServicesStatusResponse:
    """Map a status-checker snapshot onto the API response model."""
    return ServicesStatusResponse(
        interval_seconds=snapshot.interval_seconds,
        last_check_at=snapshot.last_check_at,
        services={
            name: ServiceStatus(ok=s.ok, detail=s.detail, checked_at=s.checked_at)
            for name, s in snapshot.services.items()
        },
    )


def create_api_router(ctx: "AppContext") -> APIRouter:
    """Build the ``/api`` router bound to a specific application context."""
    router = APIRouter(prefix="/api")
    log = get_logger("api")

    @router.get("/status", response_model=StatusResponse)
    async def get_status() -> StatusResponse:
        return StatusResponse(
            trakt_connected=ctx.trakt.is_authenticated(),
            counts=Counts(**ctx.db.counts_by_status()),
        )

    @router.get("/items", response_model=list[Item])
    async def get_items(
        status: str | None = None,
        list_id: str | None = Query(default=None, alias="list"),
    ) -> list[Item]:
        return [
            Item(**row) for row in ctx.db.list_items(status=status, list_id=list_id)
        ]

    @router.get("/lists", response_model=list[ListSummary])
    async def get_lists() -> list[ListSummary]:
        counts = ctx.db.counts_by_list()
        removed = ctx.db.removed_counts_by_list()
        last_synced = ctx.db.list_last_synced()
        interval = ctx.settings_store.sync_interval_minutes()
        summaries: list[ListSummary] = []
        for tracked in ctx.settings_store.tracked_lists():
            last = last_synced.get(tracked.slug)
            summaries.append(
                ListSummary(
                    owner_user=tracked.owner_user,
                    slug=tracked.slug,
                    name=tracked.name,
                    item_count=counts.get(tracked.slug, 0),
                    removed_count=removed.get(tracked.slug, 0),
                    last_synced_at=last,
                    next_sync_at=next_sync_at(last, interval),
                    interval_minutes=interval,
                )
            )
        return summaries

    @router.get("/posters/{media_type}/{tmdb_id}")
    async def get_poster(
        media_type: str, tmdb_id: int, imdb: str | None = None
    ) -> Response:
        """Serve a cached poster thumbnail, fetching it on first request."""
        if media_type not in ("movie", "show") or ctx.poster_cache is None:
            return JSONResponse(status_code=404, content={"detail": "poster not found"})
        path = await ctx.poster_cache.get_poster(
            media_type=media_type, tmdb_id=tmdb_id, imdb_id=imdb
        )
        if path is None:
            return JSONResponse(status_code=404, content={"detail": "poster not found"})
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )

    @router.get("/activity", response_model=list[ActivityEntry])
    async def get_activity() -> list[ActivityEntry]:
        return [ActivityEntry(**row) for row in ctx.db.recent_activity()]

    @router.post("/sync", response_model=SyncResponse, status_code=200)
    async def post_sync() -> JSONResponse:
        if ctx.sync_now is None:  # no module registered a sync callable
            log.warning("manual sync requested but no sync handler registered")
            return JSONResponse(
                status_code=503, content={"detail": "sync unavailable"}
            )
        started = perf_counter()
        status = "success"
        try:
            await ctx.sync_gate.try_run(ctx.sync_now)
        except SyncAlreadyRunning:
            status = "skipped"
            log.info("manual sync rejected: a sync is already running")
            ctx.db.add_activity(
                "Sync already running", "A sync is already running"
            )
            return JSONResponse(
                status_code=409, content={"detail": "sync already running"}
            )
        except Exception:
            status = "error"
            raise
        finally:
            record_sync_run(
                trigger="manual",
                status=status,
                duration_seconds=perf_counter() - started,
            )
        log.info("manual sync completed")
        ctx.db.add_activity("Sync completed", "Manual sync completed")
        return JSONResponse(status_code=200, content={"status": "completed"})

    def _general_settings() -> GeneralSettingsResponse:
        return GeneralSettingsResponse(
            interval_seconds=ctx.settings_store.status_check_interval_seconds(),
            sync_interval_minutes=ctx.settings_store.sync_interval_minutes(),
            trending_sync_interval_minutes=(
                ctx.settings_store.trending_sync_interval_minutes()
            ),
            auto_remove_when_available=ctx.settings_store.auto_remove_when_available(),
        )

    @router.get("/settings/general", response_model=GeneralSettingsResponse)
    async def get_general_settings() -> GeneralSettingsResponse:
        return _general_settings()

    def _database_stats() -> DatabaseStatsResponse:
        counts = ctx.db.table_counts()
        poster_cache_bytes = (
            ctx.poster_cache.total_size_bytes() if ctx.poster_cache is not None else 0
        )
        return DatabaseStatsResponse(
            db_size_bytes=ctx.db.disk_size_bytes(),
            poster_cache_bytes=poster_cache_bytes,
            item_count=counts["items"],
            activity_count=counts["activity"],
            list_state_count=counts["list_state"],
        )

    @router.get("/settings/database", response_model=DatabaseStatsResponse)
    async def get_database_settings() -> DatabaseStatsResponse:
        return _database_stats()

    @router.post("/settings/database/clear-activity", response_model=DatabaseStatsResponse)
    async def post_clear_activity() -> DatabaseStatsResponse:
        removed = ctx.db.clear_activity()
        ctx.db.add_activity("Activity log cleared", f"Removed {removed} activity entries")
        return _database_stats()

    @router.post("/settings/database/clear-items", response_model=DatabaseStatsResponse)
    async def post_clear_items() -> DatabaseStatsResponse:
        removed = ctx.db.clear_items_and_sync_state()
        ctx.db.add_activity(
            "Synced items cleared", f"Removed {removed} tracked items and sync state"
        )
        return _database_stats()

    @router.post("/settings/database/clear-posters", response_model=DatabaseStatsResponse)
    async def post_clear_posters() -> DatabaseStatsResponse:
        if ctx.poster_cache is not None:
            freed = ctx.poster_cache.clear()
            ctx.db.add_activity("Poster cache cleared", f"Freed {freed} bytes")
        return _database_stats()

    @router.get("/status/services", response_model=ServicesStatusResponse)
    async def get_services_status() -> ServicesStatusResponse:
        return _services_status_response(ctx.status_checker.get_statuses())

    @router.post("/status/services/check", response_model=ServicesStatusResponse)
    async def post_services_check() -> ServicesStatusResponse:
        result = _services_status_response(await ctx.status_checker.check_now())
        ctx.db.add_activity(
            "Integration status check completed", "All service statuses refreshed"
        )
        return result

    @router.put("/settings/general", response_model=GeneralSettingsResponse)
    async def put_general_settings(
        body: GeneralSettingsRequest,
    ) -> GeneralSettingsResponse:
        if body.interval_seconds is not None:
            previous = ctx.settings_store.status_check_interval_seconds()
            seconds = ctx.settings_store.update_status_check_interval(
                body.interval_seconds
            )
            if seconds != previous:
                ctx.db.add_activity(
                    "Status interval updated",
                    f"Status interval updated to {seconds} seconds",
                )
        if body.sync_interval_minutes is not None:
            previous = ctx.settings_store.sync_interval_minutes()
            minutes = ctx.settings_store.update_sync_interval(body.sync_interval_minutes)
            if minutes != previous:
                ctx.db.add_activity(
                    "Sync interval updated",
                    f"Sync interval updated to {minutes} minutes",
                )
            if ctx.reschedule_sync is not None:
                await ctx.reschedule_sync(minutes)
        if body.trending_sync_interval_minutes is not None:
            previous = ctx.settings_store.trending_sync_interval_minutes()
            minutes = ctx.settings_store.update_trending_sync_interval(
                body.trending_sync_interval_minutes
            )
            if minutes != previous:
                ctx.db.add_activity(
                    "Trending sync interval updated",
                    f"Trending sync interval updated to {minutes} minutes",
                )
            if ctx.reschedule_trending is not None:
                await ctx.reschedule_trending(minutes)
        if body.auto_remove_when_available is not None:
            previous = ctx.settings_store.auto_remove_when_available()
            enabled = ctx.settings_store.update_auto_remove_when_available(
                body.auto_remove_when_available
            )
            if enabled != previous:
                if enabled:
                    ctx.db.add_activity(
                        "Auto-remove when available enabled",
                        "Items will be removed from Trakt once available in Seer",
                    )
                else:
                    ctx.db.add_activity(
                        "Auto-remove when available disabled",
                        "Available items stay on their Trakt list until manually removed",
                    )
        return _general_settings()

    @router.post("/items/remove-available", response_model=SyncResponse, status_code=202)
    async def post_remove_available() -> JSONResponse:
        """Sweep every Available item out of its Trakt list (manual reconcile)."""
        if ctx.remove_available is not None:
            ctx.db.add_activity(
                "Remove available items triggered",
                "Available items are being removed from their Trakt lists",
            )
            _remember_task(asyncio.create_task(ctx.remove_available()))
            log.info("manual remove-available triggered")
        else:  # no module registered the removal callable
            log.warning("remove-available requested but no handler registered")
        return JSONResponse(status_code=202, content={"status": "triggered"})

    @router.delete("/items/{list_id}/{trakt_id}")
    async def delete_item(list_id: str, trakt_id: int) -> JSONResponse:
        """Remove a single tracked item from its Trakt list."""
        if ctx.remove_item is None:  # no module registered the removal callable
            log.warning("item delete requested but no handler registered")
            return JSONResponse(
                status_code=503, content={"detail": "removal unavailable"}
            )
        removed = await ctx.remove_item(list_id, trakt_id)
        if not removed:
            return JSONResponse(status_code=404, content={"detail": "item not found"})
        return JSONResponse(status_code=200, content={"status": "removed"})

    return router
