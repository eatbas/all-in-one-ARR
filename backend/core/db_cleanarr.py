"""Cleanarr persistence: the strike ledger, the audit history and run state.

Mixed into :class:`core.db.Database`, which owns the SQLite connection and the
process-level lock; kept in its own module so ``core/db.py`` does not keep
growing with every feature's persistence.

* ``cleanarr_strikes`` — one row per struck ``(app, download_id)``. A run
  increments the rows it matches and clears the ones that no longer match.
* ``cleanarr_history`` — the user-facing log of removals, file actions and
  skips, pruned after :data:`CLEANARR_HISTORY_RETENTION_DAYS`.
* ``cleanarr_run_state`` — key/value state such as the last run and the last
  health warnings.
* ``cleanarr_quarantine`` — where each quarantined entry came from (its
  category folder and category names), pruned once the entry is gone.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.timefmt import utcnow_iso

# History rows older than this are pruned on every write.
CLEANARR_HISTORY_RETENTION_DAYS = 30

_STRIKE_COLUMNS = (
    "app, download_id, queue_id, title, reason, message, strikes, "
    "first_seen_at, last_seen_at, would_remove_logged"
)


def _strike_row(row: sqlite3.Row) -> dict[str, Any]:
    """Return a strike row as a plain dict with a boolean would-remove flag."""
    result = dict(row)
    result["would_remove_logged"] = bool(result["would_remove_logged"])
    return result


class CleanarrMixin:
    """Cleanarr table helpers; requires ``_conn`` and ``_lock`` from the host."""

    _conn: sqlite3.Connection
    _lock: threading.Lock

    # ---- strikes (cleanarr_strikes) ----

    def cleanarr_strike(
        self,
        app: str,
        download_id: str,
        *,
        queue_id: int,
        title: str,
        reason: str,
        message: str,
    ) -> dict[str, Any]:
        """Add one strike to ``(app, download_id)`` and return the updated row.

        A new row starts at one strike. An existing row keeps its
        ``first_seen_at`` and takes the latest queue id, title, reason and
        message, so the removal targets the current queue entry.
        """
        now = utcnow_iso()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cleanarr_strikes (
                    app, download_id, queue_id, title, reason, message, strikes,
                    first_seen_at, last_seen_at, would_remove_logged
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 0)
                ON CONFLICT(app, download_id) DO UPDATE SET
                    queue_id=excluded.queue_id,
                    title=excluded.title,
                    reason=excluded.reason,
                    message=excluded.message,
                    strikes=cleanarr_strikes.strikes + 1,
                    last_seen_at=excluded.last_seen_at
                """,
                (app, download_id, queue_id, title, reason, message, now, now),
            )
            self._conn.commit()
            row = self._conn.execute(
                f"SELECT {_STRIKE_COLUMNS} FROM cleanarr_strikes "
                "WHERE app=? AND download_id=?",
                (app, download_id),
            ).fetchone()
        return _strike_row(row)

    def cleanarr_clear_strikes_except(self, app: str, keep_ids: Iterable[str]) -> int:
        """Delete ``app``'s strike rows whose download id is not in ``keep_ids``."""
        return self._cleanarr_clear_except(app, None, keep_ids)

    def cleanarr_clear_strikes_for_reason_except(
        self, app: str, reason: str, keep_ids: Iterable[str]
    ) -> int:
        """Delete ``app``'s ``reason`` strike rows not in ``keep_ids``.

        Used while SABnzbd history is unavailable, so ``failed_download``
        strikes are kept untouched instead of being reset by the outage.
        """
        return self._cleanarr_clear_except(app, reason, keep_ids)

    def _cleanarr_clear_except(
        self, app: str, reason: str | None, keep_ids: Iterable[str]
    ) -> int:
        """Delete strike rows for ``app`` (and ``reason`` when given) not kept."""
        keep = set(keep_ids)
        query = "SELECT download_id FROM cleanarr_strikes WHERE app=?"
        params: tuple[str, ...] = (app,)
        if reason is not None:
            query += " AND reason=?"
            params = (app, reason)
        with self._lock:
            stale = [
                row["download_id"]
                for row in self._conn.execute(query, params).fetchall()
                if row["download_id"] not in keep
            ]
            self._conn.executemany(
                "DELETE FROM cleanarr_strikes WHERE app=? AND download_id=?",
                [(app, download_id) for download_id in stale],
            )
            self._conn.commit()
        return len(stale)

    def cleanarr_delete_strike(self, app: str, download_id: str) -> None:
        """Delete one strike row (after a removal or an already-gone item)."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM cleanarr_strikes WHERE app=? AND download_id=?",
                (app, download_id),
            )
            self._conn.commit()

    def cleanarr_mark_would_remove_logged(self, app: str, download_id: str) -> None:
        """Flag a strike row so its dry-run would-remove entry is logged once."""
        with self._lock:
            self._conn.execute(
                "UPDATE cleanarr_strikes SET would_remove_logged=1 "
                "WHERE app=? AND download_id=?",
                (app, download_id),
            )
            self._conn.commit()

    def cleanarr_strike_rows(self) -> list[dict[str, Any]]:
        """Return every strike row, oldest first."""
        rows = self._conn.execute(
            f"SELECT {_STRIKE_COLUMNS} FROM cleanarr_strikes "
            "ORDER BY first_seen_at, app, download_id"
        ).fetchall()
        return [_strike_row(row) for row in rows]

    def cleanarr_clear_all_strikes(self) -> int:
        """Delete every strike row and return the count removed."""
        with self._lock:
            cursor = self._conn.execute("DELETE FROM cleanarr_strikes")
            self._conn.commit()
            return cursor.rowcount

    # ---- history (cleanarr_history) ----

    def cleanarr_add_history(
        self,
        *,
        app: str,
        action: str,
        download_id: str | None,
        title: str | None,
        detail: str,
        dry_run: bool,
    ) -> int:
        """Append a history entry, prune expired rows and return the new id."""
        cutoff = (
            datetime.now(UTC) - timedelta(days=CLEANARR_HISTORY_RETENTION_DAYS)
        ).isoformat()
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO cleanarr_history
                    (ts, app, action, download_id, title, detail, dry_run)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utcnow_iso(), app, action, download_id, title, detail, int(dry_run)),
            )
            self._prune_cleanarr_history(cutoff)
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def _prune_cleanarr_history(self, cutoff_iso: str) -> None:
        """Remove history rows older than ``cutoff_iso`` (a seam for tests)."""
        self._conn.execute("DELETE FROM cleanarr_history WHERE ts < ?", (cutoff_iso,))

    def cleanarr_history_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return recent history entries, newest first."""
        rows = self._conn.execute(
            "SELECT id, ts, app, action, download_id, title, detail, dry_run "
            "FROM cleanarr_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [{**dict(row), "dry_run": bool(row["dry_run"])} for row in rows]

    # ---- run state (cleanarr_run_state) ----

    def cleanarr_set_run_state(self, key: str, value: str) -> None:
        """Persist one Cleanarr run-state value."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO cleanarr_run_state (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def cleanarr_run_state(self) -> dict[str, str]:
        """Return all persisted Cleanarr run-state values."""
        rows = self._conn.execute(
            "SELECT key, value FROM cleanarr_run_state"
        ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ---- quarantine provenance (cleanarr_quarantine) ----

    def cleanarr_record_quarantine(
        self, name: str, *, container: str | None, categories: Iterable[str]
    ) -> None:
        """Remember where the entry now quarantined as ``name`` came from."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO cleanarr_quarantine
                    (name, container, categories, quarantined_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    container=excluded.container,
                    categories=excluded.categories,
                    quarantined_at=excluded.quarantined_at
                """,
                (name, container, json.dumps(sorted(categories)), utcnow_iso()),
            )
            self._conn.commit()

    def cleanarr_quarantine_origins(
        self,
    ) -> dict[str, tuple[str | None, tuple[str, ...]]]:
        """Return ``{quarantined name: (container, category names)}``."""
        rows = self._conn.execute(
            "SELECT name, container, categories FROM cleanarr_quarantine"
        ).fetchall()
        return {
            row["name"]: (row["container"], tuple(json.loads(row["categories"])))
            for row in rows
        }

    def cleanarr_prune_quarantine(self, keep_names: Iterable[str]) -> int:
        """Delete provenance rows whose entry is no longer in quarantine."""
        keep = set(keep_names)
        with self._lock:
            stale = [
                row["name"]
                for row in self._conn.execute(
                    "SELECT name FROM cleanarr_quarantine"
                ).fetchall()
                if row["name"] not in keep
            ]
            self._conn.executemany(
                "DELETE FROM cleanarr_quarantine WHERE name=?",
                [(name,) for name in stale],
            )
            self._conn.commit()
        return len(stale)
