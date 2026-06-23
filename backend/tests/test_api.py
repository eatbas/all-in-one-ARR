"""Tests for core.api (dashboard JSON endpoints)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import _SYNC_TASKS, _remember_task, create_api_router
from tests.conftest import StubTrakt, make_ctx

_ITEM = dict(
    trakt_id=1, type="movie", title="Dune", year=2021, tmdb=100,
    tvdb=None, imdb="tt1", list_id="watchlist",
)


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_api_router(ctx))
    return TestClient(app)


def test_status_endpoint(db) -> None:
    db.upsert_item(**_ITEM)
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=True), dry_run=True)
    body = build_client(ctx).get("/api/status").json()
    assert body["dry_run"] is True
    assert body["trakt_connected"] is True
    assert body["counts"]["synced"] == 1


def test_items_endpoint_filtered_and_unfiltered(db) -> None:
    db.upsert_item(**_ITEM)
    db.set_status(trakt_id=1, list_id="watchlist", status="requested")
    ctx = make_ctx(db=db)
    client = build_client(ctx)
    assert len(client.get("/api/items").json()) == 1
    assert len(client.get("/api/items?status=removed").json()) == 0
    assert len(client.get("/api/items?status=requested").json()) == 1


def test_activity_endpoint(db) -> None:
    db.add_activity("requested", "requested Dune")
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/activity").json()
    assert body[0]["detail"] == "requested Dune"


def test_sync_endpoint_triggers_handler(db) -> None:
    ctx = make_ctx(db=db)
    ctx.sync_now = AsyncMock()
    resp = build_client(ctx).post("/api/sync")
    assert resp.status_code == 202
    assert resp.json() == {"status": "triggered"}
    ctx.sync_now.assert_awaited()


def test_sync_endpoint_without_handler(db) -> None:
    ctx = make_ctx(db=db)
    ctx.sync_now = None
    resp = build_client(ctx).post("/api/sync")
    assert resp.status_code == 202


def test_dry_run_toggle(db) -> None:
    ctx = make_ctx(db=db, dry_run=True)
    resp = build_client(ctx).post("/api/settings/dry-run", json={"enabled": False})
    assert resp.json() == {"dry_run": False}
    assert ctx.dry_run is False


async def test_remember_task_discards_on_success() -> None:
    async def ok() -> None:
        return None

    task = asyncio.create_task(ok())
    _remember_task(task)
    assert task in _SYNC_TASKS
    await task
    await asyncio.sleep(0)  # let the done-callback run
    assert task not in _SYNC_TASKS


async def test_remember_task_logs_failure() -> None:
    async def boom() -> None:
        raise RuntimeError("sync exploded")

    task = asyncio.create_task(boom())
    _remember_task(task)
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert task not in _SYNC_TASKS


async def test_remember_task_handles_cancellation() -> None:
    async def forever() -> None:
        await asyncio.sleep(10)

    task = asyncio.create_task(forever())
    _remember_task(task)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert task not in _SYNC_TASKS


def test_services_status_endpoint_returns_snapshot(db) -> None:
    ctx = make_ctx(db=db)
    build_client(ctx).post("/api/status/services/check")
    body = build_client(ctx).get("/api/status/services").json()
    assert body["interval_seconds"] == 60
    assert body["last_check_at"] is not None
    assert "trakt" in body["services"]
    assert "jellyseerr" in body["services"]


def test_services_check_endpoint_triggers_check(db) -> None:
    ctx = make_ctx(db=db)
    ctx.status_checker.check_now = AsyncMock(
        return_value=ctx.status_checker.get_statuses()
    )
    body = build_client(ctx).post("/api/status/services/check").json()
    assert "interval_seconds" in body
    ctx.status_checker.check_now.assert_awaited_once()


def test_put_general_settings_updates_interval(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put("/api/settings/general", json={"interval_seconds": 30})
    assert resp.status_code == 200
    assert resp.json() == {"interval_seconds": 30}
    assert ctx.settings_store.status_check_interval_seconds() == 30


def test_put_general_settings_rejects_invalid_interval(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put("/api/settings/general", json={"interval_seconds": 99})
    assert resp.status_code == 200
    assert resp.json() == {"interval_seconds": 60}


def test_get_general_settings_returns_interval(db) -> None:
    ctx = make_ctx(db=db)
    ctx.settings_store.update_status_check_interval(45)
    body = build_client(ctx).get("/api/settings/general").json()
    assert body == {"interval_seconds": 45}
