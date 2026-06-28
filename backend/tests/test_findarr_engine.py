"""Tests for Findarr run logic."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from core.db import Database
from modules.findarr import engine, findarr_job, register_context, setup
from modules.findarr.client import FindarrClientError
from modules.findarr.models import FindarrItem
from modules.findarr.models import Compatibility
from tests.conftest import StubSettingsStore, make_ctx


@dataclass
class StubFindarrClient:
    app: str
    compatible: bool = True
    queue_size_value: int = 0
    command_error: Exception | None = None

    async def compatibility(self) -> Compatibility:
        return Compatibility(
            ok=self.compatible,
            app_name=self.app.capitalize(),
            version="4.0.0" if self.app == "sonarr" else "6.0.0",
            detail="ok" if self.compatible else "unsupported",
        )

    async def queue_size(self) -> int:
        return self.queue_size_value

    async def wanted(self, kind: str) -> list[dict]:
        if self.app == "sonarr":
            return [
                {
                    "id": 10 if kind == "missing" else 11,
                    "title": "Pilot",
                    "seasonNumber": 1,
                    "episodeNumber": 1,
                    "airDateUtc": "2020-01-01T00:00:00Z",
                    "monitored": True,
                    "series": {"title": "Series", "monitored": True},
                },
                {
                    "id": 12,
                    "title": "Future",
                    "seasonNumber": 1,
                    "episodeNumber": 2,
                    "airDateUtc": "2999-01-01T00:00:00Z",
                    "monitored": True,
                    "series": {"title": "Series", "monitored": True},
                },
            ]
        return [
            {
                "id": 20 if kind == "missing" else 21,
                "title": "Movie",
                "year": 2024,
                "monitored": True,
                "digitalRelease": "2020-01-01T00:00:00Z",
            }
        ]

    async def trigger_search(self, *, item_id: str) -> None:
        if self.command_error is not None:
            raise self.command_error

    async def aclose(self) -> None:
        pass


def _enabled_store(**overrides) -> StubSettingsStore:
    store = StubSettingsStore()
    settings = store.findarr_settings()
    settings["enabled"] = True
    settings.update(overrides)
    store.update_findarr_settings(settings)
    return store


async def test_status_contains_settings_and_counts(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_mark_processed(app="sonarr", mode="missing", item_id="1", title="One")
    body = await engine.status(ctx)
    assert body["settings"]["enabled"] is True
    assert body["apps"]["sonarr"]["processed"]["missing"] == 1
    assert body["running"] is False


async def test_run_skips_when_disabled(db) -> None:
    ctx = make_ctx(db=db)
    result = await engine.run(ctx)
    assert result["status"] == "skipped"
    assert db.findarr_run_state()["last_run_status"] == "skipped"


async def test_module_setup_registers_callbacks_and_job(db) -> None:
    database = Database(":memory:")
    ctx = make_ctx(db=database)
    ctx.db.init_db()
    try:
        await setup(ctx.scheduler, FastAPI(), ctx)
        ctx.scheduler.add_interval.assert_awaited()
        assert ctx.findarr_status is not None
        register_context(ctx)
        await findarr_job()
    finally:
        ctx.db.close()


async def test_run_rejects_unknown_app(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    result = await engine.run(ctx, app="lidarr")
    assert result["status"] == "error"


async def test_run_processes_missing_and_upgrades(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(hourly_cap=10))
    clients = {
        "sonarr": StubFindarrClient("sonarr"),
        "radarr": StubFindarrClient("radarr"),
    }
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: clients[app])
    result = await engine.run(ctx, manual=True)
    assert result["status"] == "completed"
    assert result["processed"] == 4
    assert db.findarr_counts()["sonarr"]["missing"] == 1
    assert db.findarr_counts()["radarr"]["upgrade"] == 1
    assert any(row["status"] == "success" for row in db.findarr_recent_history())
    assert any(row["action"] == "Findarr run completed" for row in db.recent_activity())


async def test_run_handles_disabled_app_and_command_error(db, monkeypatch) -> None:
    store = _enabled_store(hourly_cap=10)
    settings = store.findarr_settings()
    settings["apps"]["radarr"]["enabled"] = False
    store.update_findarr_settings(settings)
    ctx = make_ctx(db=db, settings_store=store)
    monkeypatch.setattr(
        engine,
        "_client_for",
        lambda _ctx, app: StubFindarrClient(app, command_error=FindarrClientError("boom")),
    )
    result = await engine.run(ctx)
    assert result["processed"] == 0
    assert db.findarr_run_state()["radarr_detail"] == "Disabled"
    assert db.findarr_recent_history()[0]["status"] == "error"


async def test_run_mode_returns_when_capacity_is_zero(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(hourly_cap=0))
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: StubFindarrClient(app))
    result = await engine.run(ctx, app="sonarr")
    assert result["results"][0]["detail"] == "No remaining Findarr capacity"


async def test_run_blocks_unsupported_and_queue_full(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(queue_limit=1))
    clients = {
        "sonarr": StubFindarrClient("sonarr", compatible=False),
        "radarr": StubFindarrClient("radarr", queue_size_value=1),
    }
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: clients[app])
    result = await engine.run(ctx)
    assert result["processed"] == 0
    history = db.findarr_recent_history()
    assert {row["status"] for row in history} == {"error", "skipped"}


async def test_run_records_connection_error_and_queue_limit_passes(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(queue_limit=10))

    class ErrorClient(StubFindarrClient):
        async def compatibility(self) -> Compatibility:
            raise FindarrClientError("network down")

    clients = {
        "sonarr": ErrorClient("sonarr"),
        "radarr": StubFindarrClient("radarr", queue_size_value=1),
    }
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: clients[app])
    result = await engine.run(ctx)
    assert result["processed"] == 2
    assert db.findarr_run_state()["sonarr_compatible"] == "false"
    assert any(row["detail"] == "network down" for row in db.findarr_recent_history())


async def test_reset_state_clears_processed(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_mark_processed(app="radarr", mode="missing", item_id="7", title="Seven")
    result = await engine.reset_state(ctx)
    assert result == {"status": "reset", "removed": 1}
    assert db.findarr_counts()["radarr"]["missing"] == 0


async def test_history_returns_recent_rows(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_add_history(app="sonarr", mode="missing", item_id="1", title="One", status="success", detail="done")
    rows = await engine.history(ctx)
    assert rows[0]["title"] == "One"


def test_item_allowed_filters_monitored_future_and_processed(db) -> None:
    database = Database(":memory:")
    ctx = make_ctx(db=database)
    ctx.db.init_db()
    try:
        base = FindarrItem(app="sonarr", mode="missing", item_id="1", title="One", monitored=True, is_future=False)
        assert engine._item_allowed(ctx, base, monitored_only=True, skip_future=True) is True
        assert engine._item_allowed(
            ctx,
            FindarrItem(app="sonarr", mode="missing", item_id="2", title="Two", monitored=False, is_future=False),
            monitored_only=True,
            skip_future=True,
        ) is False
        assert engine._item_allowed(
            ctx,
            FindarrItem(app="sonarr", mode="missing", item_id="3", title="Three", monitored=True, is_future=True),
            monitored_only=True,
            skip_future=True,
        ) is False
        ctx.db.findarr_mark_processed(app="sonarr", mode="missing", item_id="1", title="One")
        assert engine._item_allowed(ctx, base, monitored_only=False, skip_future=False) is False
    finally:
        ctx.db.close()


def test_client_for_uses_context_connection_fields(db) -> None:
    database = Database(":memory:")
    ctx = make_ctx(db=database)
    try:
        client = engine._client_for(ctx, "sonarr")
        assert client.base_url == "http://arr"
        assert client.api_key == "key"
    finally:
        database.close()


def test_normalise_items_skips_invalid_records() -> None:
    assert engine._normalise_items("sonarr", "missing", [{}]) == []
