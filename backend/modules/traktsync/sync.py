"""The poll-and-request half of the sync loop (steps 1-2).

Reads the configured Trakt list, mirrors each item into SQLite (storing both
TMDB and TVDB ids for later reverse lookup), then ensures each not-yet-handled
item has a Jellyseerr request. Every request honours the live DRY_RUN flag via
the Jellyseerr client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.jellyseerr import (
    AVAILABLE,
    PARTIALLY_AVAILABLE,
    PENDING,
    PROCESSING,
    JellyseerrError,
)
from core.logging import get_logger, log_action

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.settings_store import TrackedList

_log = get_logger("traktsync.sync")

# Jellyseerr states that mean the item is already in the system (do not re-request).
_ALREADY_REQUESTED = frozenset({PENDING, PROCESSING, PARTIALLY_AVAILABLE})
# Item statuses that need no further action during a poll.
_TERMINAL_STATUSES = frozenset({"requested", "available", "removed"})


async def poll_and_request(ctx: "AppContext") -> None:
    """Poll every selected Trakt list and request missing items in Jellyseerr.

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
        ctx.db.add_activity("error", f"Trakt list read failed for {list_id}: {exc}")
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
            _log.exception("failed to process item %s: %s", raw.get("title"), exc)
            ctx.db.add_activity("error", f"sync failed for {raw.get('title')}: {exc}")


async def _process_item(ctx: "AppContext", raw: dict, list_id: str) -> None:
    """Upsert one item and create a Jellyseerr request when appropriate."""
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
    if item["status"] in _TERMINAL_STATUSES:
        return

    if tmdb is None:
        _log.warning("cannot request %s: no TMDB id", title)
        ctx.db.add_activity("skipped", f"no TMDB id for {title}")
        return

    js_media_type = "movie" if media_type == "movie" else "tv"
    try:
        js_status = await ctx.jellyseerr.get_status(
            media_type=js_media_type, tmdb_id=tmdb
        )
    except JellyseerrError as exc:
        _log.error("Jellyseerr status check failed for %s: %s", title, exc)
        ctx.db.add_activity("error", f"status check failed for {title}: {exc}")
        return

    if js_status == AVAILABLE:
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="available")
        log_action(_log, "already_available", dry_run=ctx.dry_run, tmdb=tmdb, title=title)
        return

    if js_status in _ALREADY_REQUESTED:
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
        log_action(_log, "already_requested", dry_run=ctx.dry_run, tmdb=tmdb, title=title)
        return

    request_id = await ctx.jellyseerr.create_request(
        media_type=js_media_type, tmdb_id=tmdb
    )
    if ctx.dry_run:
        # Do not persist a 'requested' status in dry-run: the request was not
        # actually created, so leaving the item 'synced' ensures the real
        # request is made once DRY_RUN is switched off.
        ctx.db.add_activity("would_request", f"would request {title}")
        log_action(_log, "would_request", dry_run=True, tmdb=tmdb, title=title)
        return
    ctx.db.set_request_id(trakt_id=trakt_id, list_id=list_id, request_id=request_id)
    ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
    ctx.db.add_activity("requested", f"requested {title}")
    log_action(
        _log,
        "requested",
        dry_run=False,
        tmdb=tmdb,
        title=title,
        request_id=request_id,
    )
