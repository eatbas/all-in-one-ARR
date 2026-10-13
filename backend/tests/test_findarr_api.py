"""Tests for the Findarr API router."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.context import SyncAlreadyRunning
from core.findarr_api import create_findarr_router
from tests.conftest import make_ctx


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_findarr_router(ctx))
    return TestClient(app)


def test_settings_are_available_without_module_callbacks(db) -> None:
    body = build_client(make_ctx(db=db)).get("/api/findarr/settings").json()
    assert body["enabled"] is False
    assert set(body["apps"]) == {"sonarr", "radarr"}
    # Search granularity is Sonarr-only; Radarr always searches whole movies.
    assert body["apps"]["sonarr"]["missing_mode"] == "episodes"
    assert "missing_mode" not in body["apps"]["radarr"]
    assert "upgrade_mode" not in body["apps"]["radarr"]


def test_status_unavailable_without_callback(db) -> None:
    response = build_client(make_ctx(db=db)).get("/api/findarr/status")
    assert response.status_code == 503


def test_mutating_routes_unavailable_without_callbacks(db) -> None:
    client = build_client(make_ctx(db=db))
    assert (
        client.put("/api/findarr/settings", json={"enabled": True}).status_code == 503
    )
    assert client.get("/api/findarr/history").status_code == 503
    assert client.post("/api/findarr/run", json={}).status_code == 503
    assert client.post("/api/findarr/reset").status_code == 503
    assert client.post("/api/findarr/history/clear").status_code == 503


def test_status_history_run_reset_and_settings_callbacks(db) -> None:
    ctx = make_ctx(db=db)

    async def status():
        return {
            "settings": ctx.settings_store.findarr_settings(),
            "running": False,
            "last_run_at": None,
            "last_run_status": None,
            "last_run_detail": None,
            "retry": {"base_hours": 168, "max_hours": 720, "next_due_at": None},
            "apps": {
                "sonarr": {
                    "detail": "ok",
                    "version": "4.0.0",
                    "compatible": True,
                    "cooldown": {"missing": 0, "upgrade": 0},
                },
                "radarr": {
                    "detail": "ok",
                    "version": "6.0.0",
                    "compatible": True,
                    "cooldown": {"missing": 0, "upgrade": 0},
                },
            },
            "hourly": {"limit": 20, "used": 0, "remaining": 20},
        }

    ctx.findarr_status = status
    ctx.findarr_history = lambda: _async(
        [
            {
                "id": 1,
                "ts": "2026-01-01T00:00:00Z",
                "app": "sonarr",
                "mode": "system",
                "item_id": None,
                "title": None,
                "status": "success",
                "detail": "ok",
            }
        ]
    )
    ctx.findarr_run_now = lambda app=None: _async(
        {"status": "completed", "detail": str(app), "processed": 0, "results": []}
    )
    ctx.findarr_reset_state = lambda: _async({"status": "reset", "removed": 0})
    ctx.findarr_clear_history = lambda: _async({"status": "cleared", "removed": 3})
    captured: dict = {}

    def update_settings(updates):
        captured.update(updates)
        return ctx.findarr_status()

    ctx.findarr_update_settings = update_settings

    client = build_client(ctx)
    status_body = client.get("/api/findarr/status").json()
    assert status_body["retry"] == {
        "base_hours": 168,
        "max_hours": 720,
        "next_due_at": None,
    }
    assert client.get("/api/findarr/history").json()[0]["mode"] == "system"
    assert (
        client.post("/api/findarr/run", json={"app": "sonarr"}).json()["detail"]
        == "sonarr"
    )
    assert client.post("/api/findarr/reset").json() == {"status": "reset", "removed": 0}
    assert client.post("/api/findarr/history/clear").json() == {
        "status": "cleared",
        "removed": 3,
    }
    assert (
        client.put("/api/findarr/settings", json={"enabled": True}).status_code == 200
    )
    # The new search-mode/sleep/reset fields must survive validation and be
    # forwarded verbatim (no None pollution from exclude_none).
    new_fields = client.put(
        "/api/findarr/settings",
        json={
            "command_sleep_seconds": 5,
            "state_reset_hours": 72,
            "apps": {"sonarr": {"missing_mode": "seasons", "upgrade_mode": "shows"}},
        },
    )
    assert new_fields.status_code == 200
    assert captured["command_sleep_seconds"] == 5
    assert captured["state_reset_hours"] == 72
    assert captured["apps"]["sonarr"] == {
        "missing_mode": "seasons",
        "upgrade_mode": "shows",
    }


def test_run_conflict_returns_409(db) -> None:
    async def _raise(app=None):
        raise SyncAlreadyRunning()

    ctx = make_ctx(db=db)
    ctx.findarr_run_now = _raise
    response = build_client(ctx).post("/api/findarr/run", json={})
    assert response.status_code == 409


async def _async(value):
    return value
