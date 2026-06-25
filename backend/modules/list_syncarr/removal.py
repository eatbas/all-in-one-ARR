"""Shared Trakt list-removal primitive.

Every delete path in the module funnels through :func:`remove_tracked_item`: the
in-sync availability removal (``sync.py``), the manual "Delete availables" sweep
(``reconcile.py``), and the per-item delete (``manual.py``). Removal only deletes
the entry from the Trakt list (``ctx.trakt.remove_items``) and the corresponding
Jellyseerr request when the request id is known — it never touches the media
files in Radarr/Sonarr.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.logging import get_logger, log_action

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("list_syncarr.removal")


async def remove_tracked_item(ctx: "AppContext", item: dict[str, Any], *, reason: str) -> None:
    """Remove a tracked item from its Trakt list and mark it removed in SQLite.

    The owner of the list is resolved from the settings store so the removal hits
    the correct ``/users/{owner}/lists/{slug}`` endpoint. Trakt only permits
    removing items from a list the connected account owns; the app always operates
    as ``me``, so a list whose stored owner is not ``me`` (another user's list
    added by URL) is **skipped** without issuing a doomed request; the skip is
    recorded so it is visible in the activity feed.

    A movie is removed by its TMDB id and a show by its TVDB id; an item missing
    the id its type needs is skipped (recorded) rather than sent as a malformed
    request.

    A transient removal error is logged and the item is left active rather than
    crashing the caller.
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
            reason=reason,
            owner=owner,
            list_id=list_id,
            title=item["title"],
        )
        return

    # Trakt removes movies by TMDB id and shows by TVDB id; without the relevant
    # id the request cannot be built, so skip-and-record rather than send a
    # malformed payload (e.g. a Trakt show that carries no TVDB id).
    is_movie = item["type"] == "movie"
    removal_id = item["tmdb"] if is_movie else item["tvdb"]
    if removal_id is None:
        id_kind = "tmdb" if is_movie else "tvdb"
        ctx.db.add_activity(
            "remove_skipped",
            f"cannot remove {item['title']} from {list_id}: no {id_kind} id",
        )
        log_action(
            _log,
            "remove_skipped",
            reason=reason,
            list_id=list_id,
            title=item["title"],
        )
        return

    try:
        if is_movie:
            await ctx.trakt.remove_items(
                movies=[removal_id], list_id=list_id, owner_user=owner
            )
        else:
            await ctx.trakt.remove_items(
                shows=[removal_id], list_id=list_id, owner_user=owner
            )
    except Exception as exc:
        _log.error("Trakt remove failed for %s: %s", item["title"], exc)
        ctx.db.add_activity("error", f"Trakt remove failed for {item['title']}: {exc}")
        return

    request_deleted = await _delete_jellyseerr_request(ctx, item)
    if not request_deleted:
        return

    ctx.db.set_status(
        trakt_id=item["trakt_id"], list_id=item["list_id"], status="removed"
    )
    ctx.db.add_activity("removed", f"removed {item['title']} from Trakt ({reason})")
    log_action(
        _log,
        "removed",
        reason=reason,
        trakt_id=item["trakt_id"],
        tmdb=item["tmdb"],
        tvdb=item["tvdb"],
        title=item["title"],
    )


async def _delete_jellyseerr_request(
    ctx: "AppContext", item: dict[str, Any]
) -> bool:
    """Delete the stored Jellyseerr request, if this app knows its id."""
    request_id = item.get("jellyseerr_request_id")
    if request_id is None:
        return True
    try:
        await ctx.jellyseerr.delete_request(request_id=request_id)
    except Exception as exc:
        _log.error("Jellyseerr request delete failed for %s: %s", item["title"], exc)
        ctx.db.add_activity(
            "error",
            f"Jellyseerr request delete failed for {item['title']}: {exc}",
        )
        return False
    ctx.db.add_activity(
        "request_deleted",
        f"deleted Jellyseerr request {request_id} for {item['title']}",
    )
    return True
