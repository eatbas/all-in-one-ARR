"""Dashboard daily-snapshot persistence.

Mixed into :class:`core.db.Database`, which owns the SQLite connection and the
process-level lock; kept in its own module so ``core/db.py`` does not keep
growing with every feature's persistence.

``dashboard_snapshots`` holds one value per catalogue metric per local calendar
day (``YYYY-MM-DD``). The daily snapshot job upserts today's row, so a re-run on
the same day overwrites rather than duplicates, and prunes anything older than
:data:`DASHBOARD_SNAPSHOT_RETENTION_DAYS`. The trend charts read a day range;
the live summary reads each metric's newest row as its offline fallback.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable, Mapping
from typing import Any

# Snapshot rows older than this many days are pruned by the daily job; the
# longest chart range is 90 days, the rest is a year of history for later use.
DASHBOARD_SNAPSHOT_RETENTION_DAYS = 365


class DashboardSnapshotMixin:
    """``dashboard_snapshots`` helpers; requires ``_conn`` and ``_lock`` from the host."""

    _conn: sqlite3.Connection
    _lock: threading.Lock

    def dashboard_snapshot_upsert(
        self, *, day: str, values: Mapping[str, float], recorded_at: str
    ) -> int:
        """Store ``values`` under ``day``, overwriting that day's existing rows.

        Returns the number of rows written (one per metric in ``values``).
        """
        rows = [
            (day, metric, float(value), recorded_at) for metric, value in values.items()
        ]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO dashboard_snapshots (day, metric, value, recorded_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(day, metric) DO UPDATE SET
                    value = excluded.value,
                    recorded_at = excluded.recorded_at
                """,
                rows,
            )
            self._conn.commit()
        return len(rows)

    def dashboard_snapshot_prune(self, *, before_day: str) -> int:
        """Delete every row whose day is strictly before ``before_day``."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM dashboard_snapshots WHERE day < ?", (before_day,)
            )
            self._conn.commit()
        return cursor.rowcount

    def dashboard_snapshot_has_day(self, day: str) -> bool:
        """Return whether any snapshot row exists for ``day``."""
        row = self._conn.execute(
            "SELECT 1 FROM dashboard_snapshots WHERE day = ? LIMIT 1", (day,)
        ).fetchone()
        return row is not None

    def dashboard_snapshot_last_recorded_at(self) -> str | None:
        """Return when the newest snapshot was written, or ``None`` before the first.

        Every snapshot writes under its own local day with one ``recorded_at``, so
        this changes whenever a snapshot lands: clients use it as the version of
        the stored history.
        """
        row = self._conn.execute(
            "SELECT recorded_at FROM dashboard_snapshots "
            "ORDER BY day DESC, recorded_at DESC LIMIT 1"
        ).fetchone()
        return None if row is None else str(row["recorded_at"])

    def dashboard_snapshot_range(
        self, *, start_day: str, end_day: str
    ) -> list[dict[str, Any]]:
        """Return rows with ``start_day <= day <= end_day``, ordered by metric, day."""
        rows = self._conn.execute(
            "SELECT day, metric, value, recorded_at FROM dashboard_snapshots "
            "WHERE day >= ? AND day <= ? ORDER BY metric, day",
            (start_day, end_day),
        ).fetchall()
        return [dict(row) for row in rows]

    def dashboard_snapshot_latest(
        self, metrics: Iterable[str]
    ) -> dict[str, dict[str, Any]]:
        """Return each metric's newest row as ``{metric: {day, value, recorded_at}}``.

        Metrics with no stored row are absent from the result.
        """
        keys = list(dict.fromkeys(metrics))
        if not keys:
            return {}
        # Only "?" placeholders are interpolated; the metric keys are bound.
        placeholders = ", ".join("?" for _ in keys)
        rows = self._conn.execute(
            f"""
            SELECT metric, day, value, recorded_at
            FROM dashboard_snapshots AS snapshot
            WHERE metric IN ({placeholders})
              AND day = (
                  SELECT MAX(day) FROM dashboard_snapshots
                  WHERE metric = snapshot.metric
              )
            """,
            keys,
        ).fetchall()
        return {
            row["metric"]: {
                "day": row["day"],
                "value": row["value"],
                "recorded_at": row["recorded_at"],
            }
            for row in rows
        }
