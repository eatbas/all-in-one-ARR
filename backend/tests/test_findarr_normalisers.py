"""Tests for Findarr Sonarr/Radarr normalisers."""

from __future__ import annotations

from modules.findarr import radarr, sonarr


def test_sonarr_normalise_handles_edge_cases() -> None:
    assert sonarr.normalise({}, mode="missing") is None
    invalid_date = sonarr.normalise({"id": 1, "airDateUtc": "bad"}, mode="missing")
    assert invalid_date is not None
    assert invalid_date.is_future is False
    naive_date = sonarr.normalise({"id": 4, "airDateUtc": "2020-01-01T00:00:00"}, mode="missing")
    assert naive_date is not None
    assert naive_date.is_future is False

    nested = sonarr.normalise(
        {
            "episode": {"id": 2, "title": "", "monitored": True},
            "series": {"title": "Series", "monitored": False},
        },
        mode="upgrade",
    )
    assert nested is not None
    assert nested.title == "Series - Episode"
    assert nested.monitored is False


def test_radarr_normalise_handles_edge_cases() -> None:
    assert radarr.normalise({}, mode="missing") is None
    assert radarr.normalise({"id": 1, "digitalRelease": "bad"}, mode="missing").is_future is False
    assert radarr.normalise({"id": 2}, mode="missing").title == "Unknown movie"
    nested = radarr.normalise(
        {"movie": {"id": 3, "title": "Movie", "year": 2024, "digitalRelease": "2999-01-01T00:00:00"}},
        mode="upgrade",
    )
    assert nested is not None
    assert nested.title == "Movie (2024)"
    assert nested.is_future is True
