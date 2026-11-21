"""Tests for the Remindarr API router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.clients.plex import PlexClientError
from core.context import SyncAlreadyRunning
from core.remindarr_api import create_remindarr_router
from modules.remindarr.client import RemindarrClientError
from modules.remindarr.engine import RemindarrTagError
from tests.conftest import make_ctx

_COUNTS = {
    "unwatched": 3,
    "series_with_unwatched": 1,
    "tracked_series": 2,
    "unmatched_series": 1,
}
_EPISODE = {
    "episode_id": 7,
    "series_id": 1,
    "episode_file_id": 70,
    "season_number": 3,
    "episode_number": 8,
    "label": "S03E08",
    "title": "The Second Trial",
    "air_date_utc": "2026-11-20T00:00:00+00:00",
    "added_at": "2026-11-21T06:00:00+00:00",
    "new_today": True,
}
_RESULTS = {
    "last_success_at": "2026-11-21T09:00:00+00:00",
    "series": [
        {
            "series_id": 1,
            "series_title": "Starfall Academy",
            "series_slug": "starfall-academy",
            "tvdb_id": 101,
            "episodes_not_in_plex": 1,
            "latest_added_at": "2026-11-21T06:00:00+00:00",
            "new_today": 1,
            "episodes": [_EPISODE],
        }
    ],
    "unmatched": [
        {
            "series_id": 2,
            "series_title": "Paper Cranes",
            "series_slug": None,
            "tvdb_id": None,
            "reason": "no_tvdb_id",
            "reason_label": "No TVDB id in Sonarr",
        }
    ],
}


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_remindarr_router(ctx))
    return TestClient(app)


def _status(ctx) -> dict:
    return {
        "settings": ctx.settings_store.remindarr_settings(),
        "running": False,
        "plex_configured": True,
        "last_success_at": "2026-11-21T09:00:00+00:00",
        "last_attempt_at": "2026-11-21T10:00:00+00:00",
        "last_error": "Plex rejected the token",
        "stale": True,
        "missing_tag_ids": [9],
        "counts": _COUNTS,
    }


def _wired_ctx(db):
    ctx = make_ctx(db=db)
    ctx.remindarr_status = AsyncMock(return_value=_status(ctx))
    ctx.remindarr_results = AsyncMock(return_value=_RESULTS)
    ctx.remindarr_tags = AsyncMock(return_value=[{"id": 1, "label": "anime"}])
    ctx.remindarr_run_now = AsyncMock(
        return_value={
            "status": "success",
            "unwatched": 3,
            "series_with_unwatched": 1,
            "tracked_series": 2,
            "unmatched_series": 1,
        }
    )
    ctx.remindarr_update_settings = AsyncMock(return_value=_status(ctx))
    return ctx


def test_settings_are_readable_before_setup(db) -> None:
    resp = build_client(make_ctx(db=db)).get("/api/remindarr/settings")
    assert resp.status_code == 200
    assert resp.json() == {
        "enabled": False,
        "interval_minutes": 60,
        "tag_ids": [],
        "monitored_only": True,
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("put", "/api/remindarr/settings"),
        ("get", "/api/remindarr/tags"),
        ("get", "/api/remindarr/status"),
        ("get", "/api/remindarr/results"),
        ("post", "/api/remindarr/run"),
    ],
)
def test_routes_are_unavailable_before_setup(db, method: str, path: str) -> None:
    client = build_client(make_ctx(db=db))
    kwargs = {"json": {}} if method == "put" else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Remindarr unavailable"


def test_status_results_and_tags(db) -> None:
    ctx = _wired_ctx(db)
    client = build_client(ctx)
    status = client.get("/api/remindarr/status").json()
    assert status["stale"] is True
    assert status["counts"] == _COUNTS
    assert client.get("/api/remindarr/results").json() == _RESULTS
    assert client.get("/api/remindarr/tags").json() == [{"id": 1, "label": "anime"}]


def test_put_settings_passes_only_set_fields(db) -> None:
    ctx = _wired_ctx(db)
    resp = build_client(ctx).put(
        "/api/remindarr/settings",
        json={"enabled": True, "tag_ids": [1, 2], "interval_minutes": None},
    )
    assert resp.status_code == 200
    ctx.remindarr_update_settings.assert_awaited_once_with(
        {"enabled": True, "tag_ids": [1, 2]}
    )


@pytest.mark.parametrize(
    "body",
    [
        {"interval_minutes": 14},
        {"interval_minutes": 1441},
        {"tag_ids": [0]},
        {"tag_ids": [-1]},
        {"tag_ids": list(range(1, 52))},
        {"tag_ids": ["anime"]},
    ],
)
def test_put_settings_rejects_out_of_bounds_input(db, body: dict) -> None:
    ctx = _wired_ctx(db)
    resp = build_client(ctx).put("/api/remindarr/settings", json=body)
    assert resp.status_code == 422
    ctx.remindarr_update_settings.assert_not_awaited()


def test_put_settings_maps_unknown_tag_to_422(db) -> None:
    ctx = _wired_ctx(db)
    ctx.remindarr_update_settings.side_effect = RemindarrTagError(
        "Unknown Sonarr tag id: 8"
    )
    resp = build_client(ctx).put("/api/remindarr/settings", json={"tag_ids": [8]})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Unknown Sonarr tag id: 8"


def test_put_settings_maps_sonarr_error_to_502(db) -> None:
    ctx = _wired_ctx(db)
    ctx.remindarr_update_settings.side_effect = RemindarrClientError("down")
    resp = build_client(ctx).put("/api/remindarr/settings", json={"tag_ids": [1]})
    assert resp.status_code == 502
    assert resp.json()["detail"] == "down"


def test_tags_map_sonarr_error_to_502(db) -> None:
    ctx = _wired_ctx(db)
    ctx.remindarr_tags.side_effect = RemindarrClientError("down")
    resp = build_client(ctx).get("/api/remindarr/tags")
    assert resp.status_code == 502


def test_run_returns_summary(db) -> None:
    ctx = _wired_ctx(db)
    resp = build_client(ctx).post("/api/remindarr/run")
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_run_while_disabled_returns_disabled(db) -> None:
    ctx = _wired_ctx(db)
    ctx.remindarr_run_now.return_value = {
        "status": "disabled",
        "unwatched": 0,
        "series_with_unwatched": 0,
        "tracked_series": 0,
        "unmatched_series": 0,
    }
    assert build_client(ctx).post("/api/remindarr/run").json()["status"] == "disabled"


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (SyncAlreadyRunning(), 409),
        (RemindarrClientError("sonarr down"), 502),
        (PlexClientError("Plex rejected the token"), 502),
    ],
)
def test_run_maps_errors(db, error: Exception, status_code: int) -> None:
    ctx = _wired_ctx(db)
    ctx.remindarr_run_now.side_effect = error
    resp = build_client(ctx).post("/api/remindarr/run")
    assert resp.status_code == status_code
    if status_code == 409:
        assert resp.json()["detail"] == "A Remindarr refresh is already running."
    else:
        assert resp.json()["detail"] == str(error)
