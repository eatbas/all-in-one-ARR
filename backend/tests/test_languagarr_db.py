"""Tests for the Languagarr replacement-search queue helpers."""

from __future__ import annotations

import sqlite3

from core.db import Database


def _entry(file_id: int, **overrides) -> dict:
    entry = {
        "episode_file_id": file_id,
        "series_id": 1,
        "title": f"Show - S01E{file_id:02d}",
        "episode_ids": [file_id * 10],
        "reason": "missing_language",
    }
    entry.update(overrides)
    return entry


def test_enqueue_skips_pending_and_recent_attempts(db) -> None:
    assert db.languagarr_enqueue([_entry(1), _entry(2)], retry_before_iso="0") == (
        2,
        0,
    )
    # Already pending: skipped regardless of the retry window.
    assert db.languagarr_enqueue([_entry(1)], retry_before_iso="9999") == (0, 1)

    db.languagarr_mark_attempt(1)
    # Attempted after the retry bound: skipped.
    assert db.languagarr_enqueue([_entry(1)], retry_before_iso="0") == (0, 1)
    # Attempted before the retry bound: re-queued with refreshed metadata.
    assert db.languagarr_enqueue(
        [_entry(1, title="Renamed", episode_ids=[7, 8])], retry_before_iso="9999"
    ) == (1, 0)
    row = next(r for r in db.languagarr_queue_rows() if r["episode_file_id"] == 1)
    assert row["status"] == "pending"
    assert row["title"] == "Renamed"
    assert row["episode_ids"] == [7, 8]
    assert row["attempts"] == 1
    assert row["last_error"] is None


def test_failed_rows_bypass_the_retry_window(db) -> None:
    db.languagarr_enqueue([_entry(1)], retry_before_iso="0")
    db.languagarr_mark_attempt(1, error="sonarr 503")
    # A failure says nothing about release availability: re-queue immediately.
    assert db.languagarr_enqueue([_entry(1)], retry_before_iso="0") == (1, 0)
    db.languagarr_delete_row(1)
    assert db.languagarr_queue_rows() == []


def test_mark_attempt_records_success_and_failure(db) -> None:
    db.languagarr_enqueue([_entry(1), _entry(2)], retry_before_iso="0")
    db.languagarr_mark_attempt(1)
    db.languagarr_mark_attempt(2, error="boom")
    rows = {row["episode_file_id"]: row for row in db.languagarr_queue_rows()}
    assert rows[1]["status"] == "searched"
    assert rows[1]["searched_at"]
    assert rows[2]["status"] == "failed"
    assert rows[2]["last_error"] == "boom"
    assert rows[2]["attempts"] == 1
    assert db.languagarr_queue_counts() == {"pending": 0, "searched": 1, "failed": 1}
    assert db.languagarr_queue_status_map()[2]["status"] == "failed"


def test_next_pending_is_oldest_first_and_limited(db) -> None:
    db.languagarr_enqueue([_entry(3)], retry_before_iso="0")
    db.languagarr_enqueue([_entry(1), _entry(2)], retry_before_iso="0")
    pending = db.languagarr_next_pending(2)
    assert [row["episode_file_id"] for row in pending] == [3, 1]
    assert pending[0]["episode_ids"] == [30]


def test_prune_and_clear_pending(db) -> None:
    db.languagarr_enqueue([_entry(1), _entry(2), _entry(3)], retry_before_iso="0")
    db.languagarr_mark_attempt(3)
    assert db.languagarr_prune([1, 3]) == 1
    assert sorted(db.languagarr_queue_status_map()) == [1, 3]
    assert db.languagarr_clear_pending() == 1
    assert db.languagarr_queue_counts() == {"pending": 0, "searched": 1, "failed": 0}
    assert db.languagarr_prune([]) == 1
    assert db.languagarr_queue_rows() == []


def test_series_slugs_are_stored_and_backfilled(db) -> None:
    db.languagarr_enqueue(
        [_entry(1, series_slug="show"), _entry(2), _entry(3, series_id=2)],
        retry_before_iso="0",
    )
    slugs = {
        row["episode_file_id"]: row["series_slug"] for row in db.languagarr_queue_rows()
    }
    assert slugs == {1: "show", 2: None, 3: None}

    db.languagarr_set_series_slugs({1: "show-renamed"})
    slugs = {
        row["episode_file_id"]: row["series_slug"] for row in db.languagarr_queue_rows()
    }
    assert slugs == {1: "show-renamed", 2: "show-renamed", 3: None}


def test_init_db_adds_series_slug_to_a_legacy_queue(tmp_path) -> None:
    # A queue created before v1.11 lacks series_slug; init_db must add it and
    # keep the existing rows (their slug stays NULL until the next scan).
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(str(path))
    legacy.executescript(
        """
        CREATE TABLE languagarr_queue (
            episode_file_id INTEGER PRIMARY KEY,
            series_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            episode_ids TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            searched_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        INSERT INTO languagarr_queue VALUES
            (1, 7, 'Show - S01E01', '[10]', 'missing_english', 'pending',
             '2026-10-12T00:00:00+00:00', NULL, 0, NULL);
        """
    )
    legacy.commit()
    legacy.close()

    database = Database(str(path))
    database.init_db()
    database.init_db()  # the migration is idempotent
    [row] = database.languagarr_queue_rows()
    assert row["series_slug"] is None
    # The verdict was renamed when the target language became configurable.
    assert row["reason"] == "missing_language"
    database.languagarr_set_series_slugs({7: "show"})
    assert database.languagarr_queue_rows()[0]["series_slug"] == "show"
    database.close()
