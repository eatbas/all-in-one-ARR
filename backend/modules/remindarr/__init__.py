"""Remindarr module: remind the Plex token owner of unwatched tagged episodes.

The module-level ``_SERVICE`` mirrors Languagarr and Findarr. It is the one
piece of global state Remindarr adds, and it is required: APScheduler 4 can
only schedule a module-level coroutine (it cannot serialise a reference to a
closure or bound method; see ``core.app._PosterChurnConfig``), so the scheduled
:func:`remindarr_job` has to find its service through a module-level reference.
It is set exactly once, in :func:`setup`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from core.app_metrics import observe_scheduler_job, update_remindarr_counts
from core.logging import get_logger
from modules.remindarr.engine import RemindarrService

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("remindarr")
_SERVICE: RemindarrService | None = None


def register_service(service: RemindarrService) -> None:
    """Store the active service for the scheduled job (mirrors Languagarr)."""
    global _SERVICE
    _SERVICE = service


def _require_service() -> RemindarrService:
    if _SERVICE is None:  # pragma: no cover
        raise RuntimeError("remindarr service not initialised")
    return _SERVICE


async def remindarr_job() -> None:
    """Scheduled Remindarr entrypoint: one refresh, waiting for a manual one."""
    service = _require_service()
    await observe_scheduler_job(
        "remindarr_poll",
        lambda: service.gate.run(service.scheduled_run),
    )


async def setup(scheduler: SchedulerService, app: FastAPI, ctx: AppContext) -> None:
    """Register the Remindarr scheduler job and API callables."""
    del app
    service = RemindarrService(ctx)
    register_service(service)
    await scheduler.add_interval(
        remindarr_job,
        minutes=ctx.settings_store.remindarr_interval_minutes(),
        id="remindarr_poll",
    )
    ctx.remindarr_status = service.status
    ctx.remindarr_results = service.results
    ctx.remindarr_tags = service.tags
    ctx.remindarr_run_now = service.run_now
    ctx.remindarr_update_settings = _make_update_settings(scheduler, service)
    # The gauges start from the stored results so /metrics is right after a
    # restart, before the first refresh.
    counts = ctx.db.remindarr_counts()
    update_remindarr_counts(
        unwatched=counts["unwatched"], unmatched_series=counts["unmatched_series"]
    )
    _log.info("remindarr module ready")


def _make_update_settings(
    scheduler: SchedulerService, service: RemindarrService
) -> Callable[[dict[str, Any]], Awaitable[dict]]:
    async def update_settings(updates: dict[str, Any]) -> dict:
        previous_interval = int(service.settings()["interval_minutes"])
        settings = await service.update_settings(updates)
        next_interval = int(settings["interval_minutes"])
        if next_interval != previous_interval:
            await scheduler.reschedule_interval(
                remindarr_job, minutes=next_interval, id="remindarr_poll"
            )
        return await service.status()

    return update_settings


__all__ = ["remindarr_job", "setup"]
