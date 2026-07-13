"""Shared detached-task helpers for scheduler-adjacent modules.

Per the asyncio docs, fire-and-forget tasks must be referenced somewhere or
they can be garbage-collected mid-flight. These helpers own that bookkeeping:
callers pass the module-level ``set`` that holds the strong references, and a
done-callback clears the slot. The supervised variant additionally consumes
and logs any exception so a detached failure is never silently dropped by the
asyncio runtime.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from logging import Logger
from typing import Any


def spawn_tracked(
    tasks: set[asyncio.Task], coro: Coroutine[Any, Any, None]
) -> asyncio.Task:
    """Spawn ``coro`` detached, holding a strong reference until it completes.

    The done-callback clears the slot once the task finishes; exceptions are
    left for the caller to collect (use :func:`spawn_supervised` when nobody
    awaits the task).
    """
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def spawn_supervised(
    tasks: set[asyncio.Task],
    coro: Coroutine[Any, Any, None],
    *,
    log: Logger,
    log_msg: str = "detached task raised an exception",
) -> asyncio.Task:
    """Spawn ``coro`` detached, holding a strong reference and logging failures.

    The done-callback clears the slot and consumes any exception so it is never
    silently dropped by the asyncio runtime; ``log`` names the caller's logger
    so the failure is attributed to the owning module.
    """
    task = asyncio.create_task(coro)
    tasks.add(task)

    def _on_done(done: asyncio.Task) -> None:
        tasks.discard(done)
        if not done.cancelled() and (exc := done.exception()) is not None:
            log.exception("%s", log_msg, exc_info=exc)

    task.add_done_callback(_on_done)
    return task
