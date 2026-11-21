"""Remindarr results and run-state persistence.

Mixed into :class:`core.db.Database`, which owns the SQLite connection and the
process-level lock. A refresh replaces both result tables in one transaction,
so a failed or partial run can never leave the page with a half-written set:
readers see either the previous results or the new ones.

The run state (last success, last attempt, last error and the selected tags
Sonarr no longer reported) is a small JSON document kept in ``app_state`` under
:data:`RUN_STATE_KEY` rather than a single-row table.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

RUN_STATE_KEY = "remindarr_run_state"

_SERIES_COLUMNS = (
    "series_id",
    "series_title",
    "series_slug",
    "tvdb_id",
    "plex_match",
    "episodes_not_in_plex",
    "latest_added_at",
)
_EPISODE_COLUMNS = (
    "episode_id",
    "series_id",
    "episode_file_id",
    "season_number",
    "episode_number",
    "title",
    "air_date_utc",
    "added_at",
)


def _empty_run_state() -> dict[str, Any]:
    """Return the run state of a module that has never refreshed."""
    return {
        "last_success_at": None,
        "last_attempt_at": None,
        "last_error": None,
        "missing_tag_ids": [],
    }


def _optional_text(value: Any) -> str | None:
    """Return ``value`` when it is a string, else ``None``."""
    return value if isinstance(value, str) else None


def _tag_id_list(value: Any) -> list[int]:
    """Return the positive integer entries of a JSON list (bools excluded)."""
    if not isinstance(value, list):
        return []
    return [
        entry
        for entry in value
        if isinstance(entry, int) and not isinstance(entry, bool) and entry > 0
    ]


def _insert_sql(table: str, columns: tuple[str, ...]) -> str:
    """Build a parameterised ``INSERT`` for fixed, trusted column names."""
    placeholders = ", ".join("?" for _ in columns)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"


class RemindarrMixin:
    """``remindarr_*`` helpers; requires ``_conn``, ``_lock`` and ``app_state_*``."""

    _conn: sqlite3.Connection
    _lock: threading.Lock

    if TYPE_CHECKING:  # pragma: no cover

        def app_state_get(self, key: str) -> str | None: ...

        def app_state_set(self, key: str, value: str) -> None: ...

    def remindarr_replace_results(
        self,
        series_rows: Iterable[dict[str, Any]],
        episode_rows: Iterable[dict[str, Any]],
    ) -> None:
        """Replace every stored series and episode row in one transaction.

        Each row is a dict keyed by the table's column names. Any error rolls
        the transaction back and re-raises, leaving the previous results intact.
        """
        series_values = [
            tuple(row[column] for column in _SERIES_COLUMNS) for row in series_rows
        ]
        episode_values = [
            tuple(row[column] for column in _EPISODE_COLUMNS) for row in episode_rows
        ]
        with self._lock:
            try:
                self._conn.execute("DELETE FROM remindarr_episodes")
                self._conn.execute("DELETE FROM remindarr_series")
                self._conn.executemany(
                    _insert_sql("remindarr_series", _SERIES_COLUMNS), series_values
                )
                self._conn.executemany(
                    _insert_sql("remindarr_episodes", _EPISODE_COLUMNS),
                    episode_values,
                )
            except Exception:
                self._conn.rollback()
                raise
            self._conn.commit()

    def remindarr_series_rows(self) -> list[dict[str, Any]]:
        """Return every stored tracked-series row, ordered by series id."""
        rows = self._conn.execute(
            f"SELECT {', '.join(_SERIES_COLUMNS)} FROM remindarr_series "
            "ORDER BY series_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def remindarr_episode_rows(self) -> list[dict[str, Any]]:
        """Return every stored unwatched-episode row, ordered by episode id."""
        rows = self._conn.execute(
            f"SELECT {', '.join(_EPISODE_COLUMNS)} FROM remindarr_episodes "
            "ORDER BY episode_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def remindarr_counts(self) -> dict[str, int]:
        """Return the stored unwatched-episode and series counts.

        ``series_with_unwatched`` counts the series that have at least one
        unwatched episode (the page's series groups).
        """
        episodes = self._conn.execute(
            "SELECT COUNT(*) AS unwatched, "
            "COUNT(DISTINCT series_id) AS series_with_unwatched "
            "FROM remindarr_episodes"
        ).fetchone()
        series = self._conn.execute(
            "SELECT COUNT(*) AS tracked, "
            "COALESCE(SUM(plex_match != 'matched'), 0) AS unmatched "
            "FROM remindarr_series"
        ).fetchone()
        return {
            "unwatched": int(episodes["unwatched"]),
            "series_with_unwatched": int(episodes["series_with_unwatched"]),
            "tracked_series": int(series["tracked"]),
            "unmatched_series": int(series["unmatched"]),
        }

    def remindarr_run_state(self) -> dict[str, Any]:
        """Return the persisted run state; a missing or corrupt value reads as empty."""
        state = _empty_run_state()
        raw = self.app_state_get(RUN_STATE_KEY)
        if raw is None:
            return state
        try:
            data = json.loads(raw)
        except ValueError:
            return state
        if not isinstance(data, dict):
            return state
        for key in ("last_success_at", "last_attempt_at", "last_error"):
            state[key] = _optional_text(data.get(key))
        state["missing_tag_ids"] = _tag_id_list(data.get("missing_tag_ids"))
        return state

    def remindarr_set_run_state(
        self,
        *,
        last_success_at: str | None,
        last_attempt_at: str | None,
        last_error: str | None,
        missing_tag_ids: list[int],
    ) -> None:
        """Persist the full run state (every field is written each time)."""
        self.app_state_set(
            RUN_STATE_KEY,
            json.dumps(
                {
                    "last_success_at": last_success_at,
                    "last_attempt_at": last_attempt_at,
                    "last_error": last_error,
                    "missing_tag_ids": list(missing_tag_ids),
                }
            ),
        )
