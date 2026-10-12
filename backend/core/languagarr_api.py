"""Dashboard JSON API for Languagarr (anime English-audio enforcement)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.clients.servarr import ServarrClientError
from core.context import SyncAlreadyRunning
from core.settings_normalisers import (
    LANGUAGARR_INTERVAL_MAX,
    LANGUAGARR_INTERVAL_MIN,
    LANGUAGARR_PROFILE_NAMES_MAX,
    LANGUAGARR_RETRY_HOURS_MAX,
    LANGUAGARR_RETRY_HOURS_MIN,
    LANGUAGARR_SEARCHES_PER_RUN_MAX,
    LANGUAGARR_SEARCHES_PER_RUN_MIN,
    normalise_service_url,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

AudioVerdictLiteral = Literal["compliant", "missing_english", "unknown"]
QueueStatusLiteral = Literal["none", "pending", "searched", "failed"]
QueueRowStatusLiteral = Literal["pending", "searched", "failed"]


class LanguagarrSettings(BaseModel):
    enabled: bool
    interval_minutes: int
    searches_per_run: int
    retry_after_hours: int
    auto_queue: bool
    monitored_only: bool
    quality_profile_names: list[str]
    sonarr_link_url: str


class LanguagarrSettingsUpdate(BaseModel):
    """Partial settings update; bounds are the normaliser's, exposed in OpenAPI."""

    enabled: bool | None = None
    interval_minutes: (
        Annotated[int, Field(ge=LANGUAGARR_INTERVAL_MIN, le=LANGUAGARR_INTERVAL_MAX)]
        | None
    ) = None
    searches_per_run: (
        Annotated[
            int,
            Field(
                ge=LANGUAGARR_SEARCHES_PER_RUN_MIN,
                le=LANGUAGARR_SEARCHES_PER_RUN_MAX,
            ),
        ]
        | None
    ) = None
    retry_after_hours: (
        Annotated[
            int, Field(ge=LANGUAGARR_RETRY_HOURS_MIN, le=LANGUAGARR_RETRY_HOURS_MAX)
        ]
        | None
    ) = None
    auto_queue: bool | None = None
    monitored_only: bool | None = None
    quality_profile_names: (
        Annotated[
            list[str], Field(min_length=1, max_length=LANGUAGARR_PROFILE_NAMES_MAX)
        ]
        | None
    ) = None
    # Empty clears the override (links then use the Sonarr service URL).
    sonarr_link_url: Annotated[str, Field(max_length=2048)] | None = None

    @field_validator("sonarr_link_url")
    @classmethod
    def _valid_link_url(cls, value: str | None) -> str | None:
        """Reject non-``http(s)`` schemes with a 422 instead of dropping them."""
        return None if value is None else normalise_service_url(value)


class LanguagarrScanSummary(BaseModel):
    is_scanning: bool
    last_scan_at: str | None
    last_error: str | None
    profiles_in_scope: list[str]
    series_scanned: int
    files_scanned: int
    non_compliant: int
    unknown: int
    missing_english: int


class LanguagarrQueueCounts(BaseModel):
    pending: int
    searched: int
    failed: int


class LanguagarrStatus(BaseModel):
    settings: LanguagarrSettings
    running: bool
    scan: LanguagarrScanSummary
    queue: LanguagarrQueueCounts


class LanguagarrItem(BaseModel):
    episode_file_id: int
    series_id: int
    series_title: str
    series_slug: str | None
    season_number: int | None
    episode_ids: list[int]
    episode_label: str
    relative_path: str
    audio_languages: str
    sonarr_languages: list[str]
    verdict: AudioVerdictLiteral
    release_group: str | None
    custom_format_score: int
    cutoff_format_score: int
    recommended_action: Literal["search", "delete_and_search"]
    queue_status: QueueStatusLiteral
    last_searched_at: str | None


class LanguagarrResults(BaseModel):
    scan: LanguagarrScanSummary
    results: list[LanguagarrItem]
    unknown: list[LanguagarrItem]


class LanguagarrFileIdsRequest(BaseModel):
    episode_file_ids: list[int] = Field(min_length=1, max_length=500)


class LanguagarrDeleteRequest(BaseModel):
    episode_file_ids: list[int] = Field(min_length=1, max_length=25)
    # Must be sent explicitly: a reviewed deletion is never implied.
    confirm: Literal[True]


class LanguagarrItemError(BaseModel):
    episode_file_id: int
    error: str


class LanguagarrEnqueueResult(BaseModel):
    queued: int
    skipped: int
    errors: list[LanguagarrItemError]


class LanguagarrDeleteResult(BaseModel):
    deleted: int
    searched: int
    failed: int
    deleted_ids: list[int]
    errors: list[LanguagarrItemError]


class LanguagarrQueueRow(BaseModel):
    episode_file_id: int
    series_id: int
    series_slug: str | None
    title: str
    episode_ids: list[int]
    reason: str
    status: QueueRowStatusLiteral
    queued_at: str
    searched_at: str | None
    attempts: int
    last_error: str | None


class LanguagarrQueue(BaseModel):
    counts: LanguagarrQueueCounts
    rows: list[LanguagarrQueueRow]


class LanguagarrRunResult(BaseModel):
    status: str
    searched: int
    failed: int
    resolved: int


class LanguagarrClearResult(BaseModel):
    removed: int


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Languagarr unavailable")


def _busy() -> HTTPException:
    return HTTPException(status_code=409, detail="Languagarr is already running")


def create_languagarr_router(ctx: AppContext) -> APIRouter:
    """Create the Languagarr API router."""
    router = APIRouter(prefix="/api/languagarr", tags=["languagarr"])

    @router.get("/settings", response_model=LanguagarrSettings)
    async def get_settings() -> dict:
        return ctx.settings_store.languagarr_settings()

    @router.put("/settings", response_model=LanguagarrStatus)
    async def put_settings(body: LanguagarrSettingsUpdate) -> dict:
        if ctx.languagarr_update_settings is None:
            raise _unavailable()
        return await ctx.languagarr_update_settings(body.model_dump(exclude_none=True))

    @router.get("/status", response_model=LanguagarrStatus)
    async def get_status() -> dict:
        if ctx.languagarr_status is None:
            raise _unavailable()
        return await ctx.languagarr_status()

    @router.get("/results", response_model=LanguagarrResults)
    async def get_results() -> dict:
        if ctx.languagarr_results is None:
            raise _unavailable()
        return await ctx.languagarr_results()

    @router.post("/scan", response_model=LanguagarrResults)
    async def post_scan() -> dict:
        if ctx.languagarr_scan is None:
            raise _unavailable()
        try:
            return await ctx.languagarr_scan()
        except SyncAlreadyRunning as exc:
            raise _busy() from exc
        except ServarrClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/enqueue", response_model=LanguagarrEnqueueResult)
    async def post_enqueue(body: LanguagarrFileIdsRequest) -> dict:
        if ctx.languagarr_enqueue is None:
            raise _unavailable()
        return await ctx.languagarr_enqueue(body.episode_file_ids)

    @router.post("/delete", response_model=LanguagarrDeleteResult)
    async def post_delete(body: LanguagarrDeleteRequest) -> dict:
        if ctx.languagarr_delete is None:
            raise _unavailable()
        try:
            return await ctx.languagarr_delete(body.episode_file_ids)
        except SyncAlreadyRunning as exc:
            raise _busy() from exc
        except ServarrClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/queue", response_model=LanguagarrQueue)
    async def get_queue() -> dict:
        if ctx.languagarr_queue is None:
            raise _unavailable()
        return await ctx.languagarr_queue()

    @router.delete("/queue/pending", response_model=LanguagarrClearResult)
    async def delete_pending() -> dict:
        if ctx.languagarr_clear_pending is None:
            raise _unavailable()
        return await ctx.languagarr_clear_pending()

    @router.post("/run", response_model=LanguagarrRunResult)
    async def post_run() -> dict:
        if ctx.languagarr_run_now is None:
            raise _unavailable()
        try:
            return await ctx.languagarr_run_now()
        except SyncAlreadyRunning as exc:
            raise _busy() from exc

    return router
