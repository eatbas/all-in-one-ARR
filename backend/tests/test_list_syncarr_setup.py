"""Tests for modules.list_syncarr.setup and the scheduled job entrypoints."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from core.context import SyncAlreadyRunning, SyncGate
import modules.list_syncarr as list_syncarr
from tests.conftest import StubSeer, StubSettingsStore, StubTrakt, make_ctx


async def test_setup_registers_poll_and_callables(db) -> None:
    scheduler = AsyncMock()
    ctx = make_ctx(db=db, settings_store=StubSettingsStore(sync_interval_minutes=30))
    await list_syncarr.setup(scheduler, FastAPI(), ctx)

    scheduler.add_interval.assert_awaited_once()
    assert scheduler.add_interval.call_args.kwargs["id"] == "list_syncarr_poll"
    # The poll uses the store-backed interval, not a hard-coded value.
    assert scheduler.add_interval.call_args.kwargs["minutes"] == 30
    # Removal is no longer autonomous: no reconcile cron is scheduled.
    scheduler.add_cron.assert_not_awaited()
    # The arr import webhook has been retired; the poll itself drives removal.
    assert "arr" not in ctx.webhooks._handlers
    assert ctx.sync_now is not None
    assert ctx.remove_available is not None
    assert ctx.remove_item is not None
    assert ctx.reschedule_sync is not None


async def test_poll_job_runs_against_registered_context(db) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[]), seer=StubSeer())
    list_syncarr.register_context(ctx)
    # Should not raise; it resolves the module-level context.
    await list_syncarr.poll_job()
    ctx.trakt.read_list_items.assert_awaited()


async def test_sync_now_callable_invokes_poll(db) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[]))
    await list_syncarr.setup(AsyncMock(), FastAPI(), ctx)
    await ctx.sync_now()
    ctx.trakt.read_list_items.assert_awaited()


async def test_poll_job_runs_through_sync_gate(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[]))
    list_syncarr.register_context(ctx)

    gate_held = False

    async def poll_and_request_checked(context):
        nonlocal gate_held
        gate_held = context.sync_gate.is_running()

    monkeypatch.setattr(list_syncarr, "poll_and_request", poll_and_request_checked)
    await list_syncarr.poll_job()
    assert gate_held is True


async def test_remove_available_callable_runs_reconcile(db) -> None:
    # An available item is swept off its Trakt list by the manual sweep.
    db.upsert_item(
        trakt_id=1, type="movie", title="Dune", year=2021, tmdb=438631,
        tvdb=None, imdb=None, list_id="watchlist",
    )
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[]),
        seer=StubSeer(status=5),
    )
    await list_syncarr.setup(AsyncMock(), FastAPI(), ctx)
    await ctx.remove_available()
    ctx.trakt.remove_items.assert_awaited()


async def test_remove_item_callable_removes_one(db) -> None:
    db.upsert_item(
        trakt_id=2, type="movie", title="Arrival", year=2016, tmdb=329865,
        tvdb=None, imdb=None, list_id="watchlist",
    )
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[]))
    await list_syncarr.setup(AsyncMock(), FastAPI(), ctx)

    assert await ctx.remove_item("watchlist", 2) is True
    ctx.trakt.remove_items.assert_awaited()
    # An unknown item is reported as not found without touching Trakt.
    ctx.trakt.remove_items.reset_mock()
    assert await ctx.remove_item("watchlist", 999) is False
    ctx.trakt.remove_items.assert_not_awaited()


async def test_reschedule_sync_callable_reschedules_poll(db) -> None:
    scheduler = AsyncMock()
    ctx = make_ctx(db=db)
    await list_syncarr.setup(scheduler, FastAPI(), ctx)
    await ctx.reschedule_sync(45)
    scheduler.reschedule_interval.assert_awaited_once()
    assert scheduler.reschedule_interval.call_args.kwargs["minutes"] == 45
    assert scheduler.reschedule_interval.call_args.kwargs["id"] == "list_syncarr_poll"


async def test_sync_gate_run_waits_for_in_progress_sync() -> None:
    gate = SyncGate()
    entered = asyncio.Event()
    proceed = asyncio.Event()

    async def slow() -> None:
        entered.set()
        await proceed.wait()

    task = asyncio.create_task(gate.run(slow))
    await entered.wait()
    assert gate.is_running() is True

    second = asyncio.create_task(gate.run(lambda: asyncio.sleep(0)))
    # The second run should not start until the first finishes.
    await asyncio.sleep(0)
    assert not second.done()

    proceed.set()
    await task
    await second
    assert gate.is_running() is False


async def test_sync_gate_try_run_rejects_when_busy() -> None:
    gate = SyncGate()
    entered = asyncio.Event()
    proceed = asyncio.Event()

    async def slow() -> None:
        entered.set()
        await proceed.wait()

    task = asyncio.create_task(gate.try_run(slow))
    await entered.wait()

    with pytest.raises(SyncAlreadyRunning):
        await gate.try_run(lambda: asyncio.sleep(0))

    proceed.set()
    await task


async def test_sync_gate_try_run_releases_lock_on_failure() -> None:
    gate = SyncGate()

    async def boom() -> None:
        raise RuntimeError("sync failed")

    with pytest.raises(RuntimeError, match="sync failed"):
        await gate.try_run(boom)

    assert gate.is_running() is False
    # After the exception the gate is free again.
    await gate.try_run(lambda: asyncio.sleep(0))
