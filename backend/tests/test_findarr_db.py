"""Tests for Findarr database helpers."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from core.db import Database

_PAST = "2000-01-01T00:00:00+00:00"
_FUTURE = "2999-01-01T00:00:00+00:00"


def _add_history(db, *, item_id: str = "1", status: str = "sent") -> int:
    return db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id=item_id,
        title="One",
        status=status,
        detail="done",
    )


def test_mark_searched_keeps_attempts_and_set_retry_updates_them(db) -> None:
    db.findarr_mark_searched(
        app="sonarr", mode="missing", item_id="1", title="One", next_eligible_at=_FUTURE
    )
    assert db.findarr_retry_state(app="sonarr", mode="missing") == {
        "1": {"attempts": 0, "next_eligible_at": _FUTURE}
    }
    db.findarr_set_retry(
        app="sonarr", mode="missing", item_id="1", attempts=3, next_eligible_at=_PAST
    )
    # A re-search moves the delay but must not wipe the no-result count.
    db.findarr_mark_searched(
        app="sonarr", mode="missing", item_id="1", title="One", next_eligible_at=_FUTURE
    )
    assert db.findarr_retry_state(app="sonarr", mode="missing")["1"] == {
        "attempts": 3,
        "next_eligible_at": _FUTURE,
    }
    # Other app/mode slices are independent.
    assert db.findarr_retry_state(app="sonarr", mode="upgrade") == {}


def test_set_retry_is_a_no_op_for_a_pruned_unit(db) -> None:
    db.findarr_set_retry(
        app="radarr", mode="upgrade", item_id="9", attempts=2, next_eligible_at=_PAST
    )
    assert db.findarr_retry_state(app="radarr", mode="upgrade") == {}


def test_prune_processed_drops_units_no_longer_wanted(db) -> None:
    for item_id in ("1", "2", "3"):
        db.findarr_mark_searched(
            app="sonarr",
            mode="missing",
            item_id=item_id,
            title=item_id,
            next_eligible_at=_FUTURE,
        )
    db.findarr_mark_searched(
        app="sonarr", mode="upgrade", item_id="1", title="1", next_eligible_at=_FUTURE
    )
    removed = db.findarr_prune_processed(
        app="sonarr", mode="missing", keep_item_ids=["2"]
    )
    assert removed == 2
    assert set(db.findarr_retry_state(app="sonarr", mode="missing")) == {"2"}
    # Pruning one mode never touches another.
    assert set(db.findarr_retry_state(app="sonarr", mode="upgrade")) == {"1"}


def test_cooldown_counts_next_due_and_reset(db) -> None:
    now_iso = datetime.now(UTC).isoformat()
    soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    db.findarr_mark_searched(
        app="sonarr", mode="missing", item_id="1", title="1", next_eligible_at=_FUTURE
    )
    db.findarr_mark_searched(
        app="radarr", mode="upgrade", item_id="2", title="2", next_eligible_at=soon
    )
    db.findarr_mark_searched(
        app="radarr", mode="missing", item_id="3", title="3", next_eligible_at=_PAST
    )
    counts = db.findarr_cooldown_counts(now_iso)
    assert counts["sonarr"] == {"missing": 1, "upgrade": 0}
    assert counts["radarr"] == {"missing": 0, "upgrade": 1}
    assert db.findarr_next_due_at(now_iso) == soon

    assert db.findarr_reset_state() == 3
    assert db.findarr_cooldown_counts(now_iso)["sonarr"]["missing"] == 0
    assert db.findarr_next_due_at(now_iso) is None


def test_search_log_drives_the_cap_and_survives_a_history_clear(db) -> None:
    history_id = _add_history(db)
    db.findarr_log_search(
        app="sonarr", mode="missing", item_id="1", command_id=11, history_id=history_id
    )
    db.findarr_log_search(
        app="radarr", mode="upgrade", item_id="2", command_id=None, history_id=0
    )
    assert db.findarr_search_count_since(_PAST) == 2
    assert db.findarr_search_count_since(_FUTURE) == 0
    # Clearing History must not lift the hourly cap.
    assert db.findarr_clear_history() == 1
    assert db.findarr_search_count_since(_PAST) == 2
    # Only searches with a command id can be followed up.
    pending = db.findarr_pending_searches(app="sonarr", limit=10)
    assert [row["command_id"] for row in pending] == [11]
    assert db.findarr_pending_searches(app="radarr", limit=10) == []


def test_search_log_prunes_rows_past_retention(db) -> None:
    stale = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    db._conn.execute(
        "INSERT INTO findarr_searches "
        "(ts, app, mode, item_id, command_id, history_id, outcome) "
        "VALUES (?, 'sonarr', 'missing', 'old', 1, NULL, 'pending')",
        (stale,),
    )
    db.findarr_log_search(
        app="sonarr", mode="missing", item_id="new", command_id=2, history_id=0
    )
    pending = db.findarr_pending_searches(app="sonarr", limit=10)
    assert [row["item_id"] for row in pending] == ["new"]


def test_resolve_search_updates_log_and_history_row(db) -> None:
    history_id = _add_history(db)
    db.findarr_log_search(
        app="sonarr", mode="missing", item_id="1", command_id=5, history_id=history_id
    )
    search = db.findarr_pending_searches(app="sonarr", limit=1)[0]
    db.findarr_resolve_search(
        search_id=search["id"],
        outcome="grabbed",
        history_id=history_id,
        history_status="grabbed",
        history_detail="Sonarr grabbed 1 release(s)",
    )
    assert db.findarr_pending_searches(app="sonarr", limit=1) == []
    row = db.findarr_recent_history()[0]
    assert row["status"] == "grabbed"
    assert row["detail"] == "Sonarr grabbed 1 release(s)"


def test_resolve_search_without_history_row_still_records_outcome(db) -> None:
    db.findarr_log_search(
        app="sonarr", mode="missing", item_id="1", command_id=5, history_id=0
    )
    search = db.findarr_pending_searches(app="sonarr", limit=1)[0]
    db.findarr_resolve_search(
        search_id=search["id"],
        outcome="not_found",
        history_id=None,
        history_status="not_found",
        history_detail="none",
    )
    assert db.findarr_pending_searches(app="sonarr", limit=1) == []


def test_history_run_state_and_clear(db) -> None:
    first = _add_history(db, item_id="1")
    second = _add_history(db, item_id="2")
    assert second > first
    assert db.findarr_recent_history()[0]["item_id"] == "2"
    db.findarr_set_run_state("last_run_status", "completed")
    assert db.findarr_run_state()["last_run_status"] == "completed"
    assert db.findarr_clear_history() == 2
    assert db.findarr_recent_history() == []


def test_findarr_totals_increment_and_survive_reset(db) -> None:
    assert db.findarr_totals()["sonarr"]["missing"] == 0
    db.findarr_increment_total(app="sonarr", mode="missing")
    db.findarr_increment_total(app="sonarr", mode="missing")
    db.findarr_increment_total(app="radarr", mode="upgrade")
    assert db.findarr_totals()["sonarr"]["missing"] == 2
    assert db.findarr_totals()["radarr"]["upgrade"] == 1
    # The all-time tally is reset-proof: clearing retry state must not zero it.
    db.findarr_mark_searched(
        app="sonarr", mode="missing", item_id="1", title="One", next_eligible_at=_PAST
    )
    assert db.findarr_reset_state() == 1
    assert db.findarr_totals()["sonarr"]["missing"] == 2
    assert db.findarr_totals()["radarr"]["upgrade"] == 1


def test_init_db_adds_backoff_columns_to_a_v1_9_3_table(tmp_path) -> None:
    path = tmp_path / "old.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """
        CREATE TABLE findarr_processed (
            app TEXT NOT NULL,
            mode TEXT NOT NULL,
            item_id TEXT NOT NULL,
            title TEXT,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (app, mode, item_id)
        )
        """
    )
    legacy.execute(
        "INSERT INTO findarr_processed VALUES ('sonarr','missing','1','One',?)",
        (_PAST,),
    )
    legacy.commit()
    legacy.close()

    database = Database(str(path))
    try:
        database.init_db()
        # Existing rows start with no backoff and are due immediately.
        assert database.findarr_retry_state(app="sonarr", mode="missing") == {
            "1": {"attempts": 0, "next_eligible_at": None}
        }
        database.init_db()  # idempotent
    finally:
        database.close()
