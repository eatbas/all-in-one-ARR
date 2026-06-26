"""Tests for modules.list_syncarr.removal (the shared Trakt removal primitive)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.settings_store import TrackedList
from modules.list_syncarr.removal import remove_tracked_item
from tests.conftest import StubSeer, StubSettingsStore, StubTrakt, make_ctx

_MOVIE = {
    "trakt_id": 1, "type": "movie", "title": "Dune", "year": 2021,
    "tmdb": 100, "tvdb": None, "imdb": "tt1", "list_id": "watchlist",
}
_SHOW = {
    "trakt_id": 2, "type": "show", "title": "Severance", "year": 2022,
    "tmdb": 200, "tvdb": 300, "imdb": "tt2", "list_id": "watchlist",
}


def seed(db) -> None:
    db.upsert_item(**{k: _MOVIE[k] for k in _MOVIE if k != "list_id"}, list_id="watchlist")
    db.upsert_item(**{k: _SHOW[k] for k in _SHOW if k != "list_id"}, list_id="watchlist")


async def test_removes_movie_by_tmdb(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="available in Seer")
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )
    ctx.seer.delete_request.assert_not_awaited()
    assert any(a["action"] == "Item removed from Trakt" for a in db.recent_activity())
    assert any('Removed "Dune" from the Trakt list.' in a["detail"] for a in db.recent_activity())


async def test_removes_known_seer_request_without_touching_arr_media(db) -> None:
    seed(db)
    db.set_request_id(trakt_id=1, list_id="watchlist", request_id=77)
    trakt = StubTrakt()
    seer = StubSeer()
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    item = db.get_item(trakt_id=1, list_id="watchlist")

    await remove_tracked_item(ctx, item, reason="manual")

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )
    seer.delete_request.assert_awaited_once_with(request_id=77)
    ctx.radarr.test_connection.assert_not_awaited()
    ctx.sonarr.test_connection.assert_not_awaited()
    assert any(a["action"] == "Seer request removed" for a in db.recent_activity())
    assert any('Removed the Seer request for "Dune".' in a["detail"] for a in db.recent_activity())


async def test_request_delete_failure_leaves_item_active(db) -> None:
    seed(db)
    db.set_request_id(trakt_id=1, list_id="watchlist", request_id=77)
    trakt = StubTrakt()
    seer = StubSeer()
    seer.delete_request = AsyncMock(side_effect=RuntimeError("delete failed"))
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)
    item = db.get_item(trakt_id=1, list_id="watchlist")

    await remove_tracked_item(ctx, item, reason="manual")

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )
    assert any(
        a["action"] == "Removal failed" and "Could not remove the Seer request" in a["detail"]
        for a in db.recent_activity()
    )
    assert not any("delete failed" in a["detail"] for a in db.recent_activity())


async def test_no_stored_request_id_still_removes_trakt_entry(db) -> None:
    # When this app did not create the request, there is no stored id and removal
    # must still delete the Trakt list entry without calling the Seer service.
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=1, list_id="watchlist")

    await remove_tracked_item(ctx, item, reason="available in Seer")

    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )
    ctx.seer.delete_request.assert_not_awaited()
    assert any(a["action"] == "Item removed from Trakt" for a in db.recent_activity())


async def test_removes_show_by_tvdb(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=2, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="manual")
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="watchlist", owner_user="me"
    )
    assert any(a["action"] == "Item removed from Trakt" for a in db.recent_activity())


async def test_skipped_when_show_has_no_tvdb_id(db) -> None:
    # Trakt removes shows by TVDB id; a show carrying no TVDB id is skipped-and-
    # recorded rather than sent as a malformed request.
    db.upsert_item(
        trakt_id=3, type="show", title="No TVDB", year=2020,
        tmdb=400, tvdb=None, imdb="tt3", list_id="watchlist",
    )
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=3, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="available in Seer")
    trakt.remove_items.assert_not_awaited()
    assert db.get_item(trakt_id=3, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "Removal skipped" for a in db.recent_activity())
    assert any("no TVDB id" in a["detail"] for a in db.recent_activity())


async def test_skipped_when_movie_has_no_tmdb_id(db) -> None:
    # Symmetric to the show case: Trakt removes movies by TMDB id, so a movie with no
    # TMDB id is skipped-and-recorded rather than sent as a malformed request.
    db.upsert_item(
        trakt_id=4, type="movie", title="No TMDB", year=2019,
        tmdb=None, tvdb=None, imdb="tt4", list_id="watchlist",
    )
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=4, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="manual")
    trakt.remove_items.assert_not_awaited()
    assert db.get_item(trakt_id=4, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "Removal skipped" for a in db.recent_activity())
    assert any("no TMDB id" in a["detail"] for a in db.recent_activity())


async def test_remove_failure_is_logged_and_item_left(db) -> None:
    seed(db)
    trakt = StubTrakt()
    trakt.remove_items = AsyncMock(side_effect=RuntimeError("not your list"))
    ctx = make_ctx(db=db, trakt=trakt)
    item = db.get_item(trakt_id=2, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="manual")
    # The item is not marked removed, and the failure is recorded.
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "Removal failed" for a in db.recent_activity())
    assert any("Could not remove" in a["detail"] for a in db.recent_activity())
    assert not any("not your list" in a["detail"] for a in db.recent_activity())


async def test_removal_skipped_for_list_not_owned_by_me(db) -> None:
    # Trakt forbids removing from a list you do not own, and the app always
    # operates as 'me', so any list whose stored owner is not 'me' (another
    # user's list added by URL) is skipped without a request.
    db.upsert_item(
        trakt_id=2, type="show", title="Severance", year=2022,
        tmdb=200, tvdb=300, imdb="tt2", list_id="shared",
    )
    trakt = StubTrakt()
    store = StubSettingsStore(
        lists=[TrackedList(owner_user="sean", slug="shared", name="Shared")],
    )
    ctx = make_ctx(db=db, trakt=trakt, settings_store=store)
    item = db.get_item(trakt_id=2, list_id="shared")
    await remove_tracked_item(ctx, item, reason="available in Seer")
    trakt.remove_items.assert_not_awaited()
    assert db.get_item(trakt_id=2, list_id="shared")["status"] == "synced"
    assert any(a["action"] == "Removal skipped" for a in db.recent_activity())
    assert any("sean" in a["detail"] for a in db.recent_activity())
