"""Tests for Deletarr scanner and delete safety."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from core.context import SyncAlreadyRunning
from modules.deletarr import setup
from modules.deletarr.engine import DeletarrService, format_size
from modules.deletarr.scanner import MediaScanner
from tests.conftest import StubSettingsStore, make_ctx


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


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
    assert status["settings"] == {"movies_path": "/media/movies", "tv_path": "/media/tv"}
