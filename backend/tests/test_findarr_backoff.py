"""Tests for the Findarr retry backoff policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modules.findarr import backoff


@pytest.mark.parametrize(
    ("attempts", "expected"),
    [(0, 24), (1, 24), (2, 48), (3, 96), (5, 384), (6, 720), (40, 720)],
)
def test_delay_doubles_per_consecutive_miss_up_to_thirty_days(
    attempts: int, expected: int
) -> None:
    assert backoff.delay_hours(attempts, 24) == expected


def test_delay_never_drops_below_a_base_longer_than_the_cap() -> None:
    assert backoff.max_delay_hours(24) == 720
    assert backoff.max_delay_hours(2000) == 2000
    assert backoff.delay_hours(3, 2000) == 2000


def test_next_eligible_at_adds_the_delay() -> None:
    searched = datetime(2026, 1, 1, tzinfo=UTC)
    assert backoff.next_eligible_at(searched, 2, 24) == (
        (searched + timedelta(hours=48)).isoformat()
    )


def test_parse_iso_handles_z_naive_and_invalid_values() -> None:
    assert backoff.parse_iso("2026-01-01T00:00:00Z") == datetime(2026, 1, 1, tzinfo=UTC)
    assert backoff.parse_iso("2026-01-01T00:00:00") == datetime(2026, 1, 1, tzinfo=UTC)
    assert backoff.parse_iso("not a date") is None


def test_is_due_compares_against_now() -> None:
    now = datetime(2026, 1, 2, tzinfo=UTC)
    assert backoff.is_due(None, now) is True
    assert backoff.is_due("garbage", now) is True
    assert backoff.is_due("2026-01-01T00:00:00+00:00", now) is True
    assert backoff.is_due("2026-01-03T00:00:00+00:00", now) is False
