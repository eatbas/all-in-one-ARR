"""Cleanarr module: clear stuck Sonarr/Radarr usenet downloads and tidy SABnzbd."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from core.app_metrics import observe_scheduler_job
from core.logging import get_logger
from modules.cleanarr.engine import CleanarrService

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("cleanarr")
_SERVICE: CleanarrService | None = None


def register_service(service: CleanarrService) -> None:
    """Store the active service for the scheduled job (mirrors Languagarr)."""
    global _SERVICE
    _SERVICE = service


def _require_service() -> CleanarrService:
    if _SERVICE is None:  # pragma: no cover
        raise RuntimeError("cleanarr service not initialised")
    return _SERVICE


async def cleanarr_job() -> None:
    """Scheduled Cleanarr entrypoint: one gated clean (a no-op while disabled)."""
    service = _require_service()
    await observe_scheduler_job(
        "cleanarr_poll",
        lambda: service.gate.run(service.scheduled_run),
    )


async def setup(scheduler: SchedulerService, app: FastAPI, ctx: AppContext) -> None:
    """Register the Cleanarr scheduler job and API callables."""
    del app
    service = CleanarrService(ctx)
    register_service(service)
    await scheduler.add_interval(
        cleanarr_job,
        minutes=ctx.settings_store.cleanarr_interval_minutes(),
        id="cleanarr_poll",
    )
    ctx.cleanarr_status = service.status
    ctx.cleanarr_queue = service.queue
    ctx.cleanarr_history = service.history
    ctx.cleanarr_run_now = service.run_now
    ctx.cleanarr_clear_strikes = service.clear_strikes
    ctx.cleanarr_ignore = service.ignore
    ctx.cleanarr_update_settings = _make_update_settings(scheduler, service)
    _log.info("cleanarr module ready")


def _make_update_settings(
    scheduler: SchedulerService, service: CleanarrService
) -> Callable[[dict[str, Any]], Awaitable[dict]]:
    async def update_settings(updates: dict[str, Any]) -> dict:
        previous_interval = int(service.settings()["interval_minutes"])
        settings = service.update_settings(updates)
        next_interval = int(settings["interval_minutes"])
        if next_interval != previous_interval:
            await scheduler.reschedule_interval(
                cleanarr_job, minutes=next_interval, id="cleanarr_poll"
            )
        return await service.status()

    return update_settings


__all__ = ["cleanarr_job", "setup"]
