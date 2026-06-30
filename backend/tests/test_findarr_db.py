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


def test_findarr_clear_history_empties_log_and_returns_count(db) -> None:
    db.findarr_add_history(app="sonarr", mode="missing", item_id="1", title="One", status="success", detail="done")
    db.findarr_add_history(app="radarr", mode="upgrade", item_id="2", title="Two", status="success", detail="done")
    assert db.findarr_clear_history() == 2
    assert db.findarr_recent_history() == []


def test_findarr_totals_increment_and_survive_reset(db) -> None:
    assert db.findarr_totals()["sonarr"]["missing"] == 0
    db.findarr_increment_total(app="sonarr", mode="missing")
    db.findarr_increment_total(app="sonarr", mode="missing")
    db.findarr_increment_total(app="radarr", mode="upgrade")
    assert db.findarr_totals()["sonarr"]["missing"] == 2
    assert db.findarr_totals()["radarr"]["upgrade"] == 1
    # The all-time tally is reset-proof: clearing processed state must not zero it.
    db.findarr_mark_processed(app="sonarr", mode="missing", item_id="1", title="One")
    assert db.findarr_reset_state() == 1
    assert db.findarr_totals()["sonarr"]["missing"] == 2
    assert db.findarr_totals()["radarr"]["upgrade"] == 1
