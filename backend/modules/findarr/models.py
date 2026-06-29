"""Shared Findarr domain models."""

from __future__ import annotations

from dataclasses import dataclass

APP_NAMES = ("sonarr", "radarr")
MODES = ("missing", "upgrade")

# Sonarr search-mode granularities offered per mode and the native Sonarr v3
# command each one issues. ``episodes`` searches individual episodes,
# ``seasons`` issues one season-pack search per (series, season), and ``shows``
# issues one search per series. Radarr has no season/show concept, so it always
# uses the movie command regardless of these settings.
SEARCH_MODES = ("episodes", "seasons", "shows")
SONARR_COMMANDS = {
    "episodes": "EpisodeSearch",
    "seasons": "SeasonSearch",
    "shows": "SeriesSearch",
}
RADARR_COMMAND = "MoviesSearch"


@dataclass(frozen=True)
class FindarrItem:
    """One normalised Sonarr/Radarr wanted record eligible for a search.

    For Sonarr this is a single episode; ``series_id``/``season_number``/
    ``series_title`` carry the grouping keys used to build season-pack and
    series-level searches. For Radarr (a movie) those stay ``None``.
    """

    app: str
    mode: str
    item_id: str
    title: str
    monitored: bool
    is_future: bool
    series_id: int | None = None
    season_number: int | None = None
    series_title: str | None = None


@dataclass(frozen=True)
class SearchUnit:
    """A single grouped Findarr search command and its processed-state identity.

    ``key`` is the processed-state identifier for the chosen granularity
    (an episode id, ``"<seriesId>:s<season>"``, a bare ``"<seriesId>"``, or a
    movie id) so dedup and history operate at the same granularity as the
    command that is sent.
    """

    app: str
    mode: str
    command: str
    key: str
    title: str
    monitored: bool
    is_future: bool
    episode_ids: tuple[int, ...] = ()
    movie_ids: tuple[int, ...] = ()
    series_id: int | None = None
    season_number: int | None = None


@dataclass(frozen=True)
class Compatibility:
    """Connected Servarr application compatibility result."""

    ok: bool
    app_name: str
    version: str
    detail: str


@dataclass
class ModeResult:
    """Result of one app/mode processing slice."""

    app: str
    mode: str
    scanned: int = 0
    selected: int = 0
    processed: int = 0
    skipped: int = 0
    detail: str = ""


@dataclass
class RunResult:
    """Aggregate Findarr run result."""

    status: str
    detail: str
    processed: int = 0
    results: list[ModeResult] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "detail": self.detail,
            "processed": self.processed,
            "results": [item.__dict__ for item in self.results or []],
        }
