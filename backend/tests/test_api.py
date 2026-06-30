"""Tests for core.api (dashboard JSON endpoints)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api import _SYNC_TASKS, _remember_task, create_api_router
from tests.conftest import StubSettingsStore, StubTrakt, make_ctx

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
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=True))
    body = build_client(ctx).get("/api/status").json()
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


def test_items_endpoint_filtered_by_list(db) -> None:
    db.upsert_item(**_ITEM)
    db.upsert_item(**{**_ITEM, "trakt_id": 2, "list_id": "other"})
    ctx = make_ctx(db=db)
    client = build_client(ctx)
    assert len(client.get("/api/items?list=watchlist").json()) == 1
    assert len(client.get("/api/items?list=other").json()) == 1
    assert len(client.get("/api/items").json()) == 2


def test_lists_endpoint_with_counts_and_times(db) -> None:
    db.upsert_item(**_ITEM)  # list_id="watchlist"
    # A second item, removed, so the active/removed split is exercised.
    db.upsert_item(**{**_ITEM, "trakt_id": 2})
    db.set_status(trakt_id=2, list_id="watchlist", status="removed")
    db.touch_list_synced("watchlist")
    ctx = make_ctx(db=db)  # StubSettingsStore tracks the "watchlist" list
    body = build_client(ctx).get("/api/lists").json()
    assert len(body) == 1
    entry = body[0]
    assert entry["slug"] == "watchlist"
    assert entry["item_count"] == 2
    assert entry["removed_count"] == 1  # active = item_count - removed_count = 1
    assert entry["interval_minutes"] == 15
    assert entry["last_synced_at"] is not None
    assert entry["next_sync_at"] is not None


def test_lists_endpoint_never_synced_has_no_times(db) -> None:
    ctx = make_ctx(db=db)
    entry = build_client(ctx).get("/api/lists").json()[0]
    assert entry["item_count"] == 0
    assert entry["removed_count"] == 0
    assert entry["last_synced_at"] is None
    assert entry["next_sync_at"] is None


def test_poster_endpoint_serves_cached_file(db, tmp_path) -> None:
    poster = tmp_path / "movie-100.jpg"
    poster.write_bytes(b"JPEGDATA")
    ctx = make_ctx(db=db)
    ctx.poster_cache = AsyncMock()
    ctx.poster_cache.get_poster = AsyncMock(return_value=poster)
    resp = build_client(ctx).get("/api/posters/movie/100")
    assert resp.status_code == 200
    assert resp.content == b"JPEGDATA"
    assert resp.headers["cache-control"] == "public, max-age=604800"
    ctx.poster_cache.get_poster.assert_awaited_once_with(
        media_type="movie", tmdb_id=100, imdb_id=None
    )


def test_poster_endpoint_404_when_missing(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = AsyncMock()
    ctx.poster_cache.get_poster = AsyncMock(return_value=None)
    resp = build_client(ctx).get("/api/posters/show/100?imdb=tt9")
    assert resp.status_code == 404
    ctx.poster_cache.get_poster.assert_awaited_once_with(
        media_type="show", tmdb_id=100, imdb_id="tt9"
    )


def test_poster_endpoint_404_for_bad_media_type(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = AsyncMock()
    resp = build_client(ctx).get("/api/posters/bogus/100")
    assert resp.status_code == 404
    ctx.poster_cache.get_poster.assert_not_called()


def test_poster_endpoint_404_when_cache_unset(db) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = None
    assert build_client(ctx).get("/api/posters/movie/100").status_code == 404


def test_activity_endpoint(db) -> None:
    db.add_activity("requested", "requested Dune")
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/activity").json()
    assert body[0]["detail"] == "requested Dune"


def test_sync_endpoint_awaits_handler_and_returns_completed(db) -> None:
    ctx = make_ctx(db=db)
    ctx.sync_now = AsyncMock()
    resp = build_client(ctx).post("/api/sync")
    assert resp.status_code == 200
    assert resp.json() == {"status": "completed"}
    ctx.sync_now.assert_awaited()
    assert any(a["action"] == "Sync completed" for a in db.recent_activity())


def test_sync_endpoint_without_handler_returns_503(db) -> None:
    ctx = make_ctx(db=db)
    ctx.sync_now = None
    resp = build_client(ctx).post("/api/sync")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "sync unavailable"}


async def test_sync_endpoint_returns_409_while_sync_already_running(db) -> None:
    ctx = make_ctx(db=db)
    ctx.sync_now = AsyncMock()
    # Hold the gate's internal lock so the endpoint sees an in-progress sync.
    await ctx.sync_gate._get_lock().acquire()
    try:
        resp = build_client(ctx).post("/api/sync")
        assert resp.status_code == 409
        assert resp.json() == {"detail": "sync already running"}
        ctx.sync_now.assert_not_awaited()
        assert any(
            a["action"] == "Sync already running" for a in db.recent_activity()
        )
    finally:
        ctx.sync_gate._get_lock().release()


async def test_sync_endpoint_rejects_concurrent_manual_requests(db) -> None:
    """Two overlapping manual sync requests must produce one 200 and one 409."""
    from httpx import ASGITransport, AsyncClient

    ctx = make_ctx(db=db)
    app = FastAPI()
    app.include_router(create_api_router(ctx))

    entered = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_sync() -> None:
        entered.set()
        await proceed.wait()

    ctx.sync_now = slow_sync

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client1, \
            AsyncClient(transport=transport, base_url="http://test") as client2:
        first = asyncio.create_task(client1.post("/api/sync"))
        await asyncio.wait_for(entered.wait(), timeout=2)

        second = await asyncio.wait_for(client2.post("/api/sync"), timeout=2)
        assert second.status_code == 409
        assert second.json() == {"detail": "sync already running"}

        proceed.set()
        first_resp = await asyncio.wait_for(first, timeout=2)
        assert first_resp.status_code == 200
        assert first_resp.json() == {"status": "completed"}


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
    assert "seer" in body["services"]


def test_services_check_endpoint_triggers_check(db) -> None:
    ctx = make_ctx(db=db)
    ctx.status_checker.check_now = AsyncMock(
        return_value=ctx.status_checker.get_statuses()
    )
    body = build_client(ctx).post("/api/status/services/check").json()
    assert "interval_seconds" in body
    ctx.status_checker.check_now.assert_awaited_once()
    assert any(
        a["action"] == "Integration status check completed"
        for a in db.recent_activity()
    )


def test_put_general_settings_updates_status_interval(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put("/api/settings/general", json={"interval_seconds": 30})
    assert resp.status_code == 200
    assert resp.json() == {
        "interval_seconds": 30,
        "sync_interval_minutes": 15,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": True,
    }
    assert ctx.settings_store.status_check_interval_seconds() == 30
    assert any(
        a["action"] == "Status interval updated" for a in db.recent_activity()
    )


def test_put_general_settings_rejects_invalid_status_interval(db) -> None:
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put("/api/settings/general", json={"interval_seconds": 99})
    assert resp.status_code == 200
    assert resp.json() == {
        "interval_seconds": 60,
        "sync_interval_minutes": 15,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": True,
    }


def test_put_general_settings_updates_sync_interval_and_reschedules(db) -> None:
    ctx = make_ctx(db=db)
    ctx.reschedule_sync = AsyncMock()
    resp = build_client(ctx).put(
        "/api/settings/general", json={"sync_interval_minutes": 30}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "interval_seconds": 60,
        "sync_interval_minutes": 30,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": True,
    }
    assert ctx.settings_store.sync_interval_minutes() == 30
    ctx.reschedule_sync.assert_awaited_once_with(30)
    assert any(
        a["action"] == "Sync interval updated" for a in db.recent_activity()
    )


def test_put_general_settings_rejects_invalid_sync_interval(db) -> None:
    # No reschedule handler registered: the invalid value falls back to 15 and the
    # missing handler is tolerated.
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put(
        "/api/settings/general", json={"sync_interval_minutes": 7}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "interval_seconds": 60,
        "sync_interval_minutes": 15,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": True,
    }


def test_get_general_settings_returns_both_intervals(db) -> None:
    ctx = make_ctx(db=db)
    ctx.settings_store.update_status_check_interval(45)
    ctx.settings_store.update_sync_interval(60)
    body = build_client(ctx).get("/api/settings/general").json()
    assert body == {
        "interval_seconds": 45,
        "sync_interval_minutes": 60,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": True,
    }


def test_put_general_settings_updates_trending_interval_and_reschedules(db) -> None:
    ctx = make_ctx(db=db)
    ctx.reschedule_trending = AsyncMock()
    resp = build_client(ctx).put(
        "/api/settings/general", json={"trending_sync_interval_minutes": 120}
    )
    assert resp.status_code == 200
    assert resp.json()["trending_sync_interval_minutes"] == 120
    assert ctx.settings_store.trending_sync_interval_minutes() == 120
    ctx.reschedule_trending.assert_awaited_once_with(120)
    assert any(
        a["action"] == "Trending sync interval updated" for a in db.recent_activity()
    )


def test_put_general_settings_rejects_invalid_trending_interval(db) -> None:
    # No reschedule handler registered: the invalid value falls back to 60 and the
    # missing handler is tolerated.
    ctx = make_ctx(db=db)
    resp = build_client(ctx).put(
        "/api/settings/general", json={"trending_sync_interval_minutes": 7}
    )
    assert resp.status_code == 200
    assert resp.json()["trending_sync_interval_minutes"] == 60
    assert ctx.settings_store.trending_sync_interval_minutes() == 60


def test_put_general_settings_toggles_auto_remove_when_available(db) -> None:
    ctx = make_ctx(db=db)  # StubSettingsStore defaults auto-remove to True
    resp = build_client(ctx).put(
        "/api/settings/general", json={"auto_remove_when_available": False}
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "interval_seconds": 60,
        "sync_interval_minutes": 15,
        "trending_sync_interval_minutes": 60,
        "auto_remove_when_available": False,
    }
    assert ctx.settings_store.auto_remove_when_available() is False
    assert any(
        a["action"] == "Auto-remove when available disabled"
        for a in db.recent_activity()
    )


def test_put_general_settings_enables_auto_remove_when_available(db) -> None:
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    resp = build_client(ctx).put(
        "/api/settings/general", json={"auto_remove_when_available": True}
    )
    assert resp.status_code == 200
    assert resp.json()["auto_remove_when_available"] is True
    assert ctx.settings_store.auto_remove_when_available() is True
    assert any(
        a["action"] == "Auto-remove when available enabled"
        for a in db.recent_activity()
    )


def test_put_general_settings_no_activity_when_auto_remove_unchanged(db) -> None:
    ctx = make_ctx(
        db=db,
        settings_store=StubSettingsStore(auto_remove_when_available=False),
    )
    resp = build_client(ctx).put(
        "/api/settings/general", json={"auto_remove_when_available": False}
    )
    assert resp.status_code == 200
    assert resp.json()["auto_remove_when_available"] is False
    assert not any(
        "Auto-remove when available" in a["action"] for a in db.recent_activity()
    )


def test_remove_available_endpoint_triggers_handler(db) -> None:
    ctx = make_ctx(db=db)
    ctx.remove_available = AsyncMock()
    resp = build_client(ctx).post("/api/items/remove-available")
    assert resp.status_code == 202
    assert resp.json() == {"status": "triggered"}
    ctx.remove_available.assert_awaited()
    assert any(
        a["action"] == "Remove available items triggered"
        for a in db.recent_activity()
    )


def test_remove_available_endpoint_without_handler(db) -> None:
    ctx = make_ctx(db=db)  # ctx.remove_available defaults to None
    resp = build_client(ctx).post("/api/items/remove-available")
    assert resp.status_code == 202


def test_delete_item_endpoint_removes_item(db) -> None:
    ctx = make_ctx(db=db)
    ctx.remove_item = AsyncMock(return_value=True)
    resp = build_client(ctx).delete("/api/items/watchlist/1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "removed"}
    ctx.remove_item.assert_awaited_once_with("watchlist", 1)


def test_delete_item_endpoint_404_when_absent(db) -> None:
    ctx = make_ctx(db=db)
    ctx.remove_item = AsyncMock(return_value=False)
    resp = build_client(ctx).delete("/api/items/watchlist/999")
    assert resp.status_code == 404


def test_delete_item_endpoint_503_without_handler(db) -> None:
    ctx = make_ctx(db=db)  # ctx.remove_item defaults to None
    resp = build_client(ctx).delete("/api/items/watchlist/1")
    assert resp.status_code == 503


def test_get_database_settings_returns_counts_and_sizes(db: Database) -> None:
    db.upsert_item(**_ITEM)
    db.add_activity("sync", "synced")
    db.touch_list_synced("watchlist")
    ctx = make_ctx(db=db)
    body = build_client(ctx).get("/api/settings/database").json()
    assert body["item_count"] == 1
    assert body["activity_count"] == 1
    assert body["list_state_count"] == 1
    assert body["db_size_bytes"] == 0  # :memory: fixture
    assert body["poster_cache_bytes"] == 0  # no poster cache configured


def test_clear_activity_endpoint_empties_log_and_records_audit(db: Database) -> None:
    db.add_activity("one", "first")
    db.add_activity("two", "second")
    ctx = make_ctx(db=db)
    resp = build_client(ctx).post("/api/settings/database/clear-activity")
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_count"] == 1  # the audit entry written after clearing
    assert body["item_count"] == 0
    activity = db.recent_activity(limit=10)
    assert [a["action"] for a in activity] == ["Activity log cleared"]


def test_clear_items_endpoint_deletes_items_and_state(db: Database) -> None:
    db.upsert_item(**_ITEM)
    db.touch_list_synced("watchlist")
    ctx = make_ctx(db=db)
    resp = build_client(ctx).post("/api/settings/database/clear-items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item_count"] == 0
    assert body["list_state_count"] == 0
    assert body["activity_count"] == 1
    activity = db.recent_activity(limit=10)
    assert [a["action"] for a in activity] == ["Synced items cleared"]


def test_clear_posters_endpoint_no_op_when_cache_unset(db: Database) -> None:
    ctx = make_ctx(db=db)
    ctx.poster_cache = None
    resp = build_client(ctx).post("/api/settings/database/clear-posters")
    assert resp.status_code == 200
    assert resp.json()["poster_cache_bytes"] == 0
    assert not any(a["action"] == "Poster cache cleared" for a in db.recent_activity())


def test_clear_posters_endpoint_clears_cache_and_records_audit(db, tmp_path) -> None:
    from core.posters import PosterCache

    cache_dir = tmp_path / "posters"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "movie-1.jpg").write_bytes(b"img")

    tmdb = AsyncMock()
    omdb = AsyncMock()
    poster_cache = PosterCache(cache_dir=str(cache_dir), tmdb=tmdb, omdb=omdb)

    ctx = make_ctx(db=db)
    ctx.poster_cache = poster_cache
    resp = build_client(ctx).post("/api/settings/database/clear-posters")
    assert resp.status_code == 200
    body = resp.json()
    assert body["poster_cache_bytes"] == 0
    assert any(a["action"] == "Poster cache cleared" for a in db.recent_activity())
    assert list(cache_dir.glob("*.jpg")) == []
