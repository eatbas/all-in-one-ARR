"""Scheduled daily snapshot of the dashboard statistics.

A cron job at 23:55 local time (``TZ``; APScheduler 4's ``CronTrigger`` defaults
to the local zone) stores every snapshot metric under today's day key. When the
container starts on a day that has no snapshot yet, a supervised catch-up
snapshot runs immediately — it never delays the lifespan — so first-run users get
a data point at once; the evening run then upserts over it. The shape mirrors
``core.anime_ids_sync``: a module-level job plus a context holder, because
APScheduler 4 cannot serialise a closure.

The lifespan owns the boot snapshot's lifetime: :func:`stop_dashboard_snapshots`
cancels and awaits it before the clients and the database close, so a snapshot
still collecting at shutdown never touches closed resources.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.app_metrics import observe_scheduler_job
from core.logging import get_logger
from core.tasks import spawn_supervised

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

# The job id under which the daily snapshot is registered.
_JOB_ID = "dashboard_snapshot"
_SNAPSHOT_HOUR = 23
_SNAPSHOT_MINUTE = 55
_log = get_logger("dashboard_sync")

# Strong references to in-flight boot snapshots (see core.tasks).
_SNAPSHOT_TASKS: set[asyncio.Task] = set()


@dataclass
class _DashboardSync:
    """Holds the context the module-level job reads (APScheduler-4 constraint)."""

    ctx: AppContext | None = None


_dashboard_sync = _DashboardSync()


async def _dashboard_snapshot_job() -> None:
    """Scheduled entrypoint: store today's dashboard snapshot."""
    ctx = _dashboard_sync.ctx
    if ctx is None or ctx.dashboard is None:
        return
    await observe_scheduler_job(_JOB_ID, ctx.dashboard.take_snapshot)


async def start_dashboard_snapshots(ctx: AppContext) -> None:
    """Register the daily snapshot and catch up when today has none yet.

    A context without a dashboard service (tests may null it) is a safe no-op.
    """
    _dashboard_sync.ctx = ctx
    if ctx.dashboard is None:
        return
    await ctx.scheduler.add_cron(
        _dashboard_snapshot_job,
        hour=_SNAPSHOT_HOUR,
        minute=_SNAPSHOT_MINUTE,
        id=_JOB_ID,
    )
    if ctx.db.dashboard_snapshot_has_day(ctx.dashboard.today()):
        return
    spawn_supervised(
        _SNAPSHOT_TASKS,
        _dashboard_snapshot_job(),
        log=_log,
        log_msg="dashboard boot snapshot raised an exception",
    )


async def stop_dashboard_snapshots() -> None:
    """Cancel and await any in-flight boot snapshot, then drop the context.

    Called by the lifespan before it closes the clients and the database. The
    context is cleared first, so a job firing meanwhile is a no-op; cancelled
    tasks finish quietly (``spawn_supervised`` logs only real failures).
    """
    _dashboard_sync.ctx = None
    tasks = list(_SNAPSHOT_TASKS)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
