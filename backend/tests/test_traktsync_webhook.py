"""Tests for modules.traktsync.webhook (remove on import)."""

from __future__ import annotations

from modules.traktsync.webhook import handle_arr, remove_tracked_item
from tests.conftest import StubTrakt, make_ctx

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
    trakt.remove_items.assert_awaited_once_with(movies=[100])


async def test_sonarr_import_removes_show_by_tvdb(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=False)
    await handle_arr(ctx, {"eventType": "Download", "series": {"tvdbId": 300}})
    assert db.get_item(trakt_id=2, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(shows=[300])


async def test_dry_run_logs_but_does_not_persist_removal(db) -> None:
    # The client honours DRY_RUN internally (logging the would-be removal). The
    # handler must NOT persist a 'removed' status in dry-run, otherwise the item
    # would never be removed for real once DRY_RUN is switched off.
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, dry_run=True)
    await handle_arr(ctx, {"eventType": "Download", "movie": {"tmdbId": 100}})
    trakt.remove_items.assert_awaited_once_with(movies=[100])
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
    trakt.remove_items.assert_awaited_once_with(shows=[300])
    assert any("manual" in a["detail"] for a in db.recent_activity())
