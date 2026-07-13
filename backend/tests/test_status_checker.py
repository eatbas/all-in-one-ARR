"""Tests for core.status_checker."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.status_checker import StatusChecker


@pytest.fixture
def checker(make_context, db):
    ctx = make_context(db=db)
    return StatusChecker(ctx)


async def test_check_once_records_ok_and_failure(checker) -> None:
    checker._ctx.seer.test_connection = AsyncMock(
        return_value={"ok": True, "detail": "Connected"}
    )
    checker._ctx.sonarr.test_connection = AsyncMock(
        return_value={"ok": False, "detail": "Refused"}
    )

    await checker._check_once()
    result = checker.get_statuses()

    assert result.interval_seconds == 60
    assert result.last_check_at is not None
    assert result.services["seer"].ok is True
    assert result.services["seer"].detail == "Connected"
    assert result.services["sonarr"].ok is False
    assert result.services["sonarr"].detail == "Refused"


async def test_check_once_catches_unexpected_exception(checker) -> None:
    checker._ctx.trakt.test_connection = AsyncMock(side_effect=RuntimeError("boom"))

    await checker._check_once()
    result = checker.get_statuses()

    assert result.services["trakt"].ok is False
    assert "boom" in result.services["trakt"].detail


async def test_check_once_handles_legacy_success_payload(checker) -> None:
    checker._ctx.tmdb.test_connection = AsyncMock(return_value={"unexpected": "shape"})

    await checker._check_once()
    result = checker.get_statuses()

    assert result.services["tmdb"].ok is True
    assert result.services["tmdb"].detail == "Connected"


async def test_check_now_runs_and_returns_snapshot(checker) -> None:
    await checker.check_now()
    result = checker.get_statuses()
    assert result.last_check_at is not None
    assert len(result.services) == 8


async def test_start_stop_lifecycle(checker) -> None:
    await checker.start()
    assert checker._task is not None
    await checker.stop()
    assert checker._task is None


async def test_stop_without_start_is_safe(checker) -> None:
    await checker.stop()
    assert checker._task is None


async def test_loop_exits_immediately_when_stopped(checker) -> None:
    checker._stop_event.set()
    await checker._loop()
    assert checker.get_statuses().last_check_at is None


async def test_loop_runs_one_iteration_and_stops(checker) -> None:
    checker._check_once = AsyncMock()
    checker._ctx.settings_store.update_status_check_interval(0)
    await checker.start()
    # Give the loop time to hit the zero-second timeout at least once.
    await asyncio.sleep(0.01)
    await checker.stop()
    checker._check_once.assert_awaited()


async def test_check_once_handles_base_exception(checker) -> None:
    class Boom(BaseException):
        pass

    async def boom(_name: str, _client: object) -> object:
        raise Boom("kapow")

    checker._check_one = boom
    await checker._check_once()
    result = checker.get_statuses()
    assert any("kapow" in s.detail for s in result.services.values())


async def test_check_one_prefers_a_cheap_status_probe(checker) -> None:
    # A client exposing status_probe (OMDb) is checked through it so the
    # recurring cycle never sweeps the whole key pool.
    from unittest.mock import AsyncMock

    client = type("Probed", (), {})()
    client.status_probe = AsyncMock(return_value={"ok": True, "detail": "cheap"})
    client.test_connection = AsyncMock()

    snapshot = await checker._check_one("omdb", client)

    assert snapshot.ok is True
    assert snapshot.detail == "cheap"
    client.status_probe.assert_awaited_once()
    client.test_connection.assert_not_awaited()
