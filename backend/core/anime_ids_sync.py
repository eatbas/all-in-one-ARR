"""Scheduled refresh wiring for the Fribb anime id mapping.

The mapping itself (:mod:`core.anime_ids`) also refreshes lazily inside
``enrich()``, but that path only runs when an AniList feed is fetched during a
trending refresh — so a restart that restores the trending snapshot from the
database would never check the mapping, and its configured 1/3/5-day cadence
was effectively bounded by the trending interval. This module gives the
mapping an independent life: a supervised check at every start-up plus an
hourly interval job. Each check is a single ``stat()`` while the cached file
is fresh; the ~6 MB download happens only once the cadence elapses. The shape
mirrors ``core.trending_sync``: a module-level job plus a context holder,
because APScheduler 4 cannot serialise a closure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.app_metrics import observe_scheduler_job
from core.logging import get_logger
from core.tasks import spawn_supervised

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

# The job id under which the hourly mapping check is registered.
_JOB_ID = "anime_ids_refresh"
_REFRESH_INTERVAL_MINUTES = 60
_log = get_logger("anime_ids_sync")

# Strong references to in-flight boot checks (see core.tasks).
_REFRESH_TASKS: set[asyncio.Task] = set()


@dataclass
class _AnimeIdsSync:
    """Holds the context the module-level job reads (APScheduler-4 constraint)."""

    ctx: AppContext | None = None


_anime_ids_sync = _AnimeIdsSync()


async def _anime_ids_refresh_job() -> None:
    """Scheduled entrypoint: refresh the mapping once its cadence has elapsed."""
    ctx = _anime_ids_sync.ctx
    if ctx is None or ctx.anime_ids is None:
        return
    await observe_scheduler_job(_JOB_ID, ctx.anime_ids.ensure_fresh)


async def start_anime_ids_refresh(ctx: AppContext) -> None:
    """Register the hourly mapping check and spawn one at start-up.

    The boot check runs as a supervised detached task — the download must
    never delay the lifespan — and is a ``stat()``-only no-op while the file
    is fresh. ``defer_first_run`` stops APScheduler 4's immediate first fire
    from duplicating that boot check; the asyncio lock inside the mapping
    makes any residual overlap harmless. A context without a mapping (tests
    may null it) is a safe no-op.
    """
    _anime_ids_sync.ctx = ctx
    if ctx.anime_ids is None:
        return
    await ctx.scheduler.add_interval(
        _anime_ids_refresh_job,
        minutes=_REFRESH_INTERVAL_MINUTES,
        id=_JOB_ID,
        defer_first_run=True,
    )
    spawn_supervised(
        _REFRESH_TASKS,
        ctx.anime_ids.ensure_fresh(),
        log=_log,
        log_msg="anime id mapping boot refresh raised an exception",
    )
