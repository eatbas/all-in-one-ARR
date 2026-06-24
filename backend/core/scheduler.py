"""Thin wrapper around the shared APScheduler 4.x scheduler.

All scheduler usage in the service goes through this module so that the
pre-release APScheduler 4 API is isolated to one place: a future downgrade to
the mature 3.x ``AsyncIOScheduler``/``add_job`` API is a single-file change.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from apscheduler import AsyncScheduler, ScheduleLookupError
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.logging import get_logger

JobFunc = Callable[[], Awaitable[Any]]


class SchedulerService:
    """Owns the scheduler lifecycle and exposes trigger-agnostic helpers."""

    def __init__(self, scheduler: AsyncScheduler | None = None) -> None:
        self._scheduler = scheduler or AsyncScheduler()
        self._log = get_logger("scheduler")

    async def add_interval(self, func: JobFunc, *, minutes: int, id: str) -> None:
        """Schedule ``func`` to run every ``minutes`` minutes."""
        await self._scheduler.add_schedule(
            func, IntervalTrigger(minutes=minutes), id=id
        )
        self._log.info("scheduled interval job id=%s minutes=%s", id, minutes)

    async def reschedule_interval(
        self, func: JobFunc, *, minutes: int, id: str
    ) -> None:
        """Re-point an interval job at a new period.

        Removes the existing schedule (tolerating its absence on the first call)
        and re-adds it under the same ``id`` with the new interval.
        """
        try:
            await self._scheduler.remove_schedule(id)
        except ScheduleLookupError:
            self._log.info("no existing schedule id=%s to remove", id)
        await self.add_interval(func, minutes=minutes, id=id)

    async def add_cron(self, func: JobFunc, *, hour: int, minute: int, id: str) -> None:
        """Schedule ``func`` to run daily at ``hour:minute``."""
        await self._scheduler.add_schedule(
            func, CronTrigger(hour=hour, minute=minute), id=id
        )
        self._log.info("scheduled cron job id=%s at=%02d:%02d", id, hour, minute)

    async def start(self) -> None:
        """Start the scheduler in the background."""
        await self._scheduler.__aenter__()
        await self._scheduler.start_in_background()
        self._log.info("scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler and release its resources."""
        await self._scheduler.__aexit__(None, None, None)
        self._log.info("scheduler stopped")
