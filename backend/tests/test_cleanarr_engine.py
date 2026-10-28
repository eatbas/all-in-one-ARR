"""Tests for the Cleanarr engine, queue cleaner, file passes and module wiring.

An in-process fake Sonarr/Radarr (served through ``httpx.MockTransport``) backs
real :class:`CleanarrArrClient` instances, and a small fake SABnzbd returns the
three reads a run makes, so each acceptance criterion runs end to end.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.context import SyncAlreadyRunning
from core.sabnzbd_types import SabConfig, SabHistory, SabHistoryJob
from modules.cleanarr import engine as engine_module
from modules.cleanarr.client import CleanarrArrClient, client_for
from modules.cleanarr.engine import CleanarrService
from modules.cleanarr.queue_cleaner import short_detail
from tests.conftest import StubSettingsStore, make_ctx

_OLD = timedelta(days=3)


def _record(record_id: int, **overrides: Any) -> dict[str, Any]:
    record = {
        "id": record_id,
        "downloadId": f"nzo_{record_id}",
        "protocol": "usenet",
        "downloadClient": "SABnzbd",
        "title": f"Release {record_id}",
        "status": "completed",
        "trackedDownloadStatus": "warning",
        "trackedDownloadState": "importBlocked",
        "statusMessages": [{"title": "x", "messages": ["Episode was not found"]}],
        "outputPath": f"/data/complete/tv/Release {record_id}",
    }
    record.update(overrides)
    return record


class FakeArr:
    """A tiny Sonarr/Radarr: system status, queue, delete and handling config."""

    def __init__(self, app: str) -> None:
        self.app = app
        self.app_name = app.capitalize()
        self.version = "6.0.0"
        self.records: list[dict[str, Any]] = []
        self.status_codes: dict[str, int] = {}
        self.handling: dict[str, Any] = {
            "enableCompletedDownloadHandling": True,
            "autoRedownloadFailed": True,
        }
        self.clients: list[dict[str, Any]] = [
            {"implementation": "Sabnzbd", "removeFailedDownloads": True}
        ]
        self.calls: list[tuple[str, str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path, request.url.query.decode()))
        for prefix, code in self.status_codes.items():
            if path.startswith(prefix):
                return httpx.Response(code)
        if path == "/api/v3/system/status":
            return httpx.Response(
                200, json={"appName": self.app_name, "version": self.version}
            )
        if path == "/api/v3/queue":
            return httpx.Response(
                200,
                json={"totalRecords": len(self.records), "records": self.records},
            )
        if path.startswith("/api/v3/queue/") and request.method == "DELETE":
            queue_id = int(path.rsplit("/", 1)[1])
            self.records = [r for r in self.records if r.get("id") != queue_id]
            return httpx.Response(200)
        if path == "/api/v3/config/downloadclient":
            return httpx.Response(200, json=self.handling)
        if path == "/api/v3/downloadclient":
            return httpx.Response(200, json=self.clients)
        return httpx.Response(404)  # pragma: no cover - defensive

    def client(self) -> CleanarrArrClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return CleanarrArrClient(
            app=self.app, base_url=f"http://{self.app}", api_key="k", http_client=http
        )

    def deletes(self) -> list[tuple[str, str, str]]:
        return [call for call in self.calls if call[0] == "DELETE"]


class FakeSab:
    """The three SABnzbd reads Cleanarr makes; ``None`` simulates a failure."""

    def __init__(self) -> None:
        self.config: SabConfig | None = SabConfig(
            complete_dir="/data/complete",
            unwanted_extensions=(".exe", ".scr", ".lnk"),
            unwanted_action=2,
            encrypted_rar_action=2,
            category_dirs=("tv", "movies"),
        )
        self.history: list[SabHistoryJob] | None = []
        self.history_complete = True
        self.unparsed_storage: list[str] = []
        self.queue_names: list[str] | None = []

    async def get_config(self) -> SabConfig | None:
        return self.config

    async def history_jobs(self) -> SabHistory | None:
        if self.history is None:
            return None
        return SabHistory(
            jobs=tuple(self.history),
            complete=self.history_complete,
            unparsed_storage=tuple(self.unparsed_storage),
        )

    async def queue_filenames(self) -> list[str] | None:
        return self.queue_names


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


def _settings(**overrides: Any) -> dict[str, Any]:
    settings: dict[str, Any] = {"enabled": True, "dry_run": False}
    settings.update(overrides)
    return settings


def _service(db, sab: FakeSab, **overrides: Any) -> CleanarrService:
    store = StubSettingsStore(cleanarr_settings=_settings(**overrides))
    return CleanarrService(make_ctx(db=db, settings_store=store, sabnzbd=sab))


async def _run_times(service: CleanarrService, times: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for _ in range(times):
        result = await service.run_now()
    return result


def _history(service: CleanarrService) -> list[tuple[str, str]]:
    return [
        (row["action"], row["download_id"] or row["title"])
        for row in service._ctx.db.cleanarr_history_rows()
    ]


def _strikes(service: CleanarrService) -> dict[tuple[str, str], int]:
    return {
        (row["app"], row["download_id"]): row["strikes"]
        for row in service._ctx.db.cleanarr_strike_rows()
    }


# ---- client factory ----


def test_client_for_uses_context_connections(db) -> None:
    ctx = make_ctx(db=db)
    for app in ("sonarr", "radarr"):
        client = client_for(ctx, app)
        assert (client.app, client.base_url, client.api_key) == (
            app,
            "http://arr",
            "key",
        )


def test_short_detail_trims_long_text() -> None:
    assert short_detail("x" * 400).endswith("…")
    assert len(short_detail("x" * 400)) == 300
    assert short_detail("ok") == "ok"


# ---- enable switch and run_now ----


async def test_disabled_makes_no_calls(db, arrs, sab) -> None:
    service = _service(db, sab, enabled=False)
    assert await service.run_now() == {
        "status": "skipped",
        "detail": "Cleanarr is disabled",
        "counts": {},
    }
    assert await service.scheduled_run() == await service.run_now()
    assert arrs["sonarr"].calls == [] and arrs["radarr"].calls == []
    assert service._ctx.db.cleanarr_run_state() == {}


async def test_run_now_is_rejected_while_running(db, arrs, sab) -> None:
    service = _service(db, sab)
    started = asyncio.Event()
    release = asyncio.Event()

    async def hold() -> None:
        started.set()
        await release.wait()

    holder = asyncio.create_task(service.gate.run(hold))
    await started.wait()
    with pytest.raises(SyncAlreadyRunning):
        await service.run_now()
    with pytest.raises(SyncAlreadyRunning):
        await service.clear_strikes()
    assert (await service.status())["running"] is True
    release.set()
    await holder


# ---- strikes and removals ----


async def test_dry_run_strikes_and_logs_would_remove_once(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    service = _service(db, sab, dry_run=True)

    first = await _run_times(service, 2)
    assert first["counts"]["struck"] == 1
    assert _strikes(service) == {("sonarr", "nzo_1"): 2}
    assert _history(service) == []

    third = await service.run_now()
    assert third["counts"]["would_remove"] == 1
    assert third["detail"].startswith("Dry run: ")
    await _run_times(service, 2)
    assert _history(service) == [("would_remove", "nzo_1")]
    assert service._ctx.db.cleanarr_history_rows()[0]["dry_run"] is True
    assert arrs["sonarr"].deletes() == []
    assert _strikes(service) == {("sonarr", "nzo_1"): 5}


async def test_live_removal_uses_blocklist_parameters(db, arrs, sab) -> None:
    arrs["radarr"].records = [_record(7)]
    service = _service(db, sab)
    result = await _run_times(service, 3)

    assert result["status"] == "completed"
    assert result["counts"]["removed"] == 1
    assert arrs["radarr"].deletes() == [
        (
            "DELETE",
            "/api/v3/queue/7",
            "removeFromClient=true&blocklist=true&skipRedownload=false",
        )
    ]
    assert _history(service) == [("removed", "nzo_7")]
    assert _strikes(service) == {}
    activity = service._ctx.db.recent_activity(5)
    assert activity[0]["action"] == "Cleanarr"
    assert "1 removed" in activity[0]["detail"]


async def test_removal_cap_is_shared_across_apps(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1), _record(2)]
    arrs["radarr"].records = [_record(3)]
    service = _service(db, sab, max_removals_per_run=2)
    result = await _run_times(service, 3)
    assert result["counts"]["removed"] == 2
    remaining = _strikes(service)
    assert len(remaining) == 1
    assert list(remaining.values()) == [3]
    # The item over the cap keeps its strikes and is removed on the next run.
    assert (await service.run_now())["counts"]["removed"] == 1


async def test_exclude_and_include_patterns(db, arrs, sab) -> None:
    matched = _record(
        1, statusMessages=[{"title": "t", "messages": ["matched to series by ID"]}]
    )
    plain = _record(2)
    arrs["sonarr"].records = [matched, plain]

    exclude = _service(db, sab)
    await exclude.run_now()
    assert _strikes(exclude) == {("sonarr", "nzo_2"): 1}

    include = _service(
        db,
        sab,
        queue={"pattern_mode": "include", "patterns": ["matched to series by ID"]},
    )
    await include.run_now()
    assert _strikes(include) == {("sonarr", "nzo_1"): 1}


async def test_failed_sab_job_is_struck_not_removed_on_first_sight(
    db, arrs, sab
) -> None:
    arrs["sonarr"].records = [
        _record(4, trackedDownloadState="downloading", trackedDownloadStatus="ok")
    ]
    sab.history = [
        SabHistoryJob(
            nzo_id="nzo_4", name="Job", status="Failed", category="tv", storage=""
        )
    ]
    service = _service(db, sab)
    result = await service.run_now()
    assert result["counts"] == {**result["counts"], "struck": 1, "removed": 0}
    assert service._ctx.db.cleanarr_strike_rows()[0]["reason"] == "failed_download"
    assert arrs["sonarr"].deletes() == []


async def test_strikes_clear_when_items_recover_or_leave(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1), _record(2)]
    service = _service(db, sab)
    await service.run_now()
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importing", trackedDownloadStatus="ok")
    ]
    await service.run_now()
    assert _strikes(service) == {}


async def test_unreachable_or_incompatible_app_keeps_strikes(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    arrs["radarr"].records = [_record(2)]
    service = _service(db, sab)
    await service.run_now()

    arrs["sonarr"].status_codes["/api/v3/queue"] = 503
    arrs["radarr"].version = "5.0.0"
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_1"): 1, ("radarr", "nzo_2"): 1}

    status = await service.status()
    connections = {row["app"]: row for row in status["connections"]}
    assert connections["sonarr"]["ok"] is False
    assert "503" in connections["sonarr"]["detail"]
    assert "Radarr 6+" in connections["radarr"]["detail"]
    assert connections["sabnzbd"] == {
        "app": "sabnzbd",
        "ok": True,
        "detail": "Connected to SABnzbd",
    }
    skipped = [w for w in status["health"] if w["code"] == "app_skipped"]
    assert [w["source"] for w in skipped] == ["sonarr", "radarr"]
    assert skipped[0]["detail"].endswith("Strikes left unchanged.")


async def test_sab_history_outage_preserves_failed_download_strikes(
    db, arrs, sab
) -> None:
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="downloading", trackedDownloadStatus="ok"),
        _record(2),
    ]
    sab.history = [
        SabHistoryJob(
            nzo_id="nzo_1", name="Job", status="Failed", category="tv", storage=""
        )
    ]
    service = _service(db, sab)
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_1"): 1, ("sonarr", "nzo_2"): 1}

    sab.history = None
    arrs["sonarr"].records = [_record(1, trackedDownloadState="downloading")]
    await service.run_now()
    # The failed download is neither incremented nor cleared; the import that
    # left the queue is cleared as usual.
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}
    status = await service.status()
    sab_row = next(row for row in status["connections"] if row["app"] == "sabnzbd")
    assert sab_row["ok"] is False


async def test_404_is_already_gone_and_500_keeps_the_strike(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    arrs["radarr"].records = [_record(2)]
    service = _service(db, sab)
    await _run_times(service, 2)
    arrs["sonarr"].status_codes["/api/v3/queue/1"] = 404
    arrs["radarr"].status_codes["/api/v3/queue/2"] = 500
    result = await service.run_now()
    assert result["counts"]["already_gone"] == 1
    assert result["counts"]["remove_failed"] == 1
    assert sorted(_history(service)) == [
        ("already_gone", "nzo_1"),
        ("remove_failed", "nzo_2"),
    ]
    assert _strikes(service) == {("radarr", "nzo_2"): 3}


async def test_per_app_disable_and_queue_switch(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    arrs["radarr"].records = [_record(2)]
    service = _service(db, sab, apps={"radarr": {"enabled": False}})
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_1"): 1}
    assert arrs["radarr"].calls == []

    paused = _service(db, sab, queue={"enabled": False})
    result = await paused.run_now()
    assert result["counts"]["struck"] == 0
    assert _strikes(paused) == {("sonarr", "nzo_1"): 1}


async def test_ignore_by_id_category_and_title(db, arrs, sab) -> None:
    arrs["sonarr"].records = [
        _record(1),
        _record(2),
        _record(3, title="Keep This Show"),
        _record(4),
    ]
    sab.history = [
        SabHistoryJob(
            nzo_id=f"nzo_{index}",
            name="J",
            status="Completed",
            category="Anime" if index == 2 else "tv",
            storage="",
        )
        for index in range(1, 5)
    ]
    service = _service(
        db,
        sab,
        ignore={
            "download_ids": ["nzo_1"],
            "categories": ["anime"],
            "title_contains": ["keep this"],
        },
    )
    await service.run_now()
    assert _strikes(service) == {("sonarr", "nzo_4"): 1}

    settings = await service.ignore("nzo_4")
    assert "nzo_4" in settings["ignore"]["download_ids"]
    assert _strikes(service) == {}
    await service.run_now()
    assert _strikes(service) == {}


async def test_torrent_items_are_never_struck(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1, protocol="torrent")]
    service = _service(db, sab)
    result = await service.run_now()
    assert result["counts"]["struck"] == 0
    assert result["detail"] == "nothing to clean"
    assert service._ctx.db.recent_activity(5) == []


async def test_health_warnings_are_stored_and_counted(db, arrs, sab) -> None:
    sab.config = SabConfig(
        complete_dir="/data/complete",
        unwanted_extensions=(),
        unwanted_action=0,
        encrypted_rar_action=None,
        category_dirs=(),
    )
    arrs["sonarr"].handling = {"enableCompletedDownloadHandling": False}
    arrs["radarr"].status_codes["/api/v3/config"] = 500
    service = _service(db, sab)
    await service.run_now()
    codes = {
        (w["source"], w["code"], w["level"]) for w in (await service.status())["health"]
    }
    assert ("sabnzbd", "unwanted_action_not_abort", "warning") in codes
    assert ("sabnzbd", "encrypted_rar_unknown", "info") in codes
    assert ("sonarr", "completed_handling_off", "warning") in codes
    assert ("sonarr", "redownload_failed_unknown", "info") in codes
    assert ("radarr", "download_handling_unknown", "info") in codes


async def test_unexpected_errors_record_an_error_run(db, arrs, sab) -> None:
    service = _service(db, sab)

    async def boom() -> None:
        raise RuntimeError("disk on fire")

    sab.get_config = boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.run_now()
    last_run = (await service.status())["last_run"]
    assert last_run["status"] == "error"
    assert last_run["detail"] == "Run failed: disk on fire"


# ---- read views ----


async def test_status_before_any_run(db, arrs, sab) -> None:
    status = await _service(db, sab, enabled=False, dry_run=True).status()
    assert status["last_run"] is None
    assert status["connections"] == []
    assert status["health"] == []
    assert status["enabled"] is False
    assert status["dry_run"] is True
    assert status["running"] is False
    assert status["strikes"] == {
        "sonarr": 0,
        "radarr": 0,
        "failed_import": 0,
        "failed_download": 0,
    }


async def test_status_counts_strikes(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    arrs["radarr"].records = [
        _record(2, trackedDownloadState="failed", trackedDownloadStatus="error")
    ]
    service = _service(db, sab)
    await service.run_now()
    status = await service.status()
    assert status["strikes"] == {
        "sonarr": 1,
        "radarr": 1,
        "failed_import": 1,
        "failed_download": 1,
    }
    assert status["last_run"]["status"] == "completed"
    assert status["last_run"]["detail"] == "2 struck"


async def test_queue_view_joins_strikes_and_reports_app_errors(db, arrs, sab) -> None:
    excluded = _record(
        3, statusMessages=[{"title": "t", "messages": ["matched to series by ID"]}]
    )
    arrs["sonarr"].records = [
        _record(1),
        _record(2, trackedDownloadState="downloading", trackedDownloadStatus="ok"),
        excluded,
    ]
    service = _service(db, sab, ignore={"download_ids": ["nzo_3"]})
    await _run_times(service, 3)
    arrs["sonarr"].records = [_record(1), excluded]
    arrs["radarr"].status_codes["/api/v3/queue"] = 500

    queue = await service.queue()
    assert queue["max_strikes"] == 3
    assert queue["dry_run"] is False
    assert set(queue["errors"]) == {"radarr"}
    assert queue["held"] == {}
    rows = {row["download_id"]: row for row in queue["items"]}
    assert set(rows) == {"nzo_1", "nzo_3"}
    assert rows["nzo_1"]["strikes"] == 0  # removed on the third run
    assert rows["nzo_1"]["message"] == "Episode was not found"
    assert rows["nzo_3"] == {
        "app": "sonarr",
        "queue_id": 3,
        "download_id": "nzo_3",
        "title": "Release 3",
        "reason": "failed_import",
        "message": "matched to series by ID",
        "strikes": 0,
        "max_strikes": 3,
        "would_remove": False,
        "ignored": True,
        "excluded": True,
    }


async def test_queue_view_marks_items_at_the_threshold(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1, statusMessages=[])]
    sab.history = None
    service = _service(db, sab, dry_run=True)
    await _run_times(service, 3)
    row = (await service.queue())["items"][0]
    assert row["would_remove"] is True
    assert row["strikes"] == 3
    assert row["message"] == ""
    assert row["ignored"] is False


async def test_history_and_clear_strikes(db, arrs, sab) -> None:
    arrs["sonarr"].records = [_record(1)]
    service = _service(db, sab, dry_run=True)
    await _run_times(service, 3)
    assert [row["action"] for row in await service.history()] == ["would_remove"]
    assert await service.clear_strikes() == {"count": 1}
    assert _strikes(service) == {}
    assert service._ctx.db.recent_activity(1)[0]["action"] == "Cleanarr strikes cleared"


async def test_update_settings_records_activity(db, arrs, sab) -> None:
    service = _service(db, sab)
    settings = service.update_settings({"max_strikes": 5})
    assert settings["max_strikes"] == 5
    assert service._ctx.db.recent_activity(1)[0]["action"] == "Cleanarr settings saved"


# ---- malware pass ----


def _touch(path: Path, *, age: timedelta | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    if age is not None:
        stamp = (datetime.now(UTC) - age).timestamp()
        os.utime(path, (stamp, stamp))
    return path


def _completed_job(nzo_id: str, folder: str) -> SabHistoryJob:
    return SabHistoryJob(
        nzo_id=nzo_id,
        name=folder,
        status="Completed",
        category="tv",
        storage=f"/data/complete/tv/{folder}",
    )


def _malware_setup(db, arrs, sab, tmp_path: Path, **overrides: Any):
    root = tmp_path / "complete"
    blocked = _touch(root / "tv" / "Job1" / "setup.exe")
    _touch(root / "tv" / "Job1" / "movie.mkv")
    importing = _touch(root / "tv" / "Job2" / "virus.exe")
    arrs["sonarr"].records = [
        _record(1, trackedDownloadState="importPending", trackedDownloadStatus="ok"),
        _record(2, trackedDownloadState="importing", trackedDownloadStatus="ok"),
        _record(3, trackedDownloadState="downloading", trackedDownloadStatus="ok"),
    ]
    sab.history = [
        _completed_job("nzo_1", "Job1"),
        _completed_job("nzo_2", "Job2"),
        SabHistoryJob(
            nzo_id="nzo_3", name="J3", status="Running", category="tv", storage=""
        ),
    ]
    service = _service(
        db,
        sab,
        malware={"enabled": True},
        paths={"completed_root": str(root)},
        **overrides,
    )
    return service, blocked, importing


async def test_malware_deletes_only_completed_queued_jobs(
    db, arrs, sab, tmp_path
) -> None:
    service, blocked, importing = _malware_setup(db, arrs, sab, tmp_path)
    result = await service.run_now()
    assert result["counts"]["malware_deleted"] == 1
    assert not blocked.exists()
    assert importing.exists()
    rows = service._ctx.db.cleanarr_history_rows()
    assert [(r["app"], r["action"], r["title"], r["detail"]) for r in rows] == [
        ("sonarr", "malware_deleted", "Release 1", "setup.exe")
    ]


async def test_malware_dry_run_reports_once(db, arrs, sab, tmp_path) -> None:
    service, blocked, _ = _malware_setup(db, arrs, sab, tmp_path, dry_run=True)
    first = await service.run_now()
    second = await service.run_now()
    assert first["counts"]["malware_deleted"] == 1
    assert second["counts"]["malware_deleted"] == 0
    assert blocked.exists()
    assert _history(service) == [("would_delete_malware", "nzo_1")]


async def test_malware_reports_delete_failures(
    db, arrs, sab, tmp_path, monkeypatch
) -> None:
    service, blocked, _ = _malware_setup(db, arrs, sab, tmp_path)
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name == "setup.exe":
            raise PermissionError(13, "Permission denied")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    result = await service.run_now()
    assert result["counts"]["file_failures"] == 1
    assert _history(service) == [("malware_delete_failed", "nzo_1")]
    assert service._ctx.db.cleanarr_history_rows()[0]["detail"] == "Permission denied"
    assert blocked.exists()


async def test_malware_skips_unmappable_paths(db, arrs, sab, tmp_path) -> None:
    service, blocked, _ = _malware_setup(db, arrs, sab, tmp_path)
    sab.history = [
        SabHistoryJob(
            nzo_id="nzo_1",
            name="Job1",
            status="Completed",
            category="tv",
            storage="/elsewhere/Job1",
        )
    ]
    await service.run_now()
    assert blocked.exists()
    codes = [w["code"] for w in (await service.status())["health"]]
    assert "malware_path_unmapped" in codes


@pytest.mark.parametrize(
    ("problem", "code"),
    [
        ("sab_config", "sab_unavailable"),
        ("relative", "sab_complete_dir_unknown"),
        ("unmounted", "completed_root_missing"),
    ],
)
async def test_malware_pass_skipped_without_paths(
    db, arrs, sab, tmp_path, problem: str, code: str
) -> None:
    service, blocked, _ = _malware_setup(db, arrs, sab, tmp_path)
    if problem == "sab_config":
        sab.config = None
    elif problem == "relative":
        sab.config = SabConfig(
            complete_dir="Downloads/complete",
            unwanted_extensions=(),
            unwanted_action=2,
            encrypted_rar_action=2,
            category_dirs=(),
        )
    else:
        service = _service(
            db,
            sab,
            malware={"enabled": True},
            paths={"completed_root": str(tmp_path / "not-mounted")},
        )
    await service.run_now()
    assert blocked.exists()
    assert code in [w["code"] for w in (await service.status())["health"]]


# ---- orphan pass ----


def _orphan_setup(db, arrs, sab, tmp_path: Path, **overrides: Any):
    root = tmp_path / "complete"
    orphan = _touch(root / "Orphan.Job", age=_OLD)
    referenced = _touch(root / "tv" / "Release 1", age=_OLD)
    in_history = _touch(root / "tv" / "Done.Job", age=_OLD)
    queued = _touch(root / "Downloading.Job", age=_OLD)
    os.utime(root / "tv", ((datetime.now(UTC) - _OLD).timestamp(),) * 2)
    arrs["sonarr"].records = [_record(1, outputPath="/data/complete/tv/Release 1")]
    sab.history = [_completed_job("nzo_9", "Done.Job")]
    sab.queue_names = ["Downloading.Job"]
    service = _service(
        db,
        sab,
        orphans={"enabled": True},
        paths={"completed_root": str(root)},
        **overrides,
    )
    return service, root, orphan, (referenced, in_history, queued)


async def test_orphans_are_quarantined_and_expired_ones_purged(
    db, arrs, sab, tmp_path
) -> None:
    service, root, orphan, kept = _orphan_setup(db, arrs, sab, tmp_path)
    quarantine_dir = root / "_cleanarr_quarantine"
    expired = _touch(quarantine_dir / "20200101T000000Z__Ancient")
    _touch(quarantine_dir / "Unstamped")

    result = await service.run_now()
    assert result["counts"]["quarantined"] == 1
    assert result["counts"]["purged"] == 1
    assert not orphan.exists()
    assert not expired.exists()
    assert all(path.exists() for path in kept)
    names = sorted(entry.name for entry in quarantine_dir.iterdir())
    assert len(names) == 2
    assert names[0].endswith("__Orphan.Job")
    assert names[1] == "Unstamped"
    assert sorted(action for action, _ in _history(service)) == [
        "purged",
        "quarantined",
    ]


async def test_orphan_dry_run_moves_nothing(db, arrs, sab, tmp_path) -> None:
    service, root, orphan, _ = _orphan_setup(db, arrs, sab, tmp_path, dry_run=True)
    expired = _touch(root / "_cleanarr_quarantine" / "20200101T000000Z__Ancient")
    first = await service.run_now()
    await service.run_now()
    assert first["counts"]["quarantined"] == 1
    assert first["counts"]["purged"] == 1
    assert orphan.exists() and expired.exists()
    assert sorted(action for action, _ in _history(service)) == [
        "would_purge",
        "would_quarantine",
    ]


async def test_orphan_failures_are_logged(db, arrs, sab, tmp_path, monkeypatch) -> None:
    service, _root, orphan, _ = _orphan_setup(db, arrs, sab, tmp_path)

    def rename(_source, _target) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr("modules.cleanarr.files.os.rename", rename)
    result = await service.run_now()
    assert result["counts"]["file_failures"] == 1
    row = service._ctx.db.cleanarr_history_rows()[0]
    assert (row["action"], row["detail"]) == ("quarantine_failed", "cross_device")
    assert orphan.exists()


@pytest.mark.parametrize("failure", ["sab_queue", "arr_queue", "sab_history"])
async def test_orphan_pass_skipped_when_a_read_fails(
    db, arrs, sab, tmp_path, failure: str
) -> None:
    service, _root, orphan, _ = _orphan_setup(db, arrs, sab, tmp_path)
    if failure == "sab_queue":
        sab.queue_names = None
    elif failure == "arr_queue":
        arrs["radarr"].status_codes["/api/v3/queue"] = 500
    else:
        sab.history = None
    result = await service.run_now()
    assert result["counts"]["quarantined"] == 0
    assert orphan.exists()
    codes = [w["code"] for w in (await service.status())["health"]]
    assert {"orphans_skipped", "sab_unavailable"} & set(codes)
