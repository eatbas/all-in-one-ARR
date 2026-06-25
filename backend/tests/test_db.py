"""Tests for core.db."""

from __future__ import annotations

import sqlite3

import pytest

from core.db import Database, rows_to_dicts, utcnow_iso

_MOVIE = dict(
    trakt_id=1, type="movie", title="Dune", year=2021, tmdb=438631,
    tvdb=None, imdb="tt1160419", list_id="watchlist",
)
_SHOW = dict(
    trakt_id=2, type="show", title="Severance", year=2022, tmdb=95396,
    tvdb=371980, imdb="tt11280740", list_id="watchlist",
)


def test_file_backed_db_creates_parent(tmp_path) -> None:
    path = tmp_path / "nested" / "aio.db"
    database = Database(str(path))
    database.init_db()
    assert path.exists()
    database.close()


def test_upsert_insert_and_update(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["status"] == "synced"
    assert item["title"] == "Dune"

    # Update preserves status/request id but refreshes descriptive fields.
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    db.set_request_id(trakt_id=1, list_id="watchlist", request_id=42)
    updated = {**_MOVIE, "title": "Dune: Part One"}
    db.upsert_item(**updated)
    item = db.get_item(trakt_id=1, list_id="watchlist")
    assert item["title"] == "Dune: Part One"
    assert item["status"] == "requested"
    assert item["seer_request_id"] == 42


def test_set_status_rejects_unknown(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    with pytest.raises(ValueError):
        db.set_status(trakt_id=1, list_id="watchlist", status="bogus")


def test_get_item_missing_returns_none(db: Database) -> None:
    assert db.get_item(trakt_id=999, list_id="watchlist") is None


def test_find_by_tmdb_and_tvdb(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**_SHOW)
    assert db.find_by_tmdb(438631)["trakt_id"] == 1
    assert db.find_by_tvdb(371980)["trakt_id"] == 2
    assert db.find_by_tmdb(0) is None
    assert db.find_by_tvdb(0) is None


def test_find_all_by_tmdb_and_tvdb_span_lists(db: Database) -> None:
    # The same title mirrored under two lists must surface both rows.
    db.upsert_item(**{**_SHOW, "list_id": "tv"})
    db.upsert_item(**{**_SHOW, "list_id": "anime"})
    by_tmdb = db.find_all_by_tmdb(95396)
    by_tvdb = db.find_all_by_tvdb(371980)
    assert {row["list_id"] for row in by_tmdb} == {"tv", "anime"}
    assert {row["list_id"] for row in by_tvdb} == {"tv", "anime"}
    assert db.find_all_by_tmdb(0) == []
    assert db.find_all_by_tvdb(0) == []


def test_counts_by_status_zero_filled(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**_SHOW)
    db.set_status(trakt_id=2, list_id="watchlist", status="removed")
    counts = db.counts_by_status()
    assert counts == {"synced": 1, "requested": 0, "available": 0, "removed": 1}


def test_list_items_filter_and_unfiltered(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**_SHOW)
    db.set_status(trakt_id=2, list_id="watchlist", status="removed")
    assert len(db.list_items()) == 2
    removed = db.list_items(status="removed")
    assert len(removed) == 1 and removed[0]["trakt_id"] == 2


def test_list_items_filter_by_list_and_combined(db: Database) -> None:
    db.upsert_item(**{**_MOVIE, "list_id": "movies"})
    db.upsert_item(**{**_SHOW, "list_id": "tv"})
    db.set_status(trakt_id=1, list_id="movies", status="requested")
    # Filter by list only.
    movies = db.list_items(list_id="movies")
    assert [row["trakt_id"] for row in movies] == [1]
    # Status and list compose.
    assert len(db.list_items(status="requested", list_id="movies")) == 1
    assert db.list_items(status="requested", list_id="tv") == []


def test_counts_by_list(db: Database) -> None:
    db.upsert_item(**{**_MOVIE, "list_id": "movies"})
    db.upsert_item(**{**_SHOW, "list_id": "movies"})
    db.upsert_item(**{**_SHOW, "trakt_id": 3, "list_id": "tv"})
    assert db.counts_by_list() == {"movies": 2, "tv": 1}


def test_removed_counts_by_list(db: Database) -> None:
    # "movies" keeps an active item; "tv" has only a removed one.
    db.upsert_item(**{**_MOVIE, "list_id": "movies"})
    db.upsert_item(**{**_SHOW, "list_id": "movies"})
    db.upsert_item(**{**_SHOW, "trakt_id": 3, "list_id": "tv"})
    db.set_status(trakt_id=2, list_id="movies", status="removed")
    db.set_status(trakt_id=3, list_id="tv", status="removed")
    # Only lists with removed items appear; fully-active lists are omitted.
    assert db.removed_counts_by_list() == {"movies": 1, "tv": 1}


def test_list_sync_state_touch_and_read(db: Database) -> None:
    assert db.list_last_synced() == {}
    db.touch_list_synced("movies")
    first = db.list_last_synced()
    assert "T" in first["movies"]
    # A second touch refreshes the timestamp in place (no duplicate row).
    db.touch_list_synced("movies")
    db.touch_list_synced("tv")
    states = db.list_last_synced()
    assert set(states) == {"movies", "tv"}


def test_active_items_excludes_removed(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**_SHOW)
    db.set_status(trakt_id=1, list_id="watchlist", status="removed")
    active = db.active_items()
    assert [i["trakt_id"] for i in active] == [2]


def test_activity_feed_newest_first(db: Database) -> None:
    db.add_activity("requested", "requested A")
    db.add_activity("removed", "removed B")
    feed = db.recent_activity(limit=10)
    assert feed[0]["detail"] == "removed B"
    assert len(feed) == 2


def test_rows_to_dicts_and_utcnow() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT 1 AS a, 2 AS b").fetchall()
    assert rows_to_dicts(rows) == [{"a": 1, "b": 2}]
    conn.close()
    assert "T" in utcnow_iso()
