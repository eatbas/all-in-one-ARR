"""Tests for modules.traktsync.setup and the scheduled job entrypoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI

import modules.traktsync as traktsync
from tests.conftest import StubJellyseerr, StubTrakt, make_ctx


async def test_setup_registers_jobs_webhook_and_sync(db) -> None:
    scheduler = AsyncMock()
    ctx = make_ctx(db=db)
    await traktsync.setup(scheduler, FastAPI(), ctx)

    scheduler.add_interval.assert_awaited_once()
    assert scheduler.add_interval.call_args.kwargs["id"] == "traktsync_poll"
    scheduler.add_cron.assert_awaited_once()
    assert scheduler.add_cron.call_args.kwargs["id"] == "traktsync_reconcile"
    assert "arr" in ctx.webhooks._handlers
    assert ctx.sync_now is not None


async def test_scheduled_jobs_run_against_registered_context(db) -> None:
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[]), jellyseerr=StubJellyseerr(),
    )
    traktsync.register_context(ctx)
    # Neither should raise; they resolve the module-level context.
    await traktsync.poll_job()
    await traktsync.reconcile_job()
    ctx.trakt.read_list_items.assert_awaited()


async def test_sync_now_callable_invokes_poll(db) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[]))
    await traktsync.setup(AsyncMock(), FastAPI(), ctx)
    await ctx.sync_now()
    ctx.trakt.read_list_items.assert_awaited()
