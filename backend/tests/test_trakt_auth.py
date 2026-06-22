"""Tests for core.trakt_auth (UI-driven device authorisation)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from core.trakt_auth import (
    CONNECTED,
    FAILED,
    PENDING,
    _poll_device_auth,
    cancel_device_auth,
    start_device_auth,
)
from tests.conftest import StubTrakt, make_ctx


async def test_start_sets_pending_then_connects(db) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=False))
    session = await start_device_auth(ctx)
    assert session.state == PENDING
    assert session.is_pending is True
    assert session.user_code == "ABCD-1234"
    assert session.verification_url == "https://trakt.tv/activate"

    await session.task  # poll_for_token returns True by default
    assert session.state == CONNECTED
    assert session.message == "Connected"


async def test_start_is_idempotent_while_pending(db) -> None:
    ctx = make_ctx(db=db)
    ctx.trakt_auth.state = PENDING
    session = await start_device_auth(ctx)
    assert session is ctx.trakt_auth
    ctx.trakt.request_device_code.assert_not_awaited()


async def test_poll_marks_failed_when_not_authorised(db) -> None:
    trakt = StubTrakt()
    trakt.poll_for_token = AsyncMock(return_value=False)
    ctx = make_ctx(db=db, trakt=trakt)
    await _poll_device_auth(ctx, {"device_code": "d"})
    assert ctx.trakt_auth.state == FAILED
    assert ctx.trakt_auth.message == "Authorisation did not complete"


async def test_poll_marks_failed_on_exception(db) -> None:
    trakt = StubTrakt()
    trakt.poll_for_token = AsyncMock(side_effect=RuntimeError("boom"))
    ctx = make_ctx(db=db, trakt=trakt)
    await _poll_device_auth(ctx, {"device_code": "d"})
    assert ctx.trakt_auth.state == FAILED
    assert "boom" in ctx.trakt_auth.message


async def test_cancel_cancels_running_task(db) -> None:
    ctx = make_ctx(db=db)

    async def _forever() -> None:
        await asyncio.sleep(10)

    ctx.trakt_auth.task = asyncio.create_task(_forever())
    cancel_device_auth(ctx)
    await asyncio.gather(ctx.trakt_auth.task, return_exceptions=True)
    assert ctx.trakt_auth.task.cancelled()


async def test_cancel_is_noop_without_task(db) -> None:
    ctx = make_ctx(db=db)
    cancel_device_auth(ctx)  # no task -> no-op, must not raise
