"""Dashboard JSON API.

These endpoints back the React dashboard. The Pydantic response models are the
authoritative contract that the frontend TypeScript types mirror.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from core.logging import get_logger

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
    dry_run: bool
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
    jellyseerr_request_id: int | None
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
    last_synced_at: str | None
    next_sync_at: str | None
    interval_minutes: int


class DryRunRequest(BaseModel):
    enabled: bool


class DryRunResponse(BaseModel):
    dry_run: bool


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
    # Both optional so the UI can change one without re-sending the other; a
    # ``None`` field is left unchanged.
    interval_seconds: int | None = None
    sync_interval_minutes: int | None = None


class GeneralSettingsResponse(BaseModel):
    interval_seconds: int
    sync_interval_minutes: int


def _next_sync_at(last_synced_at: str | None, interval_minutes: int) -> str | None:
    """Derive the next poll time from the last sync plus the poll interval.

    This is an approximation of the scheduler's next fire time (the APScheduler 4
    wrapper does not expose it); ``None`` when the list has never been polled.
    """
    if last_synced_at is None:
        return None
    # last_synced_at is always written by db.utcnow_iso() (valid ISO-8601), so
    # fromisoformat cannot fail here.
    last = datetime.fromisoformat(last_synced_at)
    return (last + timedelta(minutes=interval_minutes)).isoformat()


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
            dry_run=ctx.dry_run,
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
                    last_synced_at=last,
                    next_sync_at=_next_sync_at(last, interval),
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

    @router.post("/sync", response_model=SyncResponse, status_code=202)
    async def post_sync() -> JSONResponse:
        if ctx.sync_now is not None:
            _remember_task(asyncio.create_task(ctx.sync_now()))
            log.info("manual sync triggered")
        else:  # no module registered a sync callable
            log.warning("manual sync requested but no sync handler registered")
        return JSONResponse(status_code=202, content={"status": "triggered"})

    @router.post("/settings/dry-run", response_model=DryRunResponse)
    async def post_dry_run(body: DryRunRequest) -> DryRunResponse:
        ctx.set_dry_run(body.enabled)
        return DryRunResponse(dry_run=ctx.dry_run)

    def _general_settings() -> GeneralSettingsResponse:
        return GeneralSettingsResponse(
            interval_seconds=ctx.settings_store.status_check_interval_seconds(),
            sync_interval_minutes=ctx.settings_store.sync_interval_minutes(),
        )

    @router.get("/settings/general", response_model=GeneralSettingsResponse)
    async def get_general_settings() -> GeneralSettingsResponse:
        return _general_settings()

    @router.get("/status/services", response_model=ServicesStatusResponse)
    async def get_services_status() -> ServicesStatusResponse:
        return _services_status_response(ctx.status_checker.get_statuses())

    @router.post("/status/services/check", response_model=ServicesStatusResponse)
    async def post_services_check() -> ServicesStatusResponse:
        return _services_status_response(await ctx.status_checker.check_now())

    @router.put("/settings/general", response_model=GeneralSettingsResponse)
    async def put_general_settings(
        body: GeneralSettingsRequest,
    ) -> GeneralSettingsResponse:
        if body.interval_seconds is not None:
            ctx.settings_store.update_status_check_interval(body.interval_seconds)
        if body.sync_interval_minutes is not None:
            minutes = ctx.settings_store.update_sync_interval(body.sync_interval_minutes)
            if ctx.reschedule_sync is not None:
                await ctx.reschedule_sync(minutes)
        return _general_settings()

    @router.post("/items/remove-available", response_model=SyncResponse, status_code=202)
    async def post_remove_available() -> JSONResponse:
        """Sweep every Available item out of its Trakt list (manual reconcile)."""
        if ctx.remove_available is not None:
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
