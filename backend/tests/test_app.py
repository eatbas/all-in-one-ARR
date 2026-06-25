"""Tests for core.app (factory, lifespan, static serving, device auth)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core import app as app_mod
from core.app import (
    _maybe_start_device_auth,
    _mount_frontend,
    build_context,
    create_app,
)
from core.config import Settings
from core.db import Database
from tests.conftest import StubJellyseerr, StubSettingsStore, StubTrakt, make_ctx

_SECRETS = {
    "TRAKT_CLIENT_ID": "cid",
    "TRAKT_CLIENT_SECRET": "secret",
    "JELLYSEERR_URL": "http://js:5055",
    "JELLYSEERR_API_KEY": "key",
}


@pytest.fixture
def _env(monkeypatch):
    for key, value in _SECRETS.items():
        monkeypatch.setenv(key, value)


def _stub_ctx(authenticated: bool) -> object:
    database = Database(":memory:")
    database.init_db()
    return make_ctx(
        db=database,
        trakt=StubTrakt(authenticated=authenticated),
        jellyseerr=StubJellyseerr(),
    )


async def test_build_context_real(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        DB_PATH=str(tmp_path / "db.sqlite"),
        TOKEN_STORE_PATH=str(tmp_path / "tok.json"),
        SETTINGS_STORE_PATH=str(tmp_path / "settings.json"),
        **_SECRETS,
    )
    ctx = build_context(settings)
    try:
        assert ctx.trakt.is_authenticated() is False  # no token file
        assert ctx.db.counts_by_status()["synced"] == 0
        # Lists are not seeded from the environment; they start empty and are
        # chosen from the dashboard.
        assert ctx.settings_store.tracked_lists() == []
        # The new connection-test clients are constructed alongside the existing ones.
        assert ctx.tmdb is not None
        assert ctx.omdb is not None
        assert ctx.sabnzbd is not None
        assert ctx.qbittorrent is not None
        # The poster cache is wired from the TMDB/OMDb clients.
        assert ctx.poster_cache is not None
    finally:
        # Release every resource the real context opened (clients + DB).
        for client in (
            ctx.trakt,
            ctx.jellyseerr,
            ctx.sonarr,
            ctx.radarr,
            ctx.tmdb,
            ctx.omdb,
            ctx.sabnzbd,
            ctx.qbittorrent,
        ):
            await client.aclose()
        ctx.db.close()


def test_lifespan_authenticated_placeholder_frontend(_env, monkeypatch, tmp_path) -> None:
    ctx = _stub_ctx(authenticated=True)
    monkeypatch.setattr(app_mod, "build_context", lambda settings: ctx)
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", tmp_path / "missing")

    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/status").json()["synced"] == 0
        assert client.get("/api/status").status_code == 200
        # Placeholder served at root.
        assert "All-in-One ARR" in client.get("/").text

    ctx.scheduler.stop.assert_awaited()
    ctx.trakt.aclose.assert_awaited()
    ctx.jellyseerr.aclose.assert_awaited()
    ctx.tmdb.aclose.assert_awaited()
    ctx.omdb.aclose.assert_awaited()
    ctx.sabnzbd.aclose.assert_awaited()
    ctx.qbittorrent.aclose.assert_awaited()


def test_lifespan_serves_built_frontend(_env, monkeypatch, tmp_path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>built spa</html>")

    ctx = _stub_ctx(authenticated=True)
    monkeypatch.setattr(app_mod, "build_context", lambda settings: ctx)
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", dist)

    with TestClient(create_app()) as client:
        assert "built spa" in client.get("/").text
        assert client.get("/api/status").status_code == 200


def test_lifespan_unauthenticated_spawns_device_auth(_env, monkeypatch, tmp_path) -> None:
    ctx = _stub_ctx(authenticated=False)
    monkeypatch.setattr(app_mod, "build_context", lambda settings: ctx)
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", tmp_path / "missing")

    spawned = {"called": False}

    async def fake_auth(_ctx):
        spawned["called"] = True

    monkeypatch.setattr(app_mod, "_maybe_start_device_auth", fake_auth)

    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200

    assert spawned["called"] is True


async def test_maybe_start_device_auth_starts_when_unauthenticated(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=False))
    started = AsyncMock()
    monkeypatch.setattr(app_mod, "start_device_auth", started)
    await _maybe_start_device_auth(ctx)
    started.assert_awaited_once_with(ctx)


async def test_maybe_start_device_auth_skips_when_authenticated(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=True))
    started = AsyncMock()
    monkeypatch.setattr(app_mod, "start_device_auth", started)
    await _maybe_start_device_auth(ctx)
    started.assert_not_awaited()


async def test_maybe_start_device_auth_skips_without_credentials(db, monkeypatch) -> None:
    ctx = make_ctx(
        db=db,
        trakt=StubTrakt(authenticated=False),
        settings_store=StubSettingsStore(client_id=""),
    )
    started = AsyncMock()
    monkeypatch.setattr(app_mod, "start_device_auth", started)
    await _maybe_start_device_auth(ctx)
    started.assert_not_awaited()


async def test_maybe_start_device_auth_swallows_errors(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=False))
    monkeypatch.setattr(
        app_mod, "start_device_auth", AsyncMock(side_effect=RuntimeError("net down"))
    )
    await _maybe_start_device_auth(ctx)  # caught, does not raise


def test_mount_frontend_present(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("x")
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", dist)
    app = FastAPI()
    _mount_frontend(app)
    assert any(getattr(r, "name", "") == "spa" for r in app.routes)
