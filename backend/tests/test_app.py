"""Tests for core.app (factory, lifespan, static serving, device auth)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from core import app as app_mod
from core.app import (
    _maybe_start_device_auth,
    _mount_frontend,
    _start_poster_churn,
    build_context,
    create_app,
)
from core.config import Settings
from core.db import Database
from tests.conftest import StubSeer, StubSettingsStore, StubTrakt, make_ctx

_SECRETS = {
    "TRAKT_CLIENT_ID": "cid",
    "TRAKT_CLIENT_SECRET": "secret",
    "SEER_URL": "http://js:5055",
    "SEER_API_KEY": "key",
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
        seer=StubSeer(),
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
            ctx.seer,
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
        # Prometheus metrics are mounted before the SPA catch-all.
        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "bw_qbit_active_count" in metrics.text
        assert "bw_sab_active_count" in metrics.text
        assert "bw_check_status" in metrics.text
        # Bandwidth router is reachable through the assembled app.
        assert client.get("/api/bandwidth/status").status_code == 200
        # Placeholder served at root.
        assert "All-in-One ARR" in client.get("/").text

    ctx.scheduler.stop.assert_awaited()
    ctx.trakt.aclose.assert_awaited()
    ctx.seer.aclose.assert_awaited()
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
        assert "built spa" in client.get("/findarr").text
        # The Trending page's SPA route is served so a hard refresh on /trending works.
        assert "built spa" in client.get("/trending").text
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


async def test_start_poster_churn_schedules_interval(db) -> None:
    ctx = make_ctx(db=db)
    poster_cache = MagicMock()
    poster_cache.evict = MagicMock(return_value=None)
    ctx.poster_cache = poster_cache
    settings = Settings(
        _env_file=None,
        POSTER_CACHE_TTL_DAYS=10,
        POSTER_CACHE_MAX_MB=2,
        POSTER_CACHE_CHURN_INTERVAL_MIN=90,
        **_SECRETS,
    )
    await _start_poster_churn(ctx, settings)

    ctx.scheduler.add_interval.assert_awaited_once()
    call = ctx.scheduler.add_interval.await_args
    assert call.kwargs["id"] == "poster_cache_churn"
    assert call.kwargs["minutes"] == 90
    # The registered coroutine evicts with the settings-derived bounds (TTL in
    # days → seconds, cap in MB → bytes).
    job = call.args[0]
    await job()
    poster_cache.evict.assert_called_once_with(
        max_age_seconds=10 * 86_400, max_total_bytes=2 * 1024 * 1024
    )


async def test_start_poster_churn_skips_without_cache(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = None
    settings = Settings(_env_file=None, **_SECRETS)
    await _start_poster_churn(ctx, settings)
    ctx.scheduler.add_interval.assert_not_awaited()


async def test_start_poster_churn_warns_on_low_ttl(db, monkeypatch) -> None:
    # A TTL within the 7-day browser poster cache risks evicting actively-viewed
    # posters, so start-up warns — but still schedules the job.
    ctx = make_ctx(db=db)
    ctx.poster_cache = MagicMock()
    monkeypatch.setattr(app_mod, "_log", MagicMock())
    settings = Settings(_env_file=None, POSTER_CACHE_TTL_DAYS=3, **_SECRETS)
    await _start_poster_churn(ctx, settings)
    app_mod._log.warning.assert_called_once()
    ctx.scheduler.add_interval.assert_awaited_once()


def test_mount_frontend_present(tmp_path, monkeypatch) -> None:
    from fastapi import FastAPI

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("x")
    monkeypatch.setattr(app_mod, "FRONTEND_DIST", dist)
    app = FastAPI()
    _mount_frontend(app)
    assert any(getattr(r, "name", "") == "spa" for r in app.routes)
