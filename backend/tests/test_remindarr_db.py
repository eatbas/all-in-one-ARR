"""Tests for Remindarr persistence (core.db_remindarr)."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from core.db import Database
from core.db_remindarr import RUN_STATE_KEY


def _series(series_id: int, **overrides: Any) -> dict[str, Any]:
    row = {
        "series_id": series_id,
        "series_title": f"Series {series_id}",
        "series_slug": f"series-{series_id}",
        "tvdb_id": 1000 + series_id,
        "plex_match": "matched",
        "episodes_not_in_plex": 0,
        "latest_added_at": "2026-11-20T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _episode(episode_id: int, series_id: int, **overrides: Any) -> dict[str, Any]:
    row = {
        "episode_id": episode_id,
        "series_id": series_id,
        "episode_file_id": episode_id * 10,
        "season_number": 1,
        "episode_number": episode_id,
        "title": f"Episode {episode_id}",
        "air_date_utc": "2026-11-19T00:00:00+00:00",
        "added_at": "2026-11-20T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_empty_database_reads_as_empty(db: Database) -> None:
    assert db.remindarr_series_rows() == []
    assert db.remindarr_episode_rows() == []
    assert db.remindarr_counts() == {
        "unwatched": 0,
        "series_with_unwatched": 0,
        "tracked_series": 0,
        "unmatched_series": 0,
    }


def test_replace_results_swaps_the_whole_set(db: Database) -> None:
    db.remindarr_replace_results(
        [_series(1), _series(2, plex_match="no_tvdb_id", tvdb_id=None)],
        [_episode(11, 1), _episode(12, 1)],
    )
    assert [row["series_id"] for row in db.remindarr_series_rows()] == [1, 2]
    assert db.remindarr_series_rows()[1]["tvdb_id"] is None
    assert db.remindarr_episode_rows()[0] == _episode(11, 1)
    assert db.remindarr_counts() == {
        "unwatched": 2,
        "series_with_unwatched": 1,
        "tracked_series": 2,
        "unmatched_series": 1,
    }

    db.remindarr_replace_results([_series(3, plex_match="not_in_plex")], [])
    assert [row["series_id"] for row in db.remindarr_series_rows()] == [3]
    assert db.remindarr_episode_rows() == []
    assert db.remindarr_counts() == {
        "unwatched": 0,
        "series_with_unwatched": 0,
        "tracked_series": 1,
        "unmatched_series": 1,
    }


def test_failed_replace_rolls_back_and_keeps_old_rows(db: Database) -> None:
    db.remindarr_replace_results([_series(1)], [_episode(11, 1)])
    # The CHECK constraint rejects the bad series after the deletes ran.
    with pytest.raises(sqlite3.IntegrityError):
        db.remindarr_replace_results(
            [_series(5), _series(6, plex_match="bogus")], [_episode(51, 5)]
        )
    assert [row["series_id"] for row in db.remindarr_series_rows()] == [1]
    assert [row["episode_id"] for row in db.remindarr_episode_rows()] == [11]
    # The connection is still usable after the rollback.
    db.remindarr_replace_results([_series(2)], [])
    assert [row["series_id"] for row in db.remindarr_series_rows()] == [2]


def test_episode_rows_require_their_series(db: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.remindarr_replace_results([_series(1)], [_episode(21, 2)])
    assert db.remindarr_series_rows() == []


def test_run_state_defaults_and_round_trips(db: Database) -> None:
    assert db.remindarr_run_state() == {
        "last_success_at": None,
        "last_attempt_at": None,
        "last_error": None,
        "missing_tag_ids": [],
    }
    db.remindarr_set_run_state(
        last_success_at="2026-11-21T09:00:00+00:00",
        last_attempt_at="2026-11-21T10:00:00+00:00",
        last_error="Plex rejected the token",
        missing_tag_ids=[7],
    )
    assert db.remindarr_run_state() == {
        "last_success_at": "2026-11-21T09:00:00+00:00",
        "last_attempt_at": "2026-11-21T10:00:00+00:00",
        "last_error": "Plex rejected the token",
        "missing_tag_ids": [7],
    }


@pytest.mark.parametrize(
    "raw",
    ["{not json", "[1, 2]", '"text"'],
)
def test_corrupt_run_state_reads_as_empty(db: Database, raw: str) -> None:
    db.app_state_set(RUN_STATE_KEY, raw)
    assert db.remindarr_run_state()["last_success_at"] is None
    assert db.remindarr_run_state()["missing_tag_ids"] == []


def test_run_state_ignores_mistyped_fields(db: Database) -> None:
    db.app_state_set(
        RUN_STATE_KEY,
        '{"last_success_at": 5, "last_error": "boom", '
        '"missing_tag_ids": [3, true, "4", 0, 9]}',
    )
    assert db.remindarr_run_state() == {
        "last_success_at": None,
        "last_attempt_at": None,
        "last_error": "boom",
        "missing_tag_ids": [3, 9],
    }
    db.app_state_set(RUN_STATE_KEY, '{"missing_tag_ids": "3"}')
    assert db.remindarr_run_state()["missing_tag_ids"] == []
