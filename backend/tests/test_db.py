"""Tests for core.db."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from core.db import Database, rows_to_dicts, utcnow_iso

_MOVIE = dict(
    trakt_id=1,
    type="movie",
    title="Dune",
    year=2021,
    tmdb=438631,
    tvdb=None,
    imdb="tt1160419",
    list_id="watchlist",
)
_SHOW = dict(
    trakt_id=2,
    type="show",
    title="Severance",
    year=2022,
    tmdb=95396,
    tvdb=371980,
    imdb="tt11280740",
    list_id="watchlist",
)


def test_file_backed_db_creates_parent(tmp_path) -> None:
    path = tmp_path / "nested" / "aio.db"
    database = Database(str(path))
    database.init_db()
    assert path.exists()
    database.close()


def test_init_db_migrates_legacy_jellyseerr_column(tmp_path) -> None:
    # A database created before the Jellyseerr->Seer rename has the old column
    # name and lacks seer_request_id; init_db must add the column and carry the
    # stored request id forward under the new name.
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(str(path))
    legacy.executescript(
        """
        CREATE TABLE items (
            trakt_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            year INTEGER,
            tmdb INTEGER,
            tvdb INTEGER,
            imdb TEXT,
            list_id TEXT NOT NULL,
            jellyseerr_request_id INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trakt_id, list_id)
        );
        """
    )
    legacy.execute(
        "INSERT INTO items (trakt_id, type, title, year, tmdb, tvdb, imdb, "
        "list_id, jellyseerr_request_id, status, created_at, updated_at) "
        "VALUES (1, 'movie', 'Dune', 2021, 438631, NULL, 'tt1160419', "
        "'watchlist', 77, 'requested', ?, ?)",
        (utcnow_iso(), utcnow_iso()),
    )
    legacy.commit()
    legacy.close()

    database = Database(str(path))
    database.init_db()
    columns = {
        row["name"]
        for row in database._conn.execute("PRAGMA table_info(items)").fetchall()
    }
    assert "seer_request_id" in columns
    # The legacy request id is carried forward under the new column name.
    item = database.get_item(trakt_id=1, list_id="watchlist")
    assert item["seer_request_id"] == 77
    # The migrated database is fully usable and the migration is idempotent.
    database.upsert_item(**_MOVIE)
    database.init_db()  # second run must be a harmless no-op
    assert database.get_item(trakt_id=1, list_id="watchlist")["seer_request_id"] == 77
    database.close()


def test_init_db_adds_seer_column_when_legacy_absent(tmp_path) -> None:
    # An even older database lacks both the new and the legacy request-id column;
    # init_db must add seer_request_id with nothing to carry forward.
    path = tmp_path / "older.db"
    older = sqlite3.connect(str(path))
    older.executescript(
        """
        CREATE TABLE items (
            trakt_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            title TEXT,
            year INTEGER,
            tmdb INTEGER,
            tvdb INTEGER,
            imdb TEXT,
            list_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (trakt_id, list_id)
        );
        """
    )
    older.execute(
        "INSERT INTO items (trakt_id, type, title, year, tmdb, tvdb, imdb, "
        "list_id, status, created_at, updated_at) "
        "VALUES (1, 'movie', 'Dune', 2021, 438631, NULL, 'tt1160419', "
        "'watchlist', 'synced', ?, ?)",
        (utcnow_iso(), utcnow_iso()),
    )
    older.commit()
    older.close()

    database = Database(str(path))
    database.init_db()
    item = database.get_item(trakt_id=1, list_id="watchlist")
    assert item["seer_request_id"] is None
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


def test_activity_retention_prunes_old_rows(db: Database) -> None:
    # Seed one old row and one recent row, then prune against a cutoff that keeps
    # only the recent entry.
    db._conn.execute(
        "INSERT INTO activity (ts, action, detail) VALUES (?, ?, ?)",
        ("2020-01-01T00:00:00+00:00", "old", "old entry"),
    )
    db._conn.execute(
        "INSERT INTO activity (ts, action, detail) VALUES (?, ?, ?)",
        ("2026-06-26T00:00:00+00:00", "recent", "recent entry"),
    )
    db._prune_activity("2026-01-01T00:00:00+00:00")
    feed = db.recent_activity(limit=10)
    assert [a["action"] for a in feed] == ["recent"]


def test_disk_size_bytes_returns_zero_for_memory_db(db: Database) -> None:
    assert db._path == ":memory:"
    assert db.disk_size_bytes() == 0


def test_disk_size_bytes_sums_db_and_wal_and_shm(tmp_path) -> None:
    path = tmp_path / "aio.db"
    database = Database(str(path))
    database.init_db()
    database.add_activity("test", "test entry")

    # WAL mode creates at least the main file; create the sidecars if absent so
    # the sum path is fully exercised.
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if not sidecar.exists():
            sidecar.write_bytes(b"x")

    expected = sum(
        Path(str(path) + suffix).stat().st_size for suffix in ("", "-wal", "-shm")
    )
    assert database.disk_size_bytes() == expected
    database.close()


def test_disk_size_bytes_tolerates_missing_wal_and_shm(tmp_path) -> None:
    path = tmp_path / "aio.db"
    database = Database(str(path))
    database.init_db()
    # Whatever files exist on disk, the helper must sum them without raising.
    expected = sum(
        Path(str(path) + suffix).stat().st_size
        for suffix in ("", "-wal", "-shm")
        if Path(str(path) + suffix).exists()
    )
    assert database.disk_size_bytes() == expected
    database.close()


def test_disk_size_bytes_handles_partial_sidecars(tmp_path, monkeypatch) -> None:
    path = tmp_path / "aio.db"
    database = Database(str(path))
    database.init_db()
    # Simulate a missing sidecar without trying to unlink a file that Windows
    # holds open: make os.path.getsize raise FileNotFoundError for the WAL file.
    original_getsize = os.path.getsize

    def _stub_getsize(file_path: str) -> int:
        if file_path.endswith("-wal"):
            raise FileNotFoundError(file_path)
        return original_getsize(file_path)

    monkeypatch.setattr(os.path, "getsize", _stub_getsize)
    # The helper should still sum the main DB plus any existing sidecars.
    expected = Path(path).stat().st_size
    if Path(str(path) + "-shm").exists():
        expected += Path(str(path) + "-shm").stat().st_size
    assert database.disk_size_bytes() == expected
    database.close()


def test_table_counts_returns_zero_for_empty_db(db: Database) -> None:
    assert db.table_counts() == {
        "items": 0,
        "activity": 0,
        "list_state": 0,
    }


def test_table_counts_reflects_inserted_rows(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**{**_SHOW, "list_id": "tv"})
    db.add_activity("sync", "synced lists")
    db.touch_list_synced("watchlist")
    db.touch_list_synced("tv")
    assert db.table_counts() == {
        "items": 2,
        "activity": 1,
        "list_state": 2,
    }


def test_clear_activity_removes_all_rows_and_returns_count(db: Database) -> None:
    db.add_activity("one", "first")
    db.add_activity("two", "second")
    removed = db.clear_activity()
    assert removed == 2
    assert db.table_counts()["activity"] == 0
    assert db.recent_activity(limit=10) == []


def test_clear_items_and_sync_state_removes_both_tables(db: Database) -> None:
    db.upsert_item(**_MOVIE)
    db.upsert_item(**{**_SHOW, "list_id": "tv"})
    db.touch_list_synced("watchlist")
    removed = db.clear_items_and_sync_state()
    assert removed == 3
    assert db.table_counts()["items"] == 0
    assert db.table_counts()["list_state"] == 0
    # The database remains usable after the clear.
    db.upsert_item(**_MOVIE)
    assert db.table_counts()["items"] == 1
