"""Tests for core.scheduler (wrapper isolated from a stub scheduler)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.scheduler import SchedulerService


class StubScheduler:
    def __init__(self) -> None:
        self.add_schedule = AsyncMock()
        self.start_in_background = AsyncMock()
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *args):
        self.exited = True
        return False


async def def_noop() -> None:
    return None


def test_default_scheduler_is_async_scheduler() -> None:
    service = SchedulerService()
    assert isinstance(service._scheduler, AsyncScheduler)


async def test_add_interval_uses_interval_trigger() -> None:
    stub = StubScheduler()
    service = SchedulerService(scheduler=stub)
    await service.add_interval(def_noop, minutes=15, id="poll")
    func, trigger = stub.add_schedule.call_args.args
    assert func is def_noop
    assert isinstance(trigger, IntervalTrigger)
    assert stub.add_schedule.call_args.kwargs["id"] == "poll"


async def test_add_cron_uses_cron_trigger() -> None:
    stub = StubScheduler()
    service = SchedulerService(scheduler=stub)
    await service.add_cron(def_noop, hour=3, minute=0, id="recon")
    _, trigger = stub.add_schedule.call_args.args
    assert isinstance(trigger, CronTrigger)
    assert stub.add_schedule.call_args.kwargs["id"] == "recon"


async def test_start_and_stop() -> None:
    stub = StubScheduler()
    service = SchedulerService(scheduler=stub)
    await service.start()
    assert stub.entered is True
    stub.start_in_background.assert_awaited_once()
    await service.stop()
    assert stub.exited is True
