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
    """Remove items Seer now reports as Available from their Trakt list.

    Scoped to lists still in the settings store: an active item whose list the user
    has untracked is left alone, mirroring the per-sync refresh in ``sync.py`` (the
    DB keeps a list's item rows after it is untracked, so the slug filter is what
    keeps the manual sweep from touching them).
    """
    tracked_slugs = {item.slug for item in ctx.settings_store.tracked_lists()}
    items = ctx.db.active_items()
    _log.info("reconciling %d active item(s)", len(items))

    for item in items:
        if item["list_id"] not in tracked_slugs:
            continue
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
