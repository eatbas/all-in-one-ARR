"""Tests for modules.traktsync.reconcile (nightly safety net)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.clients.jellyseerr import AVAILABLE, PENDING, JellyseerrError
from modules.traktsync.reconcile import reconcile
from tests.conftest import StubJellyseerr, StubTrakt, make_ctx

_MOVIE = {
    "trakt_id": 1, "type": "movie", "title": "Dune", "year": 2021,
    "tmdb": 100, "tvdb": None, "imdb": "tt1",
}


def seed(db, *, tmdb=100) -> None:
    db.upsert_item(**{**_MOVIE, "tmdb": tmdb}, list_id="watchlist")
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")


async def test_available_item_removed(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(
        db=db, trakt=trakt,
        jellyseerr=StubJellyseerr(status=AVAILABLE), dry_run=False,
    )
    await reconcile(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_unavailable_item_left_alone(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, jellyseerr=StubJellyseerr(status=PENDING))
    await reconcile(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    trakt.remove_items.assert_not_awaited()


async def test_item_without_tmdb_skipped(db) -> None:
    db.upsert_item(**{**_MOVIE, "tmdb": None}, list_id="watchlist")
    jelly = StubJellyseerr()
    ctx = make_ctx(db=db, jellyseerr=jelly)
    await reconcile(ctx)
    jelly.get_status.assert_not_awaited()


async def test_error_recorded(db) -> None:
    seed(db)
    jelly = StubJellyseerr()
    jelly.get_status = AsyncMock(side_effect=JellyseerrError("boom"))
    ctx = make_ctx(db=db, jellyseerr=jelly)
    await reconcile(ctx)
    assert any(a["action"] == "error" for a in db.recent_activity())
