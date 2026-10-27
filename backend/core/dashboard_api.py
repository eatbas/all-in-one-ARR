"""HTTP API for the read-only statistics dashboard.

``GET /api/dashboard/summary`` serves the cached live figures (one state per
source) and ``GET /api/dashboard/history`` serves the daily-snapshot trends. The
aggregation, caching and snapshots live in :mod:`core.dashboard`; this module
only declares the response contract and the routes.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, BeforeValidator

from core.dashboard_metrics import MetricKind, MetricUnit
from core.dashboard_sources import SourceState

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.dashboard import DashboardService

DashboardRange = Literal[7, 30, 90]


def _query_int(value: Any) -> Any:
    """Parse a digit-only query string so it can match the integer literals.

    Pydantic validates ``Literal[7, 30, 90]`` strictly, so ``?days=7`` (the
    string ``"7"``) would otherwise be rejected; anything else is left for the
    literal check to reject with a 422.
    """
    return int(value) if isinstance(value, str) and value.isdigit() else value


DashboardRangeQuery = Annotated[DashboardRange, BeforeValidator(_query_int), Query()]


class DashboardMetric(BaseModel):
    """One labelled figure; ``value`` is ``None`` when it is unavailable."""

    key: str
    label: str
    unit: MetricUnit
    value: float | None


class DashboardSource(BaseModel):
    """One module or upstream service card.

    ``stale_since`` is set for an ``offline`` source whose ``metrics`` come from
    its newest daily snapshot; ``updated_at`` is when the source's own data last
    refreshed, where it has such a time.
    """

    key: str
    label: str
    state: SourceState
    detail: str | None
    stale_since: str | None
    updated_at: str | None
    link: str
    metrics: list[DashboardMetric]


class DashboardDisk(BaseModel):
    """Free and total space of one Sonarr/Radarr mount."""

    app: Literal["sonarr", "radarr"]
    path: str
    label: str | None
    free_bytes: int
    total_bytes: int


class DashboardSummary(BaseModel):
    """The live dashboard summary.

    ``latest_snapshot_at`` is when the newest daily snapshot was written
    (``None`` before the first); it changes whenever the history does.
    """

    generated_at: str
    refresh_seconds: int
    latest_snapshot_at: str | None
    kpis: list[DashboardMetric]
    sources: list[DashboardSource]
    disks: list[DashboardDisk]


class DashboardHistoryPoint(BaseModel):
    """One day's value: as stored for a gauge, the day's increase for a counter."""

    day: str
    value: float


class DashboardHistorySeries(BaseModel):
    """One metric's daily points, oldest first."""

    key: str
    label: str
    unit: MetricUnit
    kind: MetricKind
    points: list[DashboardHistoryPoint]


class DashboardHistory(BaseModel):
    """Daily-snapshot trends for the requested range.

    ``latest_snapshot_at`` is the snapshot version these trends reflect; it
    matches ``DashboardSummary.latest_snapshot_at`` until a newer snapshot lands.
    """

    days: DashboardRange
    start_day: str
    end_day: str
    latest_snapshot_at: str | None
    series: list[DashboardHistorySeries]


def create_dashboard_router(ctx: AppContext) -> APIRouter:
    """Build the ``/api/dashboard`` router."""
    router = APIRouter(prefix="/api/dashboard")

    def _service() -> DashboardService:
        if ctx.dashboard is None:
            raise HTTPException(status_code=503, detail="Dashboard unavailable")
        return ctx.dashboard

    @router.get(
        "/summary",
        response_model=DashboardSummary,
        responses={503: {"description": "Dashboard is not ready"}},
    )
    async def get_summary() -> dict:
        """Return cached live statistics with a state for every source."""
        return await _service().summary()

    @router.get(
        "/history",
        response_model=DashboardHistory,
        responses={503: {"description": "Dashboard is not ready"}},
    )
    async def get_history(days: DashboardRangeQuery = 30) -> dict:
        """Return daily-snapshot trends for the last 7, 30 or 90 days."""
        service = _service()
        return await asyncio.to_thread(service.history, days)

    return router
