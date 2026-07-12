"""Tests for Arr-backed Deletarr scanner classification."""

from __future__ import annotations

import os
from pathlib import Path

from modules.deletarr.manifest import (
    LibraryManifest,
    ManagedFolder,
    _basename_without_ext,
)
from modules.deletarr.models import LibraryType
from modules.deletarr.scanner import MediaScanner


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _manifest(
    library_type: LibraryType, root, folders: dict[str, list[str]]
) -> LibraryManifest:
    """Build a manifest directly from on-disk paths for scanner tests."""
    managed: dict[str, ManagedFolder] = {}
    known: set[str] = set()
    for folder, media in folders.items():
        normalised = os.path.normpath(folder)
        known.add(normalised)
        if media:
            managed[normalised] = ManagedFolder(
                path=normalised,
                media_paths=frozenset(os.path.normpath(path) for path in media),
                media_basenames=frozenset(
                    _basename_without_ext(os.path.basename(path)) for path in media
                ),
            )
    return LibraryManifest(
        library_type,
        os.path.normpath(str(root)),
        available=True,
        folders=managed,
        known_folders=frozenset(known),
    )


def test_arr_candidates_are_unchecked_and_typed(tmp_path) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    _write(movie / "extra.mkv", b"x")  # untracked video
    _write(movie / "Inception.nfo")  # sidecar junk

    manifest = _manifest("movies", root, {str(movie): [str(video)]})
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    by = {item.name: item for item in scanner.get_sorted_results()}

    assert by["extra.mkv"].is_checked is False
    assert by["Inception.nfo"].is_checked is False
    assert by["extra.mkv"].category == "untracked_media"
    assert by["Inception.nfo"].category == "junk"


def test_scan_arr_flags_untracked_keeps_tracked_and_companions(tmp_path) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video" * 10)
    _write(movie / "Inception.nfo")
    _write(movie / "poster.jpg")  # whitelisted companion — kept
    _write(movie / "Inception.en.srt")  # subtitle, not junk — kept
    _write(movie / ".DS_Store")  # ignored filename — skipped
    _write(movie / "extra.mkv", b"x")  # untracked video — flagged
    _write(movie / "sample" / "clip.txt")  # junk folder
    (root / "@eaDir").mkdir()  # ignored top-level folder — skipped
    _write(root / "Random Junk" / "r.mkv", b"r")  # orphaned folder

    manifest = _manifest("movies", root, {str(movie): [str(video)]})
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    items = {item.name: item for item in scanner.get_sorted_results()}

    assert items["Inception.nfo"].reason == "Junk file extension"
    assert items["extra.mkv"].reason == "Untracked video (not in Radarr)"
    assert items["sample"].type == "folder" and items["sample"].reason == "Junk folder"
    assert items["Random Junk"].reason == "Orphaned folder (not in Radarr)"
    assert items["Random Junk"].is_checked is False
    assert items["Random Junk"].category == "untracked_media"
    assert items["extra.mkv"].category == "untracked_media"
    assert items["Inception.nfo"].category == "junk"
    assert items["sample"].category == "junk"
    assert "Inception.mkv" not in items  # tracked media kept
    assert "poster.jpg" not in items  # whitelisted companion kept
    assert "Inception.en.srt" not in items  # subtitle kept
    assert ".DS_Store" not in items
    assert items["Inception.nfo"].videos_in_folder[0].name == "Inception.mkv"
    assert all(item.origin == "arr" for item in scanner.get_sorted_results())


def test_scan_arr_keeps_manager_companion_metadata(tmp_path) -> None:
    root = tmp_path / "movies"
    folder_name = "The Sheep Detectives (2026) {tmdb-1301421}"
    video_basename = (
        "The Sheep Detectives (2026) {tmdb-1301421} - "
        "[AMZN][WEBDL-1080p][EAC3 Atmos 5.1][h264]-Kitsune"
    )
    movie = root / folder_name
    video = _write(movie / f"{video_basename}.mkv", b"video" * 10)
    _write(movie / "folder.jpg")
    _write(movie / f"{folder_name}.jpg")
    _write(movie / f"{video_basename}.xml")
    _write(movie / "unrelated.xml")

    manifest = _manifest("movies", root, {str(movie): [str(video)]})
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    items = {item.name: item for item in scanner.get_sorted_results()}

    assert set(items) == {"unrelated.xml"}
    assert items["unrelated.xml"].reason == "Metadata file not matching video or folder"


def test_scan_arr_keeps_yts_mx_matching_metadata(tmp_path) -> None:
    root = tmp_path / "movies"
    folder_name = "GameStop (2026) {tmdb-12345}"
    video_basename = (
        "GameStop (2026) {tmdb-12345} - [WEBDL-1080p][AAC 2.0][x264]-YTS.MX"
    )
    movie = root / folder_name
    video = _write(movie / f"{video_basename}.mkv", b"video" * 10)
    _write(movie / f"{video_basename}.xml")  # matching tracked sidecar
    _write(movie / "unrelated-YTS.xml")  # unrelated metadata with YTS token

    manifest = _manifest("movies", root, {str(movie): [str(video)]})
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    items = {item.name: item for item in scanner.get_sorted_results()}

    assert set(items) == {"unrelated-YTS.xml"}
    assert (
        items["unrelated-YTS.xml"].reason
        == "Metadata file not matching video or folder"
    )
    assert (
        items["unrelated-YTS.xml"].videos_in_folder[0].name == f"{video_basename}.mkv"
    )


def test_scan_arr_descends_into_category_folders(tmp_path) -> None:
    root = tmp_path / "movies"
    # Movies nested under category containers, mirroring a multi-root Radarr where
    # every movie folder lives one or more levels below the scanned library root.
    movie = root / "collections" / "A View (1985)"
    video = _write(movie / "A View (1985).mkv", b"video" * 10)
    _write(movie / "A View (1985).nfo")  # untracked junk beside the tracked film
    deep = root / "animations" / "archive" / "Toy (1995)"
    deep_video = _write(deep / "Toy (1995).mkv", b"toy")
    _write(root / "Random Junk" / "r.mkv", b"r")  # genuine top-level orphan

    manifest = _manifest(
        "movies",
        root,
        {str(movie): [str(video)], str(deep): [str(deep_video)]},
    )
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    items = {item.name: item for item in scanner.get_sorted_results()}

    # Category containers (including multi-level nesting) are descended into, not
    # flagged as orphaned.
    assert "collections" not in items
    assert "animations" not in items
    assert "archive" not in items
    # The untracked file inside a nested managed folder is still surfaced.
    assert items["A View (1985).nfo"].reason == "Junk file extension"
    assert items["A View (1985).nfo"].movie_folder == "A View (1985)"
    # Tracked videos are kept.
    assert "A View (1985).mkv" not in items
    assert "Toy (1995).mkv" not in items
    # A genuinely unknown top-level folder is still surfaced as orphaned.
    assert items["Random Junk"].reason == "Orphaned folder (not in Radarr)"
    assert items["Random Junk"].is_checked is False


def test_scan_arr_leaves_known_fileless_folder_and_flags_loose_file(tmp_path) -> None:
    root = tmp_path / "movies"
    pending = root / "Pending (2025)"
    _write(pending / "not-yet-imported.txt")  # inside known-but-fileless folder
    _write(root / "loose.mkv", b"l")  # loose top-level file

    manifest = _manifest("movies", root, {str(pending): []})
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)
    items = {item.name: item for item in scanner.get_sorted_results()}

    assert "not-yet-imported.txt" not in items  # left alone
    assert items["loose.mkv"].reason == "Loose file (not in Radarr)"
    assert items["loose.mkv"].is_checked is False
    assert items["loose.mkv"].category == "untracked_media"


def test_scan_arr_classifies_empty_and_untracked_candidates(tmp_path) -> None:
    root = tmp_path / "movies"
    managed = root / "Managed (2024)"
    tracked = _write(managed / "Managed.mkv", b"video")
    managed_empty = managed / "Transcode Work"
    managed_empty.mkdir()
    known_empty = root / "Known Empty (2025)"
    known_empty.mkdir()
    managed_but_empty = root / "Managed But Empty (2027)"
    managed_but_empty.mkdir()
    missing_tracked_path = managed_but_empty / "missing.mkv"
    known_pending = root / "Known Pending (2026)"
    _write(known_pending / "pending-import.bin")
    unknown_empty = root / "Unknown Empty"
    unknown_empty.mkdir()
    _write(managed / "untracked.mkv", b"extra")
    _write(managed / "Managed.nfo")
    loose = _write(root / "loose.mkv", b"loose")

    manifest = _manifest(
        "movies",
        root,
        {
            str(managed): [str(tracked)],
            str(known_empty): [],
            str(known_pending): [],
            str(managed_but_empty): [str(missing_tracked_path)],
        },
    )
    scanner = MediaScanner([str(root)])
    results = scanner.scan_arr(manifest)
    by_path = {item.path: item for item in results}

    assert by_path[str(managed_empty)].category == "junk"
    assert by_path[str(known_empty)].category == "junk"
    assert by_path[str(managed_but_empty)].category == "junk"
    assert by_path[str(unknown_empty)].category == "untracked_media"
    assert by_path[str(managed / "untracked.mkv")].category == "untracked_media"
    assert by_path[str(managed / "Managed.nfo")].category == "junk"
    assert by_path[str(loose)].category == "untracked_media"
    assert by_path[str(loose)].movie_folder == "Loose files"
    assert all(not item.path.startswith(f"{known_pending}{os.sep}") for item in results)
    assert all(item.is_checked is False for item in results)


def test_scan_arr_does_not_collapse_empty_category_container(tmp_path) -> None:
    root = tmp_path / "movies"
    category = root / "archive"
    category.mkdir(parents=True)
    absent_known_movie = category / "Expected Movie (2027)"
    manifest = _manifest("movies", root, {str(absent_known_movie): []})

    scanner = MediaScanner([str(root)])

    assert scanner.scan_arr(manifest) == []


def test_scan_arr_skips_missing_root(tmp_path) -> None:
    manifest = _manifest("movies", tmp_path / "missing", {})
    scanner = MediaScanner([str(tmp_path / "missing")])
    assert scanner.scan_arr(manifest) == []


def test_scan_arr_skips_unstattable_junk_file(tmp_path, monkeypatch) -> None:
    import os

    root = tmp_path / "movies"
    movie = root / "M (2020)"
    video = _write(movie / "M.mkv", b"v")
    broken = _write(movie / "broken.nfo")
    manifest = _manifest("movies", root, {str(movie): [str(video)]})

    real_getsize = os.path.getsize

    def _getsize(path: str) -> int:
        if os.path.normpath(path) == os.path.normpath(str(broken)):
            raise OSError("no stat")
        return real_getsize(path)

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)

    assert all(item.name != "broken.nfo" for item in scanner.get_sorted_results())


def test_scan_arr_folder_videos_tolerate_unreadable_media(
    tmp_path, monkeypatch
) -> None:
    import os

    root = tmp_path / "movies"
    movie = root / "M (2020)"
    video = _write(movie / "M.mkv", b"v")
    _write(movie / "M.nfo")
    manifest = _manifest("movies", root, {str(movie): [str(video)]})

    real_getsize = os.path.getsize

    def _getsize(path: str) -> int:
        if os.path.normpath(path) == os.path.normpath(str(video)):
            raise OSError("no stat")
        return real_getsize(path)

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)
    scanner = MediaScanner([str(root)])
    scanner.scan_arr(manifest)

    item = scanner.get_sorted_results()[0]
    assert item.videos_in_folder[0].size == 0
