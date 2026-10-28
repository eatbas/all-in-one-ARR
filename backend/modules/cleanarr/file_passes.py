"""Cleanarr's opt-in file passes: malware deletion and orphan quarantine.

Both passes need SABnzbd's completed folder mounted at ``paths.completed_root``
and SABnzbd's own ``complete_dir`` to map SABnzbd paths onto it; otherwise the
pass is skipped and a note is surfaced on the Status tab. All filesystem work
runs in :func:`asyncio.to_thread` through :mod:`modules.cleanarr.files`.

In dry run nothing is touched. The would-be actions are logged to history only
when they differ from the last dry-run report of the same pass, so an unchanged
folder does not add rows on every run.

The ignore lists apply to every file action: an orphan is matched by its entry
name (and its category folder's categories), a quarantined entry by the name
it was moved from and the category folder and categories recorded when it was
moved. An expired entry whose origin is unknown is kept while category
exclusions exist, because they cannot be evaluated for it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from core.app_metrics import record_cleanarr_file_actions
from modules.cleanarr.files import (
    delete_files,
    expired_quarantine,
    find_blocked_files,
    orphan_candidates,
    purge,
    quarantine,
    quarantine_names,
    quarantine_original_name,
    quarantine_problem,
)
from modules.cleanarr.models import (
    AppRun,
    FileActionResult,
    HealthWarning,
    OrphanCandidate,
    QuarantineOrigin,
    QueueItem,
    RunSummary,
    SabHistoryJob,
    SabState,
)
from modules.cleanarr.paths import (
    category_container_names,
    container_categories,
    reroot,
    resolve_within,
)
from modules.cleanarr.queue_cleaner import (
    QueueProtection,
    download_ignored,
    group_downloads,
)
from modules.cleanarr.rules import is_ignored

if TYPE_CHECKING:  # pragma: no cover
    from core.db import Database


@dataclass(frozen=True)
class FileEntry:
    """A path to act on plus the history labels for it."""

    path: Path
    title: str
    detail: str
    download_id: str | None = None
    app: str = "sabnzbd"


@dataclass(frozen=True)
class _ActionSpec:
    """How one kind of file action is executed, counted and logged."""

    metric: str
    done: str
    would: str
    failed: str
    counter: str
    operation: Callable[[list[Path]], FileActionResult]


@dataclass(frozen=True)
class _Roots:
    """The resolved local folders and SABnzbd's own completed folder."""

    completed: Path
    quarantine: Path
    sab_complete_dir: str
    category_dirs: tuple[str, ...]
    category_folders: tuple[tuple[str, str], ...]


def _note(code: str, detail: str, level: str = "warning") -> HealthWarning:
    """Return a system note shown with the health checks."""
    return HealthWarning(source="system", code=code, detail=detail, level=level)


async def _roots(settings: dict[str, Any], sab: SabState) -> _Roots | HealthWarning:
    """Return the folders a file pass needs, or the note explaining the skip."""
    if sab.config is None or sab.history is None:
        return _note(
            "sab_unavailable", "SABnzbd settings or history could not be read."
        )
    if not sab.config.complete_dir.startswith("/"):
        return _note(
            "sab_complete_dir_unknown",
            "SABnzbd's completed folder is not an absolute path.",
        )
    completed = Path(settings["paths"]["completed_root"])
    if await asyncio.to_thread(resolve_within, completed, completed) is None:
        return _note(
            "completed_root_missing",
            f"The completed folder {completed} is not mounted in aio-arr.",
        )
    return _Roots(
        completed=completed,
        quarantine=Path(settings["paths"]["quarantine_dir"]),
        sab_complete_dir=sab.config.complete_dir,
        category_dirs=sab.config.category_dirs,
        category_folders=sab.config.category_folders,
    )


def _report_changed(db: Database, key: str, entries: list[FileEntry]) -> bool:
    """Store a fingerprint of a dry-run report; return whether it changed."""
    names = sorted(str(entry.path) for entry in entries)
    digest = hashlib.sha256(json.dumps(names).encode()).hexdigest()
    state_key = f"dry_run_report:{key}"
    if db.cleanarr_run_state().get(state_key) == digest:
        return False
    db.cleanarr_set_run_state(state_key, digest)
    return True


async def _apply(
    db: Database, summary: RunSummary, spec: _ActionSpec, entries: list[FileEntry]
) -> FileActionResult:
    """Run (or, in dry run, report) one file action and log each entry.

    Returns what the operation did; nothing is done in dry run.
    """
    if summary.dry_run:
        if entries and _report_changed(db, spec.metric, entries):
            for entry in entries:
                _log(db, entry, spec.would, entry.detail, dry_run=True)
            _count(summary, spec, len(entries))
        return FileActionResult()
    if not entries:
        return FileActionResult()
    by_path = {entry.path: entry for entry in entries}
    result = await asyncio.to_thread(spec.operation, list(by_path))
    for path in result.done:
        _log(db, by_path[path], spec.done, by_path[path].detail, dry_run=False)
    for path, reason in result.failed:
        _log(db, by_path[path], spec.failed, reason, dry_run=False)
    _count(summary, spec, len(result.done))
    summary.file_failures += len(result.failed)
    return result


def _count(summary: RunSummary, spec: _ActionSpec, count: int) -> None:
    """Add ``count`` to the summary counter and the metric for ``spec``."""
    setattr(summary, spec.counter, getattr(summary, spec.counter) + count)
    record_cleanarr_file_actions(
        action=spec.metric, count=count, dry_run=summary.dry_run
    )


def _log(
    db: Database, entry: FileEntry, action: str, detail: str, *, dry_run: bool
) -> None:
    """Write one history row for a file entry."""
    db.cleanarr_add_history(
        app=entry.app,
        action=action,
        download_id=entry.download_id,
        title=entry.title,
        detail=detail,
        dry_run=dry_run,
    )


# ---- malware ----


def _malware_eligible(records: tuple[QueueItem, ...]) -> bool:
    """Return whether every record of a download is usenet and not importing."""
    return all(
        record.protocol == "usenet" and record.tracked_state.lower() != "importing"
        for record in records
    )


def _malware_jobs(
    settings: dict[str, Any],
    sab: SabState,
    runs: list[AppRun],
    protection: QueueProtection,
) -> list[tuple[QueueItem, SabHistoryJob]]:
    """Return one ``(record, job)`` per queued download whose SABnzbd job completed.

    Every record of a download (one per episode, from any app) leads to the
    same job folder, so the download is decided as a whole: one importing,
    non-usenet or ignored record protects the folder, including a record
    without a usable queue id, and an eligible folder is scanned once however
    many records point at it. A download that ``protection`` holds (a record
    without a usable ``downloadId`` refers to its folder) is never scanned,
    because that record's state and title cannot be tied to the download;
    queue cleaning holds the same downloads.
    """
    records = (item for run in runs for item in run.items or ())
    pairs: list[tuple[QueueItem, SabHistoryJob]] = []
    for group in group_downloads(records):
        job = sab.jobs_by_id.get(group[0].download_id)
        if (
            job is None
            or job.status != "Completed"
            or not job.storage
            or protection.holds(group, sab)
            or not _malware_eligible(group)
            or download_ignored(group, settings, sab) is not False
        ):
            continue
        pairs.append((group[0], job))
    return pairs


def _malware_blocked(protection: QueueProtection) -> HealthWarning | None:
    """Return the note when a queue record could not be tied to its download."""
    if protection.complete:
        return None
    return _note(
        "malware_skipped",
        "Malware blocker skipped: a Sonarr/Radarr queue record could not be "
        "matched to a download, so an importing or ignored download may not "
        "be recognised.",
    )


async def malware_pass(
    db: Database,
    settings: dict[str, Any],
    sab: SabState,
    runs: list[AppRun],
    summary: RunSummary,
) -> None:
    """Delete blocked-extension files from completed, not-yet-imported jobs."""
    if not settings["malware"]["enabled"]:
        return
    protection = QueueProtection.of(runs)
    blocked = _malware_blocked(protection)
    if blocked is not None:
        summary.notes.append(blocked)
        return
    roots = await _roots(settings, sab)
    if isinstance(roots, HealthWarning):
        summary.notes.append(roots)
        return
    extensions = frozenset(settings["malware"]["extensions"])
    entries: list[FileEntry] = []
    unmapped = 0
    for item, job in _malware_jobs(settings, sab, runs, protection):
        local = reroot(job.storage, roots.sab_complete_dir, str(roots.completed))
        if local is None:
            unmapped += 1
            continue
        found = await asyncio.to_thread(
            find_blocked_files, Path(local), roots.completed, extensions
        )
        entries.extend(
            FileEntry(
                path=path,
                title=item.title,
                detail=path.name,
                download_id=item.download_id,
                app=item.app,
            )
            for path in found
        )
    if unmapped:
        summary.notes.append(
            _note(
                "malware_path_unmapped",
                f"{unmapped} SABnzbd job folder(s) are outside SABnzbd's completed "
                "folder and were not checked.",
            )
        )
    spec = _ActionSpec(
        metric="malware_delete",
        done="malware_deleted",
        would="would_delete_malware",
        failed="malware_delete_failed",
        counter="malware_deleted",
        operation=lambda paths: delete_files(paths, roots.completed),
    )
    await _apply(db, summary, spec, entries)


# ---- orphans ----


def _referenced_names(sab: SabState, runs: list[AppRun]) -> frozenset[str]:
    """Return every completed-folder name SABnzbd or an Arr still refers to."""
    names: set[str] = set(sab.queue_names or ())
    names.update(PurePosixPath(job.storage).name for job in sab.history or ())
    names.update(PurePosixPath(storage).name for storage in sab.unparsed_storage)
    names.update(
        PurePosixPath(item.output_path).name
        for run in runs
        for item in run.items or ()
        if item.output_path
    )
    names.update(
        PurePosixPath(path).name for run in runs for path in run.unparsed_output_paths
    )
    names.discard("")
    return frozenset(names)


def _folder_categories(
    container: str | None, categories: dict[str, frozenset[str]]
) -> frozenset[str]:
    """Return the category names an entry in ``container`` belongs to.

    That is the folder's current SABnzbd category names plus the folder name
    itself, in case SABnzbd's category list changed; none for an entry
    directly in the completed folder.
    """
    if container is None:
        return frozenset()
    return frozenset({container, *categories.get(container, ())})


def _title_or_category_ignored(
    title: str, category_names: Iterable[str], ignore: dict[str, list[str]]
) -> bool:
    """Return whether the ignore lists exempt ``title`` under any of the categories."""
    return any(
        bool(is_ignored(download_id="", title=title, category=category, ignore=ignore))
        for category in sorted(category_names) or [""]
    )


def _orphan_ignored(
    candidate: OrphanCandidate,
    categories: dict[str, frozenset[str]],
    ignore: dict[str, list[str]],
) -> bool:
    """Return whether the ignore lists exempt an orphan candidate."""
    return _title_or_category_ignored(
        candidate.path.name,
        _folder_categories(candidate.container, categories),
        ignore,
    )


def _purge_ignored(
    path: Path,
    origin: QuarantineOrigin | None,
    categories: dict[str, frozenset[str]],
    ignore: dict[str, list[str]],
) -> bool | None:
    """Return whether the ignore lists exempt a quarantined entry (``None``: unknown).

    The entry is matched by the name it was moved from, under the categories
    recorded when it was moved and its folder's current ones. Without a
    recorded origin its category is unknown, which is undecidable when
    category exclusions exist.
    """
    title = quarantine_original_name(path.name)
    if origin is None:
        return is_ignored(download_id="", title=title, category=None, ignore=ignore)
    names = _folder_categories(origin.container, categories) | set(origin.categories)
    return _title_or_category_ignored(title, names, ignore)


def _orphans_blocked(sab: SabState, runs: list[AppRun]) -> HealthWarning | None:
    """Return the note when the reference set is not known to be complete."""
    if sab.queue_names is None or any(run.items is None for run in runs):
        return _note(
            "orphans_skipped",
            "Orphan quarantine skipped: a SABnzbd or Sonarr/Radarr queue "
            "could not be read.",
        )
    if not all(run.references_complete for run in runs):
        return _note(
            "orphans_skipped",
            "Orphan quarantine skipped: a Sonarr/Radarr queue record could not "
            "be read in full, so some completed folders may still be referenced.",
        )
    if not sab.history_complete:
        return _note(
            "orphans_skipped",
            "Orphan quarantine skipped: SABnzbd's history is longer than "
            "Cleanarr reads or has unreadable entries, so some completed folders "
            "may still be referenced.",
        )
    return None


async def _quarantine_unsafe(roots: _Roots) -> HealthWarning | None:
    """Return the note when the quarantine folder is not safe to use."""
    problem = await asyncio.to_thread(
        quarantine_problem, roots.completed, roots.quarantine
    )
    if problem is None:
        return None
    return _note(
        "quarantine_unsafe",
        f"Orphan quarantine skipped: the quarantine folder {roots.quarantine} "
        f"must be a real folder inside the completed folder ({problem}).",
    )


async def orphan_pass(
    db: Database,
    settings: dict[str, Any],
    sab: SabState,
    runs: list[AppRun],
    summary: RunSummary,
) -> None:
    """Quarantine unreferenced completed entries, then purge expired ones."""
    orphans = settings["orphans"]
    if not orphans["enabled"]:
        return
    roots = await _roots(settings, sab)
    if isinstance(roots, HealthWarning):
        summary.notes.append(roots)
        return
    blocked = _orphans_blocked(sab, runs) or await _quarantine_unsafe(roots)
    if blocked is not None:
        summary.notes.append(blocked)
        return
    now = datetime.now(UTC)
    found = await asyncio.to_thread(
        orphan_candidates,
        roots.completed,
        roots.quarantine,
        category_container_names(roots.category_dirs, roots.sab_complete_dir),
        _referenced_names(sab, runs),
        min_age=timedelta(hours=int(orphans["min_age_hours"])),
        now=now,
    )
    categories = container_categories(roots.category_folders, roots.sab_complete_dir)
    candidates = {
        candidate.path: candidate
        for candidate in found
        if not _orphan_ignored(candidate, categories, settings["ignore"])
    }
    result = await _apply(
        db,
        summary,
        _ActionSpec(
            metric="quarantine",
            done="quarantined",
            would="would_quarantine",
            failed="quarantine_failed",
            counter="quarantined",
            operation=lambda paths: quarantine(
                paths, roots.completed, roots.quarantine, now=now
            ),
        ),
        [FileEntry(path=path, title=path.name, detail="") for path in candidates],
    )
    for source, target in result.moved_to.items():
        container = candidates[source].container
        db.cleanarr_record_quarantine(
            target.name,
            container=container,
            categories=categories.get(container, ()) if container else (),
        )
    await _purge_pass(db, settings, summary, roots, now)


def _quarantine_origins(db: Database) -> dict[str, QuarantineOrigin]:
    """Return the recorded origin of each quarantined entry, by quarantined name."""
    return {
        name: QuarantineOrigin(container=container, categories=names)
        for name, (container, names) in db.cleanarr_quarantine_origins().items()
    }


async def _purge_pass(
    db: Database,
    settings: dict[str, Any],
    summary: RunSummary,
    roots: _Roots,
    now: datetime,
) -> None:
    """Purge quarantined entries older than the retention window.

    An entry the ignore lists exempt is kept (see :func:`_purge_ignored`), as
    is one whose origin is unknown while category exclusions exist. Origins of
    entries no longer in quarantine are forgotten afterwards.
    """
    retention = timedelta(days=int(settings["orphans"]["quarantine_retention_days"]))
    found = await asyncio.to_thread(
        expired_quarantine,
        roots.completed,
        roots.quarantine,
        retention=retention,
        now=now,
    )
    origins = _quarantine_origins(db)
    categories = container_categories(roots.category_folders, roots.sab_complete_dir)
    decisions = {
        path: _purge_ignored(
            path, origins.get(path.name), categories, settings["ignore"]
        )
        for path in found
    }
    await _apply(
        db,
        summary,
        _ActionSpec(
            metric="purge",
            done="purged",
            would="would_purge",
            failed="purge_failed",
            counter="purged",
            operation=lambda paths: purge(paths, roots.completed, roots.quarantine),
        ),
        [
            FileEntry(path=path, title=path.name, detail="")
            for path, ignored in decisions.items()
            if ignored is False
        ],
    )
    unknown = sum(1 for ignored in decisions.values() if ignored is None)
    if unknown:
        summary.notes.append(
            _note(
                "quarantine_origin_unknown",
                f"{unknown} expired quarantined item(s) kept: the category "
                "folder they came from is unknown, so the category ignore list "
                "cannot be checked.",
                level="info",
            )
        )
    remaining = await asyncio.to_thread(
        quarantine_names, roots.completed, roots.quarantine
    )
    if remaining is not None:
        db.cleanarr_prune_quarantine(remaining)
