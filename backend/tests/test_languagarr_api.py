"""Tests for the Languagarr API router."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.context import SyncAlreadyRunning
from core.languagarr_api import create_languagarr_router
from modules.languagarr.client import LanguagarrClientError
from modules.languagarr.engine import LanguagarrScopeError
from tests.conftest import make_ctx

_SCAN = {
    "is_scanning": False,
    "last_scan_at": "2026-10-12T00:00:00+00:00",
    "last_error": None,
    "profiles_in_scope": ["Anime"],
    "series_scanned": 1,
    "files_scanned": 2,
    "non_compliant": 1,
    "unknown": 0,
    "missing_english": 1,
    "single_language": 0,
}
_COUNTS = {"pending": 1, "searched": 0, "failed": 0}
_ITEM = {
    "episode_file_id": 101,
    "series_id": 1,
    "series_title": "Show",
    "season_number": 1,
    "episode_ids": [1001],
    "episode_label": "S01E01",
    "relative_path": "Season 01/file.mkv",
    "audio_languages": "jpn/por",
    "sonarr_languages": ["Japanese", "Portuguese"],
    "verdict": "missing_english",
    "release_group": "Anitsu",
    "custom_format_score": -8000,
    "cutoff_format_score": 10000,
    "recommended_action": "search",
    "queue_status": "none",
    "last_searched_at": None,
}


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_languagarr_router(ctx))
    return TestClient(app)


def _status(ctx) -> dict:
    return {
        "settings": ctx.settings_store.languagarr_settings(),
        "running": False,
        "scan": _SCAN,
        "queue": _COUNTS,
    }


def test_settings_are_available_without_module_callbacks(db) -> None:
    body = build_client(make_ctx(db=db)).get("/api/languagarr/settings").json()
    assert body["quality_profile_names"] == ["Anime"]
    assert body["enabled"] is False


def test_runtime_routes_return_503_without_callbacks(db) -> None:
    client = build_client(make_ctx(db=db))
    assert client.get("/api/languagarr/status").status_code == 503
    assert client.get("/api/languagarr/results").status_code == 503
    assert client.post("/api/languagarr/scan").status_code == 503
    assert client.get("/api/languagarr/queue").status_code == 503
    assert client.delete("/api/languagarr/queue/pending").status_code == 503
    assert client.post("/api/languagarr/run").status_code == 503
    assert (
        client.post(
            "/api/languagarr/enqueue", json={"episode_file_ids": [1]}
        ).status_code
        == 503
    )
    assert (
        client.post(
            "/api/languagarr/delete", json={"episode_file_ids": [1], "confirm": True}
        ).status_code
        == 503
    )
    assert (
        client.put("/api/languagarr/settings", json={"enabled": True}).status_code
        == 503
    )


def test_callbacks_are_forwarded(db) -> None:
    ctx = make_ctx(db=db)
    results = {"scan": _SCAN, "results": [_ITEM], "unknown": []}
    ctx.languagarr_status = AsyncMock(return_value=_status(ctx))
    ctx.languagarr_results = AsyncMock(return_value=results)
    ctx.languagarr_scan = AsyncMock(return_value=results)
    ctx.languagarr_enqueue = AsyncMock(
        return_value={
            "queued": 1,
            "skipped": 0,
            "errors": [{"episode_file_id": 9, "error": "Not in scan results"}],
        }
    )
    ctx.languagarr_delete = AsyncMock(
        return_value={
            "deleted": 1,
            "searched": 1,
            "failed": 0,
            "deleted_ids": [101],
            "errors": [],
        }
    )
    ctx.languagarr_queue = AsyncMock(
        return_value={
            "counts": _COUNTS,
            "rows": [
                {
                    "episode_file_id": 101,
                    "series_id": 1,
                    "title": "Show - S01E01",
                    "episode_ids": [1001],
                    "reason": "missing_english",
                    "status": "pending",
                    "queued_at": "2026-10-12T00:00:00+00:00",
                    "searched_at": None,
                    "attempts": 0,
                    "last_error": None,
                }
            ],
        }
    )
    ctx.languagarr_clear_pending = AsyncMock(return_value={"removed": 1})
    ctx.languagarr_run_now = AsyncMock(
        return_value={
            "status": "completed",
            "searched": 1,
            "failed": 0,
            "resolved": 0,
        }
    )
    ctx.languagarr_update_settings = AsyncMock(return_value=_status(ctx))
    client = build_client(ctx)

    assert client.get("/api/languagarr/status").json()["scan"] == _SCAN
    assert client.get("/api/languagarr/results").json()["results"] == [_ITEM]
    assert client.post("/api/languagarr/scan").status_code == 200
    assert (
        client.post("/api/languagarr/enqueue", json={"episode_file_ids": [101]}).json()[
            "queued"
        ]
        == 1
    )
    ctx.languagarr_enqueue.assert_awaited_once_with([101])
    deleted = client.post(
        "/api/languagarr/delete", json={"episode_file_ids": [101], "confirm": True}
    )
    assert deleted.json()["deleted_ids"] == [101]
    ctx.languagarr_delete.assert_awaited_once_with([101])
    assert client.get("/api/languagarr/queue").json()["rows"][0]["status"] == "pending"
    assert client.delete("/api/languagarr/queue/pending").json() == {"removed": 1}
    assert client.post("/api/languagarr/run").json()["searched"] == 1
    assert (
        client.put(
            "/api/languagarr/settings",
            json={"enabled": True, "auto_queue": None, "interval_minutes": 30},
        ).status_code
        == 200
    )
    ctx.languagarr_update_settings.assert_awaited_once_with(
        {"enabled": True, "interval_minutes": 30}
    )


def test_request_validation_limits(db) -> None:
    ctx = make_ctx(db=db)
    ctx.languagarr_enqueue = AsyncMock()
    ctx.languagarr_delete = AsyncMock()
    client = build_client(ctx)
    assert (
        client.post(
            "/api/languagarr/enqueue", json={"episode_file_ids": []}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/languagarr/enqueue", json={"episode_file_ids": list(range(501))}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/languagarr/delete",
            json={"episode_file_ids": list(range(26)), "confirm": True},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/languagarr/delete", json={"episode_file_ids": [1]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/languagarr/delete", json={"episode_file_ids": [1], "confirm": False}
        ).status_code
        == 422
    )
    ctx.languagarr_enqueue.assert_not_awaited()
    ctx.languagarr_delete.assert_not_awaited()


def test_settings_update_rejects_out_of_range_values(db) -> None:
    ctx = make_ctx(db=db)
    ctx.languagarr_update_settings = AsyncMock()
    client = build_client(ctx)
    for body in (
        {"interval_minutes": 5},
        {"searches_per_run": 101},
        {"retry_after_hours": 1},
        {"quality_profile_names": []},
    ):
        assert client.put("/api/languagarr/settings", json=body).status_code == 422
    ctx.languagarr_update_settings.assert_not_awaited()


def test_errors_map_to_http_statuses(db) -> None:
    ctx = make_ctx(db=db)
    client = build_client(ctx)

    for error, code in (
        (SyncAlreadyRunning(), 409),
        (LanguagarrClientError("sonarr down"), 502),
        (LanguagarrScopeError("Sonarr has no quality profile named X"), 400),
    ):
        ctx.languagarr_scan = AsyncMock(side_effect=error)
        ctx.languagarr_delete = AsyncMock(side_effect=error)
        assert client.post("/api/languagarr/scan").status_code == code
        assert (
            client.post(
                "/api/languagarr/delete",
                json={"episode_file_ids": [1], "confirm": True},
            ).status_code
            == code
        )

    ctx.languagarr_run_now = AsyncMock(side_effect=SyncAlreadyRunning())
    response = client.post("/api/languagarr/run")
    assert response.status_code == 409
    assert response.json() == {"detail": "Languagarr is already running"}
