"""Module discovery and loading.

Each package under ``modules/`` may expose a ``setup(scheduler, app, ctx)``
entrypoint. :func:`load_modules` discovers them, imports each, and calls
``setup``. A failure in one module is logged and isolated so the others still
load.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING

from fastapi import FastAPI

import modules as modules_pkg
from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("registry")


def discover_module_names() -> list[str]:
    """Return the names of the sub-packages under ``modules/``."""
    return [name for _, name, _ in pkgutil.iter_modules(modules_pkg.__path__)]


async def load_modules(
    scheduler: SchedulerService, app: FastAPI, ctx: AppContext
) -> list[str]:
    """Import each module package and call its ``setup``; return loaded names.

    ``setup`` may be sync or async (async is required for APScheduler 4's async
    ``add_schedule``); an awaitable result is awaited.
    """
    loaded: list[str] = []
    for name in discover_module_names():
        try:
            module = importlib.import_module(f"modules.{name}")
            setup = getattr(module, "setup", None)
            if setup is None:
                _log.warning("module %s has no setup(); skipping", name)
                continue
            result = setup(scheduler, app, ctx)
            if inspect.isawaitable(result):
                await result
            loaded.append(name)
            _log.info("module loaded: %s", name)
        except Exception as exc:  # isolate per-module failures
            _log.exception("failed to load module %s: %s", name, exc)
    return loaded
