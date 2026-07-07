"""Authoritative Deletarr library manifest built from Radarr/Sonarr.

A :class:`LibraryManifest` is the "keep-set": for each media folder Radarr/Sonarr
manages, it records the tracked media files (translated onto Deletarr's local
mount). The arr-backed scanner treats anything inside a managed folder that is not
a tracked media file (and not a recognised companion) as unnecessary, and any
folder the app does not know about as *orphaned*.

Path translation is required because Radarr/Sonarr report paths as *they* see them
(their own container mounts), which usually differ from Deletarr's mount. Each Arr
path is re-rooted relative to the shared Arr *library mount* (the longest path
prefix common to every Arr root folder) onto the local library root, so a
nested/categorised layout below that mount — e.g. movies grouped under
``archive/`` or ``collections/`` category root folders — is preserved instead of
being flattened onto the local root. A path that cannot be resolved is dropped
rather than guessed at, so it can never become a deletion candidate.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from core.logging import get_logger
from modules.deletarr.arr_source import DeletarrArrClient, DeletarrArrError
from modules.deletarr.models import LibraryType

_log = get_logger("deletarr.manifest")


def _norm(path: str) -> str:
    """Normalise a path for stable set membership against ``os.walk`` output."""
    return os.path.normpath(path)


def _basename_without_ext(name: str) -> str:
    """Return a filename without its final extension (``Movie.mkv`` -> ``Movie``)."""
    suffix = Path(name).suffix
    return name[: -len(suffix)] if suffix else name


def _parts(path: str) -> list[str]:
    """Split an Arr path into components, tolerating posix and Windows separators."""
    return [part for part in path.replace("\\", "/").split("/") if part]


def _common_root(arr_roots: list[str]) -> list[str] | None:
    """Return the path components shared by every Arr root folder.

    This is the Arr-side *library mount* that maps onto Deletarr's single local
    root. With one root it is that root; with several category roots nested under
    a shared parent (e.g. ``.../movies/archive`` and ``.../movies/collections``)
    it is the shared parent, so re-rooting keeps the category segment instead of
    collapsing every category onto the local root. Returns ``None`` when the roots
    share no common prefix (an unsupported multi-mount layout); every translation
    then resolves to ``None`` and the scan falls back to the heuristic mode.
    """
    part_lists = [parts for parts in (_parts(root) for root in arr_roots) if parts]
    if not part_lists:
        return None
    shared = part_lists[0]
    for parts in part_lists[1:]:
        limit = min(len(shared), len(parts))
        matched = 0
        while matched < limit and shared[matched] == parts[matched]:
            matched += 1
        shared = shared[:matched]
        if not shared:
            return None
    return shared


def _reroot(arr_path: str, arr_roots: list[str], local_root: str) -> str | None:
    """Re-root an Arr-reported path under the local Deletarr mount.

    Translates relative to the shared Arr library mount (see :func:`_common_root`)
    so the sub-structure below it — including any category folders — is preserved,
    then joins the remainder onto ``local_root``. Returns ``None`` when the roots
    share no mount or ``arr_path`` lies outside it, so the caller treats the path
    as unresolved (never deletable).
    """
    mount = _common_root(arr_roots)
    if mount is None:
        return None
    arr_parts = _parts(arr_path)
    if arr_parts[: len(mount)] != mount:
        return None
    remainder = arr_parts[len(mount) :]
    if not remainder:
        return _norm(local_root)
    return _norm(os.path.join(local_root, *remainder))


@dataclass(frozen=True)
class ManagedFolder:
    """One media folder that an Arr app tracks, with its keep-set."""

    path: str
    media_paths: frozenset[str]
    media_basenames: frozenset[str]


@dataclass
class LibraryManifest:
    """The translated keep-set for one Deletarr library."""

    library_type: LibraryType
    root: str
    available: bool
    detail: str | None = None
    # Folders that contain at least one tracked media file (safe to clean inside).
    folders: dict[str, ManagedFolder] = field(default_factory=dict)
    # Every folder the Arr knows about (superset of ``folders``), used only to
    # decide whether an on-disk folder is *orphaned* — a fileless-but-known folder
    # is left alone, never flagged as orphaned.
    known_folders: frozenset[str] = frozenset()

    @property
    def media_paths(self) -> set[str]:
        """All tracked media file paths across every managed folder."""
        result: set[str] = set()
        for folder in self.folders.values():
            result |= set(folder.media_paths)
        return result

    def folder_for(self, path: str) -> ManagedFolder | None:
        """Return the managed folder for a normalised on-disk path, if any."""
        return self.folders.get(_norm(path))

    def is_known_folder(self, path: str) -> bool:
        """Whether the Arr knows this folder (managed or fileless-but-tracked)."""
        return _norm(path) in self.known_folders

    def contains_managed_descendant(self, path: str) -> bool:
        """Whether any known Arr folder lives strictly below ``path``.

        Detects an intermediate *category* container (e.g. ``.../movies/archive``)
        that is not itself a movie/show folder but holds managed folders deeper
        down. The scanner descends into such a container instead of flagging it as
        orphaned, so nested and categorised libraries are handled correctly.
        """
        prefix = _norm(path) + os.sep
        return any(known.startswith(prefix) for known in self.known_folders)


def _collect_roots(
    items: list[dict], root_folders: list[dict]
) -> list[str]:
    """Gather Arr root-folder paths from the rootfolder list and item fields."""
    roots: set[str] = {
        str(entry["path"]) for entry in root_folders if entry.get("path")
    }
    for item in items:
        root_path = item.get("rootFolderPath")
        if root_path:
            roots.add(str(root_path))
    return [root for root in roots if root]


async def build_movie_manifest(
    client: DeletarrArrClient, local_root: str
) -> LibraryManifest:
    """Build the movies manifest from Radarr's tracked movie files."""
    root = _norm(local_root)
    try:
        movies = await client.movies()
        root_folders = await client.root_folders()
    except DeletarrArrError as exc:
        _log.info("radarr manifest unavailable: %s", exc)
        return LibraryManifest("movies", root, available=False, detail=str(exc))

    roots = _collect_roots(movies, root_folders)
    folders: dict[str, ManagedFolder] = {}
    known: set[str] = set()

    for movie in movies:
        arr_folder = movie.get("path")
        if not arr_folder:
            continue
        local_folder = _reroot(str(arr_folder), roots, local_root)
        if local_folder is None:
            continue
        known.add(local_folder)

        media_paths: set[str] = set()
        basenames: set[str] = set()
        movie_file = movie.get("movieFile")
        if isinstance(movie_file, dict) and movie_file.get("path"):
            local_file = _reroot(str(movie_file["path"]), roots, local_root)
            if local_file is not None:
                media_paths.add(local_file)
                basenames.add(_basename_without_ext(os.path.basename(local_file)))

        if media_paths:
            folders[local_folder] = ManagedFolder(
                path=local_folder,
                media_paths=frozenset(media_paths),
                media_basenames=frozenset(basenames),
            )

    return LibraryManifest(
        "movies", root, available=True, folders=folders, known_folders=frozenset(known)
    )


async def build_tv_manifest(
    client: DeletarrArrClient, local_root: str
) -> LibraryManifest:
    """Build the TV manifest from Sonarr's tracked episode files per series."""
    root = _norm(local_root)
    try:
        series = await client.series()
        root_folders = await client.root_folders()
    except DeletarrArrError as exc:
        _log.info("sonarr manifest unavailable: %s", exc)
        return LibraryManifest("tv", root, available=False, detail=str(exc))

    roots = _collect_roots(series, root_folders)
    folders: dict[str, ManagedFolder] = {}
    known: set[str] = set()

    for show in series:
        arr_folder = show.get("path")
        series_id = show.get("id")
        if not arr_folder or series_id is None:
            continue
        local_folder = _reroot(str(arr_folder), roots, local_root)
        if local_folder is None:
            continue
        known.add(local_folder)

        try:
            episode_files = await client.episode_files(int(series_id))
        except DeletarrArrError as exc:
            _log.info("sonarr episode files unavailable: %s", exc)
            return LibraryManifest("tv", root, available=False, detail=str(exc))

        media_paths: set[str] = set()
        basenames: set[str] = set()
        for episode_file in episode_files:
            arr_file = episode_file.get("path")
            if not arr_file:
                continue
            local_file = _reroot(str(arr_file), roots, local_root)
            if local_file is not None:
                media_paths.add(local_file)
                basenames.add(_basename_without_ext(os.path.basename(local_file)))

        if media_paths:
            folders[local_folder] = ManagedFolder(
                path=local_folder,
                media_paths=frozenset(media_paths),
                media_basenames=frozenset(basenames),
            )

    return LibraryManifest(
        "tv", root, available=True, folders=folders, known_folders=frozenset(known)
    )
