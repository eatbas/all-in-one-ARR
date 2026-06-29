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


def test_sonarr_normalise_captures_series_grouping_fields() -> None:
    item = sonarr.normalise(
        {
            "id": 9,
            "seriesId": 5,
            "seasonNumber": 3,
            "episodeNumber": 4,
            "monitored": True,
            "series": {"id": 5, "title": "Show", "monitored": True},
        },
        mode="missing",
    )
    assert item is not None
    assert item.series_id == 5
    assert item.season_number == 3
    assert item.series_title == "Show"
    # Falls back to the embedded series id when the episode record omits seriesId.
    fallback = sonarr.normalise(
        {"id": 10, "seasonNumber": 1, "series": {"id": 7, "title": "Other"}}, mode="missing"
    )
    assert fallback is not None
    assert fallback.series_id == 7


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
