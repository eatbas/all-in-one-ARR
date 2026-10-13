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

_FUTURE = "2999-01-01T00:00:00+00:00"
_PAST = "2000-01-01T00:00:00+00:00"


@dataclass
class StubFindarrClient:
    app: str
    compatible: bool = True
    queue_size_value: int = 0
    command_error: Exception | None = None
    sonarr_records: list[dict] | None = None
    triggered: list = field(default_factory=list)
    commands: dict[int, dict | None] = field(default_factory=dict)
    profiles: list[dict] = field(default_factory=list)
    series_list: list[dict] = field(default_factory=list)
    episodes: dict[int, list[dict]] = field(default_factory=dict)

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

    async def trigger_search(self, unit: SearchUnit) -> int | None:
        self.triggered.append(unit)
        if self.command_error is not None:
            raise self.command_error
        return 1000 + len(self.triggered)

    async def command(self, command_id: int) -> dict | None:
        return self.commands.get(command_id)

    async def grabs_since(self, since_iso: str) -> list[dict]:
        return []

    async def quality_profiles(self) -> list[dict]:
        return self.profiles

    async def series(self) -> list[dict]:
        return self.series_list

    async def episodes_with_files(self, series_id: int) -> list[dict]:
        return self.episodes.get(series_id, [])

    async def movies(self) -> list[dict]:
        return []

    async def movie_files(self, movie_ids: list[int]) -> list[dict]:
        return []

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


def _sonarr_only_store(**app_overrides) -> StubSettingsStore:
    """Enabled store with Radarr disabled and the given Sonarr app overrides."""
    store = _enabled_store(hourly_cap=20)
    settings = store.findarr_settings()
    settings["apps"]["radarr"]["enabled"] = False
    settings["apps"]["sonarr"].update(app_overrides)
    store.update_findarr_settings(settings)
    return store


def _mark(db, item_id: str, *, mode: str = "missing", due: str = _FUTURE) -> None:
    db.findarr_mark_searched(
        app="sonarr", mode=mode, item_id=item_id, title=item_id, next_eligible_at=due
    )


async def test_status_contains_settings_cooldown_and_retry(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(state_reset_hours=24))
    _mark(db, "1")
    _mark(db, "2", due=_PAST)
    db.findarr_increment_total(app="sonarr", mode="missing")
    body = await engine.status(ctx)
    assert body["settings"]["enabled"] is True
    # Only the unit still inside its retry delay counts as cooling down.
    assert body["apps"]["sonarr"]["cooldown"] == {"missing": 1, "upgrade": 0}
    assert body["apps"]["sonarr"]["lifetime"]["missing"] == 1
    assert body["apps"]["sonarr"]["wanted"] == {"missing": 0, "upgrade": 0}
    assert body["apps"]["sonarr"]["activity"] == "Not run yet"
    assert body["retry"] == {
        "base_hours": 24,
        "max_hours": 720,
        "next_due_at": _FUTURE,
    }
    assert body["running"] is False


async def test_status_counts_hourly_use_from_the_search_log(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(hourly_cap=5))
    db.findarr_log_search(
        app="sonarr", mode="missing", item_id="1", command_id=1, history_id=0
    )
    db.findarr_clear_history()
    body = await engine.status(ctx)
    assert body["hourly"] == {"limit": 5, "used": 1, "remaining": 4}


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
    assert set(db.findarr_retry_state(app="sonarr", mode="missing")) == {"10"}
    assert set(db.findarr_retry_state(app="radarr", mode="upgrade")) == {"21"}
    # Each successful trigger bumps the reset-proof all-time tally.
    assert db.findarr_totals()["sonarr"]["missing"] == 1
    assert db.findarr_totals()["radarr"]["upgrade"] == 1
    assert db.findarr_run_state()["sonarr_activity"].startswith("Searched")
    # A sent search is "sent" until its result is read back on a later run.
    history = db.findarr_recent_history()
    assert {row["status"] for row in history} == {"sent"}
    assert history[0]["detail"].endswith("result pending")
    assert len(db.findarr_pending_searches(app="sonarr", limit=10)) == 2
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
    # A rejected command is neither logged towards the cap nor put on cooldown.
    assert db.findarr_search_count_since(_PAST) == 0
    assert db.findarr_retry_state(app="sonarr", mode="missing") == {}


async def test_run_mode_returns_when_capacity_is_zero(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store(hourly_cap=0))
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: StubFindarrClient(app))
    result = await engine.run(ctx, app="sonarr")
    assert result["results"][0]["detail"] == "No remaining Findarr capacity"
    assert db.findarr_run_state()["sonarr_activity"] == "Throttled — hourly cap reached"


async def test_history_clear_does_not_lift_the_hourly_cap(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
    store = ctx.settings_store
    settings = store.findarr_settings()
    settings["hourly_cap"] = 1
    store.update_findarr_settings(settings)
    client = StubFindarrClient(
        "sonarr", sonarr_records=[_sonarr_record(1, series_id=5, season=1, episode=1)]
    )
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    first = await engine.run(ctx, app="sonarr")
    assert first["processed"] == 1
    await engine.clear_history(ctx)
    db.findarr_reset_state()
    second = await engine.run(ctx, app="sonarr")
    assert second["processed"] == 0
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
    assert db.findarr_run_state()["radarr_activity"].startswith("Radarr queue size 1")


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


async def test_reset_state_clears_retry_state(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    _mark(db, "7")
    result = await engine.reset_state(ctx)
    assert result == {"status": "reset", "removed": 1}
    assert db.findarr_retry_state(app="sonarr", mode="missing") == {}
    assert "retry state reset" in db.findarr_recent_history()[0]["detail"]


async def test_history_returns_recent_rows(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id="1",
        title="One",
        status="sent",
        detail="done",
    )
    rows = await engine.history(ctx)
    assert rows[0]["title"] == "One"


async def test_clear_history_empties_log_and_records_audit(db) -> None:
    ctx = make_ctx(db=db, settings_store=_enabled_store())
    _mark(db, "7")
    db.findarr_add_history(
        app="sonarr",
        mode="missing",
        item_id="1",
        title="One",
        status="sent",
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
    # A history clear must not touch retry state (that is reset_state).
    assert set(db.findarr_retry_state(app="sonarr", mode="missing")) == {"7"}


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


def test_unit_due_filters_preferences_and_retry_delay() -> None:
    now = datetime.now(UTC)
    kwargs = {"now": now, "monitored_only": True, "skip_future": True}
    assert engine._unit_due(_episode_unit("1"), {}, **kwargs) is True
    assert engine._unit_due(_episode_unit("2", monitored=False), {}, **kwargs) is False
    assert engine._unit_due(_episode_unit("3", is_future=True), {}, **kwargs) is False
    waiting = {"1": {"attempts": 0, "next_eligible_at": _FUTURE}}
    assert engine._unit_due(_episode_unit("1"), waiting, **kwargs) is False
    due_again = {"1": {"attempts": 2, "next_eligible_at": _PAST}}
    assert engine._unit_due(_episode_unit("1"), due_again, **kwargs) is True
    legacy = {"1": {"attempts": 0, "next_eligible_at": None}}
    assert engine._unit_due(_episode_unit("1"), legacy, **kwargs) is True


def test_select_units_puts_never_searched_units_first() -> None:
    units = [_episode_unit("1"), _episode_unit("2"), _episode_unit("3")]
    retry_state = {"1": {"attempts": 1, "next_eligible_at": _PAST}}
    selected = engine._select_units(
        units, retry_state, monitored_only=True, skip_future=True, limit=2
    )
    assert [unit.key for unit in selected] == ["2", "3"]


def test_client_for_uses_context_connection_fields(db) -> None:
    database = Database(":memory:")
    ctx = make_ctx(db=database)
    try:
        client = engine._client_for(ctx, "sonarr")
        assert client.base_url == "http://arr"
        assert client.api_key == "key"
    finally:
        database.close()


def test_normalise_items_skips_invalid_and_duplicate_records() -> None:
    assert engine._normalise_items("sonarr", "missing", [{}]) == []
    record = _sonarr_record(1, series_id=5, season=1, episode=1)
    items = engine._normalise_items("sonarr", "upgrade", [record, dict(record)])
    assert [item.item_id for item in items] == ["1"]


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
    assert set(db.findarr_retry_state(app="sonarr", mode="missing")) == {
        "5:s1",
        "5:s2",
    }


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
    assert set(db.findarr_retry_state(app="sonarr", mode="missing")) == {"5"}


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


async def test_run_skips_units_inside_their_retry_delay(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
    # A single airable, monitored episode still cooling down in both modes:
    # nothing is filtered, so the message is the true "waiting" one.
    records = [_sonarr_record(1, series_id=5, season=1, episode=1)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    _mark(db, "1", mode="missing")
    _mark(db, "1", mode="upgrade")
    await engine.run(ctx, app="sonarr")
    assert client.triggered == []
    assert (
        db.findarr_run_state()["sonarr_activity"]
        == "Caught up — every wanted item is waiting for its retry delay"
    )
    assert db.findarr_run_state()["sonarr_missing_wanted"] == "1"


async def test_run_searches_a_unit_again_once_its_delay_passes(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store(upgrade_limit=0))
    records = [_sonarr_record(1, series_id=5, season=1, episode=1)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    _mark(db, "1", due=_PAST)
    db.findarr_set_retry(
        app="sonarr", mode="missing", item_id="1", attempts=2, next_eligible_at=_PAST
    )
    result = await engine.run(ctx, app="sonarr")
    assert result["processed"] == 1
    entry = db.findarr_retry_state(app="sonarr", mode="missing")["1"]
    # The no-result count survives the re-search; the new delay uses it
    # (base 168h doubled once for two consecutive misses).
    assert entry["attempts"] == 2
    next_due = datetime.fromisoformat(entry["next_eligible_at"])
    expected = datetime.now(UTC) + timedelta(hours=336)
    assert abs((next_due - expected).total_seconds()) < 60


async def test_run_prunes_units_that_left_the_wanted_list(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
    _mark(db, "999")
    client = StubFindarrClient("sonarr", sonarr_records=[])
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    await engine.run(ctx, app="sonarr")
    assert db.findarr_retry_state(app="sonarr", mode="missing") == {}


async def test_run_includes_custom_format_upgrades(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store(missing_limit=0))
    series = {
        "id": 7,
        "title": "Anime",
        "monitored": True,
        "qualityProfileId": 9,
        "statistics": {"episodeFileCount": 1},
    }
    episode = {
        "id": 70,
        "title": "Ep",
        "seriesId": 7,
        "seasonNumber": 1,
        "episodeNumber": 1,
        "airDateUtc": "2020-01-01T00:00:00Z",
        "monitored": True,
        "episodeFile": {"customFormatScore": -10000},
    }
    client = StubFindarrClient(
        "sonarr",
        sonarr_records=[],
        profiles=[{"id": 9, "upgradeAllowed": True, "cutoffFormatScore": 10000}],
        series_list=[series],
        episodes={7: [episode]},
    )
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    result = await engine.run(ctx, app="sonarr")
    assert result["processed"] == 1
    assert [unit.key for unit in client.triggered] == ["70"]
    assert client.triggered[0].mode == "upgrade"
    assert db.findarr_run_state()["sonarr_upgrade_wanted"] == "1"


async def test_run_resolves_pending_outcomes_before_searching(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store(state_reset_hours=24))
    records = [_sonarr_record(1, series_id=5, season=1, episode=1)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    await engine.run(ctx, app="sonarr")
    # First run sent missing + upgrade searches with command ids 1001 and 1002.
    client.commands = {
        1001: {
            "status": "completed",
            "message": "Episode search completed. 0 reports downloaded.",
        },
        1002: {
            "status": "completed",
            "message": "Episode search completed. 1 reports downloaded.",
        },
    }
    await engine.run(ctx, app="sonarr")
    statuses = {
        row["mode"]: row["status"]
        for row in db.findarr_recent_history()
        if row["mode"] != "system"
    }
    assert statuses == {"missing": "not_found", "upgrade": "grabbed"}
    assert db.findarr_retry_state(app="sonarr", mode="missing")["1"]["attempts"] == 1
    assert db.findarr_retry_state(app="sonarr", mode="upgrade")["1"]["attempts"] == 0
    assert db.findarr_pending_searches(app="sonarr", limit=10) == []


async def test_run_reports_skipped_by_settings_when_items_filtered(
    db, monkeypatch
) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
    # A future episode is excluded by skip_future — not "waiting". Both modes
    # scan it, so the per-app count is 2 (one per mode).
    records = [_sonarr_record(2, series_id=5, season=1, episode=2, future=True)]
    client = StubFindarrClient("sonarr", sonarr_records=records)
    monkeypatch.setattr(engine, "_client_for", lambda _ctx, app: client)
    await engine.run(ctx, app="sonarr")
    assert (
        db.findarr_run_state()["sonarr_activity"]
        == "Caught up — 2 wanted item(s) skipped by your monitored-only/skip-future settings"
    )


async def test_run_records_activity_when_wanted_fetch_fails(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())

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
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
    monkeypatch.setattr(
        engine,
        "_client_for",
        lambda _ctx, app: StubFindarrClient(app, sonarr_records=[]),
    )
    await engine.run(ctx, app="sonarr")
    assert db.findarr_run_state()["sonarr_activity"] == "Nothing wanted — all caught up"
    assert db.findarr_run_state()["sonarr_missing_wanted"] == "0"


async def test_run_records_search_error_activity(db, monkeypatch) -> None:
    ctx = make_ctx(db=db, settings_store=_sonarr_only_store())
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
