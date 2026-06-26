"""Tests for modules.list_syncarr.sync (poll -> request)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.clients.seer import AVAILABLE, PENDING, SeerError
from core.settings_store import TrackedList
from modules.list_syncarr.sync import poll_and_request
from tests.conftest import StubSeer, StubSettingsStore, StubTrakt, make_ctx

_MOVIE = {
    "trakt_id": 1, "type": "movie", "title": "Dune", "year": 2021,
    "tmdb": 100, "tvdb": None, "imdb": "tt1",
}


async def test_new_item_creates_request(db) -> None:
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        seer=StubSeer(status=None, request_id=77),    )
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "requested"
    assert item["seer_request_id"] == 77
    ctx.seer.create_request.assert_awaited_once()
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
        db=db, trakt=StubTrakt(items=[_MOVIE]),
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
        db=db, trakt=trakt,
        seer=StubSeer(status=AVAILABLE),    )
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
        db=db, trakt=trakt,
        seer=StubSeer(status=AVAILABLE),        settings_store=store,
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    trakt.remove_items.assert_not_awaited()


async def test_already_requested_in_seer(db) -> None:
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[_MOVIE]),
        seer=StubSeer(status=PENDING),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    ctx.seer.create_request.assert_not_awaited()


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
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    seer = StubSeer(status=PENDING)
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        seer=seer,
    )

    await poll_and_request(ctx)

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    seer.get_status.assert_awaited_once_with(media_type="movie", tmdb_id=100)
    seer.create_request.assert_not_awaited()


async def test_removed_status_skips_processing(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="removed")
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[_MOVIE]), seer=StubSeer()
    )
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
    assert any("Could not check Seer status" in a["detail"] for a in db.recent_activity())
    assert not any("boom" in a["detail"] for a in db.recent_activity())


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
        a["action"] == "List sync failed" and "Could not read the Trakt list" in a["detail"]
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
        a["action"] == "List sync failed" and "Could not read the Trakt list \"movies\"" in a["detail"]
        for a in db.recent_activity()
    )
    assert not any("not authorised" in a["detail"] for a in db.recent_activity())
