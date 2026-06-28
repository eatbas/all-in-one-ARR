"""SQLite persistence layer.

A single :class:`Database` instance is held on the shared :class:`AppContext`.
Writes are guarded by a process-level lock; the connection runs in WAL mode so
the scheduler thread and the request handlers can share it safely within one
Uvicorn worker. Multi-worker deployment is explicitly out of scope.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

# Activity rows are kept for this many days; the absolute maximum is 30 days.
ACTIVITY_RETENTION_DAYS = 15

# The lifecycle states an item moves through.
ITEM_STATUSES = ("synced", "requested", "available", "removed")


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin, thread-safe wrapper around a SQLite connection."""

    def __init__(self, path: str) -> None:
        self._path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def init_db(self) -> None:
        """Create tables and indexes if they do not already exist.

        Also applies lightweight, idempotent column migrations so a database
        created by an earlier release is brought up to the current schema
        (``CREATE TABLE IF NOT EXISTS`` never alters an existing table).
        """
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS items (
                    trakt_id INTEGER NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('movie','show')),
                    title TEXT,
                    year INTEGER,
                    tmdb INTEGER,
                    tvdb INTEGER,
                    imdb TEXT,
                    list_id TEXT NOT NULL,
                    seer_request_id INTEGER,
                    status TEXT NOT NULL
                        CHECK(status IN ('synced','requested','available','removed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (trakt_id, list_id)
                );
                CREATE INDEX IF NOT EXISTS idx_items_tmdb ON items(tmdb);
                CREATE INDEX IF NOT EXISTS idx_items_tvdb ON items(tvdb);
                CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);

                CREATE TABLE IF NOT EXISTS activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(ts);

                CREATE TABLE IF NOT EXISTS list_state (
                    list_id TEXT PRIMARY KEY,
                    last_synced_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findarr_processed (
                    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
                    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade')),
                    item_id TEXT NOT NULL,
                    title TEXT,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (app, mode, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_findarr_processed_at
                    ON findarr_processed(processed_at);

                CREATE TABLE IF NOT EXISTS findarr_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    app TEXT NOT NULL CHECK(app IN ('sonarr','radarr')),
                    mode TEXT NOT NULL CHECK(mode IN ('missing','upgrade','system')),
                    item_id TEXT,
                    title TEXT,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_findarr_history_ts
                    ON findarr_history(ts);
                CREATE INDEX IF NOT EXISTS idx_findarr_history_app
                    ON findarr_history(app);

                CREATE TABLE IF NOT EXISTS findarr_run_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._migrate_items_columns()
            self._conn.commit()

    def _migrate_items_columns(self) -> None:
        """Backfill columns added or renamed after the items table was created.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a
        database created before the Jellyseerr->Seer rename still carries
        ``jellyseerr_request_id`` and lacks ``seer_request_id``. This adds the new
        column when absent and carries forward any request ids tracked under the
        old name. It is additive and idempotent: on a fresh or already-migrated
        database the column is present and this is a no-op.
        """
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(items)").fetchall()
        }
        if "seer_request_id" not in columns:
            self._conn.execute("ALTER TABLE items ADD COLUMN seer_request_id INTEGER")
            if "jellyseerr_request_id" in columns:
                # Carry forward request ids tracked under the pre-rename name.
                self._conn.execute(
                    "UPDATE items SET seer_request_id = jellyseerr_request_id"
                )

    # ---- items ----

    def upsert_item(
        self,
        *,
        trakt_id: int,
        type: str,
        title: str | None,
        year: int | None,
        tmdb: int | None,
        tvdb: int | None,
        imdb: str | None,
        list_id: str,
    ) -> None:
        """Insert a new item (status ``synced``) or refresh an existing one.

        Existing ``status`` and ``seer_request_id`` are preserved on
        update; only the descriptive fields and ``updated_at`` change.
        """
        now = utcnow_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO items (
                    trakt_id, type, title, year, tmdb, tvdb, imdb, list_id,
                    seer_request_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'synced', ?, ?)
                ON CONFLICT(trakt_id, list_id) DO UPDATE SET
                    type=excluded.type,
                    title=excluded.title,
                    year=excluded.year,
                    tmdb=excluded.tmdb,
                    tvdb=excluded.tvdb,
                    imdb=excluded.imdb,
                    updated_at=excluded.updated_at
                """,
                (trakt_id, type, title, year, tmdb, tvdb, imdb, list_id, now, now),
            )
            self._conn.commit()

    def set_status(self, *, trakt_id: int, list_id: str, status: str) -> None:
        """Update an item's lifecycle status."""
        if status not in ITEM_STATUSES:
            raise ValueError(f"Unknown status: {status}")
        with self._lock:
            self._conn.execute(
                "UPDATE items SET status=?, updated_at=? "
                "WHERE trakt_id=? AND list_id=?",
                (status, utcnow_iso(), trakt_id, list_id),
            )
            self._conn.commit()

    def set_request_id(
        self, *, trakt_id: int, list_id: str, request_id: int | None
    ) -> None:
        """Store the Seer request id for an item."""
        with self._lock:
            self._conn.execute(
                "UPDATE items SET seer_request_id=?, updated_at=? "
                "WHERE trakt_id=? AND list_id=?",
                (request_id, utcnow_iso(), trakt_id, list_id),
            )
            self._conn.commit()

    def get_item(self, *, trakt_id: int, list_id: str) -> dict[str, Any] | None:
        """Return a single item by its composite key, or ``None``."""
        row = self._conn.execute(
            "SELECT * FROM items WHERE trakt_id=? AND list_id=?",
            (trakt_id, list_id),
        ).fetchone()
        return dict(row) if row else None

    def find_by_tmdb(self, tmdb: int) -> dict[str, Any] | None:
        """Return the most recently updated item matching a TMDB id."""
        row = self._conn.execute(
            "SELECT * FROM items WHERE tmdb=? ORDER BY updated_at DESC LIMIT 1",
            (tmdb,),
        ).fetchone()
        return dict(row) if row else None

    def find_by_tvdb(self, tvdb: int) -> dict[str, Any] | None:
        """Return the most recently updated item matching a TVDB id."""
        row = self._conn.execute(
            "SELECT * FROM items WHERE tvdb=? ORDER BY updated_at DESC LIMIT 1",
            (tvdb,),
        ).fetchone()
        return dict(row) if row else None

    def find_all_by_tmdb(self, tmdb: int) -> list[dict[str, Any]]:
        """Return every item matching a TMDB id (across all lists), newest first."""
        rows = self._conn.execute(
            "SELECT * FROM items WHERE tmdb=? ORDER BY updated_at DESC", (tmdb,)
        ).fetchall()
        return [dict(row) for row in rows]

    def find_all_by_tvdb(self, tvdb: int) -> list[dict[str, Any]]:
        """Return every item matching a TVDB id (across all lists), newest first."""
        rows = self._conn.execute(
            "SELECT * FROM items WHERE tvdb=? ORDER BY updated_at DESC", (tvdb,)
        ).fetchall()
        return [dict(row) for row in rows]

    def counts_by_status(self) -> dict[str, int]:
        """Return a count of items per status (all statuses present, zero-filled)."""
        counts = {status: 0 for status in ITEM_STATUSES}
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM items GROUP BY status"
        ).fetchall()
        for row in rows:
            counts[row["status"]] = row["n"]
        return counts

    def list_items(
        self, *, status: str | None = None, list_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return items, optionally filtered by status and/or list, newest first.

        The ``status`` and ``list_id`` filters compose: passing both narrows to
        items in that list with that status.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status=?")
            params.append(status)
        if list_id is not None:
            clauses.append("list_id=?")
            params.append(list_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM items{where} ORDER BY updated_at DESC", params
        ).fetchall()
        return [dict(row) for row in rows]

    def counts_by_list(self) -> dict[str, int]:
        """Return a count of items per ``list_id`` (empty for lists with none)."""
        rows = self._conn.execute(
            "SELECT list_id, COUNT(*) AS n FROM items GROUP BY list_id"
        ).fetchall()
        return {row["list_id"]: row["n"] for row in rows}

    def removed_counts_by_list(self) -> dict[str, int]:
        """Return a count of ``removed`` items per ``list_id``.

        Only lists with at least one removed item appear; the per-list total from
        ``counts_by_list`` minus this value gives the active (non-removed) count.
        """
        rows = self._conn.execute(
            "SELECT list_id, COUNT(*) AS n FROM items "
            "WHERE status='removed' GROUP BY list_id"
        ).fetchall()
        return {row["list_id"]: row["n"] for row in rows}

    def active_items(self) -> list[dict[str, Any]]:
        """Return items that have not yet been removed (for reconciliation)."""
        rows = self._conn.execute(
            "SELECT * FROM items WHERE status != 'removed' ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- activity ----

    def add_activity(self, action: str, detail: str) -> None:
        """Append an entry to the activity feed and prune stale rows."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO activity (ts, action, detail) VALUES (?, ?, ?)",
                (utcnow_iso(), action, detail),
            )
            self._prune_activity(
                (datetime.now(timezone.utc) - timedelta(days=ACTIVITY_RETENTION_DAYS)).isoformat()
            )
            self._conn.commit()

    def _prune_activity(self, cutoff_iso: str) -> None:
        """Remove activity rows older than ``cutoff_iso``.

        This is split out as a narrow seam so tests can prune deterministically
        without waiting for real time to pass.
        """
        self._conn.execute(
            "DELETE FROM activity WHERE ts < ?",
            (cutoff_iso,),
        )

    def recent_activity(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent activity entries, newest first."""
        rows = self._conn.execute(
            "SELECT id, ts, action, detail FROM activity "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ---- list sync state ----

    def touch_list_synced(self, list_id: str) -> None:
        """Record that a list was just polled (sets ``last_synced_at`` to now)."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO list_state (list_id, last_synced_at) VALUES (?, ?) "
                "ON CONFLICT(list_id) DO UPDATE SET last_synced_at=excluded.last_synced_at",
                (list_id, utcnow_iso()),
            )
            self._conn.commit()

    def list_last_synced(self) -> dict[str, str]:
        """Return ``{list_id: last_synced_at}`` for every list polled so far."""
        rows = self._conn.execute(
            "SELECT list_id, last_synced_at FROM list_state"
        ).fetchall()
        return {row["list_id"]: row["last_synced_at"] for row in rows}

    def disk_size_bytes(self) -> int:
        """Return the on-disk size of the database files in bytes.

        Includes the main database file plus any WAL and SHM sidecar files.
        Returns ``0`` for in-memory databases or when the files do not exist.
        """
        if self._path == ":memory:":
            return 0
        total = 0
        for suffix in ("", "-wal", "-shm"):
            file_path = self._path + suffix
            try:
                total += os.path.getsize(file_path)
            except FileNotFoundError:
                pass
        return total

    def table_counts(self) -> dict[str, int]:
        """Return row counts for the tracked tables."""
        counts: dict[str, int] = {}
        for table in ("items", "activity", "list_state"):
            row = self._conn.execute(
                f"SELECT COUNT(*) AS n FROM {table}"
            ).fetchone()
            counts[table] = row["n"]
        return counts

    def clear_activity(self) -> int:
        """Delete every row from the activity log and return the count removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM activity")
            self._conn.commit()
            return cursor.rowcount

    def clear_items_and_sync_state(self) -> int:
        """Delete every row from items and list_state, returning the total removed.

        Tracked-list configuration in ``app_settings.json`` is untouched; the next
        sync rebuilds the rows from Trakt.
        """
        with self._lock:
            items_cursor = self._conn.execute("DELETE FROM items")
            state_cursor = self._conn.execute("DELETE FROM list_state")
            self._conn.commit()
            return items_cursor.rowcount + state_cursor.rowcount

    # ---- Findarr ----

    def findarr_is_processed(self, *, app: str, mode: str, item_id: str) -> bool:
        """Return whether Findarr has already processed an item for an app/mode."""
        row = self._conn.execute(
            "SELECT 1 FROM findarr_processed WHERE app=? AND mode=? AND item_id=?",
            (app, mode, item_id),
        ).fetchone()
        return row is not None

    def findarr_mark_processed(
        self, *, app: str, mode: str, item_id: str, title: str | None
    ) -> None:
        """Record that Findarr processed an item for an app/mode."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO findarr_processed (app, mode, item_id, title, processed_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(app, mode, item_id) DO UPDATE SET
                    title=excluded.title,
                    processed_at=excluded.processed_at
                """,
                (app, mode, item_id, title, utcnow_iso()),
            )
            self._conn.commit()

    def findarr_add_history(
        self,
        *,
        app: str,
        mode: str,
        item_id: str | None,
        title: str | None,
        status: str,
        detail: str,
    ) -> None:
        """Append a Findarr history entry."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO findarr_history (ts, app, mode, item_id, title, status, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utcnow_iso(), app, mode, item_id, title, status, detail),
            )
            self._conn.commit()

    def findarr_recent_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent Findarr history entries, newest first."""
        rows = self._conn.execute(
            "SELECT id, ts, app, mode, item_id, title, status, detail "
            "FROM findarr_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def findarr_counts(self) -> dict[str, dict[str, int]]:
        """Return processed counts by app and mode."""
        counts = {
            "sonarr": {"missing": 0, "upgrade": 0},
            "radarr": {"missing": 0, "upgrade": 0},
        }
        rows = self._conn.execute(
            "SELECT app, mode, COUNT(*) AS n FROM findarr_processed GROUP BY app, mode"
        ).fetchall()
        for row in rows:
            counts[row["app"]][row["mode"]] = row["n"]
        return counts

    def findarr_success_count_since(self, cutoff_iso: str) -> int:
        """Return successful Findarr item actions since ``cutoff_iso``."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM findarr_history "
            "WHERE ts >= ? AND status='success' AND mode IN ('missing','upgrade')",
            (cutoff_iso,),
        ).fetchone()
        return int(row["n"])

    def findarr_set_run_state(self, key: str, value: str) -> None:
        """Persist one Findarr run-state value."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO findarr_run_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def findarr_run_state(self) -> dict[str, str]:
        """Return all persisted Findarr run-state values."""
        rows = self._conn.execute("SELECT key, value FROM findarr_run_state").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def findarr_reset_state(self) -> int:
        """Clear Findarr processed state and return the number of rows removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM findarr_processed")
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Helper to materialise an iterable of rows into plain dicts."""
    return [dict(row) for row in rows]
