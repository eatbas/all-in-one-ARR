"""Findarr persistence: retry state, search log, history, and run state.

Mixed into :class:`core.db.Database`, which owns the SQLite connection and the
process-level lock; kept in its own module so ``core/db.py`` does not keep
growing with every feature's persistence.

Three tables carry distinct concerns:

* ``findarr_processed`` — per-unit retry state (consecutive no-result
  ``attempts`` and ``next_eligible_at``) that drives the search backoff.
* ``findarr_searches`` — one row per search command sent; the source of the
  hourly cap and of the follow-up outcome lookup. Clearing the History log never
  touches it, so the cap cannot be bypassed by a clear.
* ``findarr_history`` — the user-facing audit log shown on the History tab.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.timefmt import utcnow_iso

# Search-log rows older than this are pruned on write. Long enough to resolve
# any outcome (Sonarr/Radarr keep finished commands for hours, not days) and to
# cover the one-hour cap window many times over.
SEARCH_LOG_RETENTION_DAYS = 7

_APP_MODE_ZEROES = {
    "sonarr": {"missing": 0, "upgrade": 0},
    "radarr": {"missing": 0, "upgrade": 0},
}


def _zeroed_app_modes() -> dict[str, dict[str, int]]:
    return {app: dict(modes) for app, modes in _APP_MODE_ZEROES.items()}


class FindarrMixin:
    """Findarr table helpers; requires ``_conn`` and ``_lock`` from the host."""

    _conn: sqlite3.Connection
    _lock: threading.Lock

    # ---- retry state (findarr_processed) ----

    def findarr_retry_state(self, *, app: str, mode: str) -> dict[str, dict[str, Any]]:
        """Return ``{item_id: {"attempts", "next_eligible_at"}}`` for an app/mode."""
        rows = self._conn.execute(
            "SELECT item_id, attempts, next_eligible_at FROM findarr_processed "
            "WHERE app=? AND mode=?",
            (app, mode),
        ).fetchall()
        return {
            row["item_id"]: {
                "attempts": int(row["attempts"]),
                "next_eligible_at": row["next_eligible_at"],
            }
            for row in rows
        }

    def findarr_mark_searched(
        self,
        *,
        app: str,
        mode: str,
        item_id: str,
        title: str | None,
        next_eligible_at: str,
    ) -> None:
        """Record a search for a unit, keeping its consecutive no-result count."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO findarr_processed
                    (app, mode, item_id, title, processed_at, attempts, next_eligible_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(app, mode, item_id) DO UPDATE SET
                    title=excluded.title,
                    processed_at=excluded.processed_at,
                    next_eligible_at=excluded.next_eligible_at
                """,
                (app, mode, item_id, title, utcnow_iso(), next_eligible_at),
            )
            self._conn.commit()

    def findarr_set_retry(
        self,
        *,
        app: str,
        mode: str,
        item_id: str,
        attempts: int,
        next_eligible_at: str,
    ) -> None:
        """Update a unit's retry state; a no-op when the unit has been pruned."""
        with self._lock:
            self._conn.execute(
                "UPDATE findarr_processed SET attempts=?, next_eligible_at=? "
                "WHERE app=? AND mode=? AND item_id=?",
                (attempts, next_eligible_at, app, mode, item_id),
            )
            self._conn.commit()

    def findarr_prune_processed(
        self, *, app: str, mode: str, keep_item_ids: Iterable[str]
    ) -> int:
        """Drop retry state for units no longer wanted; return the count removed.

        A unit that leaves the wanted list (downloaded, unmonitored, deleted)
        starts with a clean backoff if it is ever wanted again.
        """
        keep = set(keep_item_ids)
        with self._lock:
            stale = [
                (app, mode, row["item_id"])
                for row in self._conn.execute(
                    "SELECT item_id FROM findarr_processed WHERE app=? AND mode=?",
                    (app, mode),
                ).fetchall()
                if row["item_id"] not in keep
            ]
            self._conn.executemany(
                "DELETE FROM findarr_processed WHERE app=? AND mode=? AND item_id=?",
                stale,
            )
            self._conn.commit()
            return len(stale)

    def findarr_cooldown_counts(self, now_iso: str) -> dict[str, dict[str, int]]:
        """Return how many units per app/mode are waiting for their retry delay."""
        counts = _zeroed_app_modes()
        rows = self._conn.execute(
            "SELECT app, mode, COUNT(*) AS n FROM findarr_processed "
            "WHERE next_eligible_at > ? GROUP BY app, mode",
            (now_iso,),
        ).fetchall()
        for row in rows:
            counts[row["app"]][row["mode"]] = row["n"]
        return counts

    def findarr_next_due_at(self, now_iso: str) -> str | None:
        """Return the soonest future ``next_eligible_at``, or ``None``."""
        row = self._conn.execute(
            "SELECT MIN(next_eligible_at) AS due FROM findarr_processed "
            "WHERE next_eligible_at > ?",
            (now_iso,),
        ).fetchone()
        return row["due"]

    def findarr_reset_state(self) -> int:
        """Clear all Findarr retry state and return the number of rows removed.

        The all-time tallies in ``findarr_totals`` and the search log are left
        untouched, so the headline counters and the hourly cap survive a reset.
        """
        with self._lock:
            cursor = self._conn.execute("DELETE FROM findarr_processed")
            self._conn.commit()
            return cursor.rowcount

    # ---- search log (findarr_searches) ----

    def findarr_log_search(
        self,
        *,
        app: str,
        mode: str,
        item_id: str,
        command_id: int | None,
        history_id: int,
    ) -> None:
        """Log one sent search command and prune rows past the retention window.

        A command without an id cannot be followed up, so it is logged as
        ``unknown`` straight away; it still counts towards the hourly cap.
        """
        outcome = "pending" if command_id is not None else "unknown"
        retention_cutoff = (
            datetime.now(UTC) - timedelta(days=SEARCH_LOG_RETENTION_DAYS)
        ).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO findarr_searches
                    (ts, app, mode, item_id, command_id, history_id, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utcnow_iso(), app, mode, item_id, command_id, history_id, outcome),
            )
            self._conn.execute(
                "DELETE FROM findarr_searches WHERE ts < ?", (retention_cutoff,)
            )
            self._conn.commit()

    def findarr_search_count_since(self, cutoff_iso: str) -> int:
        """Return how many search commands were sent since ``cutoff_iso``."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM findarr_searches WHERE ts >= ?",
            (cutoff_iso,),
        ).fetchone()
        return int(row["n"])

    def findarr_pending_searches(self, *, app: str, limit: int) -> list[dict[str, Any]]:
        """Return the oldest searches for ``app`` whose outcome is not known yet."""
        rows = self._conn.execute(
            "SELECT id, ts, mode, item_id, command_id, history_id "
            "FROM findarr_searches WHERE app=? AND outcome='pending' "
            "ORDER BY id LIMIT ?",
            (app, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def findarr_resolve_search(
        self,
        *,
        search_id: int,
        outcome: str,
        history_id: int | None,
        history_status: str,
        history_detail: str,
    ) -> None:
        """Store a search's outcome and rewrite its History row to match.

        The History row may already be gone (the log was cleared); the outcome
        is still recorded on the search log.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE findarr_searches SET outcome=? WHERE id=?",
                (outcome, search_id),
            )
            if history_id is not None:
                self._conn.execute(
                    "UPDATE findarr_history SET status=?, detail=? WHERE id=?",
                    (history_status, history_detail, history_id),
                )
            self._conn.commit()

    # ---- history (findarr_history) ----

    def findarr_add_history(
        self,
        *,
        app: str,
        mode: str,
        item_id: str | None,
        title: str | None,
        status: str,
        detail: str,
    ) -> int:
        """Append a Findarr history entry and return its id."""
        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO findarr_history (ts, app, mode, item_id, title, status, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utcnow_iso(), app, mode, item_id, title, status, detail),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def findarr_recent_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent Findarr history entries, newest first."""
        rows = self._conn.execute(
            "SELECT id, ts, app, mode, item_id, title, status, detail "
            "FROM findarr_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def findarr_clear_history(self) -> int:
        """Delete every Findarr history row and return the count removed.

        Clears only the audit log (``findarr_history``). Retry state and the
        search log — which backs the hourly cap — are untouched.
        """
        with self._lock:
            cursor = self._conn.execute("DELETE FROM findarr_history")
            self._conn.commit()
            return cursor.rowcount

    # ---- run state and all-time totals ----

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

    def findarr_increment_total(self, *, app: str, mode: str) -> None:
        """Increment the all-time Findarr search tally for an app/mode.

        Kept apart from ``findarr_processed`` so the tally is a monotonic,
        reset-proof count of triggered searches.
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO findarr_totals (app, mode, count)
                VALUES (?, ?, 1)
                ON CONFLICT(app, mode) DO UPDATE SET count = count + 1
                """,
                (app, mode),
            )
            self._conn.commit()

    def findarr_totals(self) -> dict[str, dict[str, int]]:
        """Return all-time triggered counts by app and mode (reset-proof)."""
        totals = _zeroed_app_modes()
        rows = self._conn.execute(
            "SELECT app, mode, count FROM findarr_totals"
        ).fetchall()
        for row in rows:
            totals[row["app"]][row["mode"]] = row["count"]
        return totals
