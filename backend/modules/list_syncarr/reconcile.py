"""Availability reconciliation sweep (now a manual action).

Asks Seer which tracked items are now Available (5) and removes them from
Trakt. This used to run on a nightly cron; it is now triggered on demand by the
dashboard's "Delete availables" button (via ``ctx.remove_available``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.seer import AVAILABLE, SeerError
from core.logging import get_logger
from modules.list_syncarr.removal import remove_tracked_item

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("list_syncarr.reconcile")


async def reconcile(ctx: "AppContext") -> None:
    """Remove any tracked items Seer now reports as Available."""
    items = ctx.db.active_items()
    _log.info("reconciling %d active item(s)", len(items))

    for item in items:
        tmdb = item.get("tmdb")
        if tmdb is None:
            continue
        try:
            seer_media_type = "movie" if item["type"] == "movie" else "tv"
            seer_status = await ctx.seer.get_status(
                media_type=seer_media_type, tmdb_id=tmdb
            )
            if seer_status == AVAILABLE:
                await remove_tracked_item(ctx, item, reason="reconciled (webhook missed)")
        except SeerError as exc:
            title = item.get("title") or "unknown item"
            _log.error("reconcile failed for %s: %s", title, exc)
            ctx.db.add_activity(
                "Availability check failed",
                f'Could not check availability for "{title}".',
            )
