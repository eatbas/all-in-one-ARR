"""Tests for the Cleanarr API router."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.cleanarr_api import create_cleanarr_router
from core.context import SyncAlreadyRunning
from core.settings_modules import CleanarrIgnoreListFull
from tests.conftest import make_ctx

_QUEUE_ITEM = {
    "app": "sonarr",
    "queue_id": 7,
    "download_id": "SABnzbd_nzo_1",
    "title": "Show.S01E01",
    "reason": "failed_import",
    "message": "Episode was not found",
    "strikes": 2,
    "max_strikes": 3,
    "would_remove": False,
    "ignored": False,
    "excluded": False,
}
_HISTORY = {
    "id": 1,
    "ts": "2026-10-28T10:00:00+00:00",
    "app": "radarr",
    "action": "removed",
    "download_id": "SABnzbd_nzo_2",
    "title": "Movie",
    "detail": "failed_download",
    "dry_run": False,
}


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_cleanarr_router(ctx))
    return TestClient(app)


def _status(ctx) -> dict[str, Any]:
    return {
        "settings": ctx.settings_store.cleanarr_settings(),
        "enabled": False,
        "dry_run": True,
        "running": False,
        "last_run": {"at": "2026-10-28T10:00:00+00:00", "status": "completed", "detail": "nothing to clean"},
        "connections": [{"app": "sabnzbd", "ok": True, "detail": "Connected to SABnzbd"}],
        "health": [{"source": "sonarr", "code": "x", "detail": "d", "level": "info"}],
        "strikes": {"sonarr": 1, "radarr": 0, "failed_import": 1, "failed_download": 0},
    }  # fmt: skip


def _wired_ctx(db):
    ctx = make_ctx(db=db)
    ctx.cleanarr_status = AsyncMock(return_value=_status(ctx))
    ctx.cleanarr_update_settings = AsyncMock(return_value=_status(ctx))
    ctx.cleanarr_queue = AsyncMock(
        return_value={
            "items": [_QUEUE_ITEM],
            "errors": {"radarr": "connection refused"},
            "held": {"sonarr": "Queue cleaning held"},
            "max_strikes": 3,
            "dry_run": True,
        }
    )
    ctx.cleanarr_history = AsyncMock(return_value=[_HISTORY])
    ctx.cleanarr_run_now = AsyncMock(
        return_value={
            "status": "completed",
            "detail": "1 struck",
            "counts": {"struck": 1},
        }
    )
    ctx.cleanarr_clear_strikes = AsyncMock(return_value={"count": 2})
    ctx.cleanarr_ignore = AsyncMock(return_value=ctx.settings_store.cleanarr_settings())
    return ctx


def test_success_paths(db) -> None:
    ctx = _wired_ctx(db)
    client = build_client(ctx)

    settings = client.get("/api/cleanarr/settings")
    assert settings.status_code == 200
    assert settings.json()["dry_run"] is True

    assert client.get("/api/cleanarr/status").json()["strikes"]["sonarr"] == 1
    queue = client.get("/api/cleanarr/queue").json()
    assert queue["items"] == [_QUEUE_ITEM]
    assert queue["errors"] == {"radarr": "connection refused"}
    assert queue["held"] == {"sonarr": "Queue cleaning held"}
    assert client.get("/api/cleanarr/history").json() == [_HISTORY]
    assert client.post("/api/cleanarr/run").json()["counts"] == {"struck": 1}
    assert client.post("/api/cleanarr/strikes/clear").json() == {"count": 2}

    ignored = client.post("/api/cleanarr/ignore", json={"download_id": "nzo_x"})
    assert ignored.status_code == 200
    ctx.cleanarr_ignore.assert_awaited_once_with("nzo_x")


def test_put_settings_forwards_only_given_fields(db) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).put(
        "/api/cleanarr/settings",
        json={
            "enabled": True,
            "max_strikes": 5,
            "queue": {"pattern_mode": "include", "patterns": ["sample"]},
            "malware": {"extensions": [".exe", ".scr"]},
            "orphans": {"min_age_hours": 48},
            "paths": {"quarantine_dir": "/downloads/complete/q"},
            "apps": {"radarr": {"enabled": False}},
            "ignore": {"categories": ["anime"]},
        },
    )
    assert response.status_code == 200
    ctx.cleanarr_update_settings.assert_awaited_once_with(
        {
            "enabled": True,
            "max_strikes": 5,
            "queue": {"pattern_mode": "include", "patterns": ["sample"]},
            "malware": {"extensions": [".exe", ".scr"]},
            "orphans": {"min_age_hours": 48},
            "paths": {"quarantine_dir": "/downloads/complete/q"},
            "apps": {"radarr": {"enabled": False}},
            "ignore": {"categories": ["anime"]},
        }
    )


def test_put_settings_without_paths_skips_the_path_check(db) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).put("/api/cleanarr/settings", json={"dry_run": False})
    assert response.status_code == 200
    ctx.cleanarr_update_settings.assert_awaited_once_with({"dry_run": False})


def test_put_settings_accepts_a_new_root_with_its_quarantine(db) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).put(
        "/api/cleanarr/settings",
        json={
            "paths": {"completed_root": "/mnt/done/", "quarantine_dir": "/mnt/done/q"}
        },
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/api/cleanarr/settings", {}),
        ("get", "/api/cleanarr/status", None),
        ("get", "/api/cleanarr/queue", None),
        ("get", "/api/cleanarr/history", None),
        ("post", "/api/cleanarr/run", None),
        ("post", "/api/cleanarr/strikes/clear", None),
        ("post", "/api/cleanarr/ignore", {"download_id": "x"}),
    ],
)
def test_routes_answer_503_before_setup(
    db, method: str, path: str, body: dict | None
) -> None:
    client = build_client(make_ctx(db=db))
    response = getattr(client, method)(
        path, **({"json": body} if body is not None else {})
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Cleanarr unavailable"}


@pytest.mark.parametrize("path", ["/api/cleanarr/run", "/api/cleanarr/strikes/clear"])
def test_busy_routes_answer_409(db, path: str) -> None:
    ctx = _wired_ctx(db)
    ctx.cleanarr_run_now = AsyncMock(side_effect=SyncAlreadyRunning())
    ctx.cleanarr_clear_strikes = AsyncMock(side_effect=SyncAlreadyRunning())
    response = build_client(ctx).post(path)
    assert response.status_code == 409
    assert response.json() == {"detail": "Cleanarr is already running"}


@pytest.mark.parametrize(
    "body",
    [
        {"interval_minutes": 4},
        {"interval_minutes": 1441},
        {"max_strikes": 2},
        {"max_strikes": 21},
        {"max_removals_per_run": 0},
        {"max_removals_per_run": 51},
        {"orphans": {"min_age_hours": 0}},
        {"orphans": {"quarantine_retention_days": 366}},
        {"malware": {"extensions": ["exe"]}},
        {"malware": {"extensions": [".EXE"]}},
        {"malware": {"extensions": []}},
        {"queue": {"pattern_mode": "regex"}},
        {"queue": {"patterns": [""]}},
        {"queue": {"patterns": ["x" * 201]}},
        {"queue": {"patterns": ["p"] * 51}},
        {"paths": {"completed_root": "relative/path"}},
        {"paths": {"quarantine_dir": ""}},
        {"ignore": {"download_ids": ["x"] * 501}},
        {"ignore": {"title_contains": [""]}},
    ],
)
def test_put_settings_rejects_invalid_fields(db, body: dict) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).put("/api/cleanarr/settings", json=body)
    assert response.status_code == 422
    ctx.cleanarr_update_settings.assert_not_awaited()


@pytest.mark.parametrize(
    "paths",
    [
        {"quarantine_dir": "/elsewhere/q"},
        {"completed_root": "/mnt/other"},
        {"quarantine_dir": "/downloads/complete"},
    ],
)
def test_put_settings_rejects_quarantine_outside_root(db, paths: dict) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).put("/api/cleanarr/settings", json={"paths": paths})
    assert response.status_code == 422
    assert "quarantine folder" in response.json()["detail"]


def test_ignore_answers_409_while_running_and_422_when_the_list_is_full(db) -> None:
    ctx = _wired_ctx(db)
    client = build_client(ctx)
    ctx.cleanarr_ignore.side_effect = SyncAlreadyRunning()
    busy = client.post("/api/cleanarr/ignore", json={"download_id": "x"})
    assert (busy.status_code, busy.json()) == (
        409,
        {"detail": "Cleanarr is already running"},
    )

    ctx.cleanarr_ignore.side_effect = CleanarrIgnoreListFull()
    full = client.post("/api/cleanarr/ignore", json={"download_id": "x"})
    assert full.status_code == 422
    assert full.json()["detail"].startswith("The ignore list already holds 500")


@pytest.mark.parametrize("download_id", ["", "x" * 201, "bad\nid", "tab\tid", "\x00"])
def test_ignore_rejects_invalid_ids(db, download_id: str) -> None:
    ctx = _wired_ctx(db)
    response = build_client(ctx).post(
        "/api/cleanarr/ignore", json={"download_id": download_id}
    )
    assert response.status_code == 422
    ctx.cleanarr_ignore.assert_not_awaited()
