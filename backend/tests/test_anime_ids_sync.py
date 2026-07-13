"""Tests for core.anime_ids_sync (boot check and hourly mapping refresh)."""

from __future__ import annotations

import asyncio

from core import anime_ids_sync
from core.anime_ids_sync import (
    _anime_ids_refresh_job,
    _anime_ids_sync,
    start_anime_ids_refresh,
)
from tests.conftest import make_ctx


async def test_start_registers_hourly_job_and_spawns_boot_check(
    db, monkeypatch
) -> None:
    ctx = make_ctx(db=db)  # scheduler is an AsyncMock; anime_ids a stub
    monkeypatch.setattr(_anime_ids_sync, "ctx", None)

    await start_anime_ids_refresh(ctx)
    await asyncio.gather(*list(anime_ids_sync._REFRESH_TASKS))

    # The hourly check is registered with the first fire deferred — the boot
    # check below already covers start-up, so APScheduler 4's immediate first
    # run must not duplicate it.
    add_call = next(
        call
        for call in ctx.scheduler.add_interval.await_args_list
        if call.kwargs["id"] == "anime_ids_refresh"
    )
    assert add_call.kwargs["minutes"] == 60
    assert add_call.kwargs["defer_first_run"] is True
    # The boot check ran (detached, drained above) and the holder now feeds
    # the scheduled job.
    ctx.anime_ids.ensure_fresh.assert_awaited_once()
    assert _anime_ids_sync.ctx is ctx


async def test_job_refreshes_the_mapping_via_the_holder(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    monkeypatch.setattr(_anime_ids_sync, "ctx", ctx)

    await _anime_ids_refresh_job()

    ctx.anime_ids.ensure_fresh.assert_awaited_once()


async def test_job_is_a_no_op_without_context_or_mapping(db, monkeypatch) -> None:
    # Before start ever ran (holder empty) the job must not blow up.
    monkeypatch.setattr(_anime_ids_sync, "ctx", None)
    await _anime_ids_refresh_job()

    # A context whose mapping was nulled (tests do this) is equally safe.
    ctx = make_ctx(db=db)
    ctx.anime_ids = None
    monkeypatch.setattr(_anime_ids_sync, "ctx", ctx)
    await _anime_ids_refresh_job()


async def test_start_without_a_mapping_registers_nothing(db, monkeypatch) -> None:
    ctx = make_ctx(db=db)
    ctx.anime_ids = None
    monkeypatch.setattr(_anime_ids_sync, "ctx", None)

    await start_anime_ids_refresh(ctx)

    ctx.scheduler.add_interval.assert_not_awaited()
    assert not anime_ids_sync._REFRESH_TASKS
