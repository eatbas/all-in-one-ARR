"""Tests for modules.list_syncarr.reconcile (nightly safety net)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from core.clients.seer import AVAILABLE, PENDING, SeerError
from modules.list_syncarr.reconcile import reconcile
from tests.conftest import StubSeer, StubTrakt, make_ctx

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
        seer=StubSeer(status=AVAILABLE),
    )
    await reconcile(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "removed"
    trakt.remove_items.assert_awaited_once_with(
        movies=[100], list_id="watchlist", owner_user="me"
    )


async def test_unavailable_item_left_alone(db) -> None:
    seed(db)
    trakt = StubTrakt()
    ctx = make_ctx(db=db, trakt=trakt, seer=StubSeer(status=PENDING))
    await reconcile(ctx)
    assert db.get_item(trakt_id=1, list_id="watchlist")["status"] == "requested"
    trakt.remove_items.assert_not_awaited()


async def test_untracked_list_item_left_alone(db) -> None:
    # An active item whose list the user has untracked is not swept, even if Seer
    # reports it available — the manual sweep is scoped to currently-tracked lists.
    db.upsert_item(**{**_MOVIE, "trakt_id": 9}, list_id="oldlist")
    db.set_status(trakt_id=9, list_id="oldlist", status="requested")
    trakt = StubTrakt()
    seer = StubSeer(status=AVAILABLE)
    ctx = make_ctx(db=db, trakt=trakt, seer=seer)  # default tracks 'watchlist' only
    await reconcile(ctx)
    assert db.get_item(trakt_id=9, list_id="oldlist")["status"] == "requested"
    seer.get_status.assert_not_awaited()
    trakt.remove_items.assert_not_awaited()


async def test_item_without_tmdb_skipped(db) -> None:
    db.upsert_item(**{**_MOVIE, "tmdb": None}, list_id="watchlist")
    seer = StubSeer()
    ctx = make_ctx(db=db, seer=seer)
    await reconcile(ctx)
    seer.get_status.assert_not_awaited()


async def test_error_recorded(db) -> None:
    seed(db)
    seer = StubSeer()
    seer.get_status = AsyncMock(side_effect=SeerError("boom"))
    ctx = make_ctx(db=db, seer=seer)
    await reconcile(ctx)
    assert any(a["action"] == "Availability check failed" for a in db.recent_activity())
    assert any("Could not check availability" in a["detail"] for a in db.recent_activity())
    assert not any("boom" in a["detail"] for a in db.recent_activity())
