"""list_syncarr module: keep a Trakt list in sync with Jellyseerr and remove items
once Radarr/Sonarr import them.

The module registers:
- an interval poll job (poll Trakt -> request in Jellyseerr) at the configured,
  runtime-adjustable sync interval,
- the ``/webhook/arr`` handler (remove on import),
- ``ctx.sync_now`` so the dashboard's "Sync now" button works,
- and the manual removal/reschedule callables the dashboard's delete controls and
  sync-interval setting drive (``ctx.remove_available``/``remove_item``/``reschedule_sync``).

Removal is no longer autonomous: the nightly reconciliation cron has been retired
in favour of the manual "Delete availables" action (``ctx.remove_available``), which
runs the same :func:`reconcile` sweep on demand.

``setup`` is async because APScheduler 4's ``add_schedule`` is async; the
registry awaits it. APScheduler 4 requires top-level importable callables for
its jobs, so the scheduled poll is the module-level ``poll_job`` function which
resolves the active context from the single module-level reference set in
``setup`` (justified: one context exists per process, and the scheduler cannot
reference closures).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from core.logging import get_logger
from modules.list_syncarr.manual import remove_one
from modules.list_syncarr.reconcile import reconcile
from modules.list_syncarr.sync import poll_and_request
from modules.list_syncarr.webhook import handle_arr

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.scheduler import SchedulerService

_log = get_logger("list_syncarr")

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
        raise RuntimeError("list_syncarr context not initialised")
    return _CONTEXT


async def poll_job() -> None:
    """Scheduled entrypoint for the interval poll."""
    await poll_and_request(_require_context())


async def setup(
    scheduler: "SchedulerService", app: FastAPI, ctx: "AppContext"
) -> None:
    """Register the poll job, the webhook handler, and the manual callables."""
    register_context(ctx)

    await scheduler.add_interval(
        poll_job,
        minutes=ctx.settings_store.sync_interval_minutes(),
        id="list_syncarr_poll",
    )

    ctx.webhooks.register("arr", lambda payload: handle_arr(ctx, payload))
    ctx.sync_now = lambda: poll_and_request(ctx)
    ctx.remove_available = lambda: reconcile(ctx)
    ctx.remove_item = lambda list_id, trakt_id: remove_one(ctx, list_id, trakt_id)
    ctx.reschedule_sync = lambda minutes: scheduler.reschedule_interval(
        poll_job, minutes=minutes, id="list_syncarr_poll"
    )

    _log.info("list_syncarr module ready")
