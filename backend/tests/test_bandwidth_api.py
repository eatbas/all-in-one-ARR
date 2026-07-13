"""Tests for the Bandwidth-Controllarr API router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.bandwidth_api import create_bandwidth_router
from core.context import AppContext, BandwidthClientControlError
from core.webhooks import WebhookRegistry
from tests.conftest import StubService, StubSettingsStore, StubTrakt, _StubSettings


@pytest.fixture
def bandwidth_app(db):
    """Build a minimal app with the bandwidth router and an in-memory DB."""
    qbit = StubService()
    sab = StubService()
    sab.get_stats = AsyncMock(
        return_value={
            "online": True,
            "speed_mbps": 1.2,
            "active_downloads": 1,
            "queue_size": 2,
            "paused": False,
        }
    )

    ctx = AppContext(
        settings=_StubSettings(),
        db=db,
        trakt=StubTrakt(),
        seer=StubService(),
        sonarr=StubService(),
        radarr=StubService(),
        tmdb=StubService(),
        omdb=StubService(),
        anilist=StubService(),
        sabnzbd=sab,
        qbittorrent=qbit,
        scheduler=AsyncMock(),
        webhooks=WebhookRegistry(),
        settings_store=StubSettingsStore(),
    )

    default_payload = {
        "enabled": True,
        "status": "No active torrents",
        "last_run_at": "2024-01-01T00:00:00Z",
        "tracking_suspended": False,
        "manual_paused_clients": [],
        "check_interval_seconds": 15,
        "qbittorrent": {
            "online": True,
            "speed_mbps": 0,
            "active_downloads": 0,
            "queue_size": 0,
        },
        "sabnzbd": {
            "online": True,
            "speed_mbps": 1.2,
            "active_downloads": 1,
            "queue_size": 2,
            "paused": False,
        },
        "download_history": [
            {
                "client": "sabnzbd",
                "id": "SABnzbd_nzo_1",
                "name": "Finished.Show.S01E01",
                "status": "Completed",
                "progress": 100,
                "size_bytes": 1024,
                "size_label": "1.0 KB",
                "speed_mbps": None,
                "eta_seconds": None,
                "added_at": "2024-01-01T00:00:00Z",
                "completed_at": "2024-01-01T00:10:00Z",
            }
        ],
        "queue": {
            "qbittorrent": {
                "items": [
                    {
                        "client": "qbittorrent",
                        "id": "abc",
                        "name": "Queued.Movie",
                        "status": "queuedDL",
                        "progress": 25,
                        "size_bytes": 2048,
                        "size_label": "2.0 KB",
                        "speed_mbps": 0.5,
                        "eta_seconds": 60,
                        "added_at": "2024-01-01T00:00:00Z",
                        "completed_at": None,
                        # Unmodelled upstream field: the response model must
                        # strip it rather than leak a local filesystem path.
                        "content_path": "/downloads/Queued.Movie",
                    }
                ],
                "total": 9,
            },
            "sabnzbd": {"items": [], "total": 0},
        },
    }
    ctx.bandwidth_status = AsyncMock(return_value=default_payload)
    ctx.bandwidth_update_settings = AsyncMock(return_value=default_payload)
    ctx.bandwidth_update_client = AsyncMock(return_value=default_payload)

    app = FastAPI()
    app.state.ctx = ctx
    app.include_router(create_bandwidth_router(ctx))
    return app, ctx


async def test_get_status_returns_bandwidth_payload(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.get("/api/bandwidth/status")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["status"] == "No active torrents"
    assert body["download_history"][0]["name"] == "Finished.Show.S01E01"
    queued = body["queue"]["qbittorrent"]
    assert queued["items"][0]["status"] == "queuedDL"
    assert "content_path" not in queued["items"][0]
    # The count is cumulative: one row rendered, nine actually queued.
    assert queued["total"] == 9
    assert body["queue"]["sabnzbd"] == {"items": [], "total": 0}
    ctx.bandwidth_status.assert_awaited_once()


async def test_get_status_returns_503_when_not_ready(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    ctx.bandwidth_status = None
    with TestClient(app) as client:
        response = client.get("/api/bandwidth/status")
    assert response.status_code == 503


async def test_put_settings_applies_enabled(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put("/api/bandwidth/settings", json={"enabled": False})
    assert response.status_code == 200
    ctx.bandwidth_update_settings.assert_awaited_once_with(
        enabled=False, check_interval_seconds=None
    )


async def test_put_settings_applies_interval(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put(
            "/api/bandwidth/settings", json={"check_interval_seconds": 30}
        )
    assert response.status_code == 200
    ctx.bandwidth_update_settings.assert_awaited_once_with(
        enabled=None, check_interval_seconds=30
    )


async def test_put_settings_rejects_invalid_interval(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put(
            "/api/bandwidth/settings", json={"check_interval_seconds": 25}
        )
    assert response.status_code == 422
    ctx.bandwidth_update_settings.assert_not_awaited()


async def test_put_settings_rejects_zero_interval(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put(
            "/api/bandwidth/settings", json={"check_interval_seconds": 0}
        )
    assert response.status_code == 422


async def test_put_settings_returns_503_when_not_ready(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    ctx.bandwidth_update_settings = None
    with TestClient(app) as client:
        response = client.put("/api/bandwidth/settings", json={"enabled": True})
    assert response.status_code == 503


async def test_put_client_applies_manual_pause(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put(
            "/api/bandwidth/clients/qbittorrent", json={"paused": True}
        )

    assert response.status_code == 200
    ctx.bandwidth_update_client.assert_awaited_once_with(
        client="qbittorrent", paused=True
    )


async def test_put_client_rejects_unknown_client(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    with TestClient(app) as client:
        response = client.put("/api/bandwidth/clients/unknown", json={"paused": True})

    assert response.status_code == 422
    ctx.bandwidth_update_client.assert_not_awaited()


async def test_put_client_returns_503_when_not_ready(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    ctx.bandwidth_update_client = None
    with TestClient(app) as client:
        response = client.put("/api/bandwidth/clients/sabnzbd", json={"paused": False})

    assert response.status_code == 503


async def test_put_client_maps_downstream_failure_to_502(bandwidth_app) -> None:
    app, ctx = bandwidth_app
    ctx.bandwidth_update_client = AsyncMock(
        side_effect=BandwidthClientControlError("sabnzbd could not pause downloads")
    )
    with TestClient(app) as client:
        response = client.put("/api/bandwidth/clients/sabnzbd", json={"paused": True})

    assert response.status_code == 502
    assert response.json()["detail"] == "sabnzbd could not pause downloads"
