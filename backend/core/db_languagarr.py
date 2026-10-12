"""Languagarr replacement-search queue persistence.

Mixed into :class:`core.db.Database`, which owns the SQLite connection and the
process-level lock; kept in its own module so ``core/db.py`` does not keep
growing with every feature's persistence.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from typing import Any

from core.timefmt import utcnow_iso


class LanguagarrQueueMixin:
    """``languagarr_queue`` helpers; requires ``_conn`` and ``_lock`` from the host."""

    _conn: sqlite3.Connection
    _lock: threading.Lock

    def languagarr_enqueue(
        self, entries: Iterable[dict[str, Any]], *, retry_before_iso: str
    ) -> tuple[int, int]:
        """Queue replacement searches; return ``(queued, skipped)``.

        Each entry carries ``episode_file_id``, ``series_id``, ``title``,
        ``episode_ids`` (list of ints) and ``reason``. An entry is skipped when
        its file is already ``pending``, or was successfully searched at or after
        ``retry_before_iso`` — the retry window — so repeated scans never
        re-search the same file every run. A ``failed`` row (Sonarr rejected the
        command) is queued again immediately: the failure says nothing about
        release availability, so it must not be locked out for the whole window.
        """
        queued = 0
        skipped = 0
        now = utcnow_iso()
        with self._lock:
            for entry in entries:
                file_id = int(entry["episode_file_id"])
                row = self._conn.execute(
                    "SELECT status, searched_at FROM languagarr_queue "
                    "WHERE episode_file_id=?",
                    (file_id,),
                ).fetchone()
                if row is not None and (
                    row["status"] == "pending"
                    or (
                        row["status"] == "searched"
                        and (row["searched_at"] or "") >= retry_before_iso
                    )
                ):
                    skipped += 1
                    continue
                self._conn.execute(
                    """
                    INSERT INTO languagarr_queue (
                        episode_file_id, series_id, title, episode_ids, reason,
                        status, queued_at, searched_at, attempts, last_error
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?, NULL, 0, NULL)
                    ON CONFLICT(episode_file_id) DO UPDATE SET
                        series_id=excluded.series_id,
                        title=excluded.title,
                        episode_ids=excluded.episode_ids,
                        reason=excluded.reason,
                        status='pending',
                        queued_at=excluded.queued_at,
                        last_error=NULL
                    """,
                    (
                        file_id,
                        int(entry["series_id"]),
                        str(entry["title"]),
                        json.dumps([int(value) for value in entry["episode_ids"]]),
                        str(entry["reason"]),
                        now,
                    ),
                )
                queued += 1
            self._conn.commit()
        return queued, skipped

    def languagarr_next_pending(self, limit: int) -> list[dict[str, Any]]:
        """Return up to ``limit`` pending queue rows, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM languagarr_queue WHERE status='pending' "
            "ORDER BY queued_at, episode_file_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [_languagarr_row(row) for row in rows]

    def languagarr_mark_attempt(
        self, episode_file_id: int, *, error: str | None = None
    ) -> None:
        """Record a search attempt: ``searched`` on success, ``failed`` with ``error``."""
        with self._lock:
            self._conn.execute(
                """
                UPDATE languagarr_queue
                SET status=?, searched_at=?, attempts=attempts + 1, last_error=?
                WHERE episode_file_id=?
                """,
                (
                    "failed" if error else "searched",
                    utcnow_iso(),
                    error,
                    episode_file_id,
                ),
            )
            self._conn.commit()

    def languagarr_queue_rows(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return queue rows, most recently queued first."""
        rows = self._conn.execute(
            "SELECT * FROM languagarr_queue "
            "ORDER BY queued_at DESC, episode_file_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_languagarr_row(row) for row in rows]

    def languagarr_queue_status_map(self) -> dict[int, dict[str, Any]]:
        """Return ``{episode_file_id: {"status", "searched_at"}}`` for every queue row."""
        rows = self._conn.execute(
            "SELECT episode_file_id, status, searched_at FROM languagarr_queue"
        ).fetchall()
        return {
            int(row["episode_file_id"]): {
                "status": row["status"],
                "searched_at": row["searched_at"],
            }
            for row in rows
        }

    def languagarr_queue_counts(self) -> dict[str, int]:
        """Return queue row counts per status (every status present, zero-filled)."""
        counts = {"pending": 0, "searched": 0, "failed": 0}
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM languagarr_queue GROUP BY status"
        ).fetchall()
        for row in rows:
            counts[row["status"]] = int(row["n"])
        return counts

    def languagarr_prune(self, keep_file_ids: Iterable[int]) -> int:
        """Delete queue rows whose file is not in ``keep_file_ids``; return the count.

        A scan calls this with the ids that are still non-compliant, so rows for
        files that were replaced, fixed or deleted stop cluttering the queue.
        """
        keep = {int(value) for value in keep_file_ids}
        with self._lock:
            existing = [
                int(row["episode_file_id"])
                for row in self._conn.execute(
                    "SELECT episode_file_id FROM languagarr_queue"
                ).fetchall()
            ]
            stale = [(file_id,) for file_id in existing if file_id not in keep]
            self._conn.executemany(
                "DELETE FROM languagarr_queue WHERE episode_file_id=?", stale
            )
            self._conn.commit()
        return len(stale)

    def languagarr_delete_row(self, episode_file_id: int) -> None:
        """Delete one queue row (its file was replaced, fixed or removed)."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM languagarr_queue WHERE episode_file_id=?",
                (episode_file_id,),
            )
            self._conn.commit()

    def languagarr_clear_pending(self) -> int:
        """Delete every pending queue row and return the count removed."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM languagarr_queue WHERE status='pending'"
            )
            self._conn.commit()
            return cursor.rowcount


def _languagarr_row(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a ``languagarr_queue`` row to a dict with decoded episode ids."""
    data = dict(row)
    data["episode_ids"] = [int(value) for value in json.loads(data["episode_ids"])]
    return data
