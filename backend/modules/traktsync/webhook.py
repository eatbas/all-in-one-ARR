"""The remove-on-import half of the sync loop (steps 5-6).

Receives a Radarr/Sonarr On-Import webhook, looks the item up in SQLite by
TMDB (Radarr) or TVDB (Sonarr), and removes it from the Trakt list. Removal
honours the live DRY_RUN flag via the Trakt client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.clients.arr import parse_webhook
from core.logging import get_logger, log_action

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("traktsync.webhook")


async def remove_tracked_item(ctx: "AppContext", item: dict[str, Any], *, reason: str) -> None:
    """Remove a tracked item from Trakt and mark it removed in SQLite.

    The Trakt client honours DRY_RUN internally (logging the would-be removal
    without sending). In DRY_RUN we deliberately do **not** persist a 'removed'
    status, otherwise the item would be skipped forever and never actually
    removed once DRY_RUN is switched off.
    """
    if item["type"] == "movie":
        await ctx.trakt.remove_items(movies=[item["tmdb"]])
    else:
        await ctx.trakt.remove_items(shows=[item["tvdb"]])

    if ctx.dry_run:
        ctx.db.add_activity(
            "would_remove", f"would remove {item['title']} from Trakt ({reason})"
        )
        log_action(
            _log,
            "would_remove",
            dry_run=True,
            reason=reason,
            trakt_id=item["trakt_id"],
            tmdb=item["tmdb"],
            tvdb=item["tvdb"],
            title=item["title"],
        )
        return

    ctx.db.set_status(
        trakt_id=item["trakt_id"], list_id=item["list_id"], status="removed"
    )
    ctx.db.add_activity("removed", f"removed {item['title']} from Trakt ({reason})")
    log_action(
        _log,
        "removed",
        dry_run=False,
        reason=reason,
        trakt_id=item["trakt_id"],
        tmdb=item["tmdb"],
        tvdb=item["tvdb"],
        title=item["title"],
    )


async def handle_arr(ctx: "AppContext", payload: dict[str, Any]) -> None:
    """Handle an arr webhook: remove the matching item once it is imported."""
    event = parse_webhook(payload)
    if not event.is_import:
        _log.info("ignoring arr event=%s (not an import)", event.event)
        return

    item = None
    if event.tmdb is not None:
        item = ctx.db.find_by_tmdb(event.tmdb)
    if item is None and event.tvdb is not None:
        item = ctx.db.find_by_tvdb(event.tvdb)

    if item is None:
        _log.info(
            "no matching tracked item for import tmdb=%s tvdb=%s",
            event.tmdb,
            event.tvdb,
        )
        return

    if item["status"] == "removed":
        _log.info("item already removed: %s", item["title"])
        return

    await remove_tracked_item(ctx, item, reason="imported")
