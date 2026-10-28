"""Dashboard JSON API for Cleanarr (stuck download cleaning and SABnzbd tidying)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.context import SyncAlreadyRunning
from core.settings_modules import CleanarrIgnoreListFull
from core.settings_normalisers import (
    CLEANARR_EXTENSION_PATTERN,
    CLEANARR_EXTENSIONS_MAX,
    CLEANARR_IGNORE_LENGTH_MAX,
    CLEANARR_IGNORE_MAX,
    CLEANARR_INTERVAL_MAX,
    CLEANARR_INTERVAL_MIN,
    CLEANARR_MAX_STRIKES_MAX,
    CLEANARR_MAX_STRIKES_MIN,
    CLEANARR_MIN_AGE_HOURS_MAX,
    CLEANARR_MIN_AGE_HOURS_MIN,
    CLEANARR_PATH_LENGTH_MAX,
    CLEANARR_PATTERN_LENGTH_MAX,
    CLEANARR_PATTERNS_MAX,
    CLEANARR_REMOVALS_PER_RUN_MAX,
    CLEANARR_REMOVALS_PER_RUN_MIN,
    CLEANARR_RETENTION_DAYS_MAX,
    CLEANARR_RETENTION_DAYS_MIN,
    is_strictly_under,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

PatternModeLiteral = Literal["include", "exclude"]
CleanarrAppLiteral = Literal["sonarr", "radarr"]
StrikeReasonLiteral = Literal["failed_import", "failed_download"]

_Pattern = Annotated[str, Field(min_length=1, max_length=CLEANARR_PATTERN_LENGTH_MAX)]
_Extension = Annotated[str, Field(pattern=CLEANARR_EXTENSION_PATTERN)]
_IgnoreEntry = Annotated[
    str, Field(min_length=1, max_length=CLEANARR_IGNORE_LENGTH_MAX)
]
_IgnoreList = Annotated[list[_IgnoreEntry], Field(max_length=CLEANARR_IGNORE_MAX)]
_AbsolutePath = Annotated[
    str, Field(min_length=1, max_length=CLEANARR_PATH_LENGTH_MAX, pattern=r"^/")
]


# ---- settings (response) ----


class CleanarrQueueSettings(BaseModel):
    enabled: bool
    pattern_mode: PatternModeLiteral
    patterns: list[str]


class CleanarrMalwareSettings(BaseModel):
    enabled: bool
    extensions: list[str]


class CleanarrOrphanSettings(BaseModel):
    enabled: bool
    min_age_hours: int
    quarantine_retention_days: int


class CleanarrPathSettings(BaseModel):
    completed_root: str
    quarantine_dir: str


class CleanarrAppSettings(BaseModel):
    enabled: bool


class CleanarrAppsSettings(BaseModel):
    sonarr: CleanarrAppSettings
    radarr: CleanarrAppSettings


class CleanarrIgnoreSettings(BaseModel):
    download_ids: list[str]
    categories: list[str]
    title_contains: list[str]


class CleanarrSettings(BaseModel):
    enabled: bool
    dry_run: bool
    interval_minutes: int
    max_strikes: int
    max_removals_per_run: int
    queue: CleanarrQueueSettings
    malware: CleanarrMalwareSettings
    orphans: CleanarrOrphanSettings
    paths: CleanarrPathSettings
    apps: CleanarrAppsSettings
    ignore: CleanarrIgnoreSettings


# ---- settings (request) ----


class CleanarrQueueSettingsUpdate(BaseModel):
    enabled: bool | None = None
    pattern_mode: PatternModeLiteral | None = None
    patterns: (
        Annotated[list[_Pattern], Field(max_length=CLEANARR_PATTERNS_MAX)] | None
    ) = None


class CleanarrMalwareSettingsUpdate(BaseModel):
    enabled: bool | None = None
    # Lower-case ``.ext`` entries; the dashboard normalises before sending.
    extensions: (
        Annotated[
            list[_Extension], Field(min_length=1, max_length=CLEANARR_EXTENSIONS_MAX)
        ]
        | None
    ) = None


class CleanarrOrphanSettingsUpdate(BaseModel):
    enabled: bool | None = None
    min_age_hours: (
        Annotated[
            int, Field(ge=CLEANARR_MIN_AGE_HOURS_MIN, le=CLEANARR_MIN_AGE_HOURS_MAX)
        ]
        | None
    ) = None
    quarantine_retention_days: (
        Annotated[
            int, Field(ge=CLEANARR_RETENTION_DAYS_MIN, le=CLEANARR_RETENTION_DAYS_MAX)
        ]
        | None
    ) = None


class CleanarrPathSettingsUpdate(BaseModel):
    """Absolute paths; the quarantine folder must end up under the completed one."""

    completed_root: _AbsolutePath | None = None
    quarantine_dir: _AbsolutePath | None = None


class CleanarrAppSettingsUpdate(BaseModel):
    enabled: bool | None = None


class CleanarrAppsSettingsUpdate(BaseModel):
    sonarr: CleanarrAppSettingsUpdate | None = None
    radarr: CleanarrAppSettingsUpdate | None = None


class CleanarrIgnoreSettingsUpdate(BaseModel):
    download_ids: _IgnoreList | None = None
    categories: _IgnoreList | None = None
    title_contains: _IgnoreList | None = None


class CleanarrSettingsUpdate(BaseModel):
    """Partial settings update; bounds are the normaliser's, exposed in OpenAPI."""

    enabled: bool | None = None
    dry_run: bool | None = None
    interval_minutes: (
        Annotated[int, Field(ge=CLEANARR_INTERVAL_MIN, le=CLEANARR_INTERVAL_MAX)] | None
    ) = None
    max_strikes: (
        Annotated[int, Field(ge=CLEANARR_MAX_STRIKES_MIN, le=CLEANARR_MAX_STRIKES_MAX)]
        | None
    ) = None
    max_removals_per_run: (
        Annotated[
            int,
            Field(ge=CLEANARR_REMOVALS_PER_RUN_MIN, le=CLEANARR_REMOVALS_PER_RUN_MAX),
        ]
        | None
    ) = None
    queue: CleanarrQueueSettingsUpdate | None = None
    malware: CleanarrMalwareSettingsUpdate | None = None
    orphans: CleanarrOrphanSettingsUpdate | None = None
    paths: CleanarrPathSettingsUpdate | None = None
    apps: CleanarrAppsSettingsUpdate | None = None
    ignore: CleanarrIgnoreSettingsUpdate | None = None


class CleanarrIgnoreRequest(BaseModel):
    download_id: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("download_id")
    @classmethod
    def _printable(cls, value: str) -> str:
        """Reject control characters so the id is safe to store and display."""
        if any(not character.isprintable() for character in value):
            raise ValueError("download_id must not contain control characters")
        return value


# ---- status, queue, history, results ----


class CleanarrLastRun(BaseModel):
    at: str
    status: str
    detail: str


class CleanarrConnection(BaseModel):
    app: Literal["sabnzbd", "sonarr", "radarr"]
    ok: bool
    detail: str


class CleanarrHealthWarning(BaseModel):
    source: str
    code: str
    detail: str
    level: Literal["warning", "info"]


class CleanarrStrikeCounts(BaseModel):
    sonarr: int
    radarr: int
    failed_import: int
    failed_download: int


class CleanarrStatus(BaseModel):
    settings: CleanarrSettings
    enabled: bool
    dry_run: bool
    running: bool
    last_run: CleanarrLastRun | None
    connections: list[CleanarrConnection]
    health: list[CleanarrHealthWarning]
    strikes: CleanarrStrikeCounts


class CleanarrQueueItem(BaseModel):
    app: CleanarrAppLiteral
    queue_id: int | None
    download_id: str
    title: str
    reason: StrikeReasonLiteral
    message: str
    strikes: int
    max_strikes: int
    would_remove: bool
    ignored: bool
    excluded: bool


class CleanarrQueue(BaseModel):
    items: list[CleanarrQueueItem]
    # Per-app read failures, e.g. {"radarr": "radarr API request failed: ..."}.
    errors: dict[str, str]
    # Per-app reasons the queue read holds downloads (strikes left unchanged),
    # e.g. {"sonarr": "Queue cleaning held: ..."}.
    held: dict[str, str]
    max_strikes: int
    dry_run: bool


class CleanarrHistoryEntry(BaseModel):
    id: int
    ts: str
    app: Literal["sonarr", "radarr", "sabnzbd", "system"]
    action: str
    download_id: str | None
    title: str | None
    detail: str
    dry_run: bool


class CleanarrRunResult(BaseModel):
    status: Literal["completed", "skipped"]
    detail: str
    counts: dict[str, int]


class CleanarrCountResult(BaseModel):
    count: int


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Cleanarr unavailable")


def _busy() -> HTTPException:
    return HTTPException(status_code=409, detail="Cleanarr is already running")


def _check_paths(ctx: AppContext, body: CleanarrSettingsUpdate) -> None:
    """Reject (422) a quarantine folder that would not sit under the completed one."""
    if body.paths is None:
        return
    current = ctx.settings_store.cleanarr_settings()["paths"]
    root = (body.paths.completed_root or current["completed_root"]).rstrip("/") or "/"
    quarantine = body.paths.quarantine_dir or current["quarantine_dir"]
    if not is_strictly_under(quarantine.rstrip("/"), root):
        raise HTTPException(
            status_code=422,
            detail="The quarantine folder must be inside the completed folder.",
        )


def create_cleanarr_router(ctx: AppContext) -> APIRouter:
    """Create the Cleanarr API router."""
    router = APIRouter(prefix="/api/cleanarr", tags=["cleanarr"])

    @router.get("/settings", response_model=CleanarrSettings)
    async def get_settings() -> dict:
        return ctx.settings_store.cleanarr_settings()

    @router.put("/settings", response_model=CleanarrStatus)
    async def put_settings(body: CleanarrSettingsUpdate) -> dict:
        if ctx.cleanarr_update_settings is None:
            raise _unavailable()
        _check_paths(ctx, body)
        return await ctx.cleanarr_update_settings(body.model_dump(exclude_none=True))

    @router.get("/status", response_model=CleanarrStatus)
    async def get_status() -> dict:
        if ctx.cleanarr_status is None:
            raise _unavailable()
        return await ctx.cleanarr_status()

    @router.get("/queue", response_model=CleanarrQueue)
    async def get_queue() -> dict:
        if ctx.cleanarr_queue is None:
            raise _unavailable()
        return await ctx.cleanarr_queue()

    @router.get("/history", response_model=list[CleanarrHistoryEntry])
    async def get_history() -> list[dict]:
        if ctx.cleanarr_history is None:
            raise _unavailable()
        return await ctx.cleanarr_history()

    @router.post("/run", response_model=CleanarrRunResult)
    async def post_run() -> dict:
        if ctx.cleanarr_run_now is None:
            raise _unavailable()
        try:
            return await ctx.cleanarr_run_now()
        except SyncAlreadyRunning as exc:
            raise _busy() from exc

    @router.post("/strikes/clear", response_model=CleanarrCountResult)
    async def post_clear_strikes() -> dict:
        if ctx.cleanarr_clear_strikes is None:
            raise _unavailable()
        try:
            return await ctx.cleanarr_clear_strikes()
        except SyncAlreadyRunning as exc:
            raise _busy() from exc

    @router.post("/ignore", response_model=CleanarrSettings)
    async def post_ignore(body: CleanarrIgnoreRequest) -> dict:
        if ctx.cleanarr_ignore is None:
            raise _unavailable()
        try:
            return await ctx.cleanarr_ignore(body.download_id)
        except SyncAlreadyRunning as exc:
            raise _busy() from exc
        except CleanarrIgnoreListFull as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
