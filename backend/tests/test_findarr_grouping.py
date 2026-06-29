"""Tests for Findarr search-unit grouping."""

from __future__ import annotations

from modules.findarr import grouping
from modules.findarr.models import FindarrItem


def _item(**overrides) -> FindarrItem:
    base = dict(
        app="sonarr",
        mode="missing",
        item_id="1",
        title="t",
        monitored=True,
        is_future=False,
        series_id=5,
        season_number=1,
        series_title="Show",
    )
    base.update(overrides)
    return FindarrItem(**base)


def test_build_units_episodes_emits_one_unit_per_item() -> None:
    units = grouping.build_units(
        "sonarr", "missing", [_item(item_id="1"), _item(item_id="2")], "episodes"
    )
    assert [unit.command for unit in units] == ["EpisodeSearch", "EpisodeSearch"]
    assert units[0].episode_ids == (1,)
    assert units[0].key == "1"


def test_build_units_radarr_emits_movie_units() -> None:
    item = FindarrItem(
        app="radarr", mode="missing", item_id="9", title="Movie", monitored=False, is_future=True
    )
    units = grouping.build_units("radarr", "missing", [item], "episodes")
    assert units[0].command == "MoviesSearch"
    assert units[0].movie_ids == (9,)
    assert units[0].key == "9"


def test_build_units_seasons_groups_and_aggregates() -> None:
    items = [
        _item(item_id="1", season_number=1, monitored=False, is_future=True),
        _item(item_id="2", season_number=1, monitored=True, is_future=False),
        _item(item_id="3", season_number=2),
        _item(item_id="4", series_id=None),  # dropped: no series id
        _item(item_id="5", season_number=None),  # dropped: no season for season packs
    ]
    units = grouping.build_units("sonarr", "missing", items, "seasons")
    assert [unit.key for unit in units] == ["5:s1", "5:s2"]
    season_one = units[0]
    assert season_one.command == "SeasonSearch"
    assert season_one.monitored is True  # any member monitored
    assert season_one.is_future is False  # not all members future
    assert season_one.title == "Show — Season 1"
    assert season_one.series_id == 5
    assert season_one.season_number == 1


def test_build_units_shows_groups_by_series() -> None:
    items = [
        _item(item_id="1", season_number=1),
        _item(item_id="2", season_number=2),
        _item(item_id="3", series_id=None),  # dropped: no series id
    ]
    units = grouping.build_units("sonarr", "missing", items, "shows")
    assert len(units) == 1
    assert units[0].command == "SeriesSearch"
    assert units[0].key == "5"
    assert units[0].season_number is None


def test_build_units_falls_back_to_unknown_series_title() -> None:
    units = grouping.build_units("sonarr", "missing", [_item(series_title=None)], "shows")
    assert units[0].title == "Unknown series"
