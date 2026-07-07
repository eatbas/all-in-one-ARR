"""Shared Trakt list-removal primitive.

Every delete path in the module funnels through :func:`remove_tracked_item`: the
in-sync removal (``sync.py``), the manual "Delete availables" sweep
(``reconcile.py``), and the per-item delete (``manual.py``). Removal deletes the
entry from the Trakt list (``ctx.trakt.remove_items``) **and** the corresponding
Seer request; it never touches the media files in Radarr/Sonarr.

The Seer request is deleted using the id this app stored when it created the
request, or — when none was stored (the request was made directly in Seer) — the
ids looked up from Seer's ``mediaInfo.requests``, so externally-created requests are
cleaned up too. Deleting a Seer request removes only the request record; the title
stays in Radarr/Sonarr and keeps downloading.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.logging import get_logger, log_action

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

_log = get_logger("list_syncarr.removal")


async def remove_tracked_item(
    ctx: AppContext, item: dict[str, Any], *, reason: str
) -> None:
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

    After the Trakt entry is removed, the item's Seer request is deleted (the
    stored id, or one looked up from Seer when this app did not create it). If that
    Seer cleanup fails the item is left active so it is retried.

    A transient removal error is logged and the item is left active rather than
    crashing the caller.
    """
    list_id = item["list_id"]
    title = item["title"]
    owner = ctx.settings_store.owner_for(list_id)
    if owner != "me":
        ctx.db.add_activity(
            "Removal skipped",
            f'Cannot remove "{title}" from {owner}\'s list "{list_id}".',
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
        id_kind = "TMDB" if is_movie else "TVDB"
        ctx.db.add_activity(
            "Removal skipped",
            f'Cannot remove "{title}" from "{list_id}": no {id_kind} id.',
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
        _log.error("Trakt remove failed for %s: %s", title, exc)
        ctx.db.add_activity(
            "Removal failed",
            f'Could not remove "{title}" from Trakt.',
        )
        return

    request_deleted = await _delete_seer_request(ctx, item)
    if not request_deleted:
        return

    ctx.db.set_status(
        trakt_id=item["trakt_id"], list_id=item["list_id"], status="removed"
    )
    ctx.db.add_activity(
        "Item removed from Trakt",
        f'Removed "{title}" from the Trakt list.',
    )
    log_action(
        _log,
        "removed",
        reason=reason,
        trakt_id=item["trakt_id"],
        tmdb=item["tmdb"],
        tvdb=item["tvdb"],
        title=item["title"],
    )


async def _delete_seer_request(ctx: AppContext, item: dict[str, Any]) -> bool:
    """Delete the item's Seer request(s).

    Prefers the request id this app stored when it created the request; when none
    was stored (the request was made directly in Seer) the ids are looked up from
    Seer's ``mediaInfo.requests`` so externally-created requests are cleaned up too.
    Returns ``True`` when there is nothing to delete or every delete succeeds, and
    ``False`` (leaving the item active for retry) when a Seer call fails.
    """
    title = item["title"]
    stored = item.get("seer_request_id")
    if stored is not None:
        request_ids: list[int] = [stored]
    elif item.get("tmdb") is None:
        # Nothing stored and no TMDB id to look up by (e.g. a show with only a
        # TVDB id): there is no Seer request we can resolve.
        return True
    else:
        media_type = "movie" if item["type"] == "movie" else "tv"
        try:
            request_ids = await ctx.seer.get_request_ids(
                media_type=media_type, tmdb_id=item["tmdb"]
            )
        except Exception as exc:
            _log.error("Seer request lookup failed for %s: %s", title, exc)
            ctx.db.add_activity(
                "Removal failed",
                f'Could not look up the Seer request for "{title}".',
            )
            return False

    if not request_ids:
        return True

    for request_id in request_ids:
        try:
            await ctx.seer.delete_request(request_id=request_id)
        except Exception as exc:
            _log.error("Seer request delete failed for %s: %s", title, exc)
            ctx.db.add_activity(
                "Removal failed",
                f'Could not remove the Seer request for "{title}".',
            )
            return False
    ctx.db.add_activity(
        "Seer request removed",
        f'Removed the Seer request for "{title}".',
    )
    return True
