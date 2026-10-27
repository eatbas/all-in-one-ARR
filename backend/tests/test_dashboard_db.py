"""Tests for core.db_dashboard (the dashboard snapshot table)."""

from __future__ import annotations

from core.db import Database


def test_init_db_creates_snapshot_table_and_index(db: Database) -> None:
    names = {
        row["name"]
        for row in db._conn.execute(
            "SELECT name FROM sqlite_master WHERE tbl_name = 'dashboard_snapshots' "
            "AND name NOT LIKE 'sqlite_autoindex_%'"
        ).fetchall()
    }
    assert names == {"dashboard_snapshots", "idx_dashboard_snapshots_metric_day"}


def test_upsert_overwrites_same_day_and_metric(db: Database) -> None:
    written = db.dashboard_snapshot_upsert(
        day="2026-10-01",
        values={"sonarr.series_total": 10, "radarr.movies_total": 20},
        recorded_at="2026-10-01T23:55:00+00:00",
    )
    assert written == 2
    rewritten = db.dashboard_snapshot_upsert(
        day="2026-10-01",
        values={"sonarr.series_total": 11},
        recorded_at="2026-10-01T23:56:00+00:00",
    )
    assert rewritten == 1

    rows = db.dashboard_snapshot_range(start_day="2026-10-01", end_day="2026-10-01")
    assert rows == [
        {
            "day": "2026-10-01",
            "metric": "radarr.movies_total",
            "value": 20.0,
            "recorded_at": "2026-10-01T23:55:00+00:00",
        },
        {
            "day": "2026-10-01",
            "metric": "sonarr.series_total",
            "value": 11.0,
            "recorded_at": "2026-10-01T23:56:00+00:00",
        },
    ]


def test_upsert_with_no_values_writes_nothing(db: Database) -> None:
    assert (
        db.dashboard_snapshot_upsert(day="2026-10-01", values={}, recorded_at="x") == 0
    )
    assert not db.dashboard_snapshot_has_day("2026-10-01")


def test_prune_removes_only_rows_strictly_before_cutoff(db: Database) -> None:
    for day in ("2026-09-29", "2026-09-30", "2026-10-01"):
        db.dashboard_snapshot_upsert(day=day, values={"m": 1}, recorded_at=day)

    assert db.dashboard_snapshot_prune(before_day="2026-09-30") == 1

    days = [
        row["day"]
        for row in db.dashboard_snapshot_range(
            start_day="2000-01-01", end_day="2100-01-01"
        )
    ]
    assert days == ["2026-09-30", "2026-10-01"]


def test_has_day(db: Database) -> None:
    db.dashboard_snapshot_upsert(day="2026-10-01", values={"m": 1}, recorded_at="t")
    assert db.dashboard_snapshot_has_day("2026-10-01")
    assert not db.dashboard_snapshot_has_day("2026-10-02")


def test_range_is_inclusive_and_ordered_by_metric_then_day(db: Database) -> None:
    for day in ("2026-10-03", "2026-10-01", "2026-10-02", "2026-10-04"):
        db.dashboard_snapshot_upsert(
            day=day, values={"b.metric": 2, "a.metric": 1}, recorded_at=day
        )

    rows = db.dashboard_snapshot_range(start_day="2026-10-02", end_day="2026-10-03")
    assert [(row["metric"], row["day"]) for row in rows] == [
        ("a.metric", "2026-10-02"),
        ("a.metric", "2026-10-03"),
        ("b.metric", "2026-10-02"),
        ("b.metric", "2026-10-03"),
    ]


def test_latest_returns_newest_day_per_metric(db: Database) -> None:
    db.dashboard_snapshot_upsert(
        day="2026-10-01", values={"a": 1, "b": 5}, recorded_at="r1"
    )
    db.dashboard_snapshot_upsert(day="2026-10-02", values={"a": 2}, recorded_at="r2")

    latest = db.dashboard_snapshot_latest(["a", "b", "unknown", "a"])

    assert latest == {
        "a": {"day": "2026-10-02", "value": 2.0, "recorded_at": "r2"},
        "b": {"day": "2026-10-01", "value": 5.0, "recorded_at": "r1"},
    }


def test_latest_with_no_metrics_returns_empty(db: Database) -> None:
    db.dashboard_snapshot_upsert(day="2026-10-01", values={"a": 1}, recorded_at="r")
    assert db.dashboard_snapshot_latest([]) == {}


def test_last_recorded_at_tracks_the_newest_snapshot(db: Database) -> None:
    assert db.dashboard_snapshot_last_recorded_at() is None

    db.dashboard_snapshot_upsert(
        day="2026-10-26",
        values={"a": 1, "b": 2},
        recorded_at="2026-10-26T23:55:00+00:00",
    )
    assert db.dashboard_snapshot_last_recorded_at() == "2026-10-26T23:55:00+00:00"

    # A boot catch-up early on the next day, then the evening run over it.
    db.dashboard_snapshot_upsert(
        day="2026-10-27", values={"a": 3}, recorded_at="2026-10-27T08:00:00+00:00"
    )
    assert db.dashboard_snapshot_last_recorded_at() == "2026-10-27T08:00:00+00:00"
    db.dashboard_snapshot_upsert(
        day="2026-10-27", values={"a": 4}, recorded_at="2026-10-27T23:55:00+00:00"
    )
    assert db.dashboard_snapshot_last_recorded_at() == "2026-10-27T23:55:00+00:00"
