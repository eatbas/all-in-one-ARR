"""Tests for the Cleanarr strike, history and run-state helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.db import Database


def _strike(db: Database, app: str, download_id: str, **overrides) -> dict:
    fields = {
        "queue_id": 1,
        "title": f"Title {download_id}",
        "reason": "failed_import",
        "message": "import blocked",
    }
    fields.update(overrides)
    return db.cleanarr_strike(app, download_id, **fields)


def test_strike_inserts_then_increments_and_tracks_latest_fields(db) -> None:
    first = _strike(db, "sonarr", "nzo_a")
    assert first["strikes"] == 1
    assert first["would_remove_logged"] is False

    second = _strike(
        db, "sonarr", "nzo_a", queue_id=9, reason="failed_download", message="m2"
    )
    assert second["strikes"] == 2
    assert second["queue_id"] == 9
    assert second["reason"] == "failed_download"
    assert second["message"] == "m2"
    assert second["first_seen_at"] == first["first_seen_at"]

    # The same download id under another app is a separate row.
    assert _strike(db, "radarr", "nzo_a")["strikes"] == 1
    assert len(db.cleanarr_strike_rows()) == 2


def test_clear_strikes_except_keeps_listed_ids_for_one_app(db) -> None:
    _strike(db, "sonarr", "keep")
    _strike(db, "sonarr", "drop")
    _strike(db, "radarr", "drop")

    assert db.cleanarr_clear_strikes_except("sonarr", ["keep"]) == 1
    remaining = {(row["app"], row["download_id"]) for row in db.cleanarr_strike_rows()}
    assert remaining == {("sonarr", "keep"), ("radarr", "drop")}


def test_reason_scoped_clear_preserves_other_reasons(db) -> None:
    _strike(db, "sonarr", "import_gone", reason="failed_import")
    _strike(db, "sonarr", "download_kept", reason="failed_download")

    assert (
        db.cleanarr_clear_strikes_for_reason_except("sonarr", "failed_import", []) == 1
    )
    assert [row["download_id"] for row in db.cleanarr_strike_rows()] == [
        "download_kept"
    ]


def test_would_remove_flag_and_delete(db) -> None:
    _strike(db, "radarr", "nzo_b")
    db.cleanarr_mark_would_remove_logged("radarr", "nzo_b")
    assert db.cleanarr_strike_rows()[0]["would_remove_logged"] is True
    # A further strike keeps the flag so the dry-run entry is not repeated.
    assert _strike(db, "radarr", "nzo_b")["would_remove_logged"] is True

    db.cleanarr_delete_strike("radarr", "nzo_b")
    assert db.cleanarr_strike_rows() == []


def test_clear_all_strikes(db) -> None:
    _strike(db, "sonarr", "a")
    _strike(db, "radarr", "b")
    assert db.cleanarr_clear_all_strikes() == 2
    assert db.cleanarr_strike_rows() == []


def test_history_insert_order_and_limit(db) -> None:
    first = db.cleanarr_add_history(
        app="sonarr",
        action="removed",
        download_id="a",
        title="A",
        detail="failed_import",
        dry_run=False,
    )
    second = db.cleanarr_add_history(
        app="system",
        action="run_skipped",
        download_id=None,
        title=None,
        detail="",
        dry_run=True,
    )
    assert second > first
    rows = db.cleanarr_history_rows()
    assert [row["id"] for row in rows] == [second, first]
    assert rows[0]["dry_run"] is True
    assert rows[1]["dry_run"] is False
    assert len(db.cleanarr_history_rows(limit=1)) == 1


def test_history_prunes_rows_older_than_retention(db) -> None:
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    db._conn.execute(
        "INSERT INTO cleanarr_history (ts, app, action, detail, dry_run) "
        "VALUES (?, 'system', 'old', '', 0)",
        (old,),
    )
    db._conn.commit()
    db.cleanarr_add_history(
        app="sabnzbd",
        action="quarantined",
        download_id=None,
        title="x",
        detail="",
        dry_run=False,
    )
    assert [row["action"] for row in db.cleanarr_history_rows()] == ["quarantined"]


def test_run_state_round_trip(db) -> None:
    assert db.cleanarr_run_state() == {}
    db.cleanarr_set_run_state("last_run_status", "ok")
    db.cleanarr_set_run_state("last_run_status", "error")
    db.cleanarr_set_run_state("last_run_at", "2026-01-01T00:00:00+00:00")
    assert db.cleanarr_run_state() == {
        "last_run_status": "error",
        "last_run_at": "2026-01-01T00:00:00+00:00",
    }


def test_quarantine_origins_are_recorded_replaced_and_pruned(db) -> None:
    db.cleanarr_record_quarantine(
        "20261028T120000Z__Show", container="tv", categories=["tv", "television"]
    )
    db.cleanarr_record_quarantine(
        "20261028T120000Z__Movie", container=None, categories=[]
    )
    assert db.cleanarr_quarantine_origins() == {
        "20261028T120000Z__Show": ("tv", ("television", "tv")),
        "20261028T120000Z__Movie": (None, ()),
    }

    # Recording the same quarantined name again replaces its origin.
    db.cleanarr_record_quarantine(
        "20261028T120000Z__Show", container="anime", categories=[]
    )
    assert db.cleanarr_quarantine_origins()["20261028T120000Z__Show"] == ("anime", ())

    assert db.cleanarr_prune_quarantine(["20261028T120000Z__Show", "Other"]) == 1
    assert list(db.cleanarr_quarantine_origins()) == ["20261028T120000Z__Show"]
