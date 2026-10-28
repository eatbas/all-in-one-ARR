"""Path mapping between SABnzbd's view of the disk and aio-arr's mounts.

:func:`reroot`, :func:`folder_name` and the category helpers are pure POSIX
string logic.
:func:`split_under` and :func:`resolve_within` touch the filesystem only to
resolve the root and to inspect (never follow) each component below it; they
are the single trust boundary every destructive file operation goes through.
"""

from __future__ import annotations

import posixpath
import stat
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

_UNUSABLE_FOLDER_NAMES = frozenset({"", ".", ".."})


def folder_name(path: str) -> str | None:
    """Return the folder a SABnzbd or Arr path names, or ``None`` when it names none.

    The folder is the last component of the path. A path without one (empty,
    ``/``, ``.``) or ending in ``..`` cannot be tied to a download folder;
    every queue association goes through this one rule.
    """
    name = PurePosixPath(path).name
    return None if name in _UNUSABLE_FOLDER_NAMES else name


def _is_absolute_clean(path: str) -> bool:
    """Return whether ``path`` is absolute and free of ``..`` segments."""
    return path.startswith("/") and ".." not in path.split("/")


def reroot(remote_path: str, remote_root: str, local_root: str) -> str | None:
    """Map ``remote_path`` under ``remote_root`` onto ``local_root``.

    Returns ``None`` when either remote value is not absolute, contains a
    ``..`` segment, or the path is not at or under the remote root (a sibling
    such as ``/downloads/complete2`` never matches ``/downloads/complete``).
    """
    if not (_is_absolute_clean(remote_path) and _is_absolute_clean(remote_root)):
        return None
    path = posixpath.normpath(remote_path)
    root = posixpath.normpath(remote_root)
    local = posixpath.normpath(local_root)
    if path == root:
        return local
    prefix = root if root.endswith("/") else f"{root}/"
    if not path.startswith(prefix):
        return None
    return posixpath.join(local, path[len(prefix) :])


def _container_name(directory: str, complete_dir: str) -> str | None:
    """Return a category ``dir``'s single-segment folder name under ``complete_dir``.

    A relative ``dir`` is taken as relative to the completed folder; an
    absolute one counts only when it sits directly under ``complete_dir``.
    """
    if directory.startswith("/"):
        relative = reroot(directory, complete_dir, "/")
        directory = (relative or "").lstrip("/")
    normalised = posixpath.normpath(directory.strip("/")) if directory else ""
    if normalised and "/" not in normalised and normalised not in {".", ".."}:
        return normalised
    return None


def category_container_names(
    category_dirs: Iterable[str], complete_dir: str
) -> frozenset[str]:
    """Return the single-segment category folder names directly under ``complete_dir``."""
    names = (_container_name(directory, complete_dir) for directory in category_dirs)
    return frozenset(name for name in names if name is not None)


def container_categories(
    category_folders: Iterable[tuple[str, str]], complete_dir: str
) -> dict[str, frozenset[str]]:
    """Return each category folder name mapped to the category names using it.

    ``category_folders`` holds SABnzbd's ``(name, dir)`` pairs; folders that
    are not directly under ``complete_dir`` are left out.
    """
    categories: dict[str, set[str]] = {}
    for name, directory in category_folders:
        container = _container_name(directory, complete_dir)
        if container is not None and name:
            categories.setdefault(container, set()).add(name)
    return {key: frozenset(value) for key, value in categories.items()}


def split_under(path: Path, root: Path) -> tuple[Path, tuple[str, ...]] | None:
    """Return ``root`` resolved and ``path``'s components below it, or ``None``.

    The split is lexical: ``path`` must be absolute, free of ``..`` and
    written under ``root`` either as configured or as resolved. Only ``root``
    itself is resolved (it is the trusted mount point); nothing below it is.
    """
    if not path.is_absolute() or ".." in path.parts:
        return None
    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        return None
    for base in (root, resolved_root):
        if path.is_relative_to(base):
            return resolved_root, path.relative_to(base).parts
    return None


def resolve_within(path: Path, root: Path) -> Path | None:
    """Return ``path`` resolved when it exists inside ``root`` without symlinks.

    Every component from ``root`` down to ``path`` must exist and must not be
    a symlink, so a link can never redirect an operation, not even to another
    folder inside the root. A missing component, a symlink, a path outside the
    root or any ``OSError`` yields ``None``.
    """
    split = split_under(path, root)
    if split is None:
        return None
    current, parts = split
    for part in parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError:
            return None
        if stat.S_ISLNK(mode):
            return None
    return current
