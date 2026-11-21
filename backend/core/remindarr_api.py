"""Dashboard JSON API for Remindarr (unwatched episodes of tagged Sonarr series)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.clients.plex import PlexClientError
from core.clients.servarr import ServarrClientError
from core.context import SyncAlreadyRunning
from core.settings_normalisers import (
    REMINDARR_INTERVAL_MAX,
    REMINDARR_INTERVAL_MIN,
    REMINDARR_TAG_IDS_MAX,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

UnmatchedReasonLiteral = Literal["no_tvdb_id", "not_in_plex"]


class RemindarrSettings(BaseModel):
    enabled: bool
    interval_minutes: int
    # Sonarr tag ids; a series is tracked when it carries any of them.
    tag_ids: list[int]
    monitored_only: bool


class RemindarrSettingsUpdate(BaseModel):
    """Partial settings update; bounds are the normaliser's, exposed in OpenAPI."""

    enabled: bool | None = None
    interval_minutes: (
        Annotated[int, Field(ge=REMINDARR_INTERVAL_MIN, le=REMINDARR_INTERVAL_MAX)]
        | None
    ) = None
    tag_ids: (
        Annotated[
            list[Annotated[int, Field(ge=1)]],
            Field(max_length=REMINDARR_TAG_IDS_MAX),
        ]
        | None
    ) = None
    monitored_only: bool | None = None


class RemindarrTag(BaseModel):
    """A Sonarr tag offered in the tag checklist."""

    id: int
    label: str


class RemindarrCounts(BaseModel):
    unwatched: int
    # Series with at least one unwatched episode. The page's series groups also
    # include matched series whose only details are episodes not in Plex.
    series_with_unwatched: int
    tracked_series: int
    unmatched_series: int


class RemindarrStatus(BaseModel):
    settings: RemindarrSettings
    running: bool
    plex_configured: bool
    last_success_at: str | None
    last_attempt_at: str | None
    last_error: str | None
    # True when the last refresh failed: the stored results are older.
    stale: bool
    # Selected tag ids Sonarr no longer reported at the last refresh.
    missing_tag_ids: list[int]
    counts: RemindarrCounts


class RemindarrEpisode(BaseModel):
    episode_id: int
    series_id: int
    episode_file_id: int
    season_number: int
    episode_number: int
    label: str
    title: str
    air_date_utc: str | None
    added_at: str | None
    # The episode file was added on today's local date (computed per request).
    new_today: bool


class RemindarrSeriesGroup(BaseModel):
    series_id: int
    series_title: str
    series_slug: str | None
    tvdb_id: int | None
    # Downloaded episodes of this matched series that Plex does not list.
    episodes_not_in_plex: int
    latest_added_at: str | None
    new_today: int
    # Empty when every episode Plex lists is watched but some are not in Plex.
    episodes: list[RemindarrEpisode]


class RemindarrUnmatchedSeries(BaseModel):
    series_id: int
    series_title: str
    series_slug: str | None
    tvdb_id: int | None
    reason: UnmatchedReasonLiteral
    reason_label: str


class RemindarrResults(BaseModel):
    last_success_at: str | None
    series: list[RemindarrSeriesGroup]
    unmatched: list[RemindarrUnmatchedSeries]


class RemindarrRunResult(BaseModel):
    status: Literal["success", "disabled"]
    unwatched: int
    series_with_unwatched: int
    tracked_series: int
    unmatched_series: int


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Remindarr unavailable")


def _busy() -> HTTPException:
    return HTTPException(
        status_code=409, detail="A Remindarr refresh is already running."
    )


def create_remindarr_router(ctx: AppContext) -> APIRouter:
    """Create the Remindarr API router."""
    router = APIRouter(prefix="/api/remindarr", tags=["remindarr"])

    @router.get("/settings", response_model=RemindarrSettings)
    async def get_settings() -> dict:
        return ctx.settings_store.remindarr_settings()

    @router.put("/settings", response_model=RemindarrStatus)
    async def put_settings(body: RemindarrSettingsUpdate) -> dict:
        if ctx.remindarr_update_settings is None:
            raise _unavailable()
        try:
            return await ctx.remindarr_update_settings(
                body.model_dump(exclude_none=True)
            )
        except ServarrClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            # An unknown newly selected tag (RemindarrTagError).
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/tags", response_model=list[RemindarrTag])
    async def get_tags() -> list[dict]:
        if ctx.remindarr_tags is None:
            raise _unavailable()
        try:
            return await ctx.remindarr_tags()
        except ServarrClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/status", response_model=RemindarrStatus)
    async def get_status() -> dict:
        if ctx.remindarr_status is None:
            raise _unavailable()
        return await ctx.remindarr_status()

    @router.get("/results", response_model=RemindarrResults)
    async def get_results() -> dict:
        if ctx.remindarr_results is None:
            raise _unavailable()
        return await ctx.remindarr_results()

    @router.post("/run", response_model=RemindarrRunResult)
    async def post_run() -> dict:
        if ctx.remindarr_run_now is None:
            raise _unavailable()
        try:
            return await ctx.remindarr_run_now()
        except SyncAlreadyRunning as exc:
            raise _busy() from exc
        except (ServarrClientError, PlexClientError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
