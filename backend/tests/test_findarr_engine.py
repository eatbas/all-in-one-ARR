"""Tests for Findarr run logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI

from core.db import Database
from modules.findarr import engine, findarr_job, register_context, setup
from modules.findarr.client import FindarrClientError
from modules.findarr.models import Compatibility, SearchUnit
from tests.conftest import StubSettingsStore, make_ctx


@dataclass
class StubFindarrClient:
    app: str
    compatible: bool = True
    queue_size_value: int = 0
    command_error: Exception | None = None
    sonarr_records: list[dict] | None = None
    triggered: list = field(default_factory=list)

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
            if self.sonarr_records is not None:
                return list(self.sonarr_records)
            return [
                {
                    "id": 10 if kind == "missing" else 11,
                    "title": "Pilot",
                    "seriesId": 5,
                    "seasonNumber": 1,
                    "episodeNumber": 1,
                    "airDateUtc": "2020-01-01T00:00:00Z",
                    "monitored": True,
                    "series": {"id": 5, "title": "Series", "monitored": True},
                },
                {
                    "id": 12,
                    "title": "Future",
                    "seriesId": 5,
                    "seasonNumber": 1,
                    "episodeNumber": 2,
                    "airDateUtc": "2999-01-01T00:00:00Z",
                    "monitored": True,
                    "series": {"id": 5, "title": "Series", "monitored": True},
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

    async def trigger_search(self, unit: SearchUnit) -> None:
        self.triggered.append(unit)
        if self.command_error is not None:
            raise self.command_error

    async def aclose(self) -> None:
        pass


def _sonarr_record(
    episode_id: int, *, series_id: int, season: int, episode: int, future: bool = False
) -> dict:
    air = "2999-01-01T00:00:00Z" if future else "2020-01-01T00:00:00Z"
    return {
        "id": episode_id,
        "title": f"E{episode}",
        "seriesId": series_id,
        "seasonNumber": season,
        "episodeNumber": episode,
        "airDateUtc": air,
        "monitored": True,
        "series": {"id": series_id, "title": "Show", "monitored": True},
    }


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
    db.findarr_increment_total(app="sonarr", mode="missing")
    body = await engine.status(ctx)
    assert body["settings"]["enabled"] is True
    assert body["apps"]["sonarr"]["processed"]["missing"] == 1
    # Lifetime tally, last-run wanted telemetry and the activity line back the
    # honest Status UI; they default cleanly before the first run.
    assert body["apps"]["sonarr"]["lifetime"]["missing"] == 1
    assert body["apps"]["sonarr"]["wanted"] == {"missing": 0, "upgrade": 0}
    assert body["apps"]["sonarr"]["activity"] == "Not run yet"
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
    # Each successful trigger bumps the reset-proof all-time tally.
    assert db.findarr_totals()["sonarr"]["missing"] == 1
    assert db.findarr_totals()["radarr"]["upgrade"] == 1
    assert db.findarr_run_state()["sonarr_activity"].startswith("Searched")
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
        lambda _ctx, app: StubFindarrClient(
            app, command_error=FindarrClientError("boom")
        ),
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
    assert db.findarr_run_state()["sonarr_activity"] == "Throttled — hourly cap reached"


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


async def test_run_records_connection_error_and_queue_limit_passes(
    db, monkeypatch
) -> None:
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
    assert db.findarr_run_state()["sonarr_activity"].startswith("Connection error")
    assert any(row["detail"] == "network down" for row in db.findarr_recent_history())


async def test_reset_state_clears_processed_and_restarts_window(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_mark_processed(app="radarr", mode="missing", item_id="7", title="Seven")
    result = await engine.reset_state(ctx)
    assert result == {"status": "reset", "removed": 1}
    assert db.findarr_counts()["radarr"]["missing"] == 0
    assert "state_created_at" in db.findarr_run_state()


async def test_history_returns_recent_rows(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id="1",
        title="One",
        status="success",
        detail="done",
    )
    rows = await engine.history(ctx)
    assert rows[0]["title"] == "One"


async def test_clear_history_empties_log_and_records_audit(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_mark_processed(app="radarr", mode="missing", item_id="7", title="Seven")
    db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id="1",
        title="One",
        status="success",
        detail="done",
    )
    result = await engine.clear_history(ctx)
    assert result == {"status": "cleared", "removed": 1}
    # Only the audit row documenting the clearance itself remains.
    rows = db.findarr_recent_history()
    assert len(rows) == 1
    assert "history cleared" in rows[0]["detail"]
    assert any(
        row["action"] == "Findarr history cleared" for row in db.recent_activity()
    )
    # A history clear must not touch processed-state bookkeeping (that is reset_state).
    assert db.findarr_is_processed(app="radarr", mode="missing", item_id="7") is True


def _episode_unit(
    key: str, *, monitored: bool = True, is_future: bool = False
) -> SearchUnit:
    return SearchUnit(
        app="sonarr",
        mode="missing",
        command="EpisodeSearch",
        key=key,
        title=key,
        monitored=monitored,
        is_future=is_future,
        episode_ids=(int(key),),
    )


def test_unit_allowed_filters_monitored_future_and_processed(db) -> None:
    database = Database(":memory:")
    ctx = make_ctx(db=database)
    ctx.db.init_db()
    try:
        base = _episode_unit("1")
        assert (
            engine._unit_allowed(ctx, base, monitored_only=True, skip_future=True)
            is True
        )
        assert (
            engine._unit_allowed(
                ctx,
                _episode_unit("2", monitored=False),
                monitored_only=True,
                skip_future=True,
            )
            is False
        )
        assert (
            engine._unit_allowed(
                ctx,
                _episode_unit("3", is_future=True),
                monitored_only=True,
                skip_future=True,
            )
            is False
        )
        ctx.db.findarr_mark_processed(
            app="sonarr", mode="missing", item_id="1", title="One"
        )
        assert (
            engine._unit_allowed(ctx, base, monitored_only=False, skip_future=False)
            is False
        )
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


def _sonarr_only_store(**app_overrides) -> StubSettingsStore:
    """Enabled store with Radarr disabled and the given Sonarr app overrides."""
    store = _enabled_store(hourly_cap=20)
    settings = store.findarr_settings()
    settings["apps"]["radarr"]["enabled"] = False
    settings["apps"]["sonarr"].update(app_overrides)
    store.update_findarr_settings(settings)
    return store


async def test_run_sonarr_seasons_mode_issues_season_searches(db, monkeypatch) -> None:
    store = _sonarr_only_store(missing_mode="seasons", upgrade_mode="seasons")
    ctx = make_ctx(db=db, settings_store=store)
    records = [
        _sonarr_record(1, series_id=5, season=1, episode=1),
        _sonarr_record(2, series_id=5, season=1, episode=2),
        _sonarr_record(3, series_id=5, season=2, episode=1),
    ]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    result = await engine.run(ctx, app="sonarr", manual=True)
    # Two seasons × two modes = four season-pack searches.
    assert result["processed"] == 4
    assert {unit.command for unit in client.triggered} == {"SeasonSearch"}
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="5:s1") is True
    assert db.findarr_is_processed(app="sonarr", mode="upgrade", item_id="5:s2") is True


async def test_run_sonarr_shows_mode_issues_series_searches(db, monkeypatch) -> None:
    store = _sonarr_only_store(missing_mode="shows", upgrade_mode="shows")
    ctx = make_ctx(db=db, settings_store=store)
    records = [
        _sonarr_record(1, series_id=5, season=1, episode=1),
        _sonarr_record(3, series_id=5, season=2, episode=1),
    ]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    result = await engine.run(ctx, app="sonarr")
    # One series → one series search per mode.
    assert result["processed"] == 2
    assert {unit.command for unit in client.triggered} == {"SeriesSearch"}
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="5") is True


async def test_run_sleeps_between_successive_commands(db, monkeypatch) -> None:
    store = _sonarr_only_store()
    settings = store.findarr_settings()
    settings["command_sleep_seconds"] = 2
    store.update_findarr_settings(settings)
    ctx = make_ctx(db=db, settings_store=store)
    records = [
        _sonarr_record(1, series_id=5, season=1, episode=1),
        _sonarr_record(2, series_id=5, season=1, episode=2),
    ]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    sleeps: list[int] = []

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(engine.asyncio, "sleep", fake_sleep)
    result = await engine.run(ctx, app="sonarr")
    # Two episodes per mode → one inter-command sleep per mode (not before the first).
    assert result["processed"] == 4
    assert sleeps == [2, 2]


async def test_run_reports_already_searched_when_all_processed(db, monkeypatch) -> None:
    store = _sonarr_only_store()
    ctx = make_ctx(db=db, settings_store=store)
    # A single airable, monitored episode, already processed for both modes:
    # nothing is filtered, so the message is the true "already searched" one.
    records = [_sonarr_record(1, series_id=5, season=1, episode=1)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    db.findarr_mark_processed(app="sonarr", mode="missing", item_id="1", title="x")
    db.findarr_mark_processed(app="sonarr", mode="upgrade", item_id="1", title="x")
    await engine.run(ctx, app="sonarr")
    assert (
        db.findarr_run_state()["sonarr_activity"]
        == "Caught up — every wanted item is already searched this window"
    )
    assert db.findarr_run_state()["sonarr_missing_wanted"] == "1"


async def test_run_reports_skipped_by_settings_when_items_filtered(
    db, monkeypatch
) -> None:
    store = _sonarr_only_store()
    ctx = make_ctx(db=db, settings_store=store)
    # A future episode is excluded by skip_future — not "already searched". Both
    # modes scan it, so the per-app count is 2 (one per mode).
    records = [_sonarr_record(2, series_id=5, season=1, episode=2, future=True)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    await engine.run(ctx, app="sonarr")
    assert (
        db.findarr_run_state()["sonarr_activity"]
        == "Caught up — 2 wanted item(s) skipped by your monitored-only/skip-future settings"
    )


async def test_run_records_activity_when_wanted_fetch_fails(db, monkeypatch) -> None:
    store = _sonarr_only_store()
    ctx = make_ctx(db=db, settings_store=store)

    class WantedErrorClient(StubFindarrClient):
        async def wanted(self, kind: str) -> list[dict]:
            raise FindarrClientError("wanted down")

    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: WantedErrorClient(app))
    result = await engine.run(ctx, app="sonarr")
    # The run completes gracefully (no 500) and records the failure as activity.
    assert result["status"] == "completed"
    assert result["processed"] == 0
    assert db.findarr_run_state()["sonarr_activity"] == "Connection error — wanted down"
    assert any(row["detail"] == "wanted down" for row in db.findarr_recent_history())


async def test_run_reports_nothing_wanted_activity_when_no_records(
    db, monkeypatch
) -> None:
    store = _sonarr_only_store()
    ctx = make_ctx(db=db, settings_store=store)
    monkeypatch.setattr(
        engine,
        "_client_for",
        lambda _ctx, app: StubFindarrClient(app, sonarr_records=[]),
    )
    await engine.run(ctx, app="sonarr")
    assert db.findarr_run_state()["sonarr_activity"] == "Nothing wanted — all caught up"
    assert db.findarr_run_state()["sonarr_missing_wanted"] == "0"


async def test_run_records_search_error_activity(db, monkeypatch) -> None:
    store = _sonarr_only_store()
    ctx = make_ctx(db=db, settings_store=store)
    monkeypatch.setattr(
        engine,
        "_client_for",
        lambda _ctx, app: StubFindarrClient(
            app, command_error=FindarrClientError("boom")
        ),
    )
    await engine.run(ctx, app="sonarr")
    assert (
        db.findarr_run_state()["sonarr_activity"]
        == "Search errors on the last run — see history"
    )


async def test_run_seeds_state_anchor_on_first_enabled_run(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(hourly_cap=10))
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: StubFindarrClient(app))
    assert "state_created_at" not in db.findarr_run_state()
    await engine.run(ctx)
    assert "state_created_at" in db.findarr_run_state()


async def test_run_auto_resets_state_when_window_elapses(db, monkeypatch) -> None:
    store = _enabled_store(hourly_cap=10, state_reset_hours=1)
    ctx = make_ctx(db=db, settings_store=store)
    db.findarr_mark_processed(app="sonarr", mode="missing", item_id="old", title="Old")
    past = engine._format_iso(datetime.now(UTC) - timedelta(hours=2))
    db.findarr_set_run_state("state_created_at", past)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: StubFindarrClient(app))
    await engine.run(ctx)
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="old") is False
    assert any("auto-reset" in row["detail"] for row in db.findarr_recent_history())
    assert any(
        row["action"] == "Findarr state auto-reset" for row in db.recent_activity()
    )
    assert db.findarr_run_state()["state_created_at"] != past


async def test_run_keeps_state_when_window_not_elapsed(db, monkeypatch) -> None:
    store = _enabled_store(hourly_cap=10, state_reset_hours=24)
    ctx = make_ctx(db=db, settings_store=store)
    db.findarr_mark_processed(
        app="sonarr", mode="missing", item_id="keep", title="Keep"
    )
    recent = engine._format_iso(datetime.now(UTC) - timedelta(hours=1))
    db.findarr_set_run_state("state_created_at", recent)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: StubFindarrClient(app))
    await engine.run(ctx)
    assert db.findarr_is_processed(app="sonarr", mode="missing", item_id="keep") is True
    assert db.findarr_run_state()["state_created_at"] == recent


async def test_status_exposes_state_window(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(state_reset_hours=24))
    db.findarr_set_run_state("state_created_at", "2026-01-01T00:00:00Z")
    body = await engine.status(ctx)
    assert body["state"]["created_at"] == "2026-01-01T00:00:00Z"
    assert body["state"]["reset_at"] == "2026-01-02T00:00:00Z"
    assert body["state"]["reset_hours"] == 24


async def test_status_state_window_without_anchor(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    body = await engine.status(ctx)
    assert body["state"]["created_at"] is None
    assert body["state"]["reset_at"] is None
