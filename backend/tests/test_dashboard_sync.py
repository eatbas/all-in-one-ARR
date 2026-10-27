"""Tests for core.dashboard_sync (daily snapshot cron and start-up catch-up)."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from core import dashboard_sync
from core.dashboard_sync import (
    _dashboard_snapshot_job,
    _dashboard_sync,
    start_dashboard_snapshots,
    stop_dashboard_snapshots,
)
from tests.conftest import make_ctx


def _dashboard(*, today: str = "2026-10-27") -> MagicMock:
    dashboard = MagicMock()
    dashboard.today.return_value = today
    dashboard.take_snapshot = AsyncMock(return_value=3)
    return dashboard


async def test_start_registers_cron_and_spawns_boot_snapshot(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)  # scheduler is an AsyncMock
    ctx.dashboard = _dashboard()
    monkeypatch.setattr(_dashboard_sync, "ctx", None)

    await start_dashboard_snapshots(ctx)
    await asyncio.gather(*list(dashboard_sync._SNAPSHOT_TASKS))

    ctx.scheduler.add_cron.assert_awaited_once()
    call = ctx.scheduler.add_cron.await_args
    assert call.args == (_dashboard_snapshot_job,)
    assert call.kwargs == {"hour": 23, "minute": 55, "id": "dashboard_snapshot"}
    ctx.dashboard.take_snapshot.assert_awaited_once()
    assert _dashboard_sync.ctx is ctx


async def test_start_skips_boot_snapshot_when_today_exists(db, monkeypatch) -> None:
    db.dashboard_snapshot_upsert(day="2026-10-27", values={"m": 1}, recorded_at="r")
    ctx = make_ctx(db=db)
    ctx.dashboard = _dashboard()
    monkeypatch.setattr(_dashboard_sync, "ctx", None)

    await start_dashboard_snapshots(ctx)

    ctx.scheduler.add_cron.assert_awaited_once()
    assert not dashboard_sync._SNAPSHOT_TASKS
    ctx.dashboard.take_snapshot.assert_not_awaited()


async def test_start_without_a_service_registers_nothing(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_dashboard_sync, "ctx", None)

    await start_dashboard_snapshots(ctx)

    ctx.scheduler.add_cron.assert_not_awaited()
    assert not dashboard_sync._SNAPSHOT_TASKS


async def test_job_is_a_no_op_without_context_or_service(db, monkeypatch) -> None:
    monkeypatch.setattr(_dashboard_sync, "ctx", None)
    await _dashboard_snapshot_job()

    ctx = make_ctx(db=db)
    monkeypatch.setattr(_dashboard_sync, "ctx", ctx)
    await _dashboard_snapshot_job()


async def test_job_runs_snapshot_through_scheduler_metrics(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    ctx.dashboard = _dashboard()
    monkeypatch.setattr(_dashboard_sync, "ctx", ctx)
    observed: list[str] = []

    async def fake_observe(job_id, job):
        observed.append(job_id)
        return await job()

    monkeypatch.setattr(dashboard_sync, "observe_scheduler_job", fake_observe)

    await _dashboard_snapshot_job()

    assert observed == ["dashboard_snapshot"]
    ctx.dashboard.take_snapshot.assert_awaited_once()


async def test_boot_snapshot_failure_is_logged_not_raised(
    db, monkeypatch, caplog
) -> None:
    ctx = make_ctx(db=db)
    ctx.dashboard = _dashboard()
    ctx.dashboard.take_snapshot = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(_dashboard_sync, "ctx", None)

    with caplog.at_level(logging.ERROR):
        await start_dashboard_snapshots(ctx)
        tasks = list(dashboard_sync._SNAPSHOT_TASKS)
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)

    assert "dashboard boot snapshot raised an exception" in caplog.text
    assert not dashboard_sync._SNAPSHOT_TASKS


async def test_stop_cancels_and_awaits_an_in_flight_boot_snapshot(
    db, monkeypatch, caplog
) -> None:
    ctx = make_ctx(db=db)
    ctx.dashboard = _dashboard()
    started = asyncio.Event()

    async def hang() -> int:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    ctx.dashboard.take_snapshot = AsyncMock(side_effect=hang)
    monkeypatch.setattr(_dashboard_sync, "ctx", None)

    with caplog.at_level(logging.ERROR):
        await start_dashboard_snapshots(ctx)
        await started.wait()
        tasks = list(dashboard_sync._SNAPSHOT_TASKS)

        await stop_dashboard_snapshots()

    assert tasks and all(task.cancelled() for task in tasks)
    assert not dashboard_sync._SNAPSHOT_TASKS
    assert _dashboard_sync.ctx is None
    # A cancellation is a normal shutdown, not a failed snapshot.
    assert "dashboard boot snapshot raised an exception" not in caplog.text


async def test_stop_without_a_boot_snapshot_clears_the_context(db, monkeypatch) -> None:
    monkeypatch.setattr(_dashboard_sync, "ctx", make_ctx(db=db))

    await stop_dashboard_snapshots()

    assert _dashboard_sync.ctx is None
    assert not dashboard_sync._SNAPSHOT_TASKS
