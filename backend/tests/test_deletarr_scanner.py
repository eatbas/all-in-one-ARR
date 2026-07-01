"""Tests for Deletarr scanner and delete safety."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from core.context import SyncAlreadyRunning
from modules.deletarr import setup
from modules.deletarr.engine import DeletarrService, format_size
from modules.deletarr.manifest import (
    LibraryManifest,
    ManagedFolder,
    _basename_without_ext,
)
from modules.deletarr.models import LibraryType
from modules.deletarr.scanner import MediaScanner
from tests.conftest import FakeDeletarrArr, StubSettingsStore, make_ctx


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _manifest(
    library_type: LibraryType, root, folders: dict[str, list[str]]
) -> LibraryManifest:
    """Build a manifest directly from on-disk paths for scanner tests."""
    import os

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


def _fake_client_factory(fake: FakeDeletarrArr):
    def _factory(_ctx, _selected):
        return fake

    return _factory


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
    assert reasons["Other Film.mkv"] == "Misplaced video (filename does not match folder)"
    assert any(item.name == "sample" and item.type == "folder" for item in results)
    assert "poster.jpg" not in reasons
    assert scanner.get_stats().total_files == 4
    assert scanner.get_stats().total_folders == 1


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
    assert reasons["Bad Name.mkv"] == "Irregular episode naming (missing SxxExx or show name)"
    assert reasons["Extras"] == "Junk folder"
    assert reasons["Featurettes"] == "Unexpected folder in TV Show directory"
    assert all(item.videos_in_folder[0].name == "Example Show S01E01.mkv" for item in results if item.movie_folder_path == str(season))


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


def test_movie_video_without_suffix_uses_defensive_branch(tmp_path, monkeypatch) -> None:
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


async def test_delete_requires_scan_membership_and_library_containment(db, tmp_path) -> None:
    root = tmp_path / "movies"
    outside = tmp_path / "outside"
    movie = root / "Example Movie"
    junk = _write(movie / "Example Movie.nfo")
    video = _write(movie / "Example Movie.mkv", b"video")
    outside_file = _write(outside / "evil.nfo")
    symlink = movie / "evil-link.nfo"
    symlink.symlink_to(outside_file)

    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")
    state = await service.results("movies")
    paths = {item["name"]: item["path"] for item in state["results"]}
    assert paths["Example Movie.nfo"] == str(junk)

    result = await service.delete(
        "movies",
        [str(junk), str(video), str(symlink), str(outside_file)],
    )

    assert result["deleted"] == 1
    assert result["failed"] == 3
    assert not junk.exists()
    assert video.exists()
    assert outside_file.exists()
    errors = {entry["path"]: entry["error"] for entry in result["errors"]}
    assert errors[str(video)] == "Not in scan results"
    assert errors[str(symlink)] == "Path is outside configured library"
    assert errors[str(outside_file)] == "Not in scan results"


async def test_delete_removes_scanned_junk_folder(db, tmp_path) -> None:
    root = tmp_path / "movies"
    junk_folder = root / "sample"
    _write(junk_folder / "clip.txt", b"sample")
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")

    result = await service.delete("movies", [str(junk_folder)])

    assert result["success"] is True
    assert result["deleted"] == 1
    assert result["freed_bytes"] == len(b"sample")
    assert not junk_folder.exists()
    assert (await service.results("movies"))["results"] == []


async def test_delete_reports_missing_scanned_path(db, tmp_path) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    junk = _write(movie / "Example Movie.nfo")
    _write(movie / "Example Movie.mkv", b"video")
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")
    junk.unlink()

    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 0
    assert result["errors"] == [{"path": str(junk), "error": "Path no longer exists"}]


async def test_delete_reports_path_that_disappears_after_validation(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    junk = _write(movie / "Example Movie.nfo")
    _write(movie / "Example Movie.mkv", b"video")
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")
    monkeypatch.setattr("modules.deletarr.engine.os.path.isfile", lambda _path: False)
    monkeypatch.setattr("modules.deletarr.engine.os.path.isdir", lambda _path: False)

    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 0
    assert result["errors"] == [{"path": str(junk), "error": "Path no longer exists"}]


async def test_delete_reports_missing_configured_root(db, tmp_path) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    junk = _write(movie / "Example Movie.nfo")
    _write(movie / "Example Movie.mkv", b"video")
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")
    await service.update_settings(movies_path=str(tmp_path / "missing"))

    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 0
    assert result["errors"] == [
        {"path": str(junk), "error": "Configured library path does not exist"}
    ]


async def test_delete_reports_filesystem_exception(db, tmp_path, monkeypatch) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    junk = _write(movie / "Example Movie.nfo")
    _write(movie / "Example Movie.mkv", b"video")
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")

    def _raise_remove(path: str) -> None:
        if path == str(junk):
            raise PermissionError("denied")

    monkeypatch.setattr("modules.deletarr.engine.os.remove", _raise_remove)

    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 0
    assert result["errors"] == [{"path": str(junk), "error": "denied"}]


async def test_scan_records_failure_and_status(db, tmp_path, monkeypatch) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)

    def _raise_scan(_scanner, _library_type):
        raise RuntimeError("scan failed")

    monkeypatch.setattr("modules.deletarr.engine.MediaScanner.scan", _raise_scan)

    with pytest.raises(RuntimeError, match="scan failed"):
        await service.scan("movies")

    status = await service.status()
    assert status["libraries"]["movies"]["last_error"] == "scan failed"
    assert status["libraries"]["movies"]["stats"]["is_scanning"] is False


async def test_busy_gate_rejects_scan_and_delete(db, tmp_path) -> None:
    root = tmp_path / "movies"
    root.mkdir()
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(deletarr_movies_path=str(root)),
    )
    service = DeletarrService(ctx)
    lock = ctx.deletarr_gate._get_lock()
    await lock.acquire()
    try:
        with pytest.raises(SyncAlreadyRunning):
            await service.scan("movies")
        with pytest.raises(SyncAlreadyRunning):
            await service.delete("movies", [])
    finally:
        lock.release()


def test_engine_folder_size_ignores_unreadable_files(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "folder"
    ok = _write(folder / "ok.txt", b"ok")
    broken = _write(folder / "broken.txt")
    real_getsize = Path.stat

    def _getsize(path: str) -> int:
        if path == str(broken):
            raise OSError("no stat")
        return real_getsize(Path(path)).st_size

    monkeypatch.setattr("modules.deletarr.engine.os.path.getsize", _getsize)

    assert DeletarrService._folder_size(str(folder)) == ok.stat().st_size


def test_scanning_missing_path_returns_empty_results(tmp_path) -> None:
    scanner = MediaScanner([str(tmp_path / "missing")])
    assert scanner.scan("movies") == []
    assert scanner.get_stats().total_size == 0


def test_invalid_library_type_is_rejected() -> None:
    scanner = MediaScanner([])
    with pytest.raises(ValueError):
        scanner.scan("music")  # type: ignore[arg-type]


def test_format_size_reaches_petabytes() -> None:
    assert format_size(1024**5) == "1.0 PB"


async def test_setup_registers_context_callables(db) -> None:
    ctx = make_ctx(db=db)

    await setup(AsyncMock(), FastAPI(), ctx)

    assert ctx.deletarr_status is not None
    assert ctx.deletarr_scan is not None
    assert ctx.deletarr_results is not None
    assert ctx.deletarr_delete is not None
    assert ctx.deletarr_update_settings is not None
    status = await ctx.deletarr_status()
    assert status["settings"] == {
        "movies_path": "/media/movies",
        "tv_path": "/media/tv",
        "use_arr_source": False,
    }


# ---- P0 safety: never auto-select a video or whole folder on a fuzzy-name miss ----


def test_movie_demoted_videos_unchecked_sidecars_checked(tmp_path) -> None:
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
    assert by["Example Movie 2024.nfo"].is_checked is True


def test_tv_videos_and_folders_unchecked_on_name_miss(tmp_path) -> None:
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
    assert by["notes.nfo"].is_checked is True


def test_arr_untracked_video_unchecked_sidecar_checked(tmp_path) -> None:
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
    assert by["Inception.nfo"].is_checked is True


# ---- Arr-backed scanner ----


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
    assert "Inception.mkv" not in items  # tracked media kept
    assert "poster.jpg" not in items  # whitelisted companion kept
    assert "Inception.en.srt" not in items  # subtitle kept
    assert ".DS_Store" not in items
    assert items["Inception.nfo"].videos_in_folder[0].name == "Inception.mkv"
    assert all(item.origin == "arr" for item in scanner.get_sorted_results())


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


def test_scan_arr_folder_videos_tolerate_unreadable_media(tmp_path, monkeypatch) -> None:
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


# ---- Engine scan-mode selection and Arr-aware delete ----


async def test_scan_uses_arr_mode_when_manifest_available(db, tmp_path, monkeypatch) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    _write(movie / "Inception.nfo")
    _write(root / "Random" / "r.mkv", b"r")

    fake = FakeDeletarrArr(
        movies=[
            {
                "path": str(movie),
                "rootFolderPath": str(root),
                "movieFile": {"path": str(video)},
            }
        ],
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    result = await service.scan("movies")

    assert result["scan_mode"] == "arr"
    assert result["arr_available"] is True
    names = {item["name"] for item in result["results"]}
    assert "Inception.nfo" in names
    assert "Random" in names
    assert fake.closed is True
    status = await service.status()
    assert status["libraries"]["movies"]["scan_mode"] == "arr"


async def test_scan_uses_arr_mode_for_tv(db, tmp_path, monkeypatch) -> None:
    root = tmp_path / "tv"
    show = root / "Example Show (2019)"
    season = show / "Season 01"
    episode = _write(season / "Example Show S01E01.mkv", b"ep")
    _write(season / "notes.nfo")

    fake = FakeDeletarrArr(
        series=[{"id": 1, "path": str(show), "rootFolderPath": str(root)}],
        episode_files={1: [{"path": str(episode)}]},
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_tv_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    result = await service.scan("tv")

    assert result["scan_mode"] == "arr"
    names = {item["name"]: item["reason"] for item in result["results"]}
    assert names["notes.nfo"] == "Junk file extension"
    assert "Example Show S01E01.mkv" not in names


async def test_scan_falls_back_to_heuristic_when_arr_unavailable(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "Example Movie.nfo")

    fake = FakeDeletarrArr(fail=("movies",))
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    result = await service.scan("movies")

    assert result["scan_mode"] == "heuristic"
    assert result["arr_available"] is False
    assert result["arr_detail"] is not None and "boom" in result["arr_detail"]
    assert any(item["name"] == "Example Movie.nfo" for item in result["results"])


async def test_scan_falls_back_when_manifest_has_no_managed_folders(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "Example Movie.nfo")

    fake = FakeDeletarrArr(movies=[], root_folders=[{"path": str(root)}])
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    result = await service.scan("movies")

    assert result["scan_mode"] == "heuristic"
    assert result["arr_available"] is True


async def test_scan_disabled_arr_source_never_builds_client(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "Example Movie.nfo")

    def _factory(_ctx, _selected):
        raise AssertionError("client_for should not be called when disabled")

    monkeypatch.setattr("modules.deletarr.engine.client_for", _factory)
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=False
        ),
    )
    service = DeletarrService(ctx)
    result = await service.scan("movies")

    assert result["scan_mode"] == "heuristic"
    assert result["arr_detail"] == "Arr source disabled"


async def test_arr_mode_delete_succeeds_for_untracked_junk(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    junk = _write(movie / "Inception.nfo")

    fake = FakeDeletarrArr(
        movies=[
            {
                "path": str(movie),
                "rootFolderPath": str(root),
                "movieFile": {"path": str(video)},
            }
        ],
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")

    result = await service.delete("movies", [str(junk)])
    assert result["deleted"] == 1
    assert not junk.exists()


async def test_arr_mode_delete_blocks_now_tracked_path(db, tmp_path, monkeypatch) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    junk = _write(movie / "Inception.nfo")

    fake = FakeDeletarrArr(
        movies=[
            {
                "path": str(movie),
                "rootFolderPath": str(root),
                "movieFile": {"path": str(video)},
            }
        ],
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")

    # Radarr now tracks the previously-flagged sidecar; the delete must refuse it.
    fake._movies[0]["movieFile"]["path"] = str(junk)
    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 0
    assert result["errors"] == [
        {"path": str(junk), "error": "Now tracked by Radarr/Sonarr"}
    ]
    assert junk.exists()


async def test_arr_mode_delete_blocks_folder_containing_tracked_file(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    orphan = root / "Random"
    orphan_video = _write(orphan / "r.mkv", b"r")

    fake = FakeDeletarrArr(
        movies=[
            {
                "path": str(movie),
                "rootFolderPath": str(root),
                "movieFile": {"path": str(video)},
            }
        ],
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")  # "Random" is orphaned at scan time

    # Radarr now tracks a file inside the orphaned folder; deleting the whole
    # folder must be refused even though the folder path itself is not tracked.
    fake._movies.append(
        {
            "path": str(orphan),
            "rootFolderPath": str(root),
            "movieFile": {"path": str(orphan_video)},
        }
    )
    result = await service.delete("movies", [str(orphan)])

    assert result["deleted"] == 0
    assert result["errors"] == [
        {"path": str(orphan), "error": "Now tracked by Radarr/Sonarr"}
    ]
    assert orphan.exists()


async def test_arr_mode_delete_tolerates_unavailable_manifest(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    movie = root / "Inception (2010)"
    video = _write(movie / "Inception.mkv", b"video")
    junk = _write(movie / "Inception.nfo")

    fake = FakeDeletarrArr(
        movies=[
            {
                "path": str(movie),
                "rootFolderPath": str(root),
                "movieFile": {"path": str(video)},
            }
        ],
        root_folders=[{"path": str(root)}],
    )
    monkeypatch.setattr(
        "modules.deletarr.engine.client_for", _fake_client_factory(fake)
    )
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=True
        ),
    )
    service = DeletarrService(ctx)
    await service.scan("movies")

    # Arr goes down before the delete: re-verification degrades to the local guards.
    fake._fail.add("movies")
    result = await service.delete("movies", [str(junk)])

    assert result["deleted"] == 1
    assert not junk.exists()
