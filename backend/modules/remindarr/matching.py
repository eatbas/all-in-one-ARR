"""Pure Remindarr matching rules: scope, Plex matching, watch state and order.

Nothing here performs I/O, so every rule is unit-testable on plain payloads:

* **Scope:** a Sonarr series is tracked when it carries **any** selected tag
  (and is monitored, when ``monitored_only``); within it only downloaded
  episodes (``episodeFileId > 0``) count, monitored ones when required.
* **Matching:** a series matches every Plex show whose ``Guid`` list carries
  its ``tvdb://`` id; episodes match by season and episode number.
* **Watch state:** an episode is watched when **any** matched Plex item has
  ``viewCount >= 1`` for it (a 4K copy in another library counts). An episode
  Plex does not list is counted as "not in Plex", never as unwatched.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from core.clients.plex import PlexEpisode, PlexShow
from core.coerce import coerce_int, stripped_text
from modules.remindarr.models import ReminderEpisode, TrackedSeries

SeriesGroup = tuple[TrackedSeries, list[ReminderEpisode]]


def _is_monitored(item: Mapping[str, Any]) -> bool:
    """Whether a Sonarr series or episode is monitored (missing means monitored)."""
    return bool(item.get("monitored", True))


def _tag_ids(series: Mapping[str, Any]) -> set[int]:
    """Return a Sonarr series' integer tag ids (anything else is ignored)."""
    tags = series.get("tags")
    if not isinstance(tags, list):
        return set()
    return {tag for tag in tags if isinstance(tag, int) and not isinstance(tag, bool)}


def select_series(
    series: Iterable[dict[str, Any]], tag_ids: Iterable[int], monitored_only: bool
) -> list[dict[str, Any]]:
    """Return the series carrying any of ``tag_ids`` (monitored when required).

    An empty selection tracks nothing: any-of semantics can only narrow scope.
    """
    wanted = set(tag_ids)
    if not wanted:
        return []
    return [
        item
        for item in series
        if _tag_ids(item) & wanted and (not monitored_only or _is_monitored(item))
    ]


def downloaded_episodes(
    episodes: Iterable[dict[str, Any]], monitored_only: bool
) -> list[dict[str, Any]]:
    """Return the episodes that have a file (monitored ones when required)."""
    return [
        episode
        for episode in episodes
        if coerce_int(episode.get("episodeFileId"), 0) > 0
        and (not monitored_only or _is_monitored(episode))
    ]


def index_plex_shows(shows: Iterable[PlexShow]) -> dict[int, list[str]]:
    """Map each TVDB id to the rating keys of every Plex show carrying it."""
    index: dict[int, list[str]] = {}
    for show in shows:
        for tvdb_id in show.tvdb_ids:
            keys = index.setdefault(tvdb_id, [])
            if show.rating_key not in keys:
                keys.append(show.rating_key)
    return index


def episode_key(episode: Mapping[str, Any]) -> tuple[int, int]:
    """Return a Sonarr episode's ``(seasonNumber, episodeNumber)``."""
    return (
        coerce_int(episode.get("seasonNumber"), -1),
        coerce_int(episode.get("episodeNumber"), -1),
    )


def unwatched(
    sonarr_episodes: Iterable[dict[str, Any]],
    plex_episodes_by_item: Iterable[Iterable[PlexEpisode]],
) -> tuple[list[dict[str, Any]], int]:
    """Split downloaded Sonarr episodes into unwatched ones and a not-in-Plex count.

    ``plex_episodes_by_item`` holds one episode list per matched Plex show. An
    episode is watched when any of them has watched it; one none of them lists
    is counted as not in Plex and left out of the unwatched list.
    """
    watched: dict[tuple[int, int], bool] = {}
    for item in plex_episodes_by_item:
        for plex_episode in item:
            key = (plex_episode.season, plex_episode.episode)
            watched[key] = watched.get(key, False) or plex_episode.view_count >= 1
    pending: list[dict[str, Any]] = []
    not_in_plex = 0
    for episode in sonarr_episodes:
        state = watched.get(episode_key(episode))
        if state is None:
            not_in_plex += 1
        elif not state:
            pending.append(episode)
    return pending, not_in_plex


def normalise_timestamp(value: Any) -> str | None:
    """Return an ISO-8601 timestamp as a second-precision UTC string.

    Sonarr writes ``2026-11-21T08:12:00Z``; anything unparsable (or naive,
    which carries no zone to convert from) yields ``None``.
    """
    text = stripped_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def is_new_today(added_at: str | None, now_local: datetime) -> bool:
    """Whether ``added_at`` falls on ``now_local``'s calendar day in its zone."""
    normalised = normalise_timestamp(added_at)
    if normalised is None:
        return False
    added = datetime.fromisoformat(normalised).astimezone(now_local.tzinfo)
    return added.date() == now_local.date()


def reminder_episode(
    episode: Mapping[str, Any], *, series_id: int, added_at: str | None
) -> ReminderEpisode:
    """Build the stored reminder for one unwatched Sonarr episode."""
    season, number = episode_key(episode)
    return ReminderEpisode(
        episode_id=coerce_int(episode.get("id"), 0),
        series_id=series_id,
        episode_file_id=coerce_int(episode.get("episodeFileId"), 0),
        season_number=season,
        episode_number=number,
        title=stripped_text(episode.get("title")),
        air_date_utc=normalise_timestamp(episode.get("airDateUtc")),
        added_at=added_at,
    )


def latest_timestamp(values: Iterable[str | None]) -> str | None:
    """Return the newest of normalised UTC timestamps, ignoring ``None``."""
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _episode_order(episode: ReminderEpisode) -> tuple[str, int, int]:
    """Air date, then season and episode; a missing air date sorts last."""
    return (episode.air_date_utc or "", episode.season_number, episode.episode_number)


def order_groups(groups: Iterable[SeriesGroup]) -> list[SeriesGroup]:
    """Order series newest first and each series' episodes newest aired first.

    Series sort by ``latest_added_at`` descending (missing last), ties by
    title. Normalised timestamps share one format, so they compare as text.
    """
    ordered = [
        (series, sorted(episodes, key=_episode_order, reverse=True))
        for series, episodes in groups
    ]
    ordered.sort(key=lambda group: group[0].series_title.casefold())
    ordered.sort(key=lambda group: group[0].latest_added_at or "", reverse=True)
    return ordered
