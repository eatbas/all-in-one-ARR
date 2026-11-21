"""Tests for Remindarr's pure matching rules and models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.clients.plex import PlexEpisode, PlexShow
from modules.remindarr.matching import (
    downloaded_episodes,
    index_plex_shows,
    is_new_today,
    latest_timestamp,
    normalise_timestamp,
    order_groups,
    reminder_episode,
    select_series,
    unwatched,
)
from modules.remindarr.models import ReminderEpisode, RunSummary, TrackedSeries


def _episode(season: int, number: int, **extra: object) -> dict[str, object]:
    return {"seasonNumber": season, "episodeNumber": number, **extra}


def _tracked(series_id: int, title: str, latest: str | None) -> TrackedSeries:
    return TrackedSeries(series_id, title, None, None, "matched", 0, latest)


def _reminder(episode_id: int, season: int, number: int, aired: str | None):
    return ReminderEpisode(episode_id, 1, 1, season, number, "", aired, None)


# ---- scope ----


def test_select_series_matches_any_selected_tag() -> None:
    series = [
        {"id": 1, "tags": [1]},
        {"id": 2, "tags": [2, 5]},
        {"id": 3, "tags": [3]},
        {"id": 4, "tags": "1"},
        {"id": 5, "tags": [True]},
        {"id": 6},
    ]
    selected = select_series(series, [1, 2], monitored_only=False)
    assert [item["id"] for item in selected] == [1, 2]


def test_select_series_with_no_tags_tracks_nothing() -> None:
    assert select_series([{"id": 1, "tags": [1]}], [], monitored_only=False) == []


def test_select_series_respects_monitored_only() -> None:
    series = [
        {"id": 1, "tags": [1], "monitored": True},
        {"id": 2, "tags": [1], "monitored": False},
        {"id": 3, "tags": [1]},
    ]
    assert [item["id"] for item in select_series(series, [1], True)] == [1, 3]
    assert [item["id"] for item in select_series(series, [1], False)] == [1, 2, 3]


def test_downloaded_episodes_need_a_file_and_monitoring_when_required() -> None:
    episodes = [
        {"id": 1, "episodeFileId": 10, "monitored": True},
        {"id": 2, "episodeFileId": 0, "monitored": True},
        {"id": 3, "monitored": True},
        {"id": 4, "episodeFileId": 11, "monitored": False},
        {"id": 5, "episodeFileId": "bad"},
    ]
    assert [item["id"] for item in downloaded_episodes(episodes, True)] == [1]
    assert [item["id"] for item in downloaded_episodes(episodes, False)] == [1, 4]


# ---- Plex matching ----


def test_index_plex_shows_maps_every_tvdb_id_to_unique_keys() -> None:
    shows = [
        PlexShow("100", "Show", frozenset({11})),
        PlexShow("200", "Show 4K", frozenset({11, 12})),
        PlexShow("100", "Show (dupe)", frozenset({11})),
        PlexShow("300", "No ids", frozenset()),
    ]
    assert index_plex_shows(shows) == {11: ["100", "200"], 12: ["200"]}


def test_unwatched_splits_watched_unwatched_and_not_in_plex() -> None:
    sonarr = [_episode(1, 1), _episode(1, 2), _episode(1, 3), _episode(2, 1)]
    plex = [[PlexEpisode(1, 1, 1), PlexEpisode(1, 2, 0), PlexEpisode(2, 1, 0)]]
    pending, not_in_plex = unwatched(sonarr, plex)
    assert pending == [_episode(1, 2), _episode(2, 1)]
    assert not_in_plex == 1


def test_watched_in_any_matched_item_counts_as_watched() -> None:
    sonarr = [_episode(1, 1), _episode(1, 2)]
    plex = [
        [PlexEpisode(1, 1, 0), PlexEpisode(1, 2, 0)],
        [PlexEpisode(1, 1, 3)],
        [PlexEpisode(1, 1, 0)],
    ]
    pending, not_in_plex = unwatched(sonarr, plex)
    assert pending == [_episode(1, 2)]
    assert not_in_plex == 0


def test_unwatched_with_no_plex_items_counts_everything_missing() -> None:
    assert unwatched([_episode(1, 1)], []) == ([], 1)


# ---- timestamps and "new today" ----


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-21T08:12:00Z", "2026-11-21T08:12:00+00:00"),
        ("2026-11-21T10:12:00.123+02:00", "2026-11-21T08:12:00+00:00"),
        ("2026-11-21T08:12:00", None),
        ("not a date", None),
        ("", None),
        (None, None),
        (17, None),
    ],
)
def test_normalise_timestamp(value: object, expected: str | None) -> None:
    assert normalise_timestamp(value) == expected


def test_new_today_rolls_over_at_local_midnight() -> None:
    zone = timezone(timedelta(hours=3))
    now = datetime(2026, 11, 21, 0, 30, tzinfo=zone)
    # 21:00 UTC on the 20th is exactly local midnight on the 21st.
    assert is_new_today("2026-11-20T21:00:00Z", now) is True
    assert is_new_today("2026-11-20T20:59:59Z", now) is False
    assert is_new_today("2026-11-21T20:59:59Z", now) is True
    assert is_new_today("2026-11-21T21:00:00Z", now) is False
    assert is_new_today(None, now) is False
    assert is_new_today("garbage", now) is False


def test_reminder_episode_reads_sonarr_fields() -> None:
    episode = {
        "id": 7,
        "episodeFileId": 70,
        "seasonNumber": 3,
        "episodeNumber": 8,
        "title": "  The Second Trial ",
        "airDateUtc": "2026-11-20T09:00:00Z",
    }
    reminder = reminder_episode(episode, series_id=1, added_at="x")
    assert reminder == ReminderEpisode(
        7, 1, 70, 3, 8, "The Second Trial", "2026-11-20T09:00:00+00:00", "x"
    )
    assert reminder.label == "S03E08"
    assert ReminderEpisode.from_row(reminder.to_row()) == reminder


def test_latest_timestamp_ignores_missing_values() -> None:
    assert latest_timestamp([None, "2026-01-02", "2026-01-03", None]) == "2026-01-03"
    assert latest_timestamp([None]) is None
    assert latest_timestamp([]) is None


# ---- ordering ----


def test_order_groups_newest_series_and_newest_aired_episodes_first() -> None:
    older = _tracked(1, "beta", "2026-11-19T00:00:00+00:00")
    newest = _tracked(2, "Zeta", "2026-11-21T00:00:00+00:00")
    tie_a = _tracked(3, "alpha", "2026-11-20T00:00:00+00:00")
    tie_b = _tracked(4, "Bravo", "2026-11-20T00:00:00+00:00")
    undated = _tracked(5, "Aardvark", None)
    episodes = [
        _reminder(1, 1, 1, "2026-11-01T00:00:00+00:00"),
        _reminder(2, 1, 3, None),
        _reminder(3, 1, 2, "2026-11-08T00:00:00+00:00"),
        _reminder(4, 2, 1, "2026-11-08T00:00:00+00:00"),
    ]
    ordered = order_groups(
        [(older, episodes), (undated, []), (tie_b, []), (newest, []), (tie_a, [])]
    )
    assert [series.series_id for series, _ in ordered] == [2, 3, 4, 1, 5]
    assert [episode.episode_id for episode in ordered[3][1]] == [4, 3, 1, 2]


# ---- models ----


def test_tracked_series_round_trips_through_its_row() -> None:
    series = TrackedSeries(1, "Show", "show", 99, "not_in_plex", 2, None)
    assert TrackedSeries.from_row(series.to_row()) == series


def test_run_summary_to_dict() -> None:
    assert RunSummary("disabled").to_dict() == {
        "status": "disabled",
        "unwatched": 0,
        "series_with_unwatched": 0,
        "tracked_series": 0,
        "unmatched_series": 0,
    }


def test_new_today_uses_the_given_zone_not_utc() -> None:
    now = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    assert is_new_today("2026-11-21T00:00:00Z", now) is True
