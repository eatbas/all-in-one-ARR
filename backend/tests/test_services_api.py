"""Tests for core.services_api (Seer/Sonarr/Radarr settings + test)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.services_api import create_services_router
from tests.conftest import StubArr, StubService, make_ctx


def build_client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_services_router(ctx))
    return TestClient(app)


def _activity_actions(ctx) -> list[str]:
    return [entry["action"] for entry in ctx.db.recent_activity()]


def test_get_services_masks_keys(db) -> None:
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/settings/services").json()
    assert body["seer"]["url"] == "http://js:5055"
    assert body["seer"]["api_key_set"] is True
    assert body["sonarr"]["api_key_set"] is False
    # No raw api_key is ever returned.
    assert "api_key" not in body["seer"]


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
    assert any(a["action"] == "Sonarr connection saved" for a in db.recent_activity())


def test_put_service_without_change_does_not_record_activity(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put(
        "/api/settings/services/seer",
        json={"url": "http://js:5055"},
    )
    assert resp.status_code == 200
    assert resp.json()["seer"]["url"] == "http://js:5055"
    assert not any("connection saved" in a for a in _activity_actions(ctx))


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
    assert "Radarr connection test passed" in _activity_actions(ctx)


def test_test_service_failure(db) -> None:
    seer = make_ctx(db=db).seer
    seer.test_connection = AsyncMock(
        return_value={"ok": False, "detail": "Seer returned HTTP 403"}
    )
    ctx = make_ctx(db=db, seer=seer)
    body = build_client(ctx).post("/api/services/seer/test").json()
    assert body["ok"] is False
    assert "403" in body["detail"]
    assert "Seer connection test failed" in _activity_actions(ctx)


def test_test_unknown_service_is_404(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).post("/api/services/plex/test")
    assert resp.status_code == 404


def test_get_services_masks_new_service_shapes(db) -> None:
    body = build_client(make_ctx(db=db)).get("/api/settings/services").json()
    # API-key-only services expose only the boolean (no url field).
    assert body["tmdb"] == {"api_key_set": False}
    assert body["omdb"] == {"api_key_set": False}
    assert body["sabnzbd"] == {"url": "", "api_key_set": False}
    # qBittorrent exposes url in clear, api_key masked away.
    assert body["qbittorrent"] == {"url": "", "api_key_set": False}
    assert "api_key" not in body["qbittorrent"]


def test_put_api_key_only_service_applies_just_the_key(db) -> None:
    tmdb = StubService()
    ctx = make_ctx(db=db, tmdb=tmdb)
    resp = build_client(ctx).put("/api/settings/services/tmdb", json={"api_key": "tk"})
    assert resp.status_code == 200
    assert resp.json()["tmdb"] == {"api_key_set": True}
    tmdb.update_credentials.assert_called_once_with(api_key="tk")
    assert "TMDB connection saved" in _activity_actions(ctx)


def test_put_qbittorrent_service_applies_url_and_api_key(db) -> None:
    qbit = StubService()
    ctx = make_ctx(db=db, qbittorrent=qbit)
    resp = build_client(ctx).put(
        "/api/settings/services/qbittorrent",
        json={"url": "http://qb:8080", "api_key": "qbt_key"},
    )
    assert resp.status_code == 200
    assert resp.json()["qbittorrent"] == {
        "url": "http://qb:8080",
        "api_key_set": True,
    }
    qbit.update_credentials.assert_called_once_with(
        base_url="http://qb:8080", api_key="qbt_key"
    )


def test_test_new_service_ok(db) -> None:
    sab = StubService()
    sab.test_connection = AsyncMock(
        return_value={"ok": True, "detail": "Connected to SABnzbd"}
    )
    ctx = make_ctx(db=db, sabnzbd=sab)
    body = build_client(ctx).post("/api/services/sabnzbd/test").json()
    assert body == {"ok": True, "detail": "Connected to SABnzbd"}
