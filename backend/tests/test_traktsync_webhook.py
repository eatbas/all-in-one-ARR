"""Tests for modules.traktsync.webhook (remove on import)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.settings_store import TrackedList
from modules.traktsync.webhook import handle_arr, remove_tracked_item
from tests.conftest import StubSettingsStore, StubTrakt, make_ctx

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


async def test_radarr_import_removes_movie_by_tmdb(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    await handle_arr(ctx, {"eventType": "Download", "movie": {"tmdbId": 100}})
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_sonarr_import_removes_show_by_tvdb(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    await handle_arr(ctx, {"eventType": "Download", "series": {"tvdbId": 300}})
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="watchlist", owner_user="me"
    )


async def test_dry_run_logs_but_does_not_persist_removal(db) -> None:
    # The client honours DRY_RUN internally (logging the would-be removal). The
    # handler must NOT persist a 'removed' status in dry-run, otherwise the item
    # would never be removed for real once DRY_RUN is switched off.
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=True)
    await handle_arr(ctx, {"eventType": "Download", "movie": {"tmdbId": 100}})
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "would_remove" for a in db.recent_activity())


async def test_non_import_event_ignored(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    await handle_arr(ctx, {"eventType": "Test", "movie": {"tmdbId": 100}})
    trakt.remove_items.assert_not_awaited()


async def test_no_matching_item(db) -> None:
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    await handle_arr(ctx, {"eventType": "Download", "movie": {"tmdbId": 999}})
    trakt.remove_items.assert_not_awaited()


async def test_no_ids_in_payload(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    await handle_arr(ctx, {"eventType": "Download"})
    trakt.remove_items.assert_not_awaited()


async def test_already_removed_is_noop(db) -> None:
    seed(db)
    db.set_status(trakt_id=1, list_id="watchlist", status="removed")
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt)
    await handle_arr(ctx, {"eventType": "Download", "movie": {"tmdbId": 100}})
    trakt.remove_items.assert_not_awaited()


async def test_remove_tracked_item_helper(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    item = db.get_item(trakt_id=2, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="manual")
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="watchlist", owner_user="me"
    )
    assert any("manual" in a["detail"] for a in db.recent_activity())


async def test_import_removes_from_every_matching_list(db) -> None:
    # The same show is tracked in two lists; an import removes it from both,
    # each against its own list endpoint.
    for slug in ("tv", "anime"):
        db.upsert_item(
            trakt_id=2, type="show", title="Severance", year=2022,
            tmdb=200, tvdb=300, imdb="tt2", list_id=slug,
        )
    trakt = StubTrakt()
    store = StubSettingsStore(
        lists=[
            TrackedList(owner_user="me", slug="tv", name="TV"),
            TrackedList(owner_user="me", slug="anime", name="Anime"),
        ]
    )
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False, settings_store=store)
    await handle_arr(ctx, {"eventType": "Download", "series": {"tvdbId": 300}})
    assert db.get_item(trakt_id=2, list_id="tv")["status"] == "removed"
    assert db.get_item(trakt_id=2, list_id="anime")["status"] == "removed"
    removed_lists = {
        call.kwargs["list_id"] for call in trakt.remove_items.await_args_list
    }
    assert removed_lists == {"tv", "anime"}


async def test_import_skips_already_removed_list_entry(db) -> None:
    # One of two matching entries is already removed: the loop skips it and still
    # removes the other (covers the per-item 'already removed' branch).
    for slug in ("tv", "anime"):
        db.upsert_item(
            trakt_id=2, type="show", title="Severance", year=2022,
            tmdb=200, tvdb=300, imdb="tt2", list_id=slug,
        )
    db.set_status(trakt_id=2, list_id="tv", status="removed")
    trakt = StubTrakt()
    store = StubSettingsStore(
        lists=[
            TrackedList(owner_user="me", slug="tv", name="TV"),
            TrackedList(owner_user="me", slug="anime", name="Anime"),
        ]
    )
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False, settings_store=store)
    await handle_arr(ctx, {"eventType": "Download", "series": {"tvdbId": 300}})
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="anime", owner_user="me"
    )


async def test_import_dedupes_double_id_match(db) -> None:
    # A payload carrying both tmdb and tvdb for the same item must remove it once.
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    await handle_arr(
        ctx,
        {"eventType": "Download", "movie": {"tmdbId": 200}, "series": {"tvdbId": 300}},
    )
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="watchlist", owner_user="me"
    )


async def test_remove_failure_is_logged_and_item_left(db) -> None:
    seed(db)
    trakt = StubTrakt()
    trakt.remove_items = AsyncMock(side_effect=RuntimeError("not your list"))
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    item = db.get_item(trakt_id=2, list_id="watchlist")
    await remove_tracked_item(ctx, item, reason="manual")
    # The item is not marked removed, and the failure is recorded.
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "synced"
    assert any(a["action"] == "error" for a in db.recent_activity())


async def test_removal_skipped_for_list_owned_by_someone_else(db) -> None:
    # Trakt forbids removing from a list you do not own: skip without a request.
    db.upsert_item(
        trakt_id=2, type="show", title="Severance", year=2022,
        tmdb=200, tvdb=300, imdb="tt2", list_id="shared",
    )
    trakt = StubTrakt()
    store = StubSettingsStore(
        lists=[TrackedList(owner_user="sean", slug="shared", name="Shared")],
        user="me",
    )
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False, settings_store=store)
    item = db.get_item(trakt_id=2, list_id="shared")
    await remove_tracked_item(ctx, item, reason="imported")
    trakt.remove_items.assert_not_awaited()
    assert db.get_item(trakt_id=2, list_id="shared")["status"] == "synced"
    assert any(a["action"] == "remove_skipped" for a in db.recent_activity())


async def test_removal_proceeds_for_list_owned_by_connected_username(db) -> None:
    # A list owned by the connected account's real username (not the 'me' alias)
    # is still owned, so removal proceeds.
    db.upsert_item(
        trakt_id=2, type="show", title="Severance", year=2022,
        tmdb=200, tvdb=300, imdb="tt2", list_id="mine",
    )
    trakt = StubTrakt()
    store = StubSettingsStore(
        lists=[TrackedList(owner_user="erena", slug="mine", name="Mine")],
        user="erena",
    )
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False, settings_store=store)
    item = db.get_item(trakt_id=2, list_id="mine")
    await remove_tracked_item(ctx, item, reason="imported")
    trakt.remove_items.assert_awaited_once_with(
        shows=[300], list_id="mine", owner_user="erena"
    )
    assert db.get_item(trakt_id=2, list_id="mine")["status"] == "removed"
