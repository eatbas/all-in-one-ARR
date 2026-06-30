"""Group normalised Findarr items into Sonarr/Radarr search-command units.

The engine normalises each wanted record into a :class:`FindarrItem` (one
episode or one movie). This module folds those items into :class:`SearchUnit`s
at the granularity the user picked for the mode — every episode on its own
(``episodes``), one unit per (series, season) (``seasons``), or one unit per
series (``shows``) — so the engine can dedup, count, and issue commands at a
single consistent granularity. Radarr always groups one unit per movie.
"""

from __future__ import annotations

from modules.findarr.models import (
    RADARR_COMMAND,
    SONARR_COMMANDS,
    FindarrItem,
    SearchUnit,
)


def build_units(
    app: str, mode: str, items: list[FindarrItem], granularity: str
) -> list[SearchUnit]:
    """Fold normalised items into search units for the chosen granularity."""
    if app == "radarr":
        return [_movie_unit(mode, item) for item in items]
    if granularity == "seasons":
        return _grouped_units(mode, items, by_season=True)
    if granularity == "shows":
        return _grouped_units(mode, items, by_season=False)
    return [_episode_unit(mode, item) for item in items]


def _movie_unit(mode: str, item: FindarrItem) -> SearchUnit:
    return SearchUnit(
        app="radarr",
        mode=mode,
        command=RADARR_COMMAND,
        key=item.item_id,
        title=item.title,
        monitored=item.monitored,
        is_future=item.is_future,
        movie_ids=(int(item.item_id),),
    )


def _episode_unit(mode: str, item: FindarrItem) -> SearchUnit:
    return SearchUnit(
        app="sonarr",
        mode=mode,
        command=SONARR_COMMANDS["episodes"],
        key=item.item_id,
        title=item.title,
        monitored=item.monitored,
        is_future=item.is_future,
        episode_ids=(int(item.item_id),),
    )


def _grouped_units(
    mode: str, items: list[FindarrItem], *, by_season: bool
) -> list[SearchUnit]:
    """Build one unit per (series, season) when ``by_season`` else per series.

    Items without a resolvable series id (or season, for season packs) cannot
    target a season/series command and are dropped; episode-mode is the safe
    fallback for those. Insertion order is preserved so the per-cycle limit is
    deterministic.
    """
    groups: dict[tuple[int, int | None], list[FindarrItem]] = {}
    order: list[tuple[int, int | None]] = []
    for item in items:
        if item.series_id is None:
            continue
        if by_season and item.season_number is None:
            continue
        group_key = (item.series_id, item.season_number if by_season else None)
        if group_key not in groups:
            groups[group_key] = []
            order.append(group_key)
        groups[group_key].append(item)

    units: list[SearchUnit] = []
    for series_id, season in order:
        members = groups[(series_id, season)]
        series_label = _series_label(members)
        if by_season:
            command = SONARR_COMMANDS["seasons"]
            key = f"{series_id}:s{season}"
            title = f"{series_label} — Season {season}"
        else:
            command = SONARR_COMMANDS["shows"]
            key = str(series_id)
            title = series_label
        units.append(
            SearchUnit(
                app="sonarr",
                mode=mode,
                command=command,
                key=key,
                title=title,
                monitored=any(member.monitored for member in members),
                is_future=all(member.is_future for member in members),
                series_id=series_id,
                season_number=season if by_season else None,
            )
        )
    return units


def _series_label(members: list[FindarrItem]) -> str:
    """Series title with its year when known (e.g. ``"Show (2024)"``).

    Falls back to ``"Unknown series"`` when no member carries a title; the year
    is appended only when a member resolves it, keeping seasons/shows unit titles
    consistent with the per-episode label built in :mod:`modules.findarr.sonarr`.
    """
    title: str | None = None
    year: int | None = None
    for member in members:
        if title is None and member.series_title:
            title = member.series_title
        if year is None and member.series_year:
            year = member.series_year
    base = title or "Unknown series"
    return f"{base} ({year})" if year is not None else base
