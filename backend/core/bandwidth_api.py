"""HTTP API for the Bandwidth-Controllarr feature.

The router lives in ``core/`` rather than inside the module so it is registered
before the SPA catch-all mount in ``create_app()``. The actual control logic and
state live in ``modules/bandwidth_controllarr``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.settings_store import VALID_BANDWIDTH_INTERVALS

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class BandwidthSettingsRequest(BaseModel):
    """Body for updating Bandwidth-Controllarr settings.

    All fields are optional so the dashboard can change one setting at a time.
    """

    enabled: bool | None = None
    check_interval_seconds: int | None = Field(default=None, ge=1)


class BandwidthStatusResponse(BaseModel):
    """Live Bandwidth-Controllarr status returned by both endpoints."""

    enabled: bool
    status: str
    last_run_at: str | None
    check_interval_seconds: int
    qbittorrent: dict
    sabnzbd: dict


def create_bandwidth_router(ctx: "AppContext") -> APIRouter:
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

    return router
