"""Findarr module: Sonarr/Radarr missing and quality-upgrade searches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Awaitable

from fastapi import FastAPI

from core.context import SyncAlreadyRunning
from core.logging import get_logger
from modules.findarr import engine

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("findarr")
_CONTEXT: "AppContext | None" = None


def register_context(ctx: "AppContext") -> None:
    """Store the active context for scheduled jobs."""
    global _CONTEXT
    _CONTEXT = ctx


def _require_context() -> "AppContext":
    if _CONTEXT is None:  # pragma: no cover
        raise RuntimeError("findarr context not initialised")
    return _CONTEXT


async def findarr_job() -> None:
    """Scheduled Findarr entrypoint."""
    ctx = _require_context()
    await ctx.findarr_gate.run(lambda: engine.run(ctx))


async def setup(scheduler: "SchedulerService", app: FastAPI, ctx: "AppContext") -> None:
    """Register Findarr scheduler and API callables."""
    register_context(ctx)
    await scheduler.add_interval(
        findarr_job,
        minutes=ctx.settings_store.findarr_interval_minutes(),
        id="findarr_poll",
    )
    ctx.findarr_status = lambda: engine.status(ctx)
    ctx.findarr_history = lambda: engine.history(ctx)
    ctx.findarr_reset_state = lambda: engine.reset_state(ctx)
    ctx.findarr_run_now = _make_run_now(ctx)
    ctx.findarr_update_settings = _make_update_settings(scheduler, ctx)
    ctx.findarr_reschedule = lambda minutes: scheduler.reschedule_interval(
        findarr_job, minutes=minutes, id="findarr_poll"
    )
    _log.info("findarr module ready")


def _make_run_now(ctx: "AppContext") -> "Callable[..., Awaitable[dict]]":
    async def run_now(app: str | None = None) -> dict:
        return await ctx.findarr_gate.try_run(lambda: engine.run(ctx, app=app, manual=True))

    return run_now


def _make_update_settings(
    scheduler: "SchedulerService", ctx: "AppContext"
) -> "Callable[..., Awaitable[dict]]":
    async def update_settings(updates: dict) -> dict:
        previous_interval = ctx.settings_store.findarr_interval_minutes()
        settings = ctx.settings_store.update_findarr_settings(updates)
        next_interval = int(settings["interval_minutes"])
        if next_interval != previous_interval:
            await scheduler.reschedule_interval(findarr_job, minutes=next_interval, id="findarr_poll")
        ctx.db.add_activity("Findarr settings saved", "Findarr settings updated")
        return await engine.status(ctx)

    return update_settings


__all__ = ["SyncAlreadyRunning", "findarr_job", "setup"]
