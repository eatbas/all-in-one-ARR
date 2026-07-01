"""Tests for the Deletarr API router."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.context import SyncAlreadyRunning
from core.deletarr_api import create_deletarr_router
from tests.conftest import make_ctx


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_deletarr_router(ctx))
    return TestClient(app)


def test_settings_are_available_without_module_callbacks(db) -> None:
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/deletarr/settings").json()
    assert body == {
        "movies_path": "/media/movies",
        "tv_path": "/media/tv",
        "use_arr_source": False,
    }


def test_runtime_routes_return_503_without_callbacks(db) -> None:
    client = build_client(make_ctx(db=db))
    assert client.get("/api/deletarr/status").status_code == 503
    assert client.get("/api/deletarr/results").status_code == 503
    assert client.post("/api/deletarr/scan", json={"type": "movies"}).status_code == 503
    assert (
        client.post(
            "/api/deletarr/delete",
            json={"type": "movies", "paths": ["/media/movies/junk.nfo"]},
        ).status_code
        == 503
    )
    assert (
        client.put(
            "/api/deletarr/settings",
            json={"movies_path": "/media/movies2"},
        ).status_code
        == 503
    )


async def test_status_results_scan_delete_and_settings_callbacks(db) -> None:
    ctx = make_ctx(db=db)
    payload = {
        "settings": {"movies_path": "/movies", "tv_path": "/tv"},
        "libraries": {
            "movies": {
                "type": "movies",
                "path": "/movies",
                "last_scan_at": None,
                "last_error": None,
                "results_count": 0,
                "stats": {
                    "total_files": 0,
                    "total_folders": 0,
                    "total_size": 0,
                    "is_scanning": False,
                    "scan_progress": 0,
                },
            }
        },
    }
    results = {
        "type": "movies",
        "path": "/movies",
        "results": [],
        "stats": payload["libraries"]["movies"]["stats"],
    }
    delete_result = {
        "success": True,
        "deleted": 1,
        "failed": 0,
        "freed_bytes": 100,
        "freed_mb": 0,
        "freed_formatted": "100.0 B",
        "deleted_paths": ["/movies/junk.nfo"],
        "errors": [],
    }

    ctx.deletarr_status = AsyncMock(return_value=payload)
    ctx.deletarr_results = AsyncMock(return_value=results)
    ctx.deletarr_scan = AsyncMock(return_value=results)
    ctx.deletarr_delete = AsyncMock(return_value=delete_result)
    ctx.deletarr_update_settings = AsyncMock(return_value=payload)

    client = build_client(ctx)
    assert client.get("/api/deletarr/status").json() == payload
    assert client.get("/api/deletarr/results?type=movies").json() == results
    assert client.post("/api/deletarr/scan", json={"type": "movies"}).json() == results
    assert (
        client.post(
            "/api/deletarr/delete",
            json={"type": "movies", "paths": ["/movies/junk.nfo"]},
        ).json()
        == delete_result
    )
    assert (
        client.put(
            "/api/deletarr/settings",
            json={"movies_path": "/movies2", "tv_path": "/tv2"},
        ).json()
        == payload
    )
    ctx.deletarr_delete.assert_awaited_once_with("movies", ["/movies/junk.nfo"])
    ctx.deletarr_update_settings.assert_awaited_once_with(
        movies_path="/movies2",
        tv_path="/tv2",
        use_arr_source=None,
    )


def test_delete_rejects_empty_paths(db) -> None:
    ctx = make_ctx(db=db)
    ctx.deletarr_delete = AsyncMock(return_value={})
    response = build_client(ctx).post(
        "/api/deletarr/delete",
        json={"type": "movies", "paths": []},
    )
    assert response.status_code == 422
    ctx.deletarr_delete.assert_not_awaited()


def test_busy_scan_and_delete_return_409(db) -> None:
    async def _raise(*_args):
        raise SyncAlreadyRunning()

    ctx = make_ctx(db=db)
    ctx.deletarr_scan = _raise
    ctx.deletarr_delete = _raise
    client = build_client(ctx)

    assert client.post("/api/deletarr/scan", json={"type": "movies"}).status_code == 409
    assert (
        client.post(
            "/api/deletarr/delete",
            json={"type": "movies", "paths": ["/movies/junk.nfo"]},
        ).status_code
        == 409
    )


def test_value_errors_return_400(db) -> None:
    async def _raise(*_args):
        raise ValueError("bad library")

    ctx = make_ctx(db=db)
    ctx.deletarr_results = _raise
    ctx.deletarr_scan = _raise
    ctx.deletarr_delete = _raise
    client = build_client(ctx)

    assert client.get("/api/deletarr/results?type=movies").status_code == 400
    assert (
        client.post("/api/deletarr/scan", json={"type": "movies"}).json()["detail"]
        == "bad library"
    )
    assert (
        client.post(
            "/api/deletarr/delete",
            json={"type": "movies", "paths": ["/movies/junk.nfo"]},
        ).status_code
        == 400
    )
