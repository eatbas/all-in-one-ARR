"""Tests for Deletarr scanner and delete safety."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from modules.deletarr.scanner import MediaScanner


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_scanning_missing_path_returns_empty_results(tmp_path) -> None:
    scanner = MediaScanner([str(tmp_path / "missing")])
    assert scanner.scan("movies") == []
    assert scanner.get_stats().total_size == 0


def test_invalid_library_type_is_rejected() -> None:
    scanner = MediaScanner([])
    with pytest.raises(ValueError):
        scanner.scan("music")  # type: ignore[arg-type]


def test_movie_scan_flags_sidecars_duplicates_and_misplaced_videos(tmp_path) -> None:
    movie = tmp_path / "Example Movie (2024)"
    _write(movie / "Example Movie 2024.mkv", b"video" * 10)
    _write(movie / "Example Movie 2024.small.mp4", b"small")
    _write(movie / "Other Film.mkv", b"other")
    _write(movie / "Example Movie 2024.nfo")
    _write(movie / "poster.jpg")
    _write(movie / "random.png")
    _write(movie / "sample" / "clip.txt")

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")
    results = scanner.get_sorted_results()
    reasons = {item.name: item.reason for item in results}

    assert reasons["Example Movie 2024.nfo"] == "Junk file extension"
    assert reasons["random.png"] == "Metadata file not matching video or folder"
    assert reasons["Example Movie 2024.small.mp4"].startswith("Duplicate video")
    assert (
        reasons["Other Film.mkv"] == "Misplaced video (filename does not match folder)"
    )
    assert any(item.name == "sample" and item.type == "folder" for item in results)
    assert "poster.jpg" not in reasons
    assert scanner.get_stats().total_files == 4
    assert scanner.get_stats().total_folders == 1


def test_movie_scan_keeps_manager_companion_metadata(tmp_path) -> None:
    folder_name = "Man of War (2026) {tmdb-1705729}"
    video_basename = (
        "Man of War (2026) {tmdb-1705729} - [AMZN][WEBDL-1080p][EAC3 5.1][h264]-playWEB"
    )
    movie = tmp_path / folder_name
    _write(movie / f"{video_basename}.mkv", b"video" * 10)
    _write(movie / "folder.jpg")
    _write(movie / f"{folder_name}.jpg")
    _write(movie / f"{video_basename}.xml")
    _write(movie / "unrelated.xml")

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")
    results = scanner.get_sorted_results()
    reasons = {item.name: item.reason for item in results}

    assert reasons == {"unrelated.xml": "Metadata file not matching video or folder"}


def test_movie_scan_keeps_yts_mx_matching_metadata(tmp_path) -> None:
    folder_name = "GameStop (2026) {tmdb-12345}"
    video_basename = (
        "GameStop (2026) {tmdb-12345} - [WEBDL-1080p][AAC 2.0][x264]-YTS.MX"
    )
    movie = tmp_path / folder_name
    _write(movie / f"{video_basename}.mkv", b"video" * 10)
    _write(movie / f"{video_basename}.xml")  # matching Radarr metadata sidecar
    _write(movie / f"{folder_name}.jpg")  # matching folder artwork
    _write(movie / "unrelated-YTS.xml")  # unrelated metadata with YTS token

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")
    results = scanner.get_sorted_results()
    reasons = {item.name: item.reason for item in results}

    assert f"{video_basename}.xml" not in reasons
    assert f"{folder_name}.jpg" not in reasons
    assert reasons == {
        "unrelated-YTS.xml": "Metadata file not matching video or folder"
    }
    assert scanner.get_stats().total_files == 1


def test_tv_scan_flags_non_episode_files_and_unexpected_folders(tmp_path) -> None:
    season = tmp_path / "Example Show" / "Season 01"
    _write(season / "Example Show S01E01.mkv", b"episode")
    _write(season / "notes.nfo")
    _write(season / "Bad Name.mkv")
    _write(season / "@eaDir")
    _write(season / "Extras" / "clip.txt")
    _write(tmp_path / "Example Show" / "Featurettes" / "clip.txt")

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("tv")
    results = scanner.get_sorted_results()
    reasons = {item.name: item.reason for item in results}

    assert reasons["notes.nfo"] == "Non-video file in Season folder"
    assert (
        reasons["Bad Name.mkv"]
        == "Irregular episode naming (missing SxxExx or show name)"
    )
    assert reasons["Extras"] == "Junk folder"
    assert reasons["Featurettes"] == "Unexpected folder in TV Show directory"
    assert all(
        item.videos_in_folder[0].name == "Example Show S01E01.mkv"
        for item in results
        if item.movie_folder_path == str(season)
    )


def test_tv_scan_skips_files_that_cannot_be_statted(tmp_path, monkeypatch) -> None:
    season = tmp_path / "Example Show" / "Season 01"
    _write(season / "Example Show S01E01.mkv", b"episode")
    broken = _write(season / "broken.nfo")

    real_getsize = Path.stat

    def _getsize(path: str) -> int:
        if path == str(broken):
            raise OSError("no stat")
        return real_getsize(Path(path)).st_size

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("tv")

    assert all(item.name != "broken.nfo" for item in scanner.get_sorted_results())


def test_tv_specials_candidates_are_unchecked_by_default(tmp_path) -> None:
    library = tmp_path / "library"
    specials = library / "Example Show" / "Specials"
    _write(specials / "Example Show S00E01.mkv", b"special")
    _write(specials / "notes.nfo")
    _write(specials / "Bad Name.mkv")
    _write(specials / "Behind The Scenes" / "clip.txt")

    scanner = MediaScanner([str(library)])
    scanner.scan("tv")
    results = scanner.get_sorted_results()

    assert {item.name for item in results} == {
        "notes.nfo",
        "Bad Name.mkv",
        "Behind The Scenes",
    }
    assert all(item.is_checked is False for item in results)


def test_movie_scan_skips_directories_without_video_files(tmp_path) -> None:
    movie = tmp_path / "No Video Yet"
    _write(movie / "No Video Yet.nfo")
    _write(movie / "@eaDir" / "ignored.txt")

    scanner = MediaScanner([str(tmp_path)])

    assert scanner.scan("movies") == []
    assert scanner.get_sorted_results() == []


def test_movie_scan_emits_highest_empty_tree_with_stable_group(tmp_path) -> None:
    empty_movie = tmp_path / "Empty Movie (2025)"
    empty_movie.mkdir()
    populated_movie = tmp_path / "Populated Movie (2024)"
    _write(populated_movie / "Populated Movie.mkv", b"video")
    empty_nested = populated_movie / "Processing" / "nested"
    empty_nested.mkdir(parents=True)

    scanner = MediaScanner([str(tmp_path)])
    results = scanner.scan("movies")
    by_path = {item.path: item for item in results}

    assert set(by_path) == {str(empty_movie), str(populated_movie / "Processing")}
    assert str(empty_nested) not in by_path
    assert by_path[str(empty_movie)].movie_folder == empty_movie.name
    assert by_path[str(empty_movie)].movie_folder_path == str(empty_movie)
    assert by_path[str(populated_movie / "Processing")].movie_folder == (
        populated_movie.name
    )
    assert all(item.reason == "Empty folder" for item in results)
    assert all(item.category == "junk" for item in results)
    assert all(item.is_checked is False for item in results)


def test_tv_scan_emits_empty_show_and_season_as_distinct_groups(tmp_path) -> None:
    empty_show = tmp_path / "Empty Show"
    empty_show.mkdir()
    active_show = tmp_path / "Active Show"
    _write(active_show / "Season 01" / "Active Show S01E01.mkv", b"episode")
    empty_season = active_show / "Season 02"
    empty_season.mkdir()

    scanner = MediaScanner([str(tmp_path)])
    results = scanner.scan("tv")
    by_path = {item.path: item for item in results}

    assert set(by_path) == {str(empty_show), str(empty_season)}
    assert by_path[str(empty_show)].movie_folder == "Empty Show"
    assert by_path[str(empty_season)].movie_folder == "Active Show - Season 02"
    assert by_path[str(empty_season)].movie_folder_path == str(empty_season)


@pytest.mark.parametrize("library_type", ["movies", "tv"])
def test_heuristic_scan_classifies_loose_root_files_as_untracked_media(
    tmp_path, library_type
) -> None:
    loose = _write(tmp_path / "loose.mkv", b"video")

    result = MediaScanner([str(tmp_path)]).scan(library_type)

    assert len(result) == 1
    assert result[0].path == str(loose)
    assert result[0].category == "untracked_media"
    assert result[0].movie_folder == "Loose files"
    assert result[0].is_checked is False


def test_empty_detection_preserves_root_symlinks_and_hidden_content(tmp_path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    movie = root / "Protected Movie"
    _write(movie / "Protected Movie.mkv", b"video")
    (movie / "linked").symlink_to(external, target_is_directory=True)
    _write(root / "Hidden State" / ".state" / "marker")
    _write(root / "Ignored State" / "@eaDir" / "marker")

    scanner = MediaScanner([str(root)])
    results = scanner.scan("movies")

    assert results == []
    assert root.exists()
    assert all(item.path != str(movie / "linked") for item in results)


def test_empty_detection_treats_listing_errors_as_content(
    tmp_path, monkeypatch
) -> None:
    movie = tmp_path / "Movie"
    _write(movie / "Movie.mkv", b"video")
    unreadable = movie / "Unverified"
    unreadable.mkdir()
    real_scandir = os.scandir

    def _scandir(path):
        if os.path.normpath(path) == os.path.normpath(unreadable):
            raise OSError("permission denied")
        return real_scandir(path)

    monkeypatch.setattr("modules.deletarr.scanner.os.scandir", _scandir)
    scanner = MediaScanner([str(tmp_path)])

    assert scanner.scan("movies") == []


def test_empty_detection_treats_entry_type_errors_as_content(monkeypatch) -> None:
    class BrokenEntry:
        name = "uncertain"

        @staticmethod
        def is_symlink() -> bool:
            raise OSError("type unavailable")

    class BrokenScan:
        def __enter__(self):
            return iter([BrokenEntry()])

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr(
        "modules.deletarr.scanner.os.scandir", lambda _path: BrokenScan()
    )

    assert MediaScanner._is_empty_tree("unverified") is False


def test_loose_file_scan_skips_ignored_symlinked_and_unstattable_entries(
    tmp_path, monkeypatch
) -> None:
    target = _write(tmp_path / "target.bin")
    symlink = tmp_path / "linked.bin"
    symlink.symlink_to(target)
    broken = _write(tmp_path / "broken.bin")
    real_getsize = os.path.getsize

    def _getsize(path: str) -> int:
        if os.path.normpath(path) == os.path.normpath(broken):
            raise OSError("stat unavailable")
        return real_getsize(path)

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)
    scanner = MediaScanner([])

    scanner._append_loose_files(str(tmp_path), ["@eaDir", symlink.name, broken.name])

    assert scanner.scan_results == []


def test_movie_scan_skips_ignored_and_unstattable_files(tmp_path, monkeypatch) -> None:
    movie = tmp_path / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "@eaDir")
    broken = _write(movie / "broken.nfo")

    real_getsize = Path.stat

    def _getsize(path: str) -> int:
        if path == str(broken):
            raise OSError("no stat")
        return real_getsize(Path(path)).st_size

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")

    assert scanner.get_sorted_results() == []


def test_movie_video_without_suffix_uses_defensive_branch(
    tmp_path, monkeypatch
) -> None:
    movie = tmp_path / "Movie"
    video = _write(movie / "Movie", b"video")
    _write(movie / "Movie.nfo")

    def _is_video_file(filename: str) -> bool:
        return filename == video.name

    monkeypatch.setattr(
        "modules.deletarr.scanner.JunkPatterns.is_video_file",
        _is_video_file,
    )

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")

    assert [item.name for item in scanner.get_sorted_results()] == ["Movie.nfo"]


def test_folder_size_ignores_unreadable_files(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "folder"
    ok = _write(folder / "ok.txt", b"ok")
    broken = _write(folder / "broken.txt")
    real_getsize = Path.stat

    def _getsize(path: str) -> int:
        if path == str(broken):
            raise OSError("no stat")
        return real_getsize(Path(path)).st_size

    monkeypatch.setattr("modules.deletarr.scanner.os.path.getsize", _getsize)

    assert MediaScanner([])._get_folder_size(str(folder)) == ok.stat().st_size


# ---- Selection safety: every review candidate starts unselected ----


def test_movie_candidates_are_unchecked_by_default(tmp_path) -> None:
    movie = tmp_path / "Example Movie (2024)"
    _write(movie / "Example Movie 2024.mkv", b"video" * 10)
    _write(movie / "Example Movie 2024.small.mp4", b"small")  # duplicate video
    _write(movie / "Other Film.mkv", b"other")  # misplaced video
    _write(movie / "Example Movie 2024.nfo")  # sidecar junk

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("movies")
    by = {item.name: item for item in scanner.get_sorted_results()}

    assert by["Other Film.mkv"].is_checked is False
    assert by["Example Movie 2024.small.mp4"].is_checked is False
    assert by["Example Movie 2024.nfo"].is_checked is False
    assert all(item.category == "junk" for item in by.values())


def test_tv_candidates_are_unchecked_by_default(tmp_path) -> None:
    show = tmp_path / "Example Show"
    season = show / "Season 01"
    _write(season / "Example Show S01E01.mkv", b"ep")
    _write(season / "Bad Name.mkv", b"bad")  # irregular episode (video)
    _write(season / "notes.nfo")  # non-video junk
    _write(season / "Subs" / "x.srt")  # unexpected folder inside season
    _write(show / "Featurettes" / "clip.mkv")  # unexpected show-root folder

    scanner = MediaScanner([str(tmp_path)])
    scanner.scan("tv")
    by = {item.name: item for item in scanner.get_sorted_results()}

    assert by["Bad Name.mkv"].is_checked is False
    assert by["Subs"].is_checked is False
    assert by["Featurettes"].is_checked is False
    assert by["notes.nfo"].is_checked is False
    assert all(item.category == "junk" for item in by.values())
