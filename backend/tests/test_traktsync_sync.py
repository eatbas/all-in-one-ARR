"""Tests for modules.traktsync.sync (poll -> request)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.clients.jellyseerr import AVAILABLE, PENDING, JellyseerrError
from core.settings_store import TrackedList
from modules.traktsync.sync import poll_and_request
from tests.conftest import StubJellyseerr, StubSettingsStore, StubTrakt, make_ctx

_MOVIE = {
    "trakt_id": 1, "type": "movie", "title": "Dune", "year": 2021,
    "tmdb": 100, "tvdb": None, "imdb": "tt1",
}


async def test_new_item_creates_request(db) -> None:
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        jellyseerr=StubJellyseerr(status=None, request_id=77),
        dry_run=False,
    )
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "requested"
    assert item["jellyseerr_request_id"] == 77
    ctx.jellyseerr.create_request.assert_awaited_once()
    assert any(a["action"] == "requested" for a in db.recent_activity())


async def test_dry_run_does_not_persist_requested(db) -> None:
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(items=[_MOVIE]),
        jellyseerr=StubJellyseerr(status=None),
        dry_run=True,
    )
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    # Status must stay 'synced' so the real request happens once DRY_RUN is off.
    assert item["status"] == "synced"
    assert item["jellyseerr_request_id"] is None
    assert any(a["action"] == "would_request" for a in db.recent_activity())


async def test_item_without_trakt_id_skipped(db) -> None:
    raw = {**_MOVIE, "trakt_id": None}
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[raw]))
    await poll_and_request(ctx)
    assert db.list_items() == []


async def test_item_without_tmdb_skipped(db) -> None:
    raw = {**_MOVIE, "tmdb": None}
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[raw]), jellyseerr=StubJellyseerr())
    await poll_and_request(ctx)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "synced"
    ctx.jellyseerr.get_status.assert_not_awaited()
    assert any(a["action"] == "skipped" for a in db.recent_activity())


async def test_already_available_sets_available(db) -> None:
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[_MOVIE]),
        jellyseerr=StubJellyseerr(status=AVAILABLE),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "available"
    ctx.jellyseerr.create_request.assert_not_awaited()


async def test_already_requested_in_jellyseerr(db) -> None:
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[_MOVIE]),
        jellyseerr=StubJellyseerr(status=PENDING),
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    ctx.jellyseerr.create_request.assert_not_awaited()


async def test_terminal_status_skips_processing(db) -> None:
    db.upsert_item(**_MOVIE, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="removed")
    ctx = make_ctx(
        db=db, trakt=StubTrakt(items=[_MOVIE]), jellyseerr=StubJellyseerr()
    )
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    ctx.jellyseerr.get_status.assert_not_awaited()


async def test_jellyseerr_status_error_recorded(db) -> None:
    jelly = StubJellyseerr()
    jelly.get_status = AsyncMock(side_effect=JellyseerrError("boom"))
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]), jellyseerr=jelly)
    await poll_and_request(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "error" for a in db.recent_activity())


async def test_list_read_failure_recorded(db) -> None:
    trakt = StubTrakt(items=[])
    trakt.read_list_items = AsyncMock(side_effect=RuntimeError("not authorised"))
    ctx = make_ctx(db=db, trakt=trakt)
    await poll_and_request(ctx)  # must not raise
    assert any(
        a["action"] == "error" and "Trakt list read failed" in a["detail"]
        for a in db.recent_activity()
    )


async def test_per_item_exception_isolated(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(items=[_MOVIE]))

    def boom(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ctx.db, "upsert_item", boom)
    await poll_and_request(ctx)  # must not raise
    assert any(
        a["action"] == "error" and "sync failed" in a["detail"]
        for a in db.recent_activity()
    )


async def test_polls_each_selected_list(db) -> None:
    store = StubSettingsStore(
        lists=[
            TrackedList(owner_user="me", slug="movies", name="Movies"),
            TrackedList(owner_user="me", slug="anime", name="Anime"),
        ]
    )

    async def read(*, list_id, owner_user):
        return [{**_MOVIE, "trakt_id": 1 if list_id == "movies" else 2}]

    trakt = StubTrakt()
    trakt.read_list_items.side_effect = read
    ctx = make_ctx(
        db=db,
        trakt=trakt,
        jellyseerr=StubJellyseerr(status=AVAILABLE),
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
        ]
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
        jellyseerr=StubJellyseerr(status=AVAILABLE),
        settings_store=store,
    )
    await poll_and_request(ctx)
    # The anime list was still processed despite the movies list failing.
    assert db.get_item(trakt_id=2, list_id="anime")["status"] == "available"
    assert any(
        a["action"] == "error" and "Trakt list read failed for movies" in a["detail"]
        for a in db.recent_activity()
    )
