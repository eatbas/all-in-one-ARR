"""Availability reconciliation sweep (now a manual action).

Asks Jellyseerr which tracked items are now Available (5) and removes them from
Trakt. This used to run on a nightly cron; it is now triggered on demand by the
dashboard's "Delete availables" button (via ``ctx.remove_available``). Honours the
live DRY_RUN flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.jellyseerr import AVAILABLE, JellyseerrError
from core.logging import get_logger
from modules.list_syncarr.webhook import remove_tracked_item

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("list_syncarr.reconcile")


async def reconcile(ctx: "AppContext") -> None:
    """Remove any tracked items Jellyseerr now reports as Available."""
    items = ctx.db.active_items()
    _log.info("reconciling %d active item(s)", len(items))

    for item in items:
        tmdb = item.get("tmdb")
        if tmdb is None:
            continue
        try:
            js_media_type = "movie" if item["type"] == "movie" else "tv"
            js_status = await ctx.jellyseerr.get_status(
                media_type=js_media_type, tmdb_id=tmdb
            )
            if js_status == AVAILABLE:
                await remove_tracked_item(ctx, item, reason="reconciled (webhook missed)")
        except JellyseerrError as exc:
            _log.error("reconcile failed for %s: %s", item.get("title"), exc)
            ctx.db.add_activity(
                "error", f"reconcile failed for {item.get('title')}: {exc}"
            )
