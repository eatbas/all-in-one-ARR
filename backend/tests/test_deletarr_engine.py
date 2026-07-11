"""Tests for Deletarr engine state and destructive safety."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from core.context import SyncAlreadyRunning
from modules.deletarr import setup
from modules.deletarr.engine import DeletarrService, format_size
from tests.conftest import FakeDeletarrArr, StubSettingsStore, make_ctx


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _fake_client_factory(fake: FakeDeletarrArr):
    def _factory(_ctx, _selected):
        return fake

    return _factory


async def test_delete_requires_scan_membership_and_library_containment(
    db, tmp_path
) -> None:
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


async def test_scan_uses_arr_mode_when_manifest_available(
    db, tmp_path, monkeypatch
) -> None:
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


async def test_scan_uses_available_arr_manifest_with_no_managed_folders(
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

    assert result["scan_mode"] == "arr"
    assert result["arr_available"] is True
    assert result["results"][0]["name"] == "Example Movie"
    assert result["results"][0]["category"] == "untracked_media"


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


async def test_toggling_arr_source_clears_stale_scan_state(db, tmp_path) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "Example Movie.nfo")

    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=False
        ),
    )
    service = DeletarrService(ctx)

    scanned = await service.scan("movies")
    assert scanned["arr_detail"] == "Arr source disabled"
    assert len(scanned["results"]) >= 1

    # Re-enabling the source of truth must invalidate every library's stale scan
    # state so status no longer reports the now-contradictory disabled detail.
    status = await service.update_settings(use_arr_source=True)

    for library in ("movies", "tv"):
        state = status["libraries"][library]
        assert state["scan_mode"] == "heuristic"
        assert state["arr_available"] is False
        assert state["arr_detail"] is None
        assert state["results_count"] == 0
        assert state["last_scan_at"] is None


async def test_updating_settings_without_toggle_keeps_scan_results(
    db, tmp_path
) -> None:
    root = tmp_path / "movies"
    movie = root / "Example Movie"
    _write(movie / "Example Movie.mkv", b"video")
    _write(movie / "Example Movie.nfo")

    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=False
        ),
    )
    service = DeletarrService(ctx)

    scanned = await service.scan("movies")
    assert len(scanned["results"]) >= 1

    # Saving settings without changing ``use_arr_source`` must not discard the
    # existing results; only a source-of-truth toggle invalidates them.
    status = await service.update_settings(use_arr_source=False)

    movies = status["libraries"]["movies"]
    assert movies["results_count"] == len(scanned["results"])
    assert movies["arr_detail"] == "Arr source disabled"
    assert movies["last_scan_at"] is not None


async def test_empty_folder_requires_exact_submission_and_can_be_deleted(
    db, tmp_path
) -> None:
    root = tmp_path / "movies"
    empty_movie = root / "Empty Movie"
    empty_movie.mkdir(parents=True)
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(
            deletarr_movies_path=str(root), deletarr_use_arr_source=False
        ),
    )
    service = DeletarrService(ctx)

    scan = await service.scan("movies")
    assert scan["results"] == [
        {
            "path": str(empty_movie),
            "name": "Empty Movie",
            "type": "folder",
            "size": 0,
            "reason": "Empty folder",
            "parent": str(root),
            "category": "junk",
            "movie_folder": "Empty Movie",
            "movie_folder_path": str(empty_movie),
            "is_checked": False,
            "videos_in_folder": [],
            "origin": "heuristic",
        }
    ]
    rejected = await service.delete("movies", [str(root / "another-folder")])
    assert rejected["deleted"] == 0
    assert empty_movie.exists()

    deleted = await service.delete("movies", [str(empty_movie)])
    assert deleted["deleted"] == 1
    assert not empty_movie.exists()
    scan_activity = next(
        item
        for item in db.recent_activity()
        if item["action"] == "Deletarr scan completed"
    )
    assert "1 review candidate(s)" in scan_activity["detail"]


async def test_empty_folder_delete_removes_nested_directories_bottom_up(
    db, tmp_path
) -> None:
    root = tmp_path / "movies"
    empty_movie = root / "Empty Movie"
    (empty_movie / "empty" / "nested").mkdir(parents=True)
    service = DeletarrService(
        make_ctx(
            db=db,
            settings_store=StubSettingsStore(
                deletarr_movies_path=str(root), deletarr_use_arr_source=False
            ),
        )
    )
    await service.scan("movies")

    result = await service.delete("movies", [str(empty_movie)])

    assert result["deleted"] == 1
    assert not empty_movie.exists()


@pytest.mark.parametrize("filename", ["newly-arrived.mkv", ".hidden-marker"])
async def test_empty_folder_delete_preserves_files_added_after_scan(
    db, tmp_path, filename: str
) -> None:
    root = tmp_path / "movies"
    empty_movie = root / "Empty Movie"
    empty_movie.mkdir(parents=True)
    service = DeletarrService(
        make_ctx(
            db=db,
            settings_store=StubSettingsStore(
                deletarr_movies_path=str(root), deletarr_use_arr_source=False
            ),
        )
    )
    await service.scan("movies")
    arrived = _write(empty_movie / filename, b"preserve")

    result = await service.delete("movies", [str(empty_movie)])

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert arrived.read_bytes() == b"preserve"
    assert empty_movie.exists()


async def test_empty_folder_delete_preserves_symlink_added_after_scan(
    db, tmp_path
) -> None:
    root = tmp_path / "movies"
    empty_movie = root / "Empty Movie"
    empty_movie.mkdir(parents=True)
    target = _write(tmp_path / "outside" / "target.mkv", b"preserve")
    service = DeletarrService(
        make_ctx(
            db=db,
            settings_store=StubSettingsStore(
                deletarr_movies_path=str(root), deletarr_use_arr_source=False
            ),
        )
    )
    await service.scan("movies")
    link = empty_movie / "new-link.mkv"
    link.symlink_to(target)

    result = await service.delete("movies", [str(empty_movie)])

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert link.is_symlink()
    assert target.read_bytes() == b"preserve"


async def test_empty_folder_delete_preserves_concurrent_content(
    db, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "movies"
    empty_movie = root / "Empty Movie"
    empty_movie.mkdir(parents=True)
    service = DeletarrService(
        make_ctx(
            db=db,
            settings_store=StubSettingsStore(
                deletarr_movies_path=str(root), deletarr_use_arr_source=False
            ),
        )
    )
    await service.scan("movies")
    real_rmdir = os.rmdir

    def _create_before_rmdir(path: str) -> None:
        if os.path.normpath(path) == os.path.normpath(str(empty_movie)):
            _write(empty_movie / "concurrent.mkv", b"preserve")
        real_rmdir(path)

    monkeypatch.setattr("modules.deletarr.engine.os.rmdir", _create_before_rmdir)

    result = await service.delete("movies", [str(empty_movie)])

    assert result["deleted"] == 0
    assert result["failed"] == 1
    assert (empty_movie / "concurrent.mkv").read_bytes() == b"preserve"


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


async def test_arr_mode_delete_blocks_now_tracked_path(
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
