"""Typed Remindarr models shared by the matcher, the engine and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

# Why a tracked series is or is not matched to a Plex show.
PlexMatch = Literal["matched", "no_tvdb_id", "not_in_plex"]
RunStatus = Literal["success", "disabled"]


@dataclass(frozen=True)
class TrackedSeries:
    """One Sonarr series in scope (monitored if required, carrying a selected tag).

    ``episodes_not_in_plex`` counts downloaded episodes of a matched series that
    Plex does not list (not scanned yet, or numbered differently); they are never
    reported as unwatched. ``latest_added_at`` orders the series groups.
    """

    series_id: int
    series_title: str
    series_slug: str | None
    tvdb_id: int | None
    plex_match: PlexMatch
    episodes_not_in_plex: int
    latest_added_at: str | None

    def to_row(self) -> dict[str, Any]:
        """Return the ``remindarr_series`` row for this series."""
        return {
            "series_id": self.series_id,
            "series_title": self.series_title,
            "series_slug": self.series_slug,
            "tvdb_id": self.tvdb_id,
            "plex_match": self.plex_match,
            "episodes_not_in_plex": self.episodes_not_in_plex,
            "latest_added_at": self.latest_added_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> TrackedSeries:
        """Rebuild a series from its stored row."""
        return cls(
            series_id=int(row["series_id"]),
            series_title=str(row["series_title"]),
            series_slug=row["series_slug"],
            tvdb_id=row["tvdb_id"],
            plex_match=row["plex_match"],
            episodes_not_in_plex=int(row["episodes_not_in_plex"]),
            latest_added_at=row["latest_added_at"],
        )


@dataclass(frozen=True)
class ReminderEpisode:
    """One downloaded episode the Plex token owner has not watched.

    ``added_at`` is the Sonarr episode file's ``dateAdded`` (UTC ISO-8601); it
    drives "new today", which is computed when the results are read.
    """

    episode_id: int
    series_id: int
    episode_file_id: int
    season_number: int
    episode_number: int
    title: str
    air_date_utc: str | None
    added_at: str | None

    @property
    def label(self) -> str:
        """Return the ``S01E03`` label shown on the page."""
        return f"S{self.season_number:02d}E{self.episode_number:02d}"

    def to_row(self) -> dict[str, Any]:
        """Return the ``remindarr_episodes`` row for this episode."""
        return {
            "episode_id": self.episode_id,
            "series_id": self.series_id,
            "episode_file_id": self.episode_file_id,
            "season_number": self.season_number,
            "episode_number": self.episode_number,
            "title": self.title,
            "air_date_utc": self.air_date_utc,
            "added_at": self.added_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ReminderEpisode:
        """Rebuild an episode from its stored row."""
        return cls(
            episode_id=int(row["episode_id"]),
            series_id=int(row["series_id"]),
            episode_file_id=int(row["episode_file_id"]),
            season_number=int(row["season_number"]),
            episode_number=int(row["episode_number"]),
            title=str(row["title"]),
            air_date_utc=row["air_date_utc"],
            added_at=row["added_at"],
        )


@dataclass(frozen=True)
class RunSummary:
    """Outcome of one manual refresh, returned by ``POST /api/remindarr/run``."""

    status: RunStatus
    unwatched: int = 0
    series_with_unwatched: int = 0
    tracked_series: int = 0
    unmatched_series: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "unwatched": self.unwatched,
            "series_with_unwatched": self.series_with_unwatched,
            "tracked_series": self.tracked_series,
            "unmatched_series": self.unmatched_series,
        }
