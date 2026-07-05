"""The poll-and-request half of the sync loop (steps 1-2).

Reads the configured Trakt list, mirrors each item into SQLite (storing both
TMDB and TVDB ids for later reverse lookup), then ensures each not-yet-handled
item has a Seer request. When auto-remove is enabled, an item is dropped from the
Trakt list once Seer reports it **available** or **partially available** — never
the instant it is merely requested; pending/processing requests are left on the
list. Removal deletes both the Trakt entry and the Seer request (Radarr/Sonarr keep
any in-progress downloads).

After polling the lists, every item on a **successfully-polled** list that was not
seen in its read is re-checked against Seer (``refresh_tracked_statuses``) and its
stored status updated, so an item that has left a still-tracked list stops drifting
from Seer instead of keeping a frozen status forever. Items on an untracked list, or
on a list whose read failed, are left alone. The refresh updates status (and
auto-removes per the same rule) but never creates a new request.

An unreachable Seer trips a per-cycle latch (:class:`_SeerOutage`): the outage is
logged and recorded once, and every remaining Seer interaction in the same cycle is
skipped — each would otherwise pay the full connect timeout and add its own failure
entry. Item mirroring from Trakt still happens; statuses and requests simply catch
up on the next sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.seer import (
    AVAILABLE,
    PARTIALLY_AVAILABLE,
    PENDING,
    PROCESSING,
    SeerError,
    SeerUnavailableError,
)
from core.logging import get_logger, log_action
from modules.list_syncarr.removal import remove_tracked_item

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext
    from core.settings_store import TrackedList

_log = get_logger("list_syncarr.sync")

# Seer states that mean a request exists but nothing has downloaded yet: we leave
# these on the Trakt list (and never re-request). They are only removed once the
# item is at least partially available — an item is not dropped the instant it is
# requested.
_ALREADY_REQUESTED = frozenset({PENDING, PROCESSING})


class _SeerOutage:
    """Per-cycle latch that stops the sync from hammering an unreachable Seer.

    The first connection-level failure (:class:`SeerUnavailableError`) trips the
    latch: it is logged once and recorded once in the activity feed, and every
    remaining Seer interaction in the same cycle is skipped — each would otherwise
    pay the full connect timeout and add its own failure entry. Skipped items are
    simply retried on the next sync.
    """

    def __init__(self) -> None:
        self.down = False

    def trip(self, ctx: "AppContext", exc: SeerUnavailableError) -> None:
        """Latch the outage, recording it on the first trip only."""
        if self.down:
            return
        self.down = True
        _log.error("Seer unreachable; skipping remaining Seer calls this sync: %s", exc)
        ctx.db.add_activity(
            "Seer unreachable",
            "Could not connect to Seer; status checks and requests will be "
            "retried on the next sync.",
        )


async def poll_and_request(ctx: "AppContext") -> None:
    """Poll every selected Trakt list, request missing items, then refresh statuses.

    Each list is isolated: a failure reading or processing one list (e.g. an
    unauthorised or transient error) is logged and does not abort the others. After
    the lists are polled, items on a successfully-polled list that were not seen in
    its read are re-checked against Seer so their stored status cannot drift. An
    unreachable Seer trips the shared :class:`_SeerOutage` latch, which mutes every
    remaining Seer call for the rest of the cycle.
    """
    processed: set[tuple[str, int]] = set()
    polled_lists: set[str] = set()
    outage = _SeerOutage()
    for tracked in ctx.settings_store.tracked_lists():
        seen, ok = await _poll_one_list(ctx, tracked, outage)
        processed |= seen
        if ok:
            polled_lists.add(tracked.slug)
    await refresh_tracked_statuses(ctx, processed, polled_lists, outage)


async def _poll_one_list(
    ctx: "AppContext", tracked: "TrackedList", outage: _SeerOutage
) -> tuple[set[tuple[str, int]], bool]:
    """Poll a single Trakt list and request its missing items.

    Returns ``(seen, ok)`` where ``seen`` is the ``(list_id, trakt_id)`` keys read
    from the list (so the caller can skip them in the refresh pass) and ``ok`` is
    whether the read succeeded. A failed read returns ``(set(), False)`` so the
    refresh does not act on a list whose membership we could not confirm this cycle.
    """
    list_id = tracked.slug
    seen: set[tuple[str, int]] = set()
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
        return seen, False
    _log.info("polled Trakt list id=%s items=%d", list_id, len(items))

    for raw in items:
        trakt_id = raw.get("trakt_id")
        if trakt_id is None:
            _log.warning("skipping Trakt item without trakt id: %s", raw.get("title"))
            continue
        seen.add((list_id, trakt_id))
        try:
            await _process_item(ctx, raw, list_id, outage)
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
    return seen, True


async def _process_item(
    ctx: "AppContext", raw: dict, list_id: str, outage: _SeerOutage
) -> None:
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
    if outage.down:
        # Seer has been seen unreachable this cycle: status checks, requests and
        # removals (which delete the Seer request) all need Seer, so leave the
        # freshly-mirrored item as-is and let the next sync catch it up.
        return
    if item["status"] == "available":
        # Already known available (effectively terminal): retry the auto-remove but
        # deliberately do not re-check Seer — the refresh pass skips it too.
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
    except SeerUnavailableError as exc:
        outage.trip(ctx, exc)
        return
    except SeerError as exc:
        _log.error("Seer status check failed for %s: %s", title, exc)
        ctx.db.add_activity(
            "List sync failed",
            f'Could not check Seer status for "{title}".',
        )
        return

    if await _apply_seer_status(ctx, item, seer_status):
        # Seer already knows the item (available / partial / pending / processing);
        # its status was updated and removal applied — no new request to create.
        return

    try:
        request_id = await ctx.seer.create_request(
            media_type=seer_media_type, tmdb_id=tmdb
        )
    except SeerUnavailableError as exc:
        outage.trip(ctx, exc)
        return
    except SeerError as exc:
        _log.error("Seer request create failed for %s: %s", title, exc)
        ctx.db.add_activity(
            "List sync failed",
            f'Could not request "{title}" in Seer; it will be retried on the next sync.',
        )
        return
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


async def _apply_seer_status(
    ctx: "AppContext", item: dict, seer_status: int | None
) -> bool:
    """Update an item's stored status from a Seer status and auto-remove if due.

    Shared by the on-list poll (:func:`_process_item`) and the off-list refresh
    (:func:`refresh_tracked_statuses`). Returns ``True`` when Seer already knows the
    item (so the caller must not create a request) and ``False`` for an item Seer has
    no record of yet. Removal (available / partially available, when auto-remove is
    enabled) deletes the Trakt entry and the Seer request; media files are untouched,
    and a list not owned by ``me`` simply keeps the updated status.
    """
    trakt_id = item["trakt_id"]
    list_id = item["list_id"]
    tmdb = item["tmdb"]
    title = item["title"]

    if seer_status == AVAILABLE:
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="available")
        log_action(_log, "already_available", tmdb=tmdb, title=title)
        if ctx.settings_store.auto_remove_when_available():
            await remove_tracked_item(ctx, item, reason="available in Seer")
        return True

    if seer_status == PARTIALLY_AVAILABLE:
        # Part of the item is downloaded (e.g. some seasons of a show): treat it like
        # available for removal. Radarr/Sonarr keep any in-progress downloads.
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
        log_action(_log, "partially_available", tmdb=tmdb, title=title)
        if ctx.settings_store.auto_remove_when_available():
            await remove_tracked_item(ctx, item, reason="partially available in Seer")
        return True

    if seer_status in _ALREADY_REQUESTED:
        # A request exists but nothing has downloaded yet (pending/processing): record
        # the status and leave it on the list until it is at least partially available.
        ctx.db.set_status(trakt_id=trakt_id, list_id=list_id, status="requested")
        log_action(_log, "already_requested", tmdb=tmdb, title=title)
        return True

    return False


async def refresh_tracked_statuses(
    ctx: "AppContext",
    processed: set[tuple[str, int]],
    polled_lists: set[str],
    outage: _SeerOutage,
) -> None:
    """Re-check Seer for items on a polled list that were not seen in its read.

    Only items whose list was **successfully polled this cycle** are considered, so
    items on an untracked list, or on a list whose read failed, are left untouched
    (we cannot confirm their list membership). Items still on a list are handled by
    :func:`_process_item`; this pass catches those that have left a still-tracked
    list, so their stored status stops drifting from Seer. It updates the status (and
    auto-removes per the rule) but never creates a Seer request.

    Each item is isolated (mirroring :func:`_poll_one_list`): a failure on one item is
    logged and recorded, and the rest still refresh. The exception is an unreachable
    Seer, which trips the ``outage`` latch and ends the refresh — every remaining
    item would pay the same connect timeout for the same result. A latch already
    tripped during the poll skips the refresh entirely.
    """
    if outage.down:
        return
    for item in ctx.db.active_items():
        if item["list_id"] not in polled_lists:
            continue
        if (item["list_id"], item["trakt_id"]) in processed:
            continue
        if item["tmdb"] is None:
            continue
        title = item["title"] or "unknown item"
        try:
            seer_status = await ctx.seer.get_status(
                media_type="movie" if item["type"] == "movie" else "tv",
                tmdb_id=item["tmdb"],
            )
            await _apply_seer_status(ctx, item, seer_status)
        except SeerUnavailableError as exc:
            outage.trip(ctx, exc)
            return
        except Exception as exc:  # isolate per-item failures, mirroring the poll
            _log.exception("status refresh failed for %s: %s", title, exc)
            ctx.db.add_activity(
                "Status check failed",
                f'Could not refresh the Seer status for "{title}".',
            )
