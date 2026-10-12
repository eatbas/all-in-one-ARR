"""Languagarr engine: audit anime audio, queue replacement searches, guarded delete.

The audit reads each in-scope Sonarr episode file's real audio tracks and keeps
the files without an English audio track. Fixing them is two-tier:

* **Search** (default, never destructive): the file's episodes are queued and the
  scheduled worker sends bounded Sonarr ``EpisodeSearch`` commands. Sonarr replaces
  the file only when it imports a release that scores higher, so the old file
  stays until a better one exists.
* **Delete & search** (explicit, reviewed): for files Sonarr would never upgrade
  (custom-format score at or above the profile cutoff), the file is re-validated
  against Sonarr, deleted through Sonarr's API and its episodes searched at once.

With ``monitored_only`` (the default) unmonitored series are skipped and
unmonitored episodes are never searched: Sonarr runs API-triggered searches as
user-invoked, which would otherwise bypass its own monitored check.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.app_metrics import (
    record_languagarr_deletes,
    record_languagarr_scan,
    record_languagarr_searches,
)
from core.coerce import coerce_int
from core.logging import get_logger
from modules.languagarr.audio import file_audio_verdict
from modules.languagarr.client import (
    LanguagarrClientError,
    LanguagarrSonarrClient,
    client_for,
)
from modules.languagarr.models import AuditItem, ScanState, Scope
from modules.languagarr.worker import process_rows, run_result

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext, SyncGate

_log = get_logger("languagarr")

# Hard caps on a single request so one click can neither flood the queue nor
# delete more than a reviewable batch.
MAX_ENQUEUE_PER_REQUEST = 500
MAX_DELETE_PER_REQUEST = 25

# Concurrent per-series Sonarr requests during a scan.
_SCAN_CONCURRENCY = 4

# A retry-window bound that every timestamp sorts before, used when a reviewed
# delete must queue its search regardless of earlier attempts.
_ALWAYS_REQUEUE = "9999"

NO_SEARCHABLE_EPISODES = "No searchable episodes linked to file"


class LanguagarrScopeError(ValueError):
    """Raised when the configured quality profiles cannot be resolved in Sonarr."""


@dataclass(frozen=True)
class _DeleteOutcome:
    """Result of deleting and searching one reviewed file."""

    deleted: bool
    searched: bool
    error: str | None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _episode_label(season: int | None, numbers: list[int]) -> str:
    """Return ``S01E03`` or ``S01E03-E04`` for a file's episodes."""
    if season is None or not numbers:
        return "Episode"
    label = f"S{season:02d}E{numbers[0]:02d}"
    if len(numbers) > 1:
        label += f"-E{numbers[-1]:02d}"
    return label


def _audit_file(
    episode_file: dict[str, Any],
    *,
    series: dict[str, Any],
    episodes: list[dict[str, Any]],
    cutoff_format_score: int,
    monitored_only: bool,
) -> AuditItem | None:
    """Return an :class:`AuditItem` for a non-compliant file, else ``None``.

    The label covers every episode in the file; ``episode_ids`` (what a search
    targets) keeps only monitored episodes when ``monitored_only`` is set.
    """
    verdict, audio = file_audio_verdict(episode_file)
    if verdict.compliant:
        return None
    ordered = sorted(
        episodes, key=lambda episode: coerce_int(episode.get("episodeNumber"), 0)
    )
    numbers = [coerce_int(episode.get("episodeNumber"), 0) for episode in ordered]
    searchable = [
        episode
        for episode in ordered
        if not monitored_only or bool(episode.get("monitored", True))
    ]
    season_raw = episode_file.get("seasonNumber")
    season = coerce_int(season_raw, 0) if season_raw is not None else None
    score = coerce_int(episode_file.get("customFormatScore"), 0)
    languages = episode_file.get("languages")
    return AuditItem(
        episode_file_id=coerce_int(episode_file.get("id"), 0),
        series_id=coerce_int(series.get("id"), 0),
        series_title=str(series.get("title") or "Unknown series"),
        season_number=season,
        episode_ids=tuple(coerce_int(episode.get("id"), 0) for episode in searchable),
        episode_label=_episode_label(season, numbers),
        relative_path=str(episode_file.get("relativePath") or ""),
        path=str(episode_file.get("path") or ""),
        audio_languages=audio,
        sonarr_languages=tuple(
            str(language.get("name"))
            for language in (languages if isinstance(languages, list) else [])
            if isinstance(language, dict) and language.get("name")
        ),
        verdict=verdict.status,
        release_group=episode_file.get("releaseGroup") or None,
        custom_format_score=score,
        cutoff_format_score=cutoff_format_score,
        recommended_action=(
            "search" if score < cutoff_format_score else "delete_and_search"
        ),
        first_episode_number=numbers[0] if numbers else 0,
    )


class LanguagarrService:
    """Owns Languagarr scan state and Sonarr actions for one app process."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._state = ScanState()

    @property
    def gate(self) -> SyncGate:
        """The gate serialising scans, the search worker and reviewed deletes."""
        return self._ctx.languagarr_gate

    # ---- read ----

    def settings(self) -> dict[str, Any]:
        """Return the persisted Languagarr settings."""
        return self._ctx.settings_store.languagarr_settings()

    async def status(self) -> dict[str, Any]:
        """Return settings, scan summary, and queue counts."""
        return {
            "settings": self.settings(),
            "running": self.gate.is_running(),
            "scan": self._state.summary(),
            "queue": self._ctx.db.languagarr_queue_counts(),
        }

    async def results(self) -> dict[str, Any]:
        """Return the latest scan results joined with live queue status."""
        queue = self._ctx.db.languagarr_queue_status_map()

        def with_queue(item: AuditItem) -> dict[str, object]:
            data = item.to_dict()
            entry = queue.get(item.episode_file_id)
            if entry is not None:
                data["queue_status"] = entry["status"]
                data["last_searched_at"] = entry["searched_at"]
            return data

        return {
            "scan": self._state.summary(),
            "results": [with_queue(item) for item in self._state.results],
            "unknown": [item.to_dict() for item in self._state.unknown],
        }

    async def queue(self) -> dict[str, Any]:
        """Return queue counts and the most recent queue rows."""
        return {
            "counts": self._ctx.db.languagarr_queue_counts(),
            "rows": self._ctx.db.languagarr_queue_rows(),
        }

    # ---- scan ----

    async def scan(self) -> dict[str, Any]:
        """Run a manual scan; raises ``SyncAlreadyRunning`` if busy."""
        await self.gate.try_run(self._scan_unlocked)
        return await self.results()

    async def _scan_unlocked(self) -> None:
        """Audit every in-scope series. The caller must hold the gate."""
        state = self._state
        state.is_scanning = True
        state.last_error = None
        client = client_for(self._ctx)
        try:
            await self._audit(client, state)
        except (LanguagarrClientError, LanguagarrScopeError) as exc:
            state.last_error = str(exc)
            record_languagarr_scan(status="error")
            self._ctx.db.add_activity("Languagarr scan failed", str(exc))
            raise
        finally:
            state.is_scanning = False
            await client.aclose()
        pruned = self._ctx.db.languagarr_prune(
            item.episode_file_id for item in state.results
        )
        record_languagarr_scan(status="success", verdict_counts=state.verdict_counts())
        detail = (
            f"{len(state.results)} anime file(s) without English audio, "
            f"{len(state.unknown)} with unknown audio, across "
            f"{state.series_scanned} series."
        )
        if pruned:
            detail += (
                f" Removed {pruned} resolved queue entr{'y' if pruned == 1 else 'ies'}."
            )
        self._ctx.db.add_activity("Languagarr scan completed", detail)

    async def _scope(self, client: LanguagarrSonarrClient) -> Scope:
        """Resolve configured profile names to their ids and cutoff scores.

        A configured name Sonarr does not know is an error rather than being
        skipped, so a typo can never silently widen or empty the scope.
        """
        settings = self.settings()
        names = list(settings["quality_profile_names"])
        by_name = {
            str(profile.get("name")): profile
            for profile in await client.quality_profiles()
        }
        missing = [name for name in names if name not in by_name]
        if missing:
            raise LanguagarrScopeError(
                "Sonarr has no quality profile named " + ", ".join(missing)
            )
        cutoffs = {
            coerce_int(by_name[name].get("id"), 0): coerce_int(
                by_name[name].get("cutoffFormatScore"), 0
            )
            for name in names
        }
        return Scope(cutoffs, names, bool(settings["monitored_only"]))

    async def _audit(self, client: LanguagarrSonarrClient, state: ScanState) -> None:
        compatibility = await client.compatibility()
        if not compatibility.ok:
            raise LanguagarrClientError(compatibility.detail)
        scope = await self._scope(client)
        series_list = [
            series for series in await client.series() if scope.includes(series)
        ]
        semaphore = asyncio.Semaphore(_SCAN_CONCURRENCY)

        async def audit_series(
            series: dict[str, Any],
        ) -> tuple[int, list[AuditItem]]:
            series_id = coerce_int(series.get("id"), 0)
            async with semaphore:
                files = await client.episode_files(series_id)
                episodes = await client.episodes(series_id)
            by_file: dict[int, list[dict[str, Any]]] = {}
            for episode in episodes:
                file_id = coerce_int(episode.get("episodeFileId"), 0)
                if file_id:
                    by_file.setdefault(file_id, []).append(episode)
            cutoff = scope.cutoffs[coerce_int(series.get("qualityProfileId"), 0)]
            items = [
                item
                for episode_file in files
                if (
                    item := _audit_file(
                        episode_file,
                        series=series,
                        episodes=by_file.get(coerce_int(episode_file.get("id"), 0), []),
                        cutoff_format_score=cutoff,
                        monitored_only=scope.monitored_only,
                    )
                )
                is not None
            ]
            return len(files), items

        # ``return_exceptions`` keeps every task awaited even when one fails; the
        # first failure is then re-raised so a partial scan is never published.
        outcomes = await asyncio.gather(
            *(audit_series(series) for series in series_list),
            return_exceptions=True,
        )
        files_scanned = 0
        flagged: list[AuditItem] = []
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome
            count, items = outcome
            files_scanned += count
            flagged.extend(items)
        flagged.sort(
            key=lambda item: (
                item.series_title.lower(),
                item.season_number or 0,
                item.first_episode_number,
            )
        )
        state.results = [item for item in flagged if item.verdict != "unknown"]
        state.unknown = [item for item in flagged if item.verdict == "unknown"]
        state.profiles_in_scope = scope.names
        state.series_scanned = len(series_list)
        state.files_scanned = files_scanned
        state.last_scan_at = _now_iso()

    # ---- queue ----

    def _retry_before_iso(self) -> str:
        hours = int(self.settings()["retry_after_hours"])
        return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    async def enqueue(self, episode_file_ids: list[int]) -> dict[str, Any]:
        """Queue replacement searches for scanned, non-compliant files."""
        if len(episode_file_ids) > MAX_ENQUEUE_PER_REQUEST:
            raise ValueError(
                f"At most {MAX_ENQUEUE_PER_REQUEST} files can be queued per request"
            )
        index = {item.episode_file_id: item for item in self._state.results}
        entries: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for file_id in dict.fromkeys(episode_file_ids):
            item = index.get(file_id)
            if item is None:
                errors.append(
                    {"episode_file_id": file_id, "error": "Not in scan results"}
                )
                continue
            if not item.episode_ids:
                errors.append(
                    {"episode_file_id": file_id, "error": NO_SEARCHABLE_EPISODES}
                )
                continue
            entries.append(_queue_entry(item))
        queued, skipped = self._ctx.db.languagarr_enqueue(
            entries, retry_before_iso=self._retry_before_iso()
        )
        if queued:
            self._ctx.db.add_activity(
                "Languagarr searches queued",
                f"Queued {queued} anime file(s) for an English-audio replacement search.",
            )
        return {"queued": queued, "skipped": skipped, "errors": errors}

    async def clear_pending(self) -> dict[str, int]:
        """Drop every pending queue row."""
        removed = self._ctx.db.languagarr_clear_pending()
        if removed:
            self._ctx.db.add_activity(
                "Languagarr queue cleared", f"Removed {removed} pending search(es)."
            )
        return {"removed": removed}

    async def run_now(self) -> dict[str, Any]:
        """Process one batch of pending searches now, regardless of ``enabled``."""
        return await self.gate.try_run(self._process_pending)

    async def scheduled_run(self) -> dict[str, Any]:
        """Scheduled worker body; the caller must hold the gate.

        Disabled means a silent no-op. With ``auto_queue`` the run scans first and
        queues every ``search`` item — never ``delete_and_search`` ones — and stops
        if that scan fails rather than burning search attempts on an unreachable
        Sonarr.
        """
        settings = self.settings()
        if not settings["enabled"]:
            return run_result("disabled")
        if settings["auto_queue"]:
            try:
                await self._scan_unlocked()
            except LanguagarrClientError, LanguagarrScopeError:
                return run_result("error")
            searchable = [
                item.episode_file_id
                for item in self._state.results
                if item.recommended_action == "search" and item.episode_ids
            ]
            await self.enqueue(searchable[:MAX_ENQUEUE_PER_REQUEST])
        return await self._process_pending()

    async def _process_pending(self) -> dict[str, Any]:
        """Send up to ``searches_per_run`` re-validated queued searches to Sonarr.

        The scope (profiles, cutoffs, monitoring rule) is resolved once per batch;
        if that fails nothing is searched and no attempt is burned.
        """
        limit = int(self.settings()["searches_per_run"])
        rows = self._ctx.db.languagarr_next_pending(limit)
        if not rows:
            return run_result("idle")
        client = client_for(self._ctx)
        try:
            try:
                scope = await self._scope(client)
            except (LanguagarrClientError, LanguagarrScopeError) as exc:
                self._ctx.db.add_activity("Languagarr searches skipped", str(exc))
                return run_result("error")
            return await process_rows(self._ctx, client, rows, scope)
        finally:
            await client.aclose()

    # ---- reviewed delete ----

    async def delete_and_search(self, episode_file_ids: list[int]) -> dict[str, Any]:
        """Re-validate, delete through Sonarr, and search each reviewed file."""
        if len(episode_file_ids) > MAX_DELETE_PER_REQUEST:
            raise ValueError(
                f"At most {MAX_DELETE_PER_REQUEST} files can be deleted per request"
            )
        return await self.gate.try_run(
            lambda: self._delete_and_search(list(dict.fromkeys(episode_file_ids)))
        )

    async def _delete_and_search(self, episode_file_ids: list[int]) -> dict[str, Any]:
        index = {item.episode_file_id: item for item in self._state.results}
        errors: list[dict[str, Any]] = []
        deleted: list[int] = []
        searched = 0
        client = client_for(self._ctx)
        try:
            scope = await self._scope(client)
            for file_id in episode_file_ids:
                item = index.get(file_id)
                outcome = (
                    await self._delete_one(client, item, scope)
                    if item is not None
                    else _DeleteOutcome(False, False, "Not in scan results")
                )
                if outcome.deleted:
                    deleted.append(file_id)
                searched += int(outcome.searched)
                if outcome.error is not None:
                    errors.append({"episode_file_id": file_id, "error": outcome.error})
        finally:
            await client.aclose()
        removed = set(deleted)
        self._state.results = [
            item for item in self._state.results if item.episode_file_id not in removed
        ]
        failed = len(episode_file_ids) - len(deleted)
        record_languagarr_deletes(deleted=len(deleted), failed=failed)
        record_languagarr_searches(succeeded=searched, failed=len(deleted) - searched)
        self._ctx.db.add_activity(
            "Languagarr delete completed",
            f"Deleted {len(deleted)} anime file(s) through Sonarr and searched "
            f"{searched}; {failed} not deleted.",
        )
        return {
            "deleted": len(deleted),
            "searched": searched,
            "failed": failed,
            "deleted_ids": deleted,
            "errors": errors,
        }

    async def _delete_one(
        self, client: LanguagarrSonarrClient, item: AuditItem, scope: Scope
    ) -> _DeleteOutcome:
        """Re-validate, delete and search one reviewed file."""
        problem = await self._revalidate(client, item, scope)
        if problem is not None:
            return _DeleteOutcome(False, False, problem)
        try:
            await client.delete_episode_file(item.episode_file_id)
        except LanguagarrClientError as exc:
            return _DeleteOutcome(False, False, f"Delete failed: {exc}")
        _log.info("deleted non-compliant episode file %s", item.relative_path)
        self._ctx.db.languagarr_enqueue(
            [_queue_entry(item)], retry_before_iso=_ALWAYS_REQUEUE
        )
        try:
            await client.episode_search(list(item.episode_ids))
        except LanguagarrClientError as exc:
            self._ctx.db.languagarr_mark_attempt(item.episode_file_id, error=str(exc))
            return _DeleteOutcome(True, False, f"Deleted, but the search failed: {exc}")
        self._ctx.db.languagarr_mark_attempt(item.episode_file_id)
        return _DeleteOutcome(True, True, None)

    @staticmethod
    async def _revalidate(
        client: LanguagarrSonarrClient, item: AuditItem, scope: Scope
    ) -> str | None:
        """Return why ``item`` must not be deleted now, or ``None`` if it may be.

        Sonarr is re-read immediately before the delete so a file replaced,
        fixed, moved, re-profiled or unmonitored since the scan is never removed.
        """
        if not item.episode_ids:
            return NO_SEARCHABLE_EPISODES
        try:
            fresh = await client.episode_file(item.episode_file_id)
            if fresh is None:
                return "File no longer exists"
            if str(fresh.get("path") or "") != item.path:
                return "File changed since scan"
            verdict, _ = file_audio_verdict(fresh)
            if verdict.compliant or verdict.status == "unknown":
                return "No longer non-compliant"
            series = await client.series_by_id(item.series_id)
        except LanguagarrClientError as exc:
            return f"Could not re-check file: {exc}"
        if series is None or not scope.includes(series):
            return "Series no longer in scope"
        return None

    # ---- settings ----

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist settings updates and return the normalised settings."""
        settings = self._ctx.settings_store.update_languagarr_settings(updates)
        self._ctx.db.add_activity(
            "Languagarr settings saved", "Languagarr settings updated"
        )
        return settings


def _queue_entry(item: AuditItem) -> dict[str, Any]:
    """Return the DB queue payload for an audit item."""
    return {
        "episode_file_id": item.episode_file_id,
        "series_id": item.series_id,
        "title": item.queue_title,
        "episode_ids": list(item.episode_ids),
        "reason": item.verdict,
    }
