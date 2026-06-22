"""Tests for core.services_api (Jellyseerr/Sonarr/Radarr settings + test)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.services_api import create_services_router
from tests.conftest import StubArr, make_ctx


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_services_router(ctx))
    return TestClient(app)


def test_get_services_masks_keys(db) -> None:
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/settings/services").json()
    assert body["jellyseerr"]["url"] == "http://js:5055"
    assert body["jellyseerr"]["api_key_set"] is True
    assert body["sonarr"]["api_key_set"] is False
    # No raw api_key is ever returned.
    assert "api_key" not in body["jellyseerr"]


def test_put_service_updates_store_and_client(db) -> None:
    sonarr = StubArr()
    ctx = make_ctx(db=db, sonarr=sonarr)
    resp = build_client(ctx).put(
        "/api/settings/services/sonarr",
        json={"url": "http://sonarr:8989", "api_key": "sk"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sonarr"] == {"url": "http://sonarr:8989", "api_key_set": True}
    sonarr.update_credentials.assert_called_once_with(
        base_url="http://sonarr:8989", api_key="sk"
    )


def test_put_unknown_service_is_404(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put("/api/settings/services/plex", json={"url": "x"})
    assert resp.status_code == 404


def test_test_service_ok(db) -> None:
    radarr = StubArr()
    radarr.test_connection = AsyncMock(
        return_value={"ok": True, "detail": "Connected to Radarr 5.0"}
    )
    ctx = make_ctx(db=db, radarr=radarr)
    body = build_client(ctx).post("/api/services/radarr/test").json()
    assert body == {"ok": True, "detail": "Connected to Radarr 5.0"}


def test_test_service_failure(db) -> None:
    jelly = make_ctx(db=db).jellyseerr
    jelly.test_connection = AsyncMock(
        return_value={"ok": False, "detail": "Jellyseerr returned HTTP 403"}
    )
    ctx = make_ctx(db=db, jellyseerr=jelly)
    body = build_client(ctx).post("/api/services/jellyseerr/test").json()
    assert body["ok"] is False
    assert "403" in body["detail"]


def test_test_unknown_service_is_404(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).post("/api/services/plex/test")
    assert resp.status_code == 404
