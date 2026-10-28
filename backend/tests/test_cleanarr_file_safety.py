"""Safety tests for Cleanarr's file passes, end to end through the engine:
symlinked quarantine and job folders, ignore rules on orphan and purge actions
(including the category an entry was quarantined from), malware decisions per
download (including records without a usable queue id or ``downloadId``), and
incomplete SABnzbd or Sonarr/Radarr references.

These reuse the fakes and fixtures of :mod:`tests.test_cleanarr_engine`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

import pytest

from core.db import Database
from core.sabnzbd_types import SabConfig
from modules.cleanarr import engine as engine_module
from modules.cleanarr import file_passes
from modules.cleanarr.queue_cleaner import QUEUE_INCOMPLETE_DETAIL
from tests.test_cleanarr_engine import (
    _OLD,
    FakeArr,
    FakeSab,
    _history,
    _malware_setup,
    _orphan_setup,
    _record,
    _run_times,
    _service,
    _strikes,
    _touch,
)


@pytest.fixture
def arrs(monkeypatch) -> dict[str, FakeArr]:
    fakes = {"sonarr": FakeArr("sonarr"), "radarr": FakeArr("radarr")}
    fakes["sonarr"].version = "4.0.0"
    monkeypatch.setattr(
        engine_module, "client_for", lambda _ctx, app: fakes[app].client()
    )
    return fakes


@pytest.fixture
def sab() -> FakeSab:
    return FakeSab()


async def _notes(service) -> dict[str, str]:
    return {
        warning["code"]: warning["detail"]
        for warning in (await service.status())["health"]
        if warning["source"] == "system"
    }


def _age(path: Path) -> None:
    stamp = (datetime.now(UTC) - _OLD).timestamp()
    os.utime(path, (stamp, stamp), follow_symlinks=False)


def _sab_config(*category_folders: tuple[str, str]) -> SabConfig:
    return SabConfig(
        complete_dir="/data/complete",
        unwanted_extensions=(".exe", ".scr", ".lnk"),
        unwanted_action=2,
        encrypted_rar_action=2,
        category_dirs=("tv", "movies"),
        category_folders=category_folders,
    )


def _fifteen_days_later(monkeypatch: pytest.MonkeyPatch) -> None:
    """Move the file passes' clock past the default 14-day retention."""

    class _Later(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Any:
            return datetime.now(tz) + timedelta(days=15)

    monkeypatch.setattr(file_passes, "datetime", _Later)


# ---- F1: the quarantine is never trusted through a symlink ----


@pytest.mark.parametrize("target", ["outside", "inside"])
async def test_symlinked_quarantine_is_never_listed_or_purged(
    db, arrs, sab, tmp_path, target: str
) -> None:
    service, root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    orphan.unlink()  # no new quarantine candidates in this run
    linked = tmp_path / "sibling" if target == "outside" else root / "real-q"
    keep = _touch(linked / "20200101T000000Z__keep.txt")
    (root / "_cleanarr_quarantine").symlink_to(linked, target_is_directory=True)

    result = await service.run_now()
    assert result["counts"]["purged"] == 0
    assert result["counts"]["quarantined"] == 0
    assert keep.exists()
    assert _history(service) == []
    notes = await _notes(service)
    assert "quarantine_unsafe" in notes
    assert notes["quarantine_unsafe"].endswith("(symlink).")


async def test_quarantine_under_a_symlinked_folder_is_refused(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "link").symlink_to(elsewhere, target_is_directory=True)
    service._ctx.settings_store.update_cleanarr_settings(
        {
            "paths": {
                "completed_root": str(root),
                "quarantine_dir": str(root / "link" / "q"),
            }
        }
    )
    await service.run_now()
    assert orphan.exists()
    assert list(elsewhere.iterdir()) == []
    assert "quarantine_unsafe" in await _notes(service)


# ---- F8: the malware pass never follows a symlinked job ----


async def test_malware_pass_refuses_a_symlinked_job_folder(
    db, arrs, sab, tmp_path
) -> None:
    service, blocked, _importing = _malware_setup(db, arrs, sab, tmp_path)
    job = blocked.parent
    other = job.parent / "Other.Job"
    job.rename(other)
    job.symlink_to(other, target_is_directory=True)
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert (other / "setup.exe").exists()
    assert _history(service) == []


# ---- F4: the ignore lists protect orphan and purge candidates ----


async def test_ignored_orphan_titles_are_never_quarantined(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(
        db, arrs, sab, tmp_path, ignore={"title_contains": ["keep.this"]}
    )
    keep = _touch(root / "Keep.This.Release", age=_OLD)
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 1
    assert not orphan.exists()
    assert keep.exists()


async def test_ignored_categories_protect_their_folders(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(
        db, arrs, sab, tmp_path, ignore={"categories": ["Anime", "kids"]}
    )
    sab.config = SabConfig(
        complete_dir="/data/complete",
        unwanted_extensions=(".exe", ".scr", ".lnk"),
        unwanted_action=2,
        encrypted_rar_action=2,
        category_dirs=("tv", "anime-folder", "kids"),
        # "kids" is a category folder SABnzbd no longer names a category for.
        category_folders=(("tv", "tv"), ("anime", "anime-folder")),
    )
    by_name = _touch(root / "anime-folder" / "Show.S01", age=_OLD)
    _age(root / "anime-folder")
    # A folder whose own name matches an ignored category is protected too.
    by_folder = _touch(root / "kids" / "Cartoon.S01", age=_OLD)
    _age(root / "kids")
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 1
    assert not orphan.exists()
    assert by_name.exists() and by_folder.exists()


async def test_ignored_entries_already_in_quarantine_are_kept(
    db, arrs, sab, tmp_path
) -> None:
    service, root, _orphan, _kept = _orphan_setup(
        db, arrs, sab, tmp_path, ignore={"title_contains": ["Keep.This"]}
    )
    quarantine_dir = root / "_cleanarr_quarantine"
    kept = _touch(quarantine_dir / "20200101T000000Z__Keep.This.Old")
    expired = _touch(quarantine_dir / "20200101T000000Z__Ancient")
    result = await service.run_now()
    assert result["counts"]["purged"] == 1
    assert kept.exists()
    assert not expired.exists()


async def test_quarantined_category_stays_protected_after_a_restart(
    arrs, sab, tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "cleanarr.db")
    first_db = Database(db_path)
    first_db.init_db()
    service, root, orphan, _kept = _orphan_setup(first_db, arrs, sab, tmp_path)
    sab.config = _sab_config(("television", "tv"))
    keep = _touch(root / "tv" / "Keep.Category.Release", age=_OLD)
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 2
    assert not orphan.exists() and not keep.exists()
    first_db.close()

    # Reload with the category now ignored; SABnzbd also stopped naming the
    # folder's category, so only the origin recorded at quarantine protects it.
    reopened = Database(db_path)
    reopened.init_db()
    try:
        sab.config = _sab_config()
        restarted = _service(
            reopened,
            sab,
            orphans={"enabled": True},
            paths={"completed_root": str(root)},
            ignore={"categories": ["Television"]},
        )
        _fifteen_days_later(monkeypatch)
        result = await restarted.run_now()
        assert result["counts"]["purged"] == 1
        quarantine_dir = root / "_cleanarr_quarantine"
        names = [entry.name for entry in quarantine_dir.iterdir()]
        assert len(names) == 1 and names[0].endswith("__Keep.Category.Release")
        # The purged entry's origin is forgotten; the kept one's is not.
        assert list(reopened.cleanarr_quarantine_origins()) == names
    finally:
        reopened.close()


async def test_expired_entry_of_unknown_origin_is_kept_with_category_rules(
    db, arrs, sab, tmp_path
) -> None:
    service, root, _orphan, _kept = _orphan_setup(
        db, arrs, sab, tmp_path, ignore={"categories": ["anime"]}
    )
    legacy = _touch(root / "_cleanarr_quarantine" / "20200101T000000Z__Legacy")
    result = await service.run_now()
    assert result["counts"]["purged"] == 0
    assert legacy.exists()
    health = {w["code"]: w for w in (await service.status())["health"]}
    note = health["quarantine_origin_unknown"]
    assert note["level"] == "info"
    assert note["detail"].startswith("1 expired quarantined item(s) kept")


async def test_recorded_origins_survive_a_quarantine_that_cannot_be_listed(
    db, arrs, sab, tmp_path
) -> None:
    service, _root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    orphan.unlink()  # nothing to quarantine, so the folder is never created
    db.cleanarr_record_quarantine(
        "20200101T000000Z__Show", container="tv", categories=["tv"]
    )
    await service.run_now()
    assert db.cleanarr_quarantine_origins() == {
        "20200101T000000Z__Show": ("tv", ("tv",))
    }


# ---- F13: malware decisions cover the whole download ----


async def test_malware_is_kept_when_any_record_of_the_job_is_importing(
    db, arrs, sab, tmp_path
) -> None:
    service, blocked, _importing = _malware_setup(db, arrs, sab, tmp_path)
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        _record(
            5,
            downloadId="nzo_1",
            trackedDownloadState="importing",
            trackedDownloadStatus="ok",
        ),
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert _history(service) == []


async def test_an_ignored_episode_title_protects_the_shared_job(
    db, arrs, sab, tmp_path
) -> None:
    service, blocked, _importing = _malware_setup(
        db, arrs, sab, tmp_path, ignore={"title_contains": ["keep.this"]}
    )
    pending = {"trackedDownloadState": "importPending", "trackedDownloadStatus": "ok"}
    arrs["sonarr"].records = [
        _record(1, title="Show.S01E01", **pending),
        _record(5, downloadId="nzo_1", title="Keep.This.S01E02", **pending),
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()


@pytest.mark.parametrize("dry_run", [True, False])
async def test_a_job_with_duplicate_records_is_scanned_once(
    db, arrs, sab, tmp_path, dry_run: bool
) -> None:
    service, blocked, _importing = _malware_setup(
        db, arrs, sab, tmp_path, dry_run=dry_run
    )
    pending = {"trackedDownloadState": "importPending", "trackedDownloadStatus": "ok"}
    arrs["sonarr"].records = [
        _record(1, **pending),
        _record(5, downloadId="nzo_1", **pending),
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 1
    action = "would_delete_malware" if dry_run else "malware_deleted"
    assert _history(service) == [(action, "nzo_1")]
    assert blocked.exists() is dry_run


# ---- F13: records without a usable queue id still protect their download ----

# ``None`` drops the ``id`` field; the integer is the valid-id control.
_COMPANION_IDS = ["bad", True, None, 5]


def _companion(queue_id: object, **overrides: Any) -> dict[str, Any]:
    """Return a second record of download ``nzo_1`` with the given ``id``."""
    record = _record(5, downloadId="nzo_1", **overrides)
    if queue_id is None:
        del record["id"]
    else:
        record["id"] = queue_id
    return record


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("companion_id", _COMPANION_IDS)
async def test_an_importing_companion_without_a_queue_id_protects_the_job(
    db, arrs, sab, tmp_path, companion_id: object, dry_run: bool
) -> None:
    service, blocked, _importing = _malware_setup(
        db, arrs, sab, tmp_path, dry_run=dry_run
    )
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        _companion(
            companion_id, trackedDownloadState="importing", trackedDownloadStatus="ok"
        ),
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert _history(service) == []


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("companion_id", _COMPANION_IDS)
async def test_an_ignored_companion_without_a_queue_id_protects_the_download(
    db, arrs, sab, tmp_path, companion_id: object, dry_run: bool
) -> None:
    service, blocked, _importing = _malware_setup(
        db,
        arrs,
        sab,
        tmp_path,
        dry_run=dry_run,
        ignore={"title_contains": ["keep.this"]},
    )
    arrs["sonarr"].records = [
        _record(1, title="Show.S01E01"),
        _companion(
            companion_id,
            title="Keep.This.S01E02",
            trackedDownloadState="importPending",
            trackedDownloadStatus="ok",
        ),
    ]
    result = await _run_times(service, 3)
    assert result["counts"]["struck"] == 0
    assert result["counts"]["malware_deleted"] == 0
    assert _strikes(service) == {}
    assert arrs["sonarr"].deletes() == []
    assert blocked.exists()
    assert _history(service) == []


async def test_a_job_folder_named_by_a_record_without_a_download_id_is_kept(
    db, arrs, sab, tmp_path
) -> None:
    service, blocked, _importing = _malware_setup(db, arrs, sab, tmp_path)
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        {
            "id": 9,
            "trackedDownloadState": "importing",
            "outputPath": "/data/complete/tv/Job1",
        },
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert "malware_skipped" not in await _notes(service)


async def test_a_record_folder_named_by_a_record_without_a_download_id_is_kept(
    db, arrs, sab, tmp_path
) -> None:
    # The unmatched record names the queued record's own outputPath, not the
    # SABnzbd job folder: queue cleaning and the malware pass share one
    # protection, so both treat the download as unknown.
    service, blocked, _importing = _malware_setup(db, arrs, sab, tmp_path)
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        {
            "id": 9,
            "trackedDownloadState": "importing",
            "outputPath": "/data/complete/tv/Release 1",
        },
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert _history(service) == []


@pytest.mark.parametrize(
    "unmatched", [{"id": 9, "trackedDownloadState": "importing"}, "not a dict"]
)
async def test_a_record_tied_to_no_download_skips_the_malware_pass(
    db, arrs, sab, tmp_path, unmatched: object
) -> None:
    service, blocked, _importing = _malware_setup(db, arrs, sab, tmp_path)
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        unmatched,
    ]
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert _history(service) == []
    notes = await _notes(service)
    assert "could not be matched to a download" in notes["malware_skipped"]


# ---- F17: a reference that names no folder holds removal and malware ----

_JOB1 = "/data/complete/tv/Job1"
# The first two companions are controls that protect the download anyway.
_IGNORED_COMPANIONS = ["download_id", _JOB1, "/", "//", ".", "/data/complete/.."]


def _ignored_companion(companion: str) -> dict[str, Any]:
    """Return an ignored-title record of the ``Job1`` download.

    ``download_id`` keeps its ``downloadId``; any other value drops it and
    becomes the record's ``outputPath``.
    """
    record = _record(5, downloadId="nzo_1", title="Keep.This.S01E02", outputPath=_JOB1)
    if companion != "download_id":
        del record["downloadId"]
        record["outputPath"] = companion
    return record


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("companion", _IGNORED_COMPANIONS)
async def test_an_ignored_companion_naming_no_folder_holds_every_action(
    db, arrs, sab, tmp_path, companion: str, dry_run: bool
) -> None:
    service, blocked, _importing = _malware_setup(
        db,
        arrs,
        sab,
        tmp_path,
        dry_run=dry_run,
        ignore={"title_contains": ["keep.this"]},
    )
    primary = _record(1, outputPath=_JOB1)
    arrs["sonarr"].records = [primary, _ignored_companion(companion)]
    result = await _run_times(service, 3)
    for count in ("struck", "removed", "would_remove", "malware_deleted"):
        assert result["counts"][count] == 0
    assert _strikes(service) == {}
    assert arrs["sonarr"].deletes() == []
    assert blocked.exists()
    assert _history(service) == []
    queue = await service.queue()
    assert [row["would_remove"] for row in queue["items"]] == [False]
    folderless = companion not in _IGNORED_COMPANIONS[:2]
    assert ("malware_skipped" in await _notes(service)) is folderless
    assert (queue["held"].get("sonarr") == QUEUE_INCOMPLETE_DETAIL) is folderless

    # Without the companion, the failing download is struck and scanned again.
    arrs["sonarr"].records = [primary]
    result = await service.run_now()
    assert result["counts"]["struck"] == 1
    assert result["counts"]["malware_deleted"] == 1
    assert blocked.exists() is dry_run
    assert (await service.queue())["held"] == {}


# ---- F14: references of records that cannot be acted on ----


async def test_unparsed_history_and_queue_references_are_never_quarantined(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    from_history = _touch(root / "tv" / "No.Nzo.Id", age=_OLD)
    from_queue = _touch(root / "tv" / "No.Queue.Id", age=_OLD)
    sab.unparsed_storage = ["/data/complete/tv/No.Nzo.Id"]
    arrs["sonarr"].records.append(
        {"id": "bad", "downloadId": "x", "outputPath": "/data/complete/tv/No.Queue.Id"}
    )
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 1
    assert not orphan.exists()
    assert from_history.exists() and from_queue.exists()


async def test_an_unreadable_queue_reference_skips_the_orphan_pass(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    expired = _touch(root / "_cleanarr_quarantine" / "20200101T000000Z__Ancient")
    arrs["radarr"].records = [_record(2, outputPath=["/data/complete/Orphan.Job"])]
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 0
    assert result["counts"]["purged"] == 0
    assert orphan.exists() and expired.exists()
    notes = await _notes(service)
    assert "queue record could not be read in full" in notes["orphans_skipped"]


# ---- F6: an incomplete SABnzbd history blocks orphan actions ----


async def test_incomplete_history_skips_the_orphan_pass(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, _kept = _orphan_setup(db, arrs, sab, tmp_path)
    expired = _touch(root / "_cleanarr_quarantine" / "20200101T000000Z__Ancient")
    sab.history_complete = False
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 0
    assert result["counts"]["purged"] == 0
    assert orphan.exists() and expired.exists()
    notes = await _notes(service)
    assert "history is longer than Cleanarr reads" in notes["orphans_skipped"]
