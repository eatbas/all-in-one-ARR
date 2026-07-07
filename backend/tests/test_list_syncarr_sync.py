"""Tests for modules.list_syncarr.sync (poll -> request)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.clients.seer import (
    AVAILABLE,
    PARTIALLY_AVAILABLE,
    PENDING,
    PROCESSING,
    SeerError,
    SeerUnavailableError,
)
from core.settings_store import TrackedList
from modules.list_syncarr.sync import _SeerOutage, poll_and_request
from tests.conftest import StubSeer, StubSettingsStore, StubTrakt, make_ctx

_MOVIE = {
    "trakt_id": 1,
    "type": "movie",
    "title": "Dune",
    "year": 2021,
    "tmdb": 100,
    "tvdb": None,
    "imdb": "tt1",
}


async def test_new_item_creates_request(db) -> None:
    # A new item is requested in Seer and stays 'requested' on the Trakt list — a
    # freshly-requested item is never removed instantly, even with auto-remove on
    # (StubSettingsStore default). It is only removed once it is at least partially
    # available on a later poll.
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=None, request_id=77),
    )
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "requested"
    assert item["seer_request_id"] == 77
    ctx.seer.create_request.assert_awaited_once()
    trakt.remove_items.assert_not_awaited()
    assert any(a["action"] == "Request created" for a in db.recent_activity())
    assert any('Requested "Dune" in Seer.' in a["detail"] for a in db.recent_activity())


async def test_item_without_trakt_id_skipped(db) -> None:
    raw = {**_MOVIE, "trakt_id": None}
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[raw]))
    await poll_and_request(ctx)
    assert db.list_items() == []


async def test_item_without_tmdb_skipped(db) -> None:
    raw = {**_MOVIE, "tmdb": None}
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[raw]), seer=StubSeer())
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "synced"
    ctx.seer.get_status.assert_not_awaited()
    assert any(a["action"] == "Item skipped" for a in db.recent_activity())
    assert any("no TMDB id" in a["detail"] for a in db.recent_activity())


async def test_already_available_sets_available(db) -> None:
    # auto-remove off so the item stays 'available'; the enabled path is covered
    # by test_available_auto_removed_when_enabled.
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        seer=StubSeer(status=AVAILABLE),
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    ctx.seer.create_request.assert_not_awaited()


async def test_available_auto_removed_when_enabled(db) -> None:
    # auto-remove enabled (StubSettingsStore default): an available item is
    # dropped from its Trakt list in the same pass and marked 'removed'.
    # Only the Trakt list entry is removed — no Radarr/Sonarr call is made.
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=AVAILABLE),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_available_kept_when_auto_remove_disabled(db) -> None:
    # auto-remove disabled: an available item is marked 'available' and left on
    # the Trakt list for manual removal.
    trakt = StubTrakt(items=[_MOVIE])
    store = StubSettingsStore(auto_remove_when_available=False)
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=AVAILABLE),
        settings_store=store,
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    trakt.remove_items.assert_not_awaited()


async def test_already_requested_in_seer_kept_on_list(db) -> None:
    # Seer already has a pending/processing request but nothing has downloaded yet:
    # no duplicate request and — even with auto-remove on (default) — the item is
    # NOT removed; it stays 'requested' on the Trakt list until it is at least
    # partially available.
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(db=db, trakt=trakt, seer=StubSeer(status=PENDING))
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    ctx.seer.create_request.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_partially_available_removed_when_enabled(db) -> None:
    # PARTIALLY_AVAILABLE (status 4): with auto-remove on it is removed from Trakt
    # like an available item, and its Seer request is deleted too — looked up from
    # Seer here since this app stored no request id.
    trakt = StubTrakt(items=[_MOVIE])
    seer = StubSeer(status=PARTIALLY_AVAILABLE, request_ids=[55])
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    seer.create_request.assert_not_awaited()
    seer.get_request_ids.assert_awaited_once_with(media_type="movie", tmdb_id=100)
    seer.delete_request.assert_awaited_once_with(request_id=55)
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_partially_available_kept_when_disabled(db) -> None:
    # auto-remove off: a partially-available item stays 'requested' on the Trakt list.
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=PARTIALLY_AVAILABLE),
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    trakt.remove_items.assert_not_awaited()


async def test_requested_item_rechecked_and_auto_removed_when_available(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_request_id(trakt_id=1, list_id="watchlist", request_id=77)
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    trakt = StubTrakt(items=[_MOVIE])
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)

    await poll_and_request(ctx)

    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "removed"
    seer.get_status.assert_awaited_once_with(media_type="movie", tmdb_id=100)
    seer.create_request.assert_not_awaited()
    seer.delete_request.assert_awaited_once_with(request_id=77)
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_requested_item_rechecked_without_duplicate_request(db) -> None:
    # A previously-requested item still only pending in Seer is re-checked without a
    # duplicate request and stays 'requested' — it is not removed until it is at
    # least partially available.
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    seer = StubSeer(status=PENDING)
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)

    await poll_and_request(ctx)

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    seer.get_status.assert_awaited_once_with(media_type="movie", tmdb_id=100)
    seer.create_request.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_removed_status_skips_processing(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="removed")
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), seer=StubSeer())
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    ctx.seer.get_status.assert_not_awaited()


async def test_available_status_skips_processing_when_auto_remove_disabled(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="available")
    trakt = StubTrakt(items=[_MOVIE])
    seer = StubSeer()
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=seer,
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )

    await poll_and_request(ctx)

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    seer.get_status.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_available_status_retries_auto_remove_when_enabled(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="available")
    trakt = StubTrakt(items=[_MOVIE])
    seer = StubSeer()
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)

    await poll_and_request(ctx)

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    seer.get_status.assert_not_awaited()
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_seer_status_error_recorded(db) -> None:
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerError("boom"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "List sync failed" for a in db.recent_activity())
    assert any(
        "Could not check Seer status" in a["detail"] for a in db.recent_activity()
    )
    assert not any("boom" in a["detail"] for a in db.recent_activity())


async def test_seer_outage_short_circuits_poll(db) -> None:
    # Two on-list items and an unreachable Seer: the first connection-level failure
    # trips the outage latch, so the second item is never checked, no request is
    # attempted, and exactly one outage entry is recorded (no per-item spam). Both
    # items are still mirrored into SQLite and simply retried next cycle.
    items = [_MOVIE, {**_MOVIE, "trakt_id": 2, "title": "Arrival", "tmdb": 200}]
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerUnavailableError("connect failed"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=items), seer=seer)
    await poll_and_request(ctx)
    assert seer.get_status.await_count == 1
    seer.create_request.assert_not_awaited()
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "synced"
    outage_entries = [
        a for a in db.recent_activity() if a["action"] == "Seer unreachable"
    ]
    assert len(outage_entries) == 1
    assert not any("connect failed" in a["detail"] for a in db.recent_activity())
    assert not any(a["action"] == "List sync failed" for a in db.recent_activity())


async def test_seer_outage_latch_records_first_trip_only(db) -> None:
    # The latch itself is idempotent: a second trip (defensive — callers gate on
    # .down before calling Seer) must not add a duplicate activity entry.
    ctx = make_ctx(db=db)
    outage = _SeerOutage()
    outage.trip(ctx, SeerUnavailableError("down"))
    outage.trip(ctx, SeerUnavailableError("still down"))
    assert outage.down is True
    assert (
        len([a for a in db.recent_activity() if a["action"] == "Seer unreachable"]) == 1
    )


async def test_seer_outage_during_request_creation_trips_latch(db) -> None:
    # Seer dies between the status check and the request create: the create failure
    # trips the latch (one outage entry, no per-item "Could not request" entry).
    seer = StubSeer(status=None)
    seer.create_request = AsyncMock(side_effect=SeerUnavailableError("connect failed"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "Seer unreachable" for a in db.recent_activity())
    assert not any(a["action"] == "List sync failed" for a in db.recent_activity())


async def test_seer_outage_skips_available_retry_removal(db) -> None:
    # Removal needs Seer (the request delete): once the latch is tripped by an
    # earlier item, the auto-remove retry for an already-available item is skipped
    # too, so Trakt is not left half-removed while the Seer request lingers.
    second = {**_MOVIE, "trakt_id": 2, "title": "Arrival", "tmdb": 200}
    db.upsert_item(**second, list_id="watchlist")
    db.set_status(trakt_id=2, list_id="watchlist", status="available")
    trakt = StubTrakt(items=[_MOVIE, second])
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerUnavailableError("down"))
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    trakt.remove_items.assert_not_awaited()
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "available"


async def test_seer_request_error_recorded(db) -> None:
    seer = StubSeer(status=None)
    seer.create_request = AsyncMock(side_effect=SeerError("returned 500"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "List sync failed" for a in db.recent_activity())
    assert any("Could not request" in a["detail"] for a in db.recent_activity())
    assert not any("returned 500" in a["detail"] for a in db.recent_activity())


async def test_list_read_failure_recorded(db) -> None:
    trakt = StubTrakt(items=[])
    trakt.read_list_items = AsyncMock(side_effect=RuntimeError("not authorised"))
    ctx = make_ctx(db=db, trakt=trakt)
    await poll_and_request(ctx)  # must not raise
    assert any(
        a["action"] == "List sync failed"
        and "Could not read the Trakt list" in a["detail"]
        for a in db.recent_activity()
    )
    assert not any("not authorised" in a["detail"] for a in db.recent_activity())


async def test_per_item_exception_isolated(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]))

    def boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ctx.db, "upsert_item", boom)
    await poll_and_request(ctx)  # must not raise
    assert any(
        a["action"] == "List sync failed" and "Could not process" in a["detail"]
        for a in db.recent_activity()
    )
    assert not any("db down" in a["detail"] for a in db.recent_activity())


async def test_successful_poll_records_last_synced(db) -> None:
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        seer=StubSeer(status=AVAILABLE),
    )
    await poll_and_request(ctx)
    assert "watchlist" in db.list_last_synced()


async def test_failed_list_read_not_recorded(db) -> None:
    trakt = StubTrakt(items=[])
    trakt.read_list_items = AsyncMock(side_effect=RuntimeError("not authorised"))
    ctx = make_ctx(db=db, trakt=trakt)
    await poll_and_request(ctx)
    # A list whose read failed must not be marked as synced.
    assert db.list_last_synced() == {}


async def test_polls_each_selected_list(db) -> None:
    store = StubSettingsStore(
        lists=[
            TrackedList(owner_user="me", slug="movies", name="Movies"),
            TrackedList(owner_user="me", slug="anime", name="Anime"),
        ],
        auto_remove_when_available=False,
    )

    async def read(*, list_id, owner_user):
        return [{**_MOVIE, "trakt_id": 1 if list_id == "movies" else 2}]

    trakt = StubTrakt()
    trakt.read_list_items.side_effect = read
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=AVAILABLE),
        settings_store=store,
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="movies")["status"] == "available"
    assert db.get_item(trakt_id=2, list_id="anime")["status"] == "available"
    assert trakt.read_list_items.await_count == 2


async def test_one_failing_list_does_not_abort_others(db) -> None:
    store = StubSettingsStore(
        lists=[
            TrackedList(owner_user="me", slug="movies", name="Movies"),
            TrackedList(owner_user="me", slug="anime", name="Anime"),
        ],
        auto_remove_when_available=False,
    )

    async def read(*, list_id, owner_user):
        if list_id == "movies":
            raise RuntimeError("not authorised")
        return [{**_MOVIE, "trakt_id": 2}]

    trakt = StubTrakt()
    trakt.read_list_items.side_effect = read
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=StubSeer(status=AVAILABLE),
        settings_store=store,
    )
    await poll_and_request(ctx)
    # The anime list was still processed despite the movies list failing.
    assert db.get_item(trakt_id=2, list_id="anime")["status"] == "available"
    assert any(
        a["action"] == "List sync failed"
        and 'Could not read the Trakt list "movies"' in a["detail"]
        for a in db.recent_activity()
    )
    assert not any("not authorised" in a["detail"] for a in db.recent_activity())


# ---- status refresh for tracked items no longer on the Trakt list ----


def _seed_offlist(db, *, status="requested", tmdb=100, type="movie", tvdb=None) -> None:
    """Seed an active item that is NOT returned by the Trakt read (it has left the list)."""
    db.upsert_item(
        trakt_id=1,
        type=type,
        title="Dune",
        year=2021,
        tmdb=tmdb,
        tvdb=tvdb,
        imdb="tt1",
        list_id="watchlist",
    )
    db.set_status(trakt_id=1, list_id="watchlist", status=status)


async def test_refresh_updates_offlist_available_item(db) -> None:
    # An item no longer on the Trakt list is still re-checked against Seer; with
    # auto-remove off it is relabelled 'available' rather than left stale.
    _seed_offlist(db)
    trakt = StubTrakt(items=[])  # the item is gone from the list read
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=seer,
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    seer.get_status.assert_awaited_once_with(media_type="movie", tmdb_id=100)
    seer.create_request.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_refresh_removes_offlist_partial_when_enabled(db) -> None:
    # auto-remove on: an off-list partially-available item is removed and its Seer
    # request (looked up, since none was stored) is deleted.
    _seed_offlist(db)
    trakt = StubTrakt(items=[])
    seer = StubSeer(status=PARTIALLY_AVAILABLE, request_ids=[55])
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    seer.delete_request.assert_awaited_once_with(request_id=55)
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_refresh_skips_items_already_polled(db) -> None:
    # An item still on the Trakt list is handled by the poll; the refresh must not
    # re-query Seer for it, so get_status is awaited exactly once.
    trakt = StubTrakt(items=[_MOVIE])
    seer = StubSeer(status=PENDING)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    assert seer.get_status.await_count == 1


async def test_refresh_skips_offlist_item_without_tmdb(db) -> None:
    _seed_offlist(db, tmdb=None)
    trakt = StubTrakt(items=[])
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    seer.get_status.assert_not_awaited()


async def test_refresh_records_seer_error(db) -> None:
    # A Seer error during the refresh is recorded (so the stuck item is visible) and
    # the item is left unchanged rather than silently frozen without a trace.
    _seed_offlist(db)
    trakt = StubTrakt(items=[])
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerError("boom"))
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    assert any(a["action"] == "Status check failed" for a in db.recent_activity())
    assert not any("boom" in a["detail"] for a in db.recent_activity())


async def test_refresh_stops_at_first_seer_outage(db) -> None:
    # Two off-list items and an unreachable Seer: the first connection-level failure
    # ends the refresh (one status call, one outage entry) instead of paying the
    # connect timeout — and adding a traceback plus an activity row — per item.
    _seed_offlist(db)
    db.upsert_item(
        trakt_id=2,
        type="movie",
        title="Arrival",
        year=2016,
        tmdb=200,
        tvdb=None,
        imdb="tt2",
        list_id="watchlist",
    )
    db.set_status(trakt_id=2, list_id="watchlist", status="requested")
    trakt = StubTrakt(items=[])
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerUnavailableError("down"))
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert seer.get_status.await_count == 1
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "requested"
    outage_entries = [
        a for a in db.recent_activity() if a["action"] == "Seer unreachable"
    ]
    assert len(outage_entries) == 1
    assert not any(a["action"] == "Status check failed" for a in db.recent_activity())


async def test_refresh_skipped_when_outage_tripped_during_poll(db) -> None:
    # The latch tripped while polling the list also mutes the off-list refresh: the
    # single failed check for the on-list item is the only Seer call of the cycle.
    db.upsert_item(
        trakt_id=2,
        type="movie",
        title="Arrival",
        year=2016,
        tmdb=200,
        tvdb=None,
        imdb="tt2",
        list_id="watchlist",
    )
    db.set_status(trakt_id=2, list_id="watchlist", status="requested")
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerUnavailableError("down"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), seer=seer)
    await poll_and_request(ctx)
    assert seer.get_status.await_count == 1
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "requested"
    assert (
        len([a for a in db.recent_activity() if a["action"] == "Seer unreachable"]) == 1
    )


async def test_refresh_leaves_unknown_offlist_item_unchanged(db) -> None:
    # Seer has no record of the off-list item (None): the refresh neither re-requests
    # it nor changes its stored status.
    _seed_offlist(db)
    trakt = StubTrakt(items=[])
    seer = StubSeer(status=None)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    seer.create_request.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_refresh_skips_untracked_list_items(db) -> None:
    # An active item whose list is no longer tracked must NOT be re-checked or removed
    # by the refresh, even if Seer would report it available — only successfully-polled
    # lists are refreshed.
    db.upsert_item(
        trakt_id=9,
        type="movie",
        title="Orphan",
        year=2020,
        tmdb=999,
        tvdb=None,
        imdb="tt9",
        list_id="oldlist",
    )
    db.set_status(trakt_id=9, list_id="oldlist", status="requested")
    trakt = StubTrakt(items=[])  # only the tracked 'watchlist' is polled
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=9, list_id="oldlist")["status"] == "requested"
    seer.get_status.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_refresh_skips_items_when_list_read_failed(db) -> None:
    # If a tracked list's read fails, its membership is unknown this cycle, so its
    # items are not refreshed (and certainly not removed).
    _seed_offlist(db)
    trakt = StubTrakt()
    trakt.read_list_items = AsyncMock(side_effect=RuntimeError("not authorised"))
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    seer.get_status.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_refresh_processes_offlist_while_skipping_onlist(db) -> None:
    # One item is still on the Trakt list (handled by the poll, must be skipped by the
    # refresh) and another has left it (must be refreshed). Distinct tmdb ids prove the
    # loop both skips the processed item AND processes the off-list one.
    db.upsert_item(
        trakt_id=2,
        type="movie",
        title="Arrival",
        year=2016,
        tmdb=200,
        tvdb=None,
        imdb="tt2",
        list_id="watchlist",
    )
    db.set_status(trakt_id=2, list_id="watchlist", status="requested")

    async def status(*, media_type, tmdb_id):
        return PENDING if tmdb_id == 100 else AVAILABLE

    trakt = StubTrakt(items=[{**_MOVIE, "trakt_id": 1, "tmdb": 100}])
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=status)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    # On-list item: handled by the poll (PENDING -> requested), not re-queried.
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    # Off-list item: refreshed (AVAILABLE -> removed under auto-remove on).
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[200], list_id="watchlist", owner_user="me"
    )
    # Exactly two status checks: the poll for item 1 and the refresh for item 2 — the
    # on-list item is NOT re-queried by the refresh.
    assert seer.get_status.await_count == 2


async def test_refresh_removes_offlist_show_when_enabled(db) -> None:
    # The refresh -> auto-remove path for a SHOW: status checked as media_type='tv',
    # removed from Trakt by TVDB id.
    db.upsert_item(
        trakt_id=3,
        type="show",
        title="Severance",
        year=2022,
        tmdb=300,
        tvdb=400,
        imdb="tt3",
        list_id="watchlist",
    )
    db.set_status(trakt_id=3, list_id="watchlist", status="requested")
    trakt = StubTrakt(items=[])
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=3, list_id="watchlist")["status"] == "removed"
    seer.get_status.assert_awaited_once_with(media_type="tv", tmdb_id=300)
    trakt.remove_items.assert_awaited_once_with(
        shows=[400], list_id="watchlist", owner_user="me"
    )


async def test_refresh_isolates_item_failure(db) -> None:
    # A failure on one off-list item (a non-Seer error here) is recorded and the next
    # item is still refreshed — the refresh isolates per-item failures like the poll.
    db.upsert_item(
        trakt_id=1,
        type="movie",
        title="Boom",
        year=2020,
        tmdb=100,
        tvdb=None,
        imdb="tt1",
        list_id="watchlist",
    )
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    db.upsert_item(
        trakt_id=2,
        type="movie",
        title="Fine",
        year=2020,
        tmdb=200,
        tvdb=None,
        imdb="tt2",
        list_id="watchlist",
    )
    db.set_status(trakt_id=2, list_id="watchlist", status="requested")

    async def status(*, media_type, tmdb_id):
        if tmdb_id == 100:
            raise RuntimeError("kaboom")
        return AVAILABLE

    trakt = StubTrakt(items=[])
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=status)
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        seer=seer,
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    assert any(a["action"] == "Status check failed" for a in db.recent_activity())
    assert not any("kaboom" in a["detail"] for a in db.recent_activity())
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "available"


async def test_processing_in_seer_kept_on_list(db) -> None:
    # PROCESSING (3) is treated like PENDING (both in _ALREADY_REQUESTED): status
    # 'requested', no duplicate request, not removed.
    trakt = StubTrakt(items=[_MOVIE])
    ctx = make_ctx(db=db, trakt=trakt, seer=StubSeer(status=PROCESSING))
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    ctx.seer.create_request.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()
