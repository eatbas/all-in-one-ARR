"""Filesystem scanner for Deletarr media libraries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.logging import get_logger
from modules.deletarr.manifest import LibraryManifest, ManagedFolder
from modules.deletarr.models import (
    CandidateCategory,
    ItemKind,
    ItemOrigin,
    LibraryType,
    ScanItem,
    ScanStats,
    VideoReference,
    normalise_library_type,
    stats_for,
)
from modules.deletarr.patterns import JunkPatterns

_log = get_logger("deletarr.scanner")


@dataclass
class _MovieFile:
    """Typed file metadata used while classifying one movie folder."""

    path: str
    name: str
    size: int
    parent: str
    reason: str = ""


class MediaScanner:
    """Scan media directories for files and folders that are safe to review."""

    def __init__(self, media_paths: list[str]) -> None:
        self.media_paths = media_paths
        self.scan_results: list[ScanItem] = []
        self.is_scanning = False
        self.scan_progress = 0

    def scan(self, library_type: LibraryType = "movies") -> list[ScanItem]:
        """Scan configured paths for junk files using movie or TV rules."""
        selected = normalise_library_type(library_type)
        self.is_scanning = True
        self.scan_results = []
        self.scan_progress = 0

        try:
            for media_path in self.media_paths:
                if not os.path.exists(media_path):
                    _log.warning("media path does not exist: %s", media_path)
                    continue
                _log.info("scanning %s library: %s", selected, media_path)
                if selected == "tv":
                    self._scan_tv_directory(media_path)
                else:
                    self._scan_movie_directory(media_path)
            self.scan_progress = 100
            _log.info(
                "scan complete; found %d review candidate(s)", len(self.scan_results)
            )
        finally:
            self.is_scanning = False

        return self.scan_results

    def _scan_tv_directory(self, directory: str) -> None:
        """Scan TV libraries with Show -> Season -> Episode expectations."""
        for root, dirs, files in os.walk(directory):
            self._prepare_walk_directories(root, dirs, directory, "tv")
            self._emit_empty_subdirectories(root, dirs, directory, "tv")
            if os.path.normpath(root) == os.path.normpath(directory):
                self._append_loose_files(root, files)
                continue
            self._classify_tv_folder(root, dirs, files)

    def _scan_movie_directory(self, directory: str) -> None:
        """Scan movie libraries, preserving the largest matching video per folder."""
        for root, dirs, files in os.walk(directory):
            self._prepare_walk_directories(root, dirs, directory, "movies")
            self._emit_empty_subdirectories(root, dirs, directory, "movies")
            if os.path.normpath(root) == os.path.normpath(directory):
                self._append_loose_files(root, files)
                continue
            self._classify_movie_folder(root, files)

    def _prepare_walk_directories(
        self,
        root: str,
        dirs: list[str],
        library_root: str,
        library_type: LibraryType,
        *,
        group_name: str | None = None,
        group_path: str | None = None,
        origin: ItemOrigin = "heuristic",
    ) -> None:
        """Filter unsafe directories and emit junk-folder candidates."""
        dirs[:] = [
            name
            for name in dirs
            if name not in JunkPatterns.IGNORED_FOLDERS
            and not name.startswith(".")
            and not os.path.islink(os.path.join(root, name))
        ]
        for dir_name in list(dirs):
            if not JunkPatterns.is_junk_folder(dir_name):
                continue
            folder_path = os.path.join(root, dir_name)
            candidate_group_name = group_name
            candidate_group_path = group_path
            if candidate_group_name is None or candidate_group_path is None:
                candidate_group_name, candidate_group_path = self._group_for_path(
                    folder_path, library_root, library_type
                )
            self._append_candidate(
                path=folder_path,
                name=dir_name,
                item_type="folder",
                size=self._get_folder_size(folder_path),
                reason="Junk folder",
                parent=root,
                category="junk",
                group_name=candidate_group_name,
                group_path=candidate_group_path,
                origin=origin,
            )
            dirs.remove(dir_name)

    def _classify_tv_folder(self, root: str, dirs: list[str], files: list[str]) -> None:
        """Classify one show-root or season directory."""
        folder_name = os.path.basename(root)
        if self._is_tv_show_root(dirs):
            self._flag_unexpected_show_directories(root, dirs, folder_name)
        if not (
            JunkPatterns.is_tv_season_folder(folder_name)
            or JunkPatterns.is_tv_specials_folder(folder_name)
        ):
            return
        parent_name = os.path.basename(os.path.dirname(root))
        group_name = f"{parent_name} - {folder_name}"
        videos = self._classify_tv_files(root, files, parent_name, group_name)
        self._flag_unexpected_season_directories(root, dirs, group_name)
        for item in self.scan_results:
            if item.movie_folder_path == root:
                item.videos_in_folder = list(videos)

    @staticmethod
    def _is_tv_show_root(dirs: list[str]) -> bool:
        return any(
            JunkPatterns.is_tv_season_folder(name)
            or JunkPatterns.is_tv_specials_folder(name)
            for name in dirs
        )

    def _flag_unexpected_show_directories(
        self, root: str, dirs: list[str], folder_name: str
    ) -> None:
        for dir_name in list(dirs):
            if JunkPatterns.is_tv_season_folder(
                dir_name
            ) or JunkPatterns.is_tv_specials_folder(dir_name):
                continue
            folder_path = os.path.join(root, dir_name)
            self._append_candidate(
                path=folder_path,
                name=dir_name,
                item_type="folder",
                size=self._get_folder_size(folder_path),
                reason="Unexpected folder in TV Show directory",
                parent=root,
                category="junk",
                group_name=f"{folder_name} (Show Root)",
                group_path=root,
            )
            dirs.remove(dir_name)

    def _classify_tv_files(
        self, root: str, files: list[str], show_name: str, group_name: str
    ) -> list[VideoReference]:
        videos: list[VideoReference] = []
        for filename in files:
            if filename in JunkPatterns.IGNORED_FOLDERS:
                continue
            filepath = os.path.join(root, filename)
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue
            if JunkPatterns.is_video_file(
                filename
            ) and JunkPatterns.is_valid_tv_episode(filename, show_name):
                videos.append(VideoReference(name=filename, size=size))
                continue
            reason = (
                "Irregular episode naming (missing SxxExx or show name)"
                if JunkPatterns.is_video_file(filename)
                else "Non-video file in Season folder"
            )
            self._append_candidate(
                path=filepath,
                name=filename,
                item_type="file",
                size=size,
                reason=reason,
                parent=root,
                category="junk",
                group_name=group_name,
                group_path=root,
            )
        return videos

    def _flag_unexpected_season_directories(
        self, root: str, dirs: list[str], group_name: str
    ) -> None:
        for dir_name in list(dirs):
            folder_path = os.path.join(root, dir_name)
            self._append_candidate(
                path=folder_path,
                name=dir_name,
                item_type="folder",
                size=self._get_folder_size(folder_path),
                reason="Unexpected folder inside Season",
                parent=root,
                category="junk",
                group_name=group_name,
                group_path=root,
            )
            dirs.remove(dir_name)

    def _classify_movie_folder(self, root: str, files: list[str]) -> None:
        """Classify files within one movie directory."""
        all_files, videos, video_basenames = self._movie_file_metadata(root, files)
        if not videos:
            return
        folder_name = os.path.basename(root)
        junk = self._movie_junk_files(all_files, videos, video_basenames, folder_name)
        valid_videos = self._valid_movie_videos(videos, junk, folder_name)
        references = [
            VideoReference(name=video.name, size=video.size) for video in valid_videos
        ]
        for candidate in junk:
            self._append_candidate(
                path=candidate.path,
                name=candidate.name,
                item_type="file",
                size=candidate.size,
                reason=candidate.reason,
                parent=candidate.parent,
                category="junk",
                group_name=folder_name,
                group_path=root,
                videos=references,
            )

    @staticmethod
    def _movie_file_metadata(
        root: str, files: list[str]
    ) -> tuple[list[_MovieFile], list[_MovieFile], list[str]]:
        all_files: list[_MovieFile] = []
        videos: list[_MovieFile] = []
        basenames: list[str] = []
        for filename in files:
            if filename in JunkPatterns.IGNORED_FOLDERS:
                continue
            filepath = os.path.join(root, filename)
            try:
                item = _MovieFile(filepath, filename, os.path.getsize(filepath), root)
            except OSError as exc:
                _log.warning("could not stat file %s: %s", filepath, exc)
                continue
            all_files.append(item)
            if not JunkPatterns.is_video_file(filename):
                continue
            videos.append(item)
            suffix = Path(filename).suffix
            if suffix:
                basenames.append(filename[: -len(suffix)])
        return all_files, videos, basenames

    @staticmethod
    def _movie_junk_files(
        all_files: list[_MovieFile],
        videos: list[_MovieFile],
        video_basenames: list[str],
        folder_name: str,
    ) -> list[_MovieFile]:
        video_paths = {item.path for item in videos}
        junk: list[_MovieFile] = []
        for item in all_files:
            if item.path in video_paths:
                continue
            check = JunkPatterns.is_junk_file(
                item.name, item.path, video_basenames, folder_name
            )
            if check["is_junk"]:
                item.reason = str(check["reason"])
                junk.append(item)
        return junk

    @staticmethod
    def _valid_movie_videos(
        videos: list[_MovieFile], junk: list[_MovieFile], folder_name: str
    ) -> list[_MovieFile]:
        valid: list[_MovieFile] = []
        for item in videos:
            if JunkPatterns.video_matches_folder(item.name, folder_name):
                valid.append(item)
            else:
                item.reason = "Misplaced video (filename does not match folder)"
                junk.append(item)
        valid.sort(key=lambda item: item.size, reverse=True)
        if len(valid) < 2:
            return valid
        largest = valid[0]
        for duplicate in valid[1:]:
            duplicate.reason = f"Duplicate video (smaller than {largest.name})"
            junk.append(duplicate)
        return [largest]

    def scan_arr(self, manifest: LibraryManifest) -> list[ScanItem]:
        """Scan using a Radarr/Sonarr manifest as the source of truth.

        Files tracked by the Arr are kept; anything else inside a managed folder is
        flagged as unnecessary, and folders the Arr does not know about are surfaced
        as orphaned. Every candidate requires explicit selection by the caller.
        """
        app_label = "Radarr" if manifest.library_type == "movies" else "Sonarr"
        self.is_scanning = True
        self.scan_results = []
        self.scan_progress = 0
        try:
            for media_path in self.media_paths:
                if not os.path.exists(media_path):
                    _log.warning("media path does not exist: %s", media_path)
                    continue
                _log.info(
                    "scanning %s library against %s", manifest.library_type, app_label
                )
                self._scan_with_manifest(media_path, manifest, app_label)
            self.scan_progress = 100
            _log.info("arr scan complete; found %d item(s)", len(self.scan_results))
        finally:
            self.is_scanning = False
        return self.scan_results

    def _scan_with_manifest(
        self, directory: str, manifest: LibraryManifest, app_label: str
    ) -> None:
        """Scan ``directory`` against the Arr manifest.

        Managed folders are cleaned in place; a folder that merely *contains*
        managed folders deeper down (a category container such as ``archive/`` or
        ``collections/``) is descended into rather than flagged, so nested and
        categorised libraries are handled. Only folders the Arr knows nothing
        about, and loose top-level files, are surfaced as orphaned.
        """
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:  # pragma: no cover - defensive
            _log.warning("could not list %s: %s", directory, exc)
            return

        for entry in entries:
            if entry.name in JunkPatterns.IGNORED_FOLDERS or entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                folder = manifest.folder_for(entry.path)
                if folder is not None:
                    if self._is_empty_tree(entry.path):
                        self._append_empty_folder(
                            entry.path,
                            directory,
                            manifest.library_type,
                            origin="arr",
                        )
                    else:
                        self._clean_managed_folder(
                            entry.path, folder, app_label, manifest.library_type
                        )
                elif manifest.is_known_folder(entry.path):
                    # A truly empty known folder is reviewable. Any content may be
                    # pending import, so preserve the complete folder otherwise.
                    if self._is_empty_tree(entry.path):
                        self._append_empty_folder(
                            entry.path,
                            directory,
                            manifest.library_type,
                            origin="arr",
                        )
                elif manifest.contains_managed_descendant(entry.path):
                    # Category container (e.g. archive/, collections/) that holds
                    # managed folders below it — descend rather than flag it.
                    self._scan_with_manifest(entry.path, manifest, app_label)
                else:
                    self._append_candidate(
                        path=entry.path,
                        name=entry.name,
                        item_type="folder",
                        size=self._get_folder_size(entry.path),
                        reason=f"Orphaned folder (not in {app_label})",
                        parent=directory,
                        category="untracked_media",
                        group_name=entry.name,
                        group_path=entry.path,
                        origin="arr",
                    )
            else:
                try:
                    size = os.path.getsize(entry.path)
                except OSError:  # pragma: no cover - defensive
                    continue
                self._append_candidate(
                    path=entry.path,
                    name=entry.name,
                    item_type="file",
                    size=size,
                    reason=f"Loose file (not in {app_label})",
                    parent=directory,
                    category="untracked_media",
                    group_name="Loose files",
                    group_path=directory,
                    origin="arr",
                )

    def _clean_managed_folder(
        self,
        folder_dir: str,
        folder: ManagedFolder,
        app_label: str,
        library_type: LibraryType,
    ) -> None:
        """Flag every non-tracked file/folder inside one managed media folder."""
        videos = self._folder_videos(folder)
        start = len(self.scan_results)
        display_name = os.path.basename(folder_dir)

        for root, dirs, files in os.walk(folder_dir):
            self._prepare_walk_directories(
                root,
                dirs,
                folder_dir,
                library_type,
                group_name=display_name,
                group_path=folder_dir,
                origin="arr",
            )
            self._emit_empty_subdirectories(
                root,
                dirs,
                folder_dir,
                library_type,
                origin="arr",
                group_name=display_name,
                group_path=folder_dir,
            )
            self._classify_managed_files(
                root, files, folder, folder_dir, display_name, app_label
            )

        for item in self.scan_results[start:]:
            item.videos_in_folder = list(videos)

    def _classify_managed_files(
        self,
        root: str,
        files: list[str],
        folder: ManagedFolder,
        folder_dir: str,
        display_name: str,
        app_label: str,
    ) -> None:
        """Classify untracked files inside one managed folder walk step."""
        for filename in files:
            if filename in JunkPatterns.IGNORED_FOLDERS:
                continue
            filepath = os.path.join(root, filename)
            if os.path.normpath(filepath) in folder.media_paths:
                continue
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue
            is_video = JunkPatterns.is_video_file(filename)
            reason = self._managed_file_reason(
                filename, filepath, root, folder, app_label, is_video
            )
            if reason is None:
                continue
            self._append_candidate(
                path=filepath,
                name=filename,
                item_type="file",
                size=size,
                reason=reason,
                parent=root,
                category="untracked_media" if is_video else "junk",
                group_name=display_name,
                group_path=folder_dir,
                origin="arr",
            )

    @staticmethod
    def _managed_file_reason(
        filename: str,
        filepath: str,
        root: str,
        folder: ManagedFolder,
        app_label: str,
        is_video: bool,
    ) -> str | None:
        if is_video:
            return f"Untracked video (not in {app_label})"
        check = JunkPatterns.is_junk_file(
            filename,
            filepath,
            list(folder.media_basenames),
            os.path.basename(root),
        )
        return str(check["reason"]) if check["is_junk"] else None

    @staticmethod
    def _folder_videos(folder: ManagedFolder) -> list[VideoReference]:
        """Build the protected-video context for a managed folder from disk sizes."""
        videos: list[VideoReference] = []
        for media_path in sorted(folder.media_paths):
            try:
                size = os.path.getsize(media_path)
            except OSError:
                size = 0
            videos.append(VideoReference(name=os.path.basename(media_path), size=size))
        return videos

    @staticmethod
    def _is_empty_tree(folder_path: str) -> bool:
        """Return whether a directory tree is positively proven to contain no data.

        Directory symlinks and listing/type errors are content for safety purposes:
        neither can establish that deleting the tree is harmless.
        """
        try:
            with os.scandir(folder_path) as entries:
                for entry in entries:
                    if (
                        entry.name in JunkPatterns.IGNORED_FOLDERS
                        or entry.name.startswith(".")
                    ):
                        return False
                    try:
                        if entry.is_symlink():
                            return False
                        if not entry.is_dir(follow_symlinks=False):
                            return False
                    except OSError:
                        return False
                    if not MediaScanner._is_empty_tree(entry.path):
                        return False
        except OSError:
            return False
        return True

    def _append_loose_files(self, root: str, files: list[str]) -> None:
        """Surface non-symlinked files placed directly in a library root."""
        for filename in files:
            if filename in JunkPatterns.IGNORED_FOLDERS:
                continue
            filepath = os.path.join(root, filename)
            if os.path.islink(filepath):
                continue
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue
            self._append_candidate(
                path=filepath,
                name=filename,
                item_type="file",
                size=size,
                reason="Loose file in library root",
                parent=root,
                category="untracked_media",
                group_name="Loose files",
                group_path=root,
            )

    def _emit_empty_subdirectories(
        self,
        root: str,
        dirs: list[str],
        library_root: str,
        library_type: LibraryType,
        *,
        origin: ItemOrigin = "heuristic",
        group_name: str | None = None,
        group_path: str | None = None,
    ) -> None:
        """Emit and prune the highest positively empty subtrees below ``root``."""
        for dir_name in list(dirs):
            folder_path = os.path.join(root, dir_name)
            if (
                dir_name in JunkPatterns.IGNORED_FOLDERS
                or dir_name.startswith(".")
                or os.path.islink(folder_path)
                or not self._is_empty_tree(folder_path)
            ):
                continue
            self._append_empty_folder(
                folder_path,
                library_root,
                library_type,
                origin=origin,
                group_name=group_name,
                group_path=group_path,
            )
            dirs.remove(dir_name)

    def _append_empty_folder(
        self,
        folder_path: str,
        library_root: str,
        library_type: LibraryType,
        *,
        origin: ItemOrigin,
        group_name: str | None = None,
        group_path: str | None = None,
    ) -> None:
        """Append one unselected empty-folder candidate with stable grouping."""
        if group_name is None or group_path is None:
            group_name, group_path = self._group_for_path(
                folder_path, library_root, library_type
            )
        self._append_candidate(
            path=folder_path,
            name=os.path.basename(folder_path),
            item_type="folder",
            size=0,
            reason="Empty folder",
            parent=os.path.dirname(folder_path),
            category="junk",
            group_name=group_name,
            group_path=group_path,
            origin=origin,
        )

    def _append_candidate(
        self,
        *,
        path: str,
        name: str,
        item_type: ItemKind,
        size: int,
        reason: str,
        parent: str,
        category: CandidateCategory,
        group_name: str | None,
        group_path: str | None,
        origin: ItemOrigin = "heuristic",
        videos: list[VideoReference] | None = None,
    ) -> None:
        """Construct every candidate with the shared destructive defaults."""
        self.scan_results.append(
            ScanItem(
                path=path,
                name=name,
                type=item_type,
                size=size,
                reason=reason,
                parent=parent,
                category=category,
                movie_folder=group_name,
                movie_folder_path=group_path,
                is_checked=False,
                videos_in_folder=list(videos or []),
                origin=origin,
            )
        )

    @staticmethod
    def _group_for_path(
        folder_path: str, library_root: str, library_type: LibraryType
    ) -> tuple[str, str]:
        """Return stable legacy group fields for a movie or TV candidate path."""
        relative = os.path.relpath(folder_path, library_root)
        parts = relative.split(os.sep)
        title_path = os.path.join(library_root, parts[0])
        if (
            library_type == "tv"
            and len(parts) > 1
            and (
                JunkPatterns.is_tv_season_folder(parts[1])
                or JunkPatterns.is_tv_specials_folder(parts[1])
            )
        ):
            season_path = os.path.join(title_path, parts[1])
            return f"{parts[0]} - {parts[1]}", season_path
        return parts[0], title_path

    def _get_folder_size(self, folder_path: str) -> int:
        """Return the total byte size of ``folder_path``."""
        total_size = 0
        for dirpath, _, filenames in os.walk(folder_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    continue
        return total_size

    def get_stats(self) -> ScanStats:
        """Return current scan-result statistics."""
        return stats_for(
            self.scan_results,
            is_scanning=self.is_scanning,
            scan_progress=self.scan_progress,
        )

    def get_sorted_results(self) -> list[ScanItem]:
        """Return scan results sorted by total junk size per folder.

        Items are grouped by ``movie_folder_path``; orphan junk folders, which
        carry no ``movie_folder_path``, fall back to their own ``path`` so each
        is sorted as its own group. This intentionally departs from the
        standalone Deletarr scanner, which bucketed every such folder under a
        single ``"other"`` key, and matches how the frontend regroups results
        by ``movie_folder_path`` (falling back to ``parent``).
        """
        folder_groups: dict[str, dict[str, Any]] = {}
        for item in self.scan_results:
            folder_path = item.movie_folder_path or item.path
            if folder_path not in folder_groups:
                folder_groups[folder_path] = {"files": [], "total_size": 0}
            files = folder_groups[folder_path]["files"]
            assert isinstance(files, list)
            files.append(item)
            folder_groups[folder_path]["total_size"] = (
                int(folder_groups[folder_path]["total_size"]) + item.size
            )

        sorted_groups = sorted(
            folder_groups.values(),
            key=lambda item: int(item["total_size"]),
            reverse=True,
        )
        sorted_results: list[ScanItem] = []
        for group in sorted_groups:
            files = group["files"]
            assert isinstance(files, list)
            sorted_results.extend(files)
        return sorted_results
