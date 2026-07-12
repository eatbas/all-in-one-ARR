"""HTTP API for the Bandwidth-Controllarr feature.

The router lives in ``core/`` rather than inside the module so it is registered
before the SPA catch-all mount in ``create_app()``. The actual control logic and
state live in ``modules/bandwidth_controllarr``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.bandwidth_types import BandwidthClientName
from core.context import BandwidthClientControlError
from core.settings_normalisers import VALID_BANDWIDTH_INTERVALS

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class BandwidthSettingsRequest(BaseModel):
    """Body for updating Bandwidth-Controllarr settings.

    All fields are optional so the dashboard can change one setting at a time.
    """

    enabled: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=1)


class BandwidthClientRequest(BaseModel):
    """Desired manual pause state for one download client."""

    paused: bool


class BandwidthClientStatsResponse(BaseModel):
    """Aggregate statistics for one download client."""

    online: bool
    speed_mbps: float = Field(ge=0)
    active_downloads: int = Field(ge=0)
    queue_size: int = Field(ge=0)
    paused: bool | None = None


class BandwidthDownloadItem(BaseModel):
    """Display-safe queue or download-history item."""

    client: BandwidthClientName
    id: str
    name: str
    status: str
    progress: float | None = Field(default=None, ge=0, le=100)
    size_bytes: int | None = Field(default=None, ge=0)
    size_label: str | None = None
    speed_mbps: float | None = Field(default=None, ge=0)
    eta_seconds: int | None = Field(default=None, ge=0)
    added_at: str | None = None
    completed_at: str | None = None


class BandwidthQueueResponse(BaseModel):
    """Current queue items grouped by downloader."""

    qbittorrent: list[BandwidthDownloadItem] = Field(default_factory=list)
    sabnzbd: list[BandwidthDownloadItem] = Field(default_factory=list)


class BandwidthStatusResponse(BaseModel):
    """Live Bandwidth-Controllarr status returned by both endpoints."""

    enabled: bool
    status: str
    last_run_at: str | None
    tracking_suspended: bool
    manual_paused_clients: list[BandwidthClientName]
    check_interval_seconds: int
    qbittorrent: BandwidthClientStatsResponse
    sabnzbd: BandwidthClientStatsResponse
    download_history: list[BandwidthDownloadItem] = Field(default_factory=list)
    queue: BandwidthQueueResponse = Field(default_factory=BandwidthQueueResponse)


def create_bandwidth_router(ctx: AppContext) -> APIRouter:
    """Build the ``/api/bandwidth`` router."""
    router = APIRouter(prefix="/api/bandwidth")

    @router.get("/status", response_model=BandwidthStatusResponse)
    async def get_status() -> dict:
        if ctx.bandwidth_status is None:
            raise HTTPException(
                status_code=503, detail="Bandwidth-Controllarr not ready"
            )
        return await ctx.bandwidth_status()

    @router.put("/settings", response_model=BandwidthStatusResponse)
    async def put_settings(body: BandwidthSettingsRequest) -> dict:
        if ctx.bandwidth_update_settings is None:
            raise HTTPException(
                status_code=503, detail="Bandwidth-Controllarr not ready"
            )
        if (
            body.check_interval_seconds is not None
            and body.check_interval_seconds not in VALID_BANDWIDTH_INTERVALS
        ):
            allowed = ", ".join(str(s) for s in sorted(VALID_BANDWIDTH_INTERVALS))
            raise HTTPException(
                status_code=422,
                detail=f"check_interval_seconds must be one of: {allowed}",
            )
        return await ctx.bandwidth_update_settings(
            enabled=body.enabled,
            check_interval_seconds=body.check_interval_seconds,
        )

    @router.put(
        "/clients/{client}",
        response_model=BandwidthStatusResponse,
        responses={
            502: {"description": "Download client rejected the command"},
            503: {"description": "Bandwidth-Controllarr is not ready"},
        },
    )
    async def put_client(
        client: BandwidthClientName, body: BandwidthClientRequest
    ) -> dict:
        if ctx.bandwidth_update_client is None:
            raise HTTPException(
                status_code=503, detail="Bandwidth-Controllarr not ready"
            )
        try:
            return await ctx.bandwidth_update_client(client=client, paused=body.paused)
        except BandwidthClientControlError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return router
