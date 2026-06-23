"""Dashboard JSON API.

These endpoints back the React dashboard. The Pydantic response models are the
authoritative contract that the frontend TypeScript types mirror.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse
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


class StatusCheckIntervalRequest(BaseModel):
    interval_seconds: int


class StatusCheckIntervalResponse(BaseModel):
    interval_seconds: int


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
    async def get_items(status: str | None = None) -> list[Item]:
        return [Item(**row) for row in ctx.db.list_items(status=status)]

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

    @router.get("/settings/general", response_model=StatusCheckIntervalResponse)
    async def get_general_settings() -> StatusCheckIntervalResponse:
        return StatusCheckIntervalResponse(
            interval_seconds=ctx.settings_store.status_check_interval_seconds()
        )

    @router.get("/status/services", response_model=ServicesStatusResponse)
    async def get_services_status() -> ServicesStatusResponse:
        return _services_status_response(ctx.status_checker.get_statuses())

    @router.post("/status/services/check", response_model=ServicesStatusResponse)
    async def post_services_check() -> ServicesStatusResponse:
        return _services_status_response(await ctx.status_checker.check_now())

    @router.put("/settings/general", response_model=StatusCheckIntervalResponse)
    async def put_general_settings(
        body: StatusCheckIntervalRequest,
    ) -> StatusCheckIntervalResponse:
        interval = ctx.settings_store.update_status_check_interval(
            body.interval_seconds
        )
        return StatusCheckIntervalResponse(interval_seconds=interval)

    return router
