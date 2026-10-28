"""Synchronous, defensive filesystem operations for Cleanarr's file passes.

The engine calls these through :func:`asyncio.to_thread`. Every function:

* resolves each path through :func:`~modules.cleanarr.paths.resolve_within`,
  which requires it to stay under its root with no symlink anywhere between
  the root and the path (the quarantine folder is checked against the
  completed root, never trusted as a root of its own);
* never follows symlinks (``os.walk(followlinks=False)``; symlink entries are
  skipped or refused);
* moves with :func:`os.rename` only, so a cross-filesystem move fails with
  ``EXDEV`` and is reported, never retried as copy-and-delete;
* reports per-path failures in a :class:`FileActionResult` instead of raising.

Quarantined entries are renamed ``<UTC yyyymmddTHHMMSSZ>__<name>``; the purge
reads the move time back from that prefix because ``os.rename`` keeps the
source mtime. Entries without a valid prefix are never purged.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from modules.cleanarr.models import FileActionResult, OrphanCandidate
from modules.cleanarr.paths import resolve_within, split_under
from modules.cleanarr.rules import is_blocked_file

# Default cap on files examined per job directory, so one huge or looping job
# cannot stall a run.
MAX_FILES_PER_JOB = 10_000

QUARANTINE_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
QUARANTINE_SEPARATOR = "__"
# Highest numeric suffix tried when a quarantine name is already taken.
_MAX_NAME_CLASHES = 1000


def _error_reason(exc: OSError) -> str:
    """Return a short, path-free reason for a failed file operation."""
    if exc.errno == errno.EXDEV:
        return "cross_device"
    return exc.strerror or type(exc).__name__


def find_blocked_files(
    job_dir: Path,
    root: Path,
    extensions: frozenset[str],
    *,
    max_files: int = MAX_FILES_PER_JOB,
) -> list[Path]:
    """Return blocked-extension files under ``job_dir`` (a dir or a single file).

    A job path that is (or passes through) a symlink is refused outright.
    Symlinked files inside it are skipped and symlinked directories are not
    descended into; at most ``max_files`` regular files are examined.
    """
    base = resolve_within(job_dir, root)
    if base is None:
        return []
    if base.is_file():
        return [base] if is_blocked_file(base.name, extensions) else []
    blocked: list[Path] = []
    for examined, candidate in enumerate(_walk_files(base)):
        if examined >= max_files:
            break
        if is_blocked_file(candidate.name, extensions):
            resolved = resolve_within(candidate, root)
            if resolved is not None:
                blocked.append(resolved)
    return blocked


def _walk_files(base: Path) -> Iterator[Path]:
    """Yield the non-symlink files under ``base`` without following links."""
    for directory, _dirnames, filenames in os.walk(base, followlinks=False):
        for filename in sorted(filenames):
            candidate = Path(directory) / filename
            if not candidate.is_symlink():
                yield candidate


def delete_files(paths: Iterable[Path], root: Path) -> FileActionResult:
    """Unlink each file after re-checking it is a regular file under ``root``."""
    result = FileActionResult()
    for path in paths:
        if path.is_symlink():
            result.failed.append((path, "symlink"))
            continue
        if resolve_within(path, root) is None:
            result.failed.append((path, "outside_root"))
            continue
        try:
            path.unlink()
        except OSError as exc:
            result.failed.append((path, _error_reason(exc)))
            continue
        result.done.append(path)
    return result


def _is_excluded(entry: Path, quarantine: Path) -> bool:
    """Return whether ``entry`` is hidden, a symlink, or holds the quarantine."""
    if entry.name.startswith(".") or entry.is_symlink():
        return True
    return entry == quarantine or quarantine.is_relative_to(entry)


def _old_enough(entry: Path, *, min_age: timedelta, now: datetime) -> bool:
    """Return whether ``entry``'s mtime (not following links) is at least ``min_age`` old."""
    try:
        modified = datetime.fromtimestamp(entry.lstat().st_mtime, UTC)
    except OSError:
        return False
    return now - modified >= min_age


def _list_dir(directory: Path) -> list[Path]:
    """Return a directory's entries sorted by name, or ``[]`` when unreadable."""
    try:
        return sorted(directory.iterdir())
    except OSError:
        return []


def _lexical_location(path: Path, root: Path) -> Path:
    """Return where ``path`` sits below the resolved ``root``, without following links."""
    split = split_under(path, root)
    if split is None:
        return path.resolve(strict=False)
    resolved_root, parts = split
    return resolved_root.joinpath(*parts)


def orphan_candidates(
    completed_root: Path,
    quarantine_dir: Path,
    container_names: frozenset[str],
    referenced_names: frozenset[str],
    *,
    min_age: timedelta,
    now: datetime,
) -> list[OrphanCandidate]:
    """Return unreferenced, old-enough entries in the completed folder.

    Candidates are the direct children of ``completed_root``; a child directory
    named after a SABnzbd category folder is a container whose children are
    candidates instead (each records its container). Dot-entries, symlinks and
    the quarantine folder (and any folder holding it) are never candidates.
    """
    root = resolve_within(completed_root, completed_root)
    if root is None:
        return []
    quarantine = _lexical_location(quarantine_dir, completed_root)
    entries: list[OrphanCandidate] = []
    for entry in _list_dir(root):
        if _is_excluded(entry, quarantine):
            continue
        if entry.name in container_names and entry.is_dir():
            entries.extend(
                OrphanCandidate(path=child, container=entry.name)
                for child in _list_dir(entry)
                if not _is_excluded(child, quarantine)
            )
        else:
            entries.append(OrphanCandidate(path=entry))
    return [
        candidate
        for candidate in entries
        if candidate.path.name not in referenced_names
        and _old_enough(candidate.path, min_age=min_age, now=now)
    ]


def _free_target(quarantine: Path, name: str) -> Path | None:
    """Return a quarantine path for ``name`` that does not exist yet."""
    target = quarantine / name
    for clash in range(1, _MAX_NAME_CLASHES + 1):
        if not os.path.lexists(target):
            return target
        target = quarantine / f"{name}-{clash}"
    return None


def quarantine_problem(completed_root: Path, quarantine_dir: Path) -> str | None:
    """Return why ``quarantine_dir`` must not be used, or ``None`` when it is safe.

    The folder may still be missing (it is created on first use), but it must
    sit strictly inside the completed folder and no existing component between
    the two may be a symlink.
    """
    split = split_under(quarantine_dir, completed_root)
    if split is None or not split[1]:
        return "quarantine_outside_root"
    current, parts = split
    for part in parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            return None
        except OSError as exc:
            return _error_reason(exc)
        if stat.S_ISLNK(mode):
            return "symlink"
    return None


def _existing_quarantine(completed_root: Path, quarantine_dir: Path) -> Path | None:
    """Return the quarantine folder resolved when it exists and is safe to use."""
    if quarantine_problem(completed_root, quarantine_dir) is not None:
        return None
    return resolve_within(quarantine_dir, completed_root)


def _prepare_quarantine(completed_root: Path, quarantine_dir: Path) -> Path | str:
    """Create the quarantine folder; return it resolved, or a failure reason."""
    problem = quarantine_problem(completed_root, quarantine_dir)
    if problem is not None:
        return problem
    try:
        quarantine_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error_reason(exc)
    resolved = resolve_within(quarantine_dir, completed_root)
    return resolved if resolved is not None else "symlink"


def quarantine(
    paths: Iterable[Path],
    completed_root: Path,
    quarantine_dir: Path,
    *,
    now: datetime,
) -> FileActionResult:
    """Rename each entry into the quarantine folder as ``<stamp>__<name>``.

    Each entry must be a non-symlink under ``completed_root`` on the same
    device as the quarantine folder; otherwise it is reported, not moved.
    Each moved entry's new path is recorded in ``moved_to``.
    """
    result = FileActionResult()
    pending = list(paths)
    prepared = _prepare_quarantine(completed_root, quarantine_dir)
    if isinstance(prepared, str):
        result.failed.extend((path, prepared) for path in pending)
        return result
    quarantine_device = prepared.stat().st_dev
    stamp = now.astimezone(UTC).strftime(QUARANTINE_STAMP_FORMAT)
    for path in pending:
        moved = _quarantine_one(
            path, completed_root, prepared, quarantine_device, stamp
        )
        if isinstance(moved, Path):
            result.done.append(path)
            result.moved_to[path] = moved
        else:
            result.failed.append((path, moved))
    return result


def _quarantine_one(
    path: Path, completed_root: Path, quarantine: Path, device: int, stamp: str
) -> Path | str:
    """Move one entry into quarantine; return its new path or a failure reason."""
    if path.is_symlink():
        return "symlink"
    if resolve_within(path, completed_root) is None:
        return "outside_root"
    try:
        if path.lstat().st_dev != device:
            return "cross_device"
        target = _free_target(quarantine, f"{stamp}{QUARANTINE_SEPARATOR}{path.name}")
        if target is None:
            return "name_clash"
        os.rename(path, target)
    except OSError as exc:
        return _error_reason(exc)
    return target


def quarantine_stamp(name: str) -> datetime | None:
    """Return the UTC move time encoded in a quarantined name, or ``None``."""
    prefix, separator, rest = name.partition(QUARANTINE_SEPARATOR)
    if not separator or not rest:
        return None
    try:
        return datetime.strptime(prefix, QUARANTINE_STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def quarantine_original_name(name: str) -> str:
    """Return the entry name a quarantined ``<stamp>__<name>`` was moved from.

    A numeric clash suffix added by the move (``-1``, ``-2`` …) cannot be told
    apart from one in the original name, so it is kept.
    """
    _prefix, _separator, rest = name.partition(QUARANTINE_SEPARATOR)
    return rest


def expired_quarantine(
    completed_root: Path,
    quarantine_dir: Path,
    *,
    retention: timedelta,
    now: datetime,
) -> list[Path]:
    """Return stamped, non-symlink quarantine entries older than ``retention``.

    Nothing is listed unless the quarantine folder is a real folder inside the
    completed folder (see :func:`resolve_within`).
    """
    quarantine = _existing_quarantine(completed_root, quarantine_dir)
    if quarantine is None:
        return []
    expired: list[Path] = []
    for entry in _list_dir(quarantine):
        stamp = quarantine_stamp(entry.name)
        if stamp is not None and not entry.is_symlink() and now - stamp >= retention:
            expired.append(entry)
    return expired


def quarantine_names(
    completed_root: Path, quarantine_dir: Path
) -> frozenset[str] | None:
    """Return the name of every entry in the quarantine folder.

    ``None`` when the folder is missing, unsafe (see :func:`resolve_within`)
    or unreadable, so a caller never mistakes it for an empty quarantine.
    """
    quarantine = _existing_quarantine(completed_root, quarantine_dir)
    if quarantine is None:
        return None
    try:
        return frozenset(entry.name for entry in quarantine.iterdir())
    except OSError:
        return None


def purge(
    paths: Iterable[Path], completed_root: Path, quarantine_dir: Path
) -> FileActionResult:
    """Delete quarantined entries (files or whole folders) for good.

    The quarantine folder must be a real folder inside ``completed_root`` (it
    is never trusted as a root of its own), and each entry must be a stamped,
    non-symlink direct child of it.
    """
    result = FileActionResult()
    quarantine = _existing_quarantine(completed_root, quarantine_dir)
    for path in paths:
        reason = _purge_one(path, quarantine)
        if reason is None:
            result.done.append(path)
        else:
            result.failed.append((path, reason))
    return result


def _purge_one(path: Path, quarantine: Path | None) -> str | None:
    """Delete one quarantined entry; return a failure reason or ``None``."""
    if path.is_symlink():
        return "symlink"
    if quarantine_stamp(path.name) is None:
        return "unstamped"
    resolved = None if quarantine is None else resolve_within(path, quarantine)
    if resolved is None or resolved.parent != quarantine:
        return "outside_quarantine"
    try:
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
    except OSError as exc:
        return _error_reason(exc)
    return None
