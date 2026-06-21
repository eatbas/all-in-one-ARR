"""Tests for core.clients.arr (defensive webhook parsing)."""

from __future__ import annotations

from core.clients.arr import ArrEvent, parse_webhook


def test_radarr_download_movie() -> None:
    event = parse_webhook({"eventType": "Download", "movie": {"tmdbId": 438631}})
    assert event.is_import is True
    assert event.tmdb == 438631
    assert event.tvdb is None


def test_radarr_remote_movie_fallback() -> None:
    event = parse_webhook({"eventType": "Import", "remoteMovie": {"tmdbId": 42}})
    assert event.tmdb == 42
    assert event.is_import is True


def test_sonarr_download_series() -> None:
    event = parse_webhook({"eventType": "Download", "series": {"tvdbId": 371980}})
    assert event.tvdb == 371980
    assert event.tmdb is None


def test_remote_series_fallback() -> None:
    event = parse_webhook({"eventType": "Download", "remoteSeries": {"tvdbId": 7}})
    assert event.tvdb == 7


def test_non_import_event() -> None:
    event = parse_webhook({"eventType": "Test", "movie": {"tmdbId": 1}})
    assert event.is_import is False
    assert event.tmdb == 1


def test_missing_and_invalid_fields() -> None:
    event = parse_webhook({})
    assert event == ArrEvent(event=None, tmdb=None, tvdb=None)

    # Non-string event, non-dict sections, non-numeric and non-positive ids.
    event = parse_webhook(
        {"eventType": 5, "movie": "nope", "series": {"tvdbId": "abc"}}
    )
    assert event.event is None
    assert event.tmdb is None
    assert event.tvdb is None

    event = parse_webhook({"eventType": "Download", "movie": {"tmdbId": 0}})
    assert event.tmdb is None
    event = parse_webhook({"eventType": "Download", "movie": {"tmdbId": None}})
    assert event.tmdb is None
