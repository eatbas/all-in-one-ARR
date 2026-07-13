"""Tests for core.tasks (shared detached-task helpers)."""

from __future__ import annotations

import asyncio
import logging

from core.tasks import spawn_supervised, spawn_tracked


async def test_spawn_tracked_holds_a_reference_until_completion() -> None:
    tasks: set[asyncio.Task] = set()
    release = asyncio.Event()

    async def waiter() -> None:
        await release.wait()

    task = spawn_tracked(tasks, waiter())
    # The set is the strong reference keeping the detached task alive.
    assert task in tasks
    release.set()
    await task
    await asyncio.sleep(0)  # let the done-callback run
    assert not tasks


async def test_spawn_supervised_logs_and_consumes_exceptions(caplog) -> None:
    tasks: set[asyncio.Task] = set()

    async def boom() -> None:
        raise RuntimeError("kaput")

    logger = logging.getLogger("test_tasks_supervised")
    with caplog.at_level(logging.ERROR, logger="test_tasks_supervised"):
        task = spawn_supervised(tasks, boom(), log=logger, log_msg="task died")
        # gather(return_exceptions=True) waits without re-raising; the
        # done-callback must have consumed the exception and logged it.
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    assert "task died" in caplog.text
    assert "kaput" in caplog.text
    assert not tasks


async def test_spawn_supervised_success_logs_nothing(caplog) -> None:
    tasks: set[asyncio.Task] = set()

    async def fine() -> None:
        return None

    logger = logging.getLogger("test_tasks_supervised")
    with caplog.at_level(logging.ERROR, logger="test_tasks_supervised"):
        await spawn_supervised(tasks, fine(), log=logger)
        await asyncio.sleep(0)

    assert caplog.text == ""
    assert not tasks


async def test_spawn_supervised_ignores_cancellation(caplog) -> None:
    tasks: set[asyncio.Task] = set()

    async def waiter() -> None:
        await asyncio.Event().wait()

    logger = logging.getLogger("test_tasks_supervised")
    with caplog.at_level(logging.ERROR, logger="test_tasks_supervised"):
        task = spawn_supervised(tasks, waiter(), log=logger)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(0)

    # Cancellation is an orderly shutdown, not a failure worth an error log.
    assert caplog.text == ""
    assert not tasks
