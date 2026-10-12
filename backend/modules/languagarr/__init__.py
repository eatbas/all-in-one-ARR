"""Languagarr module: enforce English dual audio on Sonarr anime episode files."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from core.app_metrics import observe_scheduler_job
from core.logging import get_logger
from modules.languagarr.engine import LanguagarrService

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("languagarr")
_SERVICE: LanguagarrService | None = None


def register_service(service: LanguagarrService) -> None:
    """Store the active service for the scheduled job (mirrors Findarr's context)."""
    global _SERVICE
    _SERVICE = service


def _require_service() -> LanguagarrService:
    if _SERVICE is None:  # pragma: no cover
        raise RuntimeError("languagarr service not initialised")
    return _SERVICE


async def languagarr_job() -> None:
    """Scheduled Languagarr entrypoint: send one bounded batch of searches."""
    service = _require_service()
    await observe_scheduler_job(
        "languagarr_poll",
        lambda: service.gate.run(service.scheduled_run),
    )


async def setup(scheduler: SchedulerService, app: FastAPI, ctx: AppContext) -> None:
    """Register the Languagarr scheduler job and API callables."""
    del app
    service = LanguagarrService(ctx)
    register_service(service)
    await scheduler.add_interval(
        languagarr_job,
        minutes=ctx.settings_store.languagarr_interval_minutes(),
        id="languagarr_poll",
    )
    ctx.languagarr_status = service.status
    ctx.languagarr_scan = service.scan
    ctx.languagarr_results = service.results
    ctx.languagarr_enqueue = service.enqueue
    ctx.languagarr_delete = service.delete_and_search
    ctx.languagarr_queue = service.queue
    ctx.languagarr_clear_pending = service.clear_pending
    ctx.languagarr_run_now = service.run_now
    ctx.languagarr_update_settings = _make_update_settings(scheduler, service)
    _log.info("languagarr module ready")


def _make_update_settings(
    scheduler: SchedulerService, service: LanguagarrService
) -> Callable[[dict[str, Any]], Awaitable[dict]]:
    async def update_settings(updates: dict[str, Any]) -> dict:
        previous_interval = int(service.settings()["interval_minutes"])
        settings = service.update_settings(updates)
        next_interval = int(settings["interval_minutes"])
        if next_interval != previous_interval:
            await scheduler.reschedule_interval(
                languagarr_job, minutes=next_interval, id="languagarr_poll"
            )
        return await service.status()

    return update_settings


__all__ = ["languagarr_job", "setup"]
