"""SQLite persistence layer.

A single :class:`Database` instance is held on the shared :class:`AppContext`.
Writes are guarded by a process-level lock; the connection runs in WAL mode so
the scheduler thread and the request handlers can share it safely within one
Uvicorn worker. Multi-worker deployment is explicitly out of scope.
"""

from __future__ import annotations

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
        """Create tables and indexes if they do not already exist."""
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
                """
            )
            self._conn.commit()

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

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Helper to materialise an iterable of rows into plain dicts."""
    return [dict(row) for row in rows]
