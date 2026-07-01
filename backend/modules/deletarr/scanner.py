"""Filesystem scanner for Deletarr media libraries."""

from __future__ import annotations

import os
from pathlib import Path

from core.logging import get_logger
from modules.deletarr.manifest import LibraryManifest, ManagedFolder
from modules.deletarr.models import (
    LibraryType,
    ScanItem,
    ScanStats,
    VideoReference,
    normalise_library_type,
    stats_for,
)
from modules.deletarr.patterns import JunkPatterns

_log = get_logger("deletarr.scanner")


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
            _log.info("scan complete; found %d junk item(s)", len(self.scan_results))
        finally:
            self.is_scanning = False

        return self.scan_results

    def _scan_tv_directory(self, directory: str) -> None:
        """Scan TV libraries with Show -> Season -> Episode expectations."""
        for root, dirs, files in os.walk(directory):
            dirs[:] = [name for name in dirs if name not in JunkPatterns.IGNORED_FOLDERS]

            dirs_to_remove: list[str] = []
            for dir_name in dirs:
                if JunkPatterns.is_junk_folder(dir_name):
                    folder_path = os.path.join(root, dir_name)
                    self.scan_results.append(
                        ScanItem(
                            path=folder_path,
                            name=dir_name,
                            type="folder",
                            size=self._get_folder_size(folder_path),
                            reason="Junk folder",
                            parent=root,
                        )
                    )
                    dirs_to_remove.append(dir_name)
            for dir_name in dirs_to_remove:
                dirs.remove(dir_name)

            folder_name = os.path.basename(root)
            parent_name = os.path.basename(os.path.dirname(root))
            is_show_root = any(
                JunkPatterns.is_tv_season_folder(name)
                or JunkPatterns.is_tv_specials_folder(name)
                for name in dirs
            )

            if is_show_root:
                strict_remove: list[str] = []
                for dir_name in dirs:
                    if not (
                        JunkPatterns.is_tv_season_folder(dir_name)
                        or JunkPatterns.is_tv_specials_folder(dir_name)
                    ):
                        folder_path = os.path.join(root, dir_name)
                        self.scan_results.append(
                            ScanItem(
                                path=folder_path,
                                name=dir_name,
                                type="folder",
                                size=self._get_folder_size(folder_path),
                                reason="Unexpected folder in TV Show directory",
                                parent=root,
                                movie_folder=f"{folder_name} (Show Root)",
                                movie_folder_path=root,
                                # A whole folder is never auto-selected on a
                                # name-shape miss (it could be a real season).
                                is_checked=False,
                            )
                        )
                        strict_remove.append(dir_name)
                for dir_name in strict_remove:
                    dirs.remove(dir_name)

            is_season = JunkPatterns.is_tv_season_folder(folder_name)
            is_specials = JunkPatterns.is_tv_specials_folder(folder_name)
            if not (is_season or is_specials):
                continue

            group_name = f"{parent_name} - {folder_name}"
            video_files: list[VideoReference] = []

            for filename in files:
                if filename in JunkPatterns.IGNORED_FOLDERS:
                    continue
                filepath = os.path.join(root, filename)
                try:
                    size = os.path.getsize(filepath)
                except OSError:
                    continue

                if JunkPatterns.is_video_file(filename):
                    if JunkPatterns.is_valid_tv_episode(filename, parent_name):
                        video_files.append(VideoReference(name=filename, size=size))
                    else:
                        self.scan_results.append(
                            ScanItem(
                                path=filepath,
                                name=filename,
                                type="file",
                                size=size,
                                reason="Irregular episode naming (missing SxxExx or show name)",
                                parent=root,
                                movie_folder=group_name,
                                movie_folder_path=root,
                                # A video is never auto-selected on a name miss.
                                is_checked=False,
                            )
                        )
                else:
                    self.scan_results.append(
                        ScanItem(
                            path=filepath,
                            name=filename,
                            type="file",
                            size=size,
                            reason="Non-video file in Season folder",
                            parent=root,
                            movie_folder=group_name,
                            movie_folder_path=root,
                            is_checked=not is_specials,
                        )
                    )

            for dir_name in list(dirs):
                folder_path = os.path.join(root, dir_name)
                self.scan_results.append(
                    ScanItem(
                        path=folder_path,
                        name=dir_name,
                        type="folder",
                        size=self._get_folder_size(folder_path),
                        reason="Unexpected folder inside Season",
                        parent=root,
                        movie_folder=group_name,
                        movie_folder_path=root,
                        # A whole folder is never auto-selected for deletion.
                        is_checked=False,
                    )
                )
                dirs_to_remove.append(dir_name)
            for dir_name in dirs_to_remove:
                if dir_name in dirs:
                    dirs.remove(dir_name)

            for item in self.scan_results:
                if item.movie_folder_path == root:
                    item.videos_in_folder = list(video_files)

    def _scan_movie_directory(self, directory: str) -> None:
        """Scan movie libraries, preserving the largest matching video per folder."""
        for root, dirs, files in os.walk(directory):
            dirs[:] = [name for name in dirs if name not in JunkPatterns.IGNORED_FOLDERS]

            dirs_to_remove: list[str] = []
            for dir_name in dirs:
                if JunkPatterns.is_junk_folder(dir_name):
                    folder_path = os.path.join(root, dir_name)
                    self.scan_results.append(
                        ScanItem(
                            path=folder_path,
                            name=dir_name,
                            type="folder",
                            size=self._get_folder_size(folder_path),
                            reason="Junk folder",
                            parent=root,
                        )
                    )
                    dirs_to_remove.append(dir_name)
            for dir_name in dirs_to_remove:
                dirs.remove(dir_name)

            all_files: list[dict[str, object]] = []
            video_files: list[dict[str, object]] = []
            video_basenames: list[str] = []

            for filename in files:
                if filename in JunkPatterns.IGNORED_FOLDERS:
                    continue
                filepath = os.path.join(root, filename)
                try:
                    size = os.path.getsize(filepath)
                except OSError as exc:
                    _log.warning("could not stat file %s: %s", filepath, exc)
                    continue

                file_info: dict[str, object] = {
                    "path": filepath,
                    "name": filename,
                    "type": "file",
                    "size": size,
                    "parent": root,
                }
                all_files.append(file_info)

                if JunkPatterns.is_video_file(filename):
                    suffix = Path(filename).suffix
                    if suffix:
                        video_basenames.append(filename[: -len(suffix)])
                    file_info["is_video"] = True
                    file_info["reason"] = "Video file (protected)"
                    video_files.append(file_info)

            folder_name = os.path.basename(root)
            junk_files: list[dict[str, object]] = []
            for file_info in all_files:
                if file_info.get("is_video"):
                    continue
                check = JunkPatterns.is_junk_file(
                    str(file_info["name"]),
                    str(file_info["path"]),
                    video_basenames,
                    folder_name,
                )
                if check["is_junk"]:
                    file_info["is_video"] = False
                    file_info["reason"] = check["reason"]
                    junk_files.append(file_info)

            if not video_files:
                continue

            valid_videos: list[dict[str, object]] = []
            for video_info in video_files:
                if JunkPatterns.video_matches_folder(str(video_info["name"]), folder_name):
                    valid_videos.append(video_info)
                else:
                    video_info["is_video"] = False
                    video_info["reason"] = "Misplaced video (filename does not match folder)"
                    video_info["demoted_video"] = True
                    junk_files.append(video_info)

            if len(valid_videos) > 1:
                valid_videos.sort(key=lambda item: int(item["size"]), reverse=True)
                largest = valid_videos[0]
                for duplicate in valid_videos[1:]:
                    duplicate["is_video"] = False
                    duplicate["reason"] = f'Duplicate video (smaller than {largest["name"]})'
                    duplicate["demoted_video"] = True
                    junk_files.append(duplicate)
                valid_videos = [largest]

            videos = [
                VideoReference(name=str(video["name"]), size=int(video["size"]))
                for video in valid_videos
            ]
            for junk_file in junk_files:
                # A demoted video (misplaced/duplicate) is large and irreplaceable, so
                # a fuzzy-name miss must never pre-select it for deletion; it surfaces
                # unchecked. Sidecar junk keeps the default checked state.
                self.scan_results.append(
                    ScanItem(
                        path=str(junk_file["path"]),
                        name=str(junk_file["name"]),
                        type="file",
                        size=int(junk_file["size"]),
                        reason=str(junk_file["reason"]),
                        parent=str(junk_file["parent"]),
                        movie_folder=folder_name,
                        movie_folder_path=root,
                        is_checked=not bool(junk_file.get("demoted_video")),
                        videos_in_folder=list(videos),
                    )
                )

    def scan_arr(self, manifest: LibraryManifest) -> list[ScanItem]:
        """Scan using a Radarr/Sonarr manifest as the source of truth.

        Files tracked by the Arr are kept; anything else inside a managed folder is
        flagged as unnecessary, and folders the Arr does not know about are surfaced
        as orphaned (unchecked by default).
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
        """Walk the top level of ``directory`` against the Arr manifest."""
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:  # pragma: no cover - defensive
            _log.warning("could not list %s: %s", directory, exc)
            return

        for entry in entries:
            if entry.name in JunkPatterns.IGNORED_FOLDERS:
                continue
            if entry.is_dir():
                folder = manifest.folder_for(entry.path)
                if folder is not None:
                    self._clean_managed_folder(entry.path, folder, app_label)
                elif manifest.is_known_folder(entry.path):
                    continue  # known to the Arr but no tracked file yet — leave alone
                else:
                    self.scan_results.append(
                        ScanItem(
                            path=entry.path,
                            name=entry.name,
                            type="folder",
                            size=self._get_folder_size(entry.path),
                            reason=f"Orphaned folder (not in {app_label})",
                            parent=directory,
                            movie_folder=entry.name,
                            movie_folder_path=entry.path,
                            is_checked=False,
                            origin="arr",
                        )
                    )
            else:
                try:
                    size = os.path.getsize(entry.path)
                except OSError:  # pragma: no cover - defensive
                    continue
                self.scan_results.append(
                    ScanItem(
                        path=entry.path,
                        name=entry.name,
                        type="file",
                        size=size,
                        reason=f"Loose file (not in {app_label})",
                        parent=directory,
                        is_checked=False,
                        origin="arr",
                    )
                )

    def _clean_managed_folder(
        self, folder_dir: str, folder: ManagedFolder, app_label: str
    ) -> None:
        """Flag every non-tracked file/folder inside one managed media folder."""
        videos = self._folder_videos(folder)
        start = len(self.scan_results)
        display_name = os.path.basename(folder_dir)

        for root, dirs, files in os.walk(folder_dir):
            dirs[:] = [name for name in dirs if name not in JunkPatterns.IGNORED_FOLDERS]

            junk_dirs: list[str] = []
            for dir_name in dirs:
                if JunkPatterns.is_junk_folder(dir_name):
                    folder_path = os.path.join(root, dir_name)
                    self.scan_results.append(
                        ScanItem(
                            path=folder_path,
                            name=dir_name,
                            type="folder",
                            size=self._get_folder_size(folder_path),
                            reason="Junk folder",
                            parent=root,
                            movie_folder=display_name,
                            movie_folder_path=folder_dir,
                            origin="arr",
                        )
                    )
                    junk_dirs.append(dir_name)
            for dir_name in junk_dirs:
                dirs.remove(dir_name)

            for filename in files:
                if filename in JunkPatterns.IGNORED_FOLDERS:
                    continue
                filepath = os.path.join(root, filename)
                if os.path.normpath(filepath) in folder.media_paths:
                    continue  # tracked media — keep
                try:
                    size = os.path.getsize(filepath)
                except OSError:
                    continue

                is_video = JunkPatterns.is_video_file(filename)
                if is_video:
                    reason = f"Untracked video (not in {app_label})"
                else:
                    check = JunkPatterns.is_junk_file(
                        filename,
                        filepath,
                        list(folder.media_basenames),
                        os.path.basename(root),
                    )
                    if not check["is_junk"]:
                        continue  # recognised companion (artwork/subtitle) — keep
                    reason = str(check["reason"])

                self.scan_results.append(
                    ScanItem(
                        path=filepath,
                        name=filename,
                        type="file",
                        size=size,
                        reason=reason,
                        parent=root,
                        movie_folder=display_name,
                        movie_folder_path=folder_dir,
                        # An untracked video may simply be not-yet-imported, so never
                        # auto-select it; sidecar junk keeps the default checked state.
                        is_checked=not is_video,
                        origin="arr",
                    )
                )

        for item in self.scan_results[start:]:
            item.videos_in_folder = list(videos)

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
        folder_groups: dict[str, dict[str, object]] = {}
        for item in self.scan_results:
            folder_path = item.movie_folder_path or item.path
            if folder_path not in folder_groups:
                folder_groups[folder_path] = {"files": [], "total_size": 0}
            files = folder_groups[folder_path]["files"]
            assert isinstance(files, list)
            files.append(item)
            folder_groups[folder_path]["total_size"] = int(
                folder_groups[folder_path]["total_size"]
            ) + item.size

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
