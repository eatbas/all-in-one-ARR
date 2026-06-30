"""Findarr JSON API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.context import SyncAlreadyRunning

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class FindarrAppSettings(BaseModel):
    enabled: bool
    missing_limit: int
    upgrade_limit: int
    monitored_only: bool
    skip_future: bool
    missing_mode: str
    upgrade_mode: str


class FindarrSettings(BaseModel):
    enabled: bool
    interval_minutes: int
    hourly_cap: int
    queue_limit: int
    command_sleep_seconds: int
    state_reset_hours: int
    apps: dict[str, FindarrAppSettings]


class FindarrAppSettingsUpdate(BaseModel):
    enabled: bool | None = None
    missing_limit: int | None = None
    upgrade_limit: int | None = None
    monitored_only: bool | None = None
    skip_future: bool | None = None
    missing_mode: str | None = None
    upgrade_mode: str | None = None


class FindarrSettingsUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None
    hourly_cap: int | None = None
    queue_limit: int | None = None
    command_sleep_seconds: int | None = None
    state_reset_hours: int | None = None
    apps: dict[str, FindarrAppSettingsUpdate] | None = None


class FindarrModeResult(BaseModel):
    app: str
    mode: str
    scanned: int
    selected: int
    processed: int
    skipped: int
    detail: str


class FindarrRunResponse(BaseModel):
    status: str
    detail: str
    processed: int
    results: list[FindarrModeResult]


class FindarrRunRequest(BaseModel):
    app: Literal["sonarr", "radarr"] | None = None


class FindarrHistoryEntry(BaseModel):
    id: int
    ts: str
    app: str
    mode: str
    item_id: str | None
    title: str | None
    status: str
    detail: str


class FindarrStatusResponse(BaseModel):
    settings: FindarrSettings
    running: bool
    last_run_at: str | None
    last_run_status: str | None
    last_run_detail: str | None
    state: dict
    apps: dict
    hourly: dict[str, int]


class FindarrCountResponse(BaseModel):
    """Result of a Findarr mutation reporting how many rows it removed.

    Shared by the processed-state reset and the history clear; both report a
    status string and a removed-row count.
    """

    status: str
    removed: int


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Findarr unavailable"})


def create_findarr_router(ctx: "AppContext") -> APIRouter:
    """Build the `/api/findarr` router."""
    router = APIRouter(prefix="/api/findarr", tags=["findarr"])

    @router.get("/settings", response_model=FindarrSettings)
    async def get_settings() -> FindarrSettings:
        return FindarrSettings(**ctx.settings_store.findarr_settings())

    @router.put("/settings", response_model=FindarrStatusResponse)
    async def put_settings(
        body: FindarrSettingsUpdate,
    ) -> JSONResponse | FindarrStatusResponse:
        if ctx.findarr_update_settings is None:
            return _unavailable()
        payload = body.model_dump(exclude_none=True)
        result = await ctx.findarr_update_settings(payload)
        return FindarrStatusResponse(**result)

    @router.get("/status", response_model=FindarrStatusResponse)
    async def get_status() -> JSONResponse | FindarrStatusResponse:
        if ctx.findarr_status is None:
            return _unavailable()
        return FindarrStatusResponse(**await ctx.findarr_status())

    @router.get("/history", response_model=list[FindarrHistoryEntry])
    async def get_history() -> JSONResponse | list[FindarrHistoryEntry]:
        if ctx.findarr_history is None:
            return _unavailable()
        return [FindarrHistoryEntry(**row) for row in await ctx.findarr_history()]

    @router.post("/run", response_model=FindarrRunResponse)
    async def post_run(body: FindarrRunRequest) -> JSONResponse | FindarrRunResponse:
        if ctx.findarr_run_now is None:
            return _unavailable()
        try:
            result = await ctx.findarr_run_now(app=body.app)
        except SyncAlreadyRunning:
            return JSONResponse(status_code=409, content={"detail": "Findarr is already running"})
        return FindarrRunResponse(**result)

    @router.post("/reset", response_model=FindarrCountResponse)
    async def post_reset() -> JSONResponse | FindarrCountResponse:
        if ctx.findarr_reset_state is None:
            return _unavailable()
        return FindarrCountResponse(**await ctx.findarr_reset_state())

    @router.post("/history/clear", response_model=FindarrCountResponse)
    async def post_clear_history() -> JSONResponse | FindarrCountResponse:
        if ctx.findarr_clear_history is None:
            return _unavailable()
        return FindarrCountResponse(**await ctx.findarr_clear_history())

    return router
