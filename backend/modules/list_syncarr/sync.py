"""The poll-and-request half of the sync loop (steps 1-2).

Reads the configured Trakt list, mirrors each item into SQLite (storing both
TMDB and TVDB ids for later reverse lookup), then ensures each not-yet-handled
item has a Seer request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.seer import (
    AVAILABLE,
    PARTIALLY_AVAILABLE,
    PENDING,
    PROCESSING,
    SeerError,
)
from core.logging import get_logger, log_action
from modules.list_syncarr.removal import remove_tracked_item

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.settings_store import TrackedList

_log = get_logger("list_syncarr.sync")

# Seer states that mean the item is already in the system (do not re-request).
_ALREADY_REQUESTED = frozenset({PENDING, PROCESSING, PARTIALLY_AVAILABLE})


async def poll_and_request(ctx: "AppContext") -> None:
    """Poll every selected Trakt list and request missing items in Seer.

    Each list is isolated: a failure reading or processing one list (e.g. an
    unauthorised or transient error) is logged and does not abort the others.
    """
    for tracked in ctx.settings_store.tracked_lists():
        await _poll_one_list(ctx, tracked)


async def _poll_one_list(ctx: "AppContext", tracked: "TrackedList") -> None:
    """Poll a single Trakt list and request its missing items."""
    list_id = tracked.slug
    try:
        items = await ctx.trakt.read_list_items(
            list_id=list_id, owner_user=tracked.owner_user
        )
    except Exception as exc:
        # e.g. Trakt not yet authorised, or a transient API error.
        _log.error("Trakt list read failed for %s: %s", list_id, exc)
        ctx.db.add_activity(
            "List sync failed",
            f'Could not read the Trakt list "{list_id}"; check the Trakt connection.',
        )
        return
    _log.info("polled Trakt list id=%s items=%d", list_id, len(items))

    for raw in items:
        trakt_id = raw.get("trakt_id")
        if trakt_id is None:
            _log.warning("skipping Trakt item without trakt id: %s", raw.get("title"))
            continue
        try:
            await _process_item(ctx, raw, list_id)
        except Exception as exc:  # isolate per-item failures
            title = raw.get("title") or "unknown item"
            _log.exception("failed to process item %s: %s", title, exc)
            ctx.db.add_activity(
                "List sync failed",
                f'Could not process "{title}" during the sync.',
            )

    # The list was read successfully; record the poll time so the dashboard can
    # show "last synced" and derive the next poll (per-item failures above are
    # isolated and must not suppress this).
    ctx.db.touch_list_synced(list_id)


async def _process_item(ctx: "AppContext", raw: dict, list_id: str) -> None:
    """Upsert one item and create a Seer request when appropriate."""
    trakt_id = raw["trakt_id"]
    media_type = raw.get("type")
    title = raw.get("title")
    tmdb = raw.get("tmdb")

    ctx.db.upsert_item(
        trakt_id=trakt_id,
        type=media_type,
        title=title,
        year=raw.get("year"),
        tmdb=tmdb,
        tvdb=raw.get("tvdb"),
        imdb=raw.get("imdb"),
        list_id=list_id,
    )

    item = ctx.db.get_item(trakt_id=trakt_id, list_id=list_id)
    assert item is not None  # just upserted
    if item["status"] == "removed":
        return
    if item["status"] == "available":
        if ctx.settings_store.auto_remove_when_available():
            await remove_tracked_item(ctx, item, reason="available in Seer")
        return

    if tmdb is None:
        _log.warning("cannot request %s: no TMDB id", title)
        ctx.db.add_activity(
            "Item skipped",
            f'"{title}" has no TMDB id, so it cannot be requested.',
        )
        return

    seer_media_type = "movie" if media_type == "movie" else "tv"
    try:
        seer_status = await ctx.seer.get_status(
            media_type=seer_media_type, tmdb_id=tmdb
        )
    except SeerError as exc:
        _log.error("Seer status check failed for %s: %s", title, exc)
        ctx.db.add_activity(
            "List sync failed",
            f'Could not check Seer status for "{title}".',
        )
        return

    if seer_status == AVAILABLE:
        # The item is downloaded and ready to serve. Mark it available, then —
        # when auto-remove is enabled — drop it from the Trakt list in the same
        # pass. Removal deletes the Trakt list entry and known Seer
        # request; the media files in Radarr/Sonarr are never touched.
        # remove_tracked_item skips lists not owned by 'me', so the item simply
        # stays 'available' when it cannot (yet) be removed.
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="available")
        log_action(_log, "already_available", tmdb=tmdb, title=title)
        if ctx.settings_store.auto_remove_when_available():
            await remove_tracked_item(ctx, item, reason="available in Seer")
        return

    if seer_status in _ALREADY_REQUESTED:
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
        log_action(_log, "already_requested", tmdb=tmdb, title=title)
        return

    request_id = await ctx.seer.create_request(
        media_type=seer_media_type, tmdb_id=tmdb
    )
    ctx.db.set_request_id(trakt_id=trakt_id, list_id=list_id, request_id=request_id)
    ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
    ctx.db.add_activity("Request created", f'Requested "{title}" in Seer.')
    log_action(
        _log,
        "requested",
        tmdb=tmdb,
        title=title,
        request_id=request_id,
    )
