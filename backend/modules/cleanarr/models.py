"""Typed records shared by the Cleanarr client, rules, file helpers and engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from core.sabnzbd_types import SabConfig as SabConfig
from core.sabnzbd_types import SabHistory as SabHistory
from core.sabnzbd_types import SabHistoryJob as SabHistoryJob


@dataclass(frozen=True)
class QueueItem:
    """One Sonarr/Radarr queue record, reduced to the fields Cleanarr reads.

    ``messages`` flattens ``statusMessages[].title`` and every
    ``statusMessages[].messages[]`` entry in order, for pattern matching.
    ``queue_id`` is ``None`` when the record's ``id`` is unusable: the record
    cannot be struck or removed itself, but it still belongs to its download,
    so its state and title protect that download like any other record's.
    """

    app: str
    queue_id: int | None
    download_id: str
    protocol: str
    download_client: str
    title: str
    status: str
    tracked_status: str
    tracked_state: str
    messages: tuple[str, ...]
    output_path: str


@dataclass(frozen=True)
class ArrQueue:
    """One Sonarr/Radarr queue read: the records of each download and their references.

    ``items`` holds every record with a usable ``downloadId``, including those
    without a usable ``id`` (``queue_id`` ``None``). ``unparsed_output_paths``
    keeps the ``outputPath`` of records without a usable ``downloadId``: they
    belong to no known download, but their folders are still referenced.
    ``references_complete`` is ``False`` when a record (or its ``outputPath``)
    was malformed or paging ended short of ``totalRecords``, so the referenced
    folders are not fully known. ``downloads_complete`` is ``False`` when a
    record could be tied to neither a download nor a folder, or paging ended
    short, so any download may have a record Cleanarr has not seen.
    """

    items: tuple[QueueItem, ...]
    unparsed_output_paths: tuple[str, ...] = ()
    references_complete: bool = True
    downloads_complete: bool = True


@dataclass(frozen=True)
class ArrDownloadHandling:
    """An Arr's failed/completed download handling; ``None`` means unknown."""

    completed_handling: bool | None
    redownload_failed: bool | None
    remove_failed: bool | None
    remove_completed: bool | None


@dataclass(frozen=True)
class HealthWarning:
    """A read-only configuration warning shown on the Status tab.

    ``level`` is ``"warning"`` for a risky setting and ``"info"`` when the value
    could not be read.
    """

    source: str
    code: str
    detail: str
    level: str = "warning"


@dataclass
class FileActionResult:
    """Outcome of a batch of file operations; per-path failures never raise.

    ``moved_to`` maps each moved path to where it went (quarantine only).
    """

    done: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    moved_to: dict[Path, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class OrphanCandidate:
    """An unreferenced completed entry; ``container`` names its category folder.

    ``container`` is ``None`` for a direct child of the completed folder.
    """

    path: Path
    container: str | None = None


@dataclass(frozen=True)
class QuarantineOrigin:
    """Where a quarantined entry came from, so the ignore lists still apply at purge.

    ``container`` is the category folder it sat in (``None`` for a direct
    child of the completed folder) and ``categories`` the SABnzbd category
    names that used that folder when it was moved.
    """

    container: str | None
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class SabState:
    """SABnzbd reads for one run; each is ``None`` when its read failed.

    ``history_complete`` is ``False`` when the history read stopped before
    the end (the job cap) or held a malformed ``storage``, so it is not an
    exhaustive reference set. ``unparsed_storage`` holds the folders of
    history slots that could not become jobs.
    """

    config: SabConfig | None
    history: tuple[SabHistoryJob, ...] | None
    queue_names: tuple[str, ...] | None
    history_complete: bool = False
    unparsed_storage: tuple[str, ...] = ()

    @classmethod
    def from_reads(
        cls,
        *,
        config: SabConfig | None,
        history: SabHistory | None,
        queue_names: list[str] | None,
    ) -> SabState:
        """Build the run state from the three SABnzbd reads."""
        return cls(
            config=config,
            history=None if history is None else history.jobs,
            queue_names=None if queue_names is None else tuple(queue_names),
            history_complete=history is not None and history.complete,
            unparsed_storage=() if history is None else history.unparsed_storage,
        )

    @property
    def reachable(self) -> bool:
        """Whether both the config and the history could be read."""
        return self.config is not None and self.history is not None

    @property
    def failed_ids(self) -> frozenset[str] | None:
        """The ``nzo_id`` of every Failed history job, or ``None`` when unknown."""
        if self.history is None:
            return None
        return frozenset(job.nzo_id for job in self.history if job.status == "Failed")

    @cached_property
    def jobs_by_id(self) -> dict[str, SabHistoryJob]:
        """History jobs keyed by ``nzo_id`` (empty when history is unknown)."""
        return {job.nzo_id: job for job in self.history or ()}


@dataclass
class AppRun:
    """One Arr's part of a run: its connection result, queue and strikes.

    ``items`` is ``None`` when the app was skipped (unreachable or
    incompatible); its strikes are then left untouched. The reference and
    completeness fields come from the :class:`ArrQueue` read.
    """

    app: str
    ok: bool
    detail: str
    items: tuple[QueueItem, ...] | None = None
    unparsed_output_paths: tuple[str, ...] = ()
    references_complete: bool = True
    downloads_complete: bool = True
    handling: ArrDownloadHandling | None = None
    struck: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunSummary:
    """Counts reported by one run (live actions and dry-run would-actions)."""

    dry_run: bool
    struck: int = 0
    removed: int = 0
    would_remove: int = 0
    already_gone: int = 0
    remove_failed: int = 0
    malware_deleted: int = 0
    quarantined: int = 0
    purged: int = 0
    file_failures: int = 0
    notes: list[HealthWarning] = field(default_factory=list)

    def changed(self) -> bool:
        """Whether the run changed (or, in dry run, would have changed) anything."""
        return any(
            (
                self.removed,
                self.would_remove,
                self.already_gone,
                self.malware_deleted,
                self.quarantined,
                self.purged,
            )
        )

    def counts(self) -> dict[str, int]:
        """Return the counters as a plain dict for the API and run state."""
        return {
            "struck": self.struck,
            "removed": self.removed,
            "would_remove": self.would_remove,
            "already_gone": self.already_gone,
            "remove_failed": self.remove_failed,
            "malware_deleted": self.malware_deleted,
            "quarantined": self.quarantined,
            "purged": self.purged,
            "file_failures": self.file_failures,
        }
