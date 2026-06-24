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

_log = get_logger("list_syncarr.webhook")


async def remove_tracked_item(ctx: "AppContext", item: dict[str, Any], *, reason: str) -> None:
    """Remove a tracked item from its Trakt list and mark it removed in SQLite.

    The owner of the list is resolved from the settings store so the removal hits
    the correct ``/users/{owner}/lists/{slug}`` endpoint. Trakt only permits
    removing items from a list the connected account owns; the app always operates
    as ``me``, so a list whose stored owner is not ``me`` (another user's list
    added by URL) is **skipped** without issuing a doomed request; the skip is
    recorded so it is visible in the activity feed.

    The Trakt client honours DRY_RUN internally (logging the would-be removal
    without sending). In DRY_RUN we deliberately do **not** persist a 'removed'
    status, otherwise the item would be skipped forever and never actually
    removed once DRY_RUN is off. A transient removal error is logged and the item
    is left untouched rather than crashing the caller.
    """
    list_id = item["list_id"]
    owner = ctx.settings_store.owner_for(list_id)
    if owner != "me":
        ctx.db.add_activity(
            "remove_skipped",
            f"cannot remove {item['title']} from {owner}'s list {list_id}",
        )
        log_action(
            _log,
            "remove_skipped",
            dry_run=ctx.dry_run,
            reason=reason,
            owner=owner,
            list_id=list_id,
            title=item["title"],
        )
        return
    try:
        if item["type"] == "movie":
            await ctx.trakt.remove_items(
                movies=[item["tmdb"]], list_id=list_id, owner_user=owner
            )
        else:
            await ctx.trakt.remove_items(
                shows=[item["tvdb"]], list_id=list_id, owner_user=owner
            )
    except Exception as exc:
        _log.error("Trakt remove failed for %s: %s", item["title"], exc)
        ctx.db.add_activity("error", f"Trakt remove failed for {item['title']}: {exc}")
        return

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
    """Handle an arr webhook: remove the imported item from every list holding it.

    A title can appear in more than one tracked list (e.g. a show in both ``tv``
    and ``anime``), so all matches are collected — by TMDB (Radarr) and TVDB
    (Sonarr) — de-duplicated, and each removed from its own list.
    """
    event = parse_webhook(payload)
    if not event.is_import:
        _log.info("ignoring arr event=%s (not an import)", event.event)
        return

    matches: list[dict[str, Any]] = []
    if event.tmdb is not None:
        matches.extend(ctx.db.find_all_by_tmdb(event.tmdb))
    if event.tvdb is not None:
        matches.extend(ctx.db.find_all_by_tvdb(event.tvdb))

    seen: set[tuple[int, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in matches:
        key = (item["trakt_id"], item["list_id"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    if not unique:
        _log.info(
            "no matching tracked item for import tmdb=%s tvdb=%s",
            event.tmdb,
            event.tvdb,
        )
        return

    for item in unique:
        if item["status"] == "removed":
            _log.info("item already removed: %s", item["title"])
            continue
        await remove_tracked_item(ctx, item, reason="imported")
