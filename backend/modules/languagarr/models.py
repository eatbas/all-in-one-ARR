"""Typed Languagarr audit models shared by the engine and the API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from core.coerce import coerce_int
from modules.languagarr.audio import AudioStatus

RecommendedAction = Literal["search", "delete_and_search"]
QueueStatus = Literal["none", "pending", "searched", "failed"]


@dataclass(frozen=True)
class AuditItem:
    """One Sonarr episode file without an English audio track.

    ``recommended_action`` is ``search`` when the file's custom-format score is
    below the profile's cutoff score: Sonarr will then treat a better release as
    an upgrade and replace the file on import, so a search alone suffices. At or
    above the cutoff Sonarr never upgrades it, so the file must be deleted before
    a search can replace it.
    """

    episode_file_id: int
    series_id: int
    series_title: str
    season_number: int | None
    episode_ids: tuple[int, ...]
    episode_label: str
    relative_path: str
    path: str
    audio_languages: str
    sonarr_languages: tuple[str, ...]
    verdict: AudioStatus
    release_group: str | None
    custom_format_score: int
    cutoff_format_score: int
    recommended_action: RecommendedAction
    queue_status: QueueStatus = "none"
    last_searched_at: str | None = None
    # Numeric sort key (lowest episode number); not part of the API payload.
    first_episode_number: int = 0

    @property
    def queue_title(self) -> str:
        """Human-readable label stored on queue rows and shown in activity."""
        return f"{self.series_title} - {self.episode_label}"

    def to_dict(self) -> dict[str, object]:
        return {
            "episode_file_id": self.episode_file_id,
            "series_id": self.series_id,
            "series_title": self.series_title,
            "season_number": self.season_number,
            "episode_ids": list(self.episode_ids),
            "episode_label": self.episode_label,
            "relative_path": self.relative_path,
            "audio_languages": self.audio_languages,
            "sonarr_languages": list(self.sonarr_languages),
            "verdict": self.verdict,
            "release_group": self.release_group,
            "custom_format_score": self.custom_format_score,
            "cutoff_format_score": self.cutoff_format_score,
            "recommended_action": self.recommended_action,
            "queue_status": self.queue_status,
            "last_searched_at": self.last_searched_at,
        }


@dataclass(frozen=True)
class Scope:
    """Resolved scope: ``{profile_id: cutoffFormatScore}`` plus monitoring rule."""

    cutoffs: dict[int, int]
    names: list[str]
    monitored_only: bool

    def includes(self, series: dict[str, Any]) -> bool:
        """Whether ``series`` is on an in-scope profile (and monitored if required)."""
        if coerce_int(series.get("qualityProfileId"), -1) not in self.cutoffs:
            return False
        return not self.monitored_only or bool(series.get("monitored", True))


@dataclass
class ScanState:
    """Mutable in-memory result of the latest Languagarr scan.

    Like Deletarr's library state this lives only in the process: a restart
    clears it until the next scan, while the replacement queue persists in SQLite.
    """

    results: list[AuditItem] = field(default_factory=list)
    unknown: list[AuditItem] = field(default_factory=list)
    is_scanning: bool = False
    last_scan_at: str | None = None
    last_error: str | None = None
    profiles_in_scope: list[str] = field(default_factory=list)
    series_scanned: int = 0
    files_scanned: int = 0

    def verdict_counts(self) -> dict[str, int]:
        """Return file counts per non-compliant verdict, including ``unknown``."""
        counts = {
            "missing_english": 0,
            "unknown": len(self.unknown),
        }
        for item in self.results:
            counts[item.verdict] += 1
        return counts

    def summary(self) -> dict[str, object]:
        """Return the counts and metadata shown on the status endpoint."""
        by_verdict = self.verdict_counts()
        return {
            "is_scanning": self.is_scanning,
            "last_scan_at": self.last_scan_at,
            "last_error": self.last_error,
            "profiles_in_scope": list(self.profiles_in_scope),
            "series_scanned": self.series_scanned,
            "files_scanned": self.files_scanned,
            "non_compliant": len(self.results),
            "unknown": len(self.unknown),
            "missing_english": by_verdict["missing_english"],
        }
