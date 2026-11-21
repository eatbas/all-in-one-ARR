"""Remindarr engine: refresh, store and serve unwatched-episode reminders.

A refresh reads Sonarr (series, tags, episodes, episode files) and Plex (TV
sections, show GUIDs, matched shows' episodes) entirely into memory, then
replaces the stored results in one transaction. Any upstream failure leaves
the previous results untouched and records the error, so the page and the nav
badge keep showing the last good data, flagged as stale.

Nothing is ever written to Sonarr or Plex. A disabled module makes no upstream
call at all: the scheduled job is a silent no-op and a manual run returns
``{"status": "disabled"}``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from core.app_metrics import record_remindarr_run, update_remindarr_counts
from core.clients.plex import PlexClientError, PlexEpisode
from core.clients.servarr import ServarrClientError, series_slug
from core.coerce import coerce_int, stripped_text
from core.logging import get_logger
from core.timefmt import utcnow_iso
from modules.remindarr.client import (
    RemindarrClientError,
    RemindarrSonarrClient,
    client_for,
)
from modules.remindarr.matching import (
    SeriesGroup,
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
from modules.remindarr.models import (
    PlexMatch,
    ReminderEpisode,
    RunSummary,
    TrackedSeries,
)

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext, SyncGate

_log = get_logger("remindarr")

# Concurrent per-series Sonarr reads and per-show Plex ``allLeaves`` reads.
_SONARR_CONCURRENCY = 4
_PLEX_CONCURRENCY = 4

# Errors that mean "an upstream service could not be read"; they never publish
# a partial result.
UPSTREAM_ERRORS = (ServarrClientError, PlexClientError)

_UNMATCHED_REASONS = {
    "no_tvdb_id": "No TVDB id in Sonarr",
    "not_in_plex": "No Plex show with this TVDB id",
}


class RemindarrTagError(ValueError):
    """Raised when a newly selected tag id is unknown to Sonarr."""


@dataclass(frozen=True)
class _SeriesData:
    """One tracked series' downloaded episodes and their files' ``dateAdded``."""

    series: dict[str, Any]
    episodes: list[dict[str, Any]]
    added_at: dict[int, str | None]

    @property
    def series_id(self) -> int:
        return coerce_int(self.series.get("id"), 0)

    @property
    def tvdb_id(self) -> int | None:
        tvdb_id = coerce_int(self.series.get("tvdbId"), 0)
        return tvdb_id if tvdb_id > 0 else None

    def file_added_at(self, episode: dict[str, Any]) -> str | None:
        return self.added_at.get(coerce_int(episode.get("episodeFileId"), 0))


@dataclass(frozen=True)
class _Collected:
    """Everything one refresh read, before it is turned into rows."""

    series: list[_SeriesData]
    plex_index: dict[int, list[str]]
    plex_episodes: dict[str, list[PlexEpisode]]
    missing_tag_ids: list[int]


def _local_now() -> datetime:
    """Return the current time in the container's local zone (``TZ``)."""
    return datetime.now().astimezone()


async def _bounded_gather[T](
    factories: list[Callable[[], Awaitable[T]]], limit: int
) -> list[T]:
    """Run ``factories`` with at most ``limit`` in flight; re-raise the first error.

    ``return_exceptions`` keeps every task awaited even when one fails, so no
    request is left running; the first failure is then re-raised.
    """
    semaphore = asyncio.Semaphore(limit)

    async def bounded(factory: Callable[[], Awaitable[T]]) -> T:
        async with semaphore:
            return await factory()

    outcomes = await asyncio.gather(
        *(bounded(factory) for factory in factories), return_exceptions=True
    )
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    return cast("list[T]", outcomes)


def _build_group(data: _SeriesData, collected: _Collected) -> SeriesGroup:
    """Match one series to Plex and build its tracked row and reminders."""
    tvdb_id = data.tvdb_id
    rating_keys = collected.plex_index.get(tvdb_id, []) if tvdb_id else []
    pending: list[dict[str, Any]] = []
    not_in_plex = 0
    plex_match: PlexMatch
    if tvdb_id is None:
        plex_match = "no_tvdb_id"
    elif not rating_keys:
        plex_match = "not_in_plex"
    else:
        plex_match = "matched"
        pending, not_in_plex = unwatched(
            data.episodes, [collected.plex_episodes[key] for key in rating_keys]
        )
    reminders = [
        reminder_episode(
            episode, series_id=data.series_id, added_at=data.file_added_at(episode)
        )
        for episode in pending
    ]
    latest = latest_timestamp(item.added_at for item in reminders) or (
        latest_timestamp(data.file_added_at(episode) for episode in data.episodes)
    )
    tracked = TrackedSeries(
        series_id=data.series_id,
        series_title=stripped_text(data.series.get("title")) or "Unknown series",
        series_slug=series_slug(data.series),
        tvdb_id=tvdb_id,
        plex_match=plex_match,
        episodes_not_in_plex=not_in_plex,
        latest_added_at=latest,
    )
    return tracked, reminders


def _episode_dict(episode: ReminderEpisode, now_local: datetime) -> dict[str, Any]:
    """Serialise one stored reminder, computing "new today" at read time."""
    return {
        **episode.to_row(),
        "label": episode.label,
        "new_today": is_new_today(episode.added_at, now_local),
    }


def _group_dict(group: SeriesGroup, now_local: datetime) -> dict[str, Any]:
    """Serialise one series group with its episodes."""
    series, episodes = group
    serialised = [_episode_dict(episode, now_local) for episode in episodes]
    return {
        "series_id": series.series_id,
        "series_title": series.series_title,
        "series_slug": series.series_slug,
        "tvdb_id": series.tvdb_id,
        "episodes_not_in_plex": series.episodes_not_in_plex,
        "latest_added_at": series.latest_added_at,
        "new_today": sum(1 for item in serialised if item["new_today"]),
        "episodes": serialised,
    }


def _has_details(group: SeriesGroup) -> bool:
    """Whether a matched series has unwatched episodes or episodes not in Plex.

    A series whose unwatched episodes are all watched still has a group while
    Plex does not list some of its downloaded episodes, so that count stays
    visible. Unmatched series carry neither and are listed separately.
    """
    series, episodes = group
    return bool(episodes) or series.episodes_not_in_plex > 0


def _unmatched_dict(series: TrackedSeries) -> dict[str, Any]:
    """Serialise one series that could not be matched to Plex."""
    return {
        "series_id": series.series_id,
        "series_title": series.series_title,
        "series_slug": series.series_slug,
        "tvdb_id": series.tvdb_id,
        "reason": series.plex_match,
        "reason_label": _UNMATCHED_REASONS[series.plex_match],
    }


class RemindarrService:
    """Owns Remindarr refreshes and result reads for one app process."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    @property
    def gate(self) -> SyncGate:
        """The gate keeping scheduled and manual refreshes from overlapping."""
        return self._ctx.remindarr_gate

    # ---- read ----

    def settings(self) -> dict[str, Any]:
        """Return the persisted Remindarr settings."""
        return self._ctx.settings_store.remindarr_settings()

    def plex_configured(self) -> bool:
        """Whether a Plex URL and token are stored (no request is made)."""
        url, token = self._ctx.settings_store.service_connection("plex")
        return bool(url and token)

    async def status(self) -> dict[str, Any]:
        """Return settings, run state and stored counts; never calls upstream."""
        run_state = self._ctx.db.remindarr_run_state()
        return {
            "settings": self.settings(),
            "running": self.gate.is_running(),
            "plex_configured": self.plex_configured(),
            "last_success_at": run_state["last_success_at"],
            "last_attempt_at": run_state["last_attempt_at"],
            "last_error": run_state["last_error"],
            "stale": run_state["last_error"] is not None,
            "missing_tag_ids": run_state["missing_tag_ids"],
            "counts": self._ctx.db.remindarr_counts(),
        }

    async def tags(self) -> list[dict[str, Any]]:
        """Return Sonarr's tags as ``{id, label}``, sorted by label (live read)."""
        client = client_for(self._ctx)
        try:
            tags = await client.tags()
        finally:
            await client.aclose()
        options = [
            {"id": tag_id, "label": label}
            for tag in tags
            if (tag_id := coerce_int(tag.get("id"), 0)) > 0
            and (label := stripped_text(tag.get("label")))
        ]
        return sorted(options, key=lambda option: option["label"].casefold())

    async def results(self) -> dict[str, Any]:
        """Return the stored results grouped by series, newest first.

        ``series`` holds every matched series with unwatched episodes or
        episodes not in Plex (its ``episodes`` may be empty); ``unmatched``
        holds the series whose watch state is unknown.
        """
        by_series: dict[int, list[ReminderEpisode]] = {}
        for row in self._ctx.db.remindarr_episode_rows():
            episode = ReminderEpisode.from_row(row)
            by_series.setdefault(episode.series_id, []).append(episode)
        tracked = [
            TrackedSeries.from_row(row) for row in self._ctx.db.remindarr_series_rows()
        ]
        groups = order_groups(
            (series, by_series.get(series.series_id, [])) for series in tracked
        )
        now_local = _local_now()
        return {
            "last_success_at": self._ctx.db.remindarr_run_state()["last_success_at"],
            "series": [
                _group_dict(group, now_local) for group in groups if _has_details(group)
            ],
            "unmatched": [
                _unmatched_dict(series)
                for series, _ in groups
                if series.plex_match != "matched"
            ],
        }

    # ---- refresh ----

    async def run_now(self) -> dict[str, Any]:
        """Refresh now; raises ``SyncAlreadyRunning`` if a refresh is in progress.

        Disabled returns ``{"status": "disabled"}`` without any upstream call.
        Upstream failures are recorded and re-raised for the API to map to 502.
        """
        if not self.settings()["enabled"]:
            record_remindarr_run(status="skipped")
            return RunSummary("disabled").to_dict()
        summary = await self.gate.try_run(self._refresh)
        return summary.to_dict()

    async def scheduled_run(self) -> None:
        """Scheduled refresh body; the caller must hold the gate.

        Disabled is a silent no-op. A failure is already recorded (run state,
        activity and metrics) by :meth:`_refresh`, so it is not re-raised.
        """
        if not self.settings()["enabled"]:
            record_remindarr_run(status="skipped")
            return
        try:
            await self._refresh()
        except UPSTREAM_ERRORS as exc:
            _log.warning("scheduled Remindarr refresh failed: %s", exc)

    async def _refresh(self) -> RunSummary:
        """Collect, then atomically replace the results. The caller holds the gate."""
        previous = self._ctx.db.remindarr_run_state()
        previous_unwatched = self._ctx.db.remindarr_counts()["unwatched"]
        try:
            collected = await self._collect(self.settings())
        except UPSTREAM_ERRORS as exc:
            self._record_failure(previous, str(exc))
            raise
        groups = [_build_group(data, collected) for data in collected.series]
        self._ctx.db.remindarr_replace_results(
            [series.to_row() for series, _ in groups],
            [episode.to_row() for _, episodes in groups for episode in episodes],
        )
        counts = self._ctx.db.remindarr_counts()
        self._record_success(previous, previous_unwatched, counts, collected)
        return RunSummary(
            "success",
            unwatched=counts["unwatched"],
            series_with_unwatched=counts["series_with_unwatched"],
            tracked_series=counts["tracked_series"],
            unmatched_series=counts["unmatched_series"],
        )

    async def _collect(self, settings: dict[str, Any]) -> _Collected:
        """Read Sonarr, then Plex, into memory; raise on any upstream failure."""
        client = client_for(self._ctx)
        try:
            compatibility = await client.compatibility()
            if not compatibility.ok:
                raise RemindarrClientError(compatibility.detail)
            if not self.plex_configured():
                raise PlexClientError("Plex is not connected")
            tag_ids = list(settings["tag_ids"])
            known = {coerce_int(tag.get("id"), 0) for tag in await client.tags()}
            selected = select_series(
                await client.series(), tag_ids, settings["monitored_only"]
            )
            series = await _bounded_gather(
                [
                    self._series_reader(client, item, settings["monitored_only"])
                    for item in selected
                ],
                _SONARR_CONCURRENCY,
            )
        finally:
            await client.aclose()
        plex_index, plex_episodes = await self._read_plex(series)
        return _Collected(
            series=series,
            plex_index=plex_index,
            plex_episodes=plex_episodes,
            missing_tag_ids=[tag_id for tag_id in tag_ids if tag_id not in known],
        )

    @staticmethod
    def _series_reader(
        client: RemindarrSonarrClient, series: dict[str, Any], monitored_only: bool
    ) -> Callable[[], Awaitable[_SeriesData]]:
        """Return a factory reading one series' downloaded episodes and files."""

        async def read() -> _SeriesData:
            series_id = coerce_int(series.get("id"), 0)
            episodes = downloaded_episodes(
                await client.episodes(series_id), monitored_only
            )
            files = await client.episode_files(series_id) if episodes else []
            added_at = {
                coerce_int(item.get("id"), 0): normalise_timestamp(
                    item.get("dateAdded")
                )
                for item in files
            }
            return _SeriesData(series=series, episodes=episodes, added_at=added_at)

        return read

    async def _read_plex(
        self, series: list[_SeriesData]
    ) -> tuple[dict[int, list[str]], dict[str, list[PlexEpisode]]]:
        """Index Plex's TV shows by TVDB id and read the tracked ones' episodes.

        ``allLeaves`` is fetched only for shows matched to a tracked series. With
        nothing tracked, Plex is not read at all.
        """
        if not series:
            return {}, {}
        plex = self._ctx.plex
        shows = [
            show
            for section in await plex.show_sections()
            for show in await plex.shows(section)
        ]
        index = index_plex_shows(shows)
        keys = list(
            dict.fromkeys(
                key
                for data in series
                if data.tvdb_id is not None
                for key in index.get(data.tvdb_id, [])
            )
        )

        def reader(key: str) -> Callable[[], Awaitable[list[PlexEpisode]]]:
            return lambda: plex.episodes(key)

        episodes = await _bounded_gather(
            [reader(key) for key in keys], _PLEX_CONCURRENCY
        )
        return index, dict(zip(keys, episodes, strict=True))

    # ---- run state, activity and metrics ----

    def _record_failure(self, previous: dict[str, Any], error: str) -> None:
        """Keep the old results, mark them stale and log the first failure only."""
        self._ctx.db.remindarr_set_run_state(
            last_success_at=previous["last_success_at"],
            last_attempt_at=utcnow_iso(),
            last_error=error,
            missing_tag_ids=previous["missing_tag_ids"],
        )
        record_remindarr_run(status="error")
        if previous["last_error"] is None:
            self._ctx.db.add_activity("Remindarr refresh failed", error)

    def _record_success(
        self,
        previous: dict[str, Any],
        previous_unwatched: int,
        counts: dict[str, int],
        collected: _Collected,
    ) -> None:
        """Clear the error and log recovery or a changed unwatched count."""
        now = utcnow_iso()
        self._ctx.db.remindarr_set_run_state(
            last_success_at=now,
            last_attempt_at=now,
            last_error=None,
            missing_tag_ids=collected.missing_tag_ids,
        )
        record_remindarr_run(status="success")
        update_remindarr_counts(
            unwatched=counts["unwatched"], unmatched_series=counts["unmatched_series"]
        )
        detail = (
            f"{counts['unwatched']} unwatched episode(s) across "
            f"{counts['tracked_series']} tracked series; "
            f"{counts['unmatched_series']} not found in Plex."
        )
        if previous["last_error"] is not None:
            self._ctx.db.add_activity("Remindarr refresh recovered", detail)
        elif counts["unwatched"] != previous_unwatched:
            self._ctx.db.add_activity("Remindarr reminders updated", detail)

    # ---- settings ----

    async def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Validate newly added tags against Sonarr, persist and return settings.

        Only ids not already saved are checked, so a tag Sonarr has since deleted
        can always be kept or unchecked. Raises :class:`RemindarrTagError` for an
        unknown new id, or a Servarr error when Sonarr cannot be read.
        """
        tag_ids = updates.get("tag_ids")
        if tag_ids is not None:
            saved = set(self.settings()["tag_ids"])
            added = [tag_id for tag_id in tag_ids if tag_id not in saved]
            if added:
                await self._require_known_tags(added)
        settings = self._ctx.settings_store.update_remindarr_settings(updates)
        self._ctx.db.add_activity(
            "Remindarr settings saved", "Remindarr settings updated"
        )
        return settings

    async def _require_known_tags(self, tag_ids: list[int]) -> None:
        """Raise :class:`RemindarrTagError` if Sonarr does not know every id."""
        known = {option["id"] for option in await self.tags()}
        unknown = [tag_id for tag_id in tag_ids if tag_id not in known]
        if unknown:
            noun = "id" if len(unknown) == 1 else "ids"
            raise RemindarrTagError(
                f"Unknown Sonarr tag {noun}: "
                + ", ".join(str(item) for item in unknown)
            )
