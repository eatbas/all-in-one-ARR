"""traktsync module: keep a Trakt list in sync with Jellyseerr and remove items
once Radarr/Sonarr import them.

The module registers:
- an interval poll job (poll Trakt -> request in Jellyseerr),
- a nightly reconciliation job (safety net),
- the ``/webhook/arr`` handler (remove on import),
- and ``ctx.sync_now`` so the dashboard's "Sync now" button works.

``setup`` is async because APScheduler 4's ``add_schedule`` is async; the
registry awaits it. APScheduler 4 requires top-level importable callables for
its jobs, so the scheduled jobs are the module-level ``poll_job``/
``reconcile_job`` functions which resolve the active context from the single
module-level reference set in ``setup`` (justified: one context exists per
process, and the scheduler cannot reference closures).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from core.logging import get_logger
from modules.traktsync.reconcile import reconcile
from modules.traktsync.sync import poll_and_request
from modules.traktsync.webhook import handle_arr

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("traktsync")

# The active context, set during setup() so the top-level scheduled jobs can
# reach the shared clients/db without the scheduler needing to reference a
# closure (an APScheduler 4 constraint).
_CONTEXT: "AppContext | None" = None


def register_context(ctx: "AppContext") -> None:
    """Store the active context for the scheduled jobs to use."""
    global _CONTEXT
    _CONTEXT = ctx


def _require_context() -> "AppContext":
    if _CONTEXT is None:  # pragma: no cover - guarded by setup ordering
        raise RuntimeError("traktsync context not initialised")
    return _CONTEXT


async def poll_job() -> None:
    """Scheduled entrypoint for the interval poll."""
    await poll_and_request(_require_context())


async def reconcile_job() -> None:
    """Scheduled entrypoint for the nightly reconciliation."""
    await reconcile(_require_context())


async def setup(
    scheduler: "SchedulerService", app: FastAPI, ctx: "AppContext"
) -> None:
    """Register jobs, the webhook handler, and the manual-sync callable."""
    register_context(ctx)

    await scheduler.add_interval(
        poll_job, minutes=ctx.settings.SYNC_INTERVAL_MIN, id="traktsync_poll"
    )
    await scheduler.add_cron(
        reconcile_job, hour=3, minute=0, id="traktsync_reconcile"
    )

    ctx.webhooks.register("arr", lambda payload: handle_arr(ctx, payload))
    ctx.sync_now = lambda: poll_and_request(ctx)

    _log.info("traktsync module ready")
