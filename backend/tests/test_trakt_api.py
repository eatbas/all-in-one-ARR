"""Tests for core.trakt_api (settings, device auth, list management)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import trakt_api as trakt_api_mod
from core.settings_store import SettingsStore, TrackedList
from core.trakt_api import create_trakt_router
from tests.conftest import StubTrakt, make_ctx


def _store(tmp_path, *, client_id="cid", lists=None) -> SettingsStore:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(
        client_id=client_id,
        client_secret="secret" if client_id else "",
    )
    for item in (
        lists
        if lists is not None
        else [TrackedList(owner_user="me", slug="movies", name="Movies")]
    ):
        store.add_list(owner_user=item.owner_user, slug=item.slug, name=item.name)
    return store


def _client(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(create_trakt_router(ctx))
    return TestClient(app)


def _ctx(db, tmp_path, *, trakt=None, **store_kw):
    return make_ctx(
        db=db,
        trakt=trakt or StubTrakt(authenticated=False),
        settings_store=_store(tmp_path, **store_kw),
    )


def _activity_actions(ctx) -> list[str]:
    return [entry["action"] for entry in ctx.db.recent_activity()]


# ---- settings ----


def test_get_settings_masks_secrets(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    body = _client(ctx).get("/api/settings/trakt").json()
    assert body["client_id"] == "cid"
    assert body["client_id_hint"] == "cid"[-4:] or body["client_id_hint"] == "cid"
    assert body["client_id_set"] is True
    assert body["client_secret_set"] is True
    assert "client_secret" not in body
    assert body["connected"] is False
    assert body["lists"][0]["slug"] == "movies"


def test_get_settings_without_credentials(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path, client_id="")
    body = _client(ctx).get("/api/settings/trakt").json()
    assert body["client_id"] == ""
    assert body["client_id_hint"] == ""
    assert body["client_id_set"] is False


def test_put_settings_updates_store_and_client(db, tmp_path) -> None:
    trakt = StubTrakt(authenticated=False)
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).put(
        "/api/settings/trakt",
        json={"client_id": "newid1234", "client_secret": "newsec"},
    )
    assert resp.status_code == 200
    assert resp.json()["client_id"] == "newid1234"
    assert resp.json()["client_id_hint"] == "1234"
    assert ctx.settings_store.trakt_credentials() == ("newid1234", "newsec")
    trakt.update_credentials.assert_called_once_with(
        client_id="newid1234", client_secret="newsec"
    )
    assert "Trakt credentials updated" in _activity_actions(ctx)


def test_put_settings_without_change_does_not_record_activity(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    resp = _client(ctx).put("/api/settings/trakt", json={})
    assert resp.status_code == 200
    assert "Trakt credentials updated" not in _activity_actions(ctx)


# ---- device auth ----


def test_auth_start_requires_credentials(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path, client_id="")
    resp = _client(ctx).post("/api/trakt/auth/start")
    assert resp.status_code == 400


def test_auth_start_returns_code(db, tmp_path, monkeypatch) -> None:
    ctx = _ctx(db, tmp_path)

    async def fake_start(context):
        context.trakt_auth.state = "pending"
        context.trakt_auth.user_code = "XYZ-987"
        context.trakt_auth.verification_url = "https://trakt.tv/activate"
        context.trakt_auth.message = "Waiting"
        return context.trakt_auth

    monkeypatch.setattr(trakt_api_mod, "start_device_auth", fake_start)
    resp = _client(ctx).post("/api/trakt/auth/start")
    assert resp.status_code == 200
    assert resp.json()["user_code"] == "XYZ-987"
    assert "Trakt authorisation started" in _activity_actions(ctx)


def test_auth_start_handles_failure(db, tmp_path, monkeypatch) -> None:
    ctx = _ctx(db, tmp_path)
    monkeypatch.setattr(
        trakt_api_mod,
        "start_device_auth",
        AsyncMock(side_effect=RuntimeError("net down")),
    )
    resp = _client(ctx).post("/api/trakt/auth/start")
    assert resp.status_code == 502
    assert "Trakt authorisation failed" in _activity_actions(ctx)


def test_auth_status_reports_session(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    ctx.trakt_auth.state = "pending"
    ctx.trakt_auth.user_code = "ABCD"
    body = _client(ctx).get("/api/trakt/auth/status").json()
    assert body["state"] == "pending"
    assert body["user_code"] == "ABCD"
    assert body["connected"] is False


# ---- test connection ----


def test_test_connection_ok(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.test_connection = AsyncMock(
        return_value={"ok": True, "detail": "Connected as erena", "username": "erena"}
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    body = _client(ctx).post("/api/trakt/test").json()
    assert body == {"ok": True, "user": "erena", "message": "Connected as erena"}
    assert "Trakt connection test passed" in _activity_actions(ctx)


def test_test_connection_failure(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.test_connection = AsyncMock(
        return_value={"ok": False, "detail": "no token", "username": None}
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    body = _client(ctx).post("/api/trakt/test").json()
    assert body["ok"] is False
    assert "no token" in body["message"]
    assert "Trakt connection test failed" in _activity_actions(ctx)


# ---- list discovery ----


def test_get_lists_marks_selected(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_user_lists = AsyncMock(
        return_value=[
            {"name": "Movies", "slug": "movies", "owner_user": "me", "item_count": 19},
            {"name": "TV", "slug": "tv", "owner_user": "me", "item_count": 6},
        ]
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)  # only "movies" is tracked
    body = _client(ctx).get("/api/trakt/lists").json()
    selected = {entry["slug"]: entry["selected"] for entry in body}
    assert selected == {"movies": True, "tv": False}


def test_get_lists_handles_error(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_user_lists = AsyncMock(side_effect=RuntimeError("not authed"))
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).get("/api/trakt/lists")
    assert resp.status_code == 400


# ---- add / remove list ----


def test_add_list_by_url(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(
        return_value={"name": "Anime", "slug": "anime", "owner_user": "me", "item_count": 7}
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists", json={"url": "https://trakt.tv/users/me/lists/anime"}
    )
    assert resp.status_code == 200
    slugs = {entry["slug"] for entry in resp.json()["lists"]}
    assert "anime" in slugs
    assert "Trakt list added" in _activity_actions(ctx)


def test_add_list_by_owner_and_slug(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(
        return_value={"name": "TV", "slug": "tv", "owner_user": "me", "item_count": 6}
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists", json={"owner_user": "me", "slug": "tv"}
    )
    assert resp.status_code == 200
    assert {e["slug"] for e in resp.json()["lists"]} == {"movies", "tv"}


def test_add_list_invalid_url(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    resp = _client(ctx).post("/api/trakt/lists", json={"url": "https://example.com/x"})
    assert resp.status_code == 400


def test_add_list_missing_reference(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    resp = _client(ctx).post("/api/trakt/lists", json={})
    assert resp.status_code == 400


def test_add_list_validation_error(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(side_effect=RuntimeError("api down"))
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists", json={"url": "https://trakt.tv/users/me/lists/anime"}
    )
    assert resp.status_code == 400


def test_add_list_not_found(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(return_value=None)
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists", json={"url": "https://trakt.tv/users/me/lists/ghost"}
    )
    assert resp.status_code == 404
    assert "me/ghost" in resp.json()["detail"]


def test_add_official_list_by_url(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(
        return_value={
            "name": "The Matrix Collection",
            "slug": "the-matrix-collection",
            "owner_user": "official",
            "item_count": 42,
        }
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists",
        json={"url": "https://app.trakt.tv/lists/official/the-matrix-collection"},
    )
    assert resp.status_code == 200
    trakt.get_list_summary.assert_awaited_once_with(
        owner_user="official", slug="the-matrix-collection"
    )
    slugs = {entry["slug"] for entry in resp.json()["lists"]}
    assert "the-matrix-collection" in slugs


def test_add_user_list_app_subdomain_by_url(db, tmp_path) -> None:
    trakt = StubTrakt()
    trakt.get_list_summary = AsyncMock(
        return_value={
            "name": "Matrix",
            "slug": "matrix",
            "owner_user": "josephg5",
            "item_count": 12,
        }
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists",
        json={"url": "https://app.trakt.tv/users/josephg5/lists/matrix"},
    )
    assert resp.status_code == 200
    trakt.get_list_summary.assert_awaited_once_with(
        owner_user="josephg5", slug="matrix"
    )
    slugs = {entry["slug"] for entry in resp.json()["lists"]}
    assert "matrix" in slugs


def test_add_list_http_error_includes_status(db, tmp_path) -> None:
    trakt = StubTrakt()
    response = httpx.Response(403, text="private list")
    trakt.get_list_summary = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "forbidden", request=httpx.Request("GET", "test"), response=response
        )
    )
    ctx = _ctx(db, tmp_path, trakt=trakt)
    resp = _client(ctx).post(
        "/api/trakt/lists", json={"url": "https://trakt.tv/users/me/lists/private"}
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "me/private" in detail
    assert "HTTP 403" in detail
    assert "private list" in detail


def test_remove_list(db, tmp_path) -> None:
    ctx = _ctx(db, tmp_path)
    resp = _client(ctx).delete("/api/trakt/lists/me/movies")
    assert resp.status_code == 200
    assert resp.json()["lists"] == []
    assert "Trakt list removed" in _activity_actions(ctx)
