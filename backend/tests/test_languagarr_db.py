"""Tests for the Languagarr replacement-search queue helpers."""

from __future__ import annotations


def _entry(file_id: int, **overrides) -> dict:
    entry = {
        "episode_file_id": file_id,
        "series_id": 1,
        "title": f"Show - S01E{file_id:02d}",
        "episode_ids": [file_id * 10],
        "reason": "missing_english",
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
