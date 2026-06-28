"""Tests for Findarr database helpers."""

from __future__ import annotations


def test_findarr_processed_history_counts_and_reset(db) -> None:
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="1") is False
    db.findarr_mark_processed(app="sonarr", mode="missing", item_id="1", title="One")
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="1") is True
    assert db.findarr_counts()["sonarr"]["missing"] == 1

    db.findarr_add_history(app="sonarr", mode="missing", item_id="1", title="One", status="success", detail="done")
    assert db.findarr_success_count_since("2000-01-01T00:00:00+00:00") == 1
    assert db.findarr_recent_history()[0]["detail"] == "done"

    db.findarr_set_run_state("last_run_status", "completed")
    assert db.findarr_run_state()["last_run_status"] == "completed"

    assert db.findarr_reset_state() == 1
    assert db.findarr_counts()["sonarr"]["missing"] == 0
