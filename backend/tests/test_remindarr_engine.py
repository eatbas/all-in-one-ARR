"""Tests for the Remindarr engine, client and module wiring.

Small in-process fakes of Sonarr and Plex (served through ``httpx.MockTransport``)
back a real :class:`RemindarrSonarrClient` and a real :class:`PlexClient`, so the
clients and the engine's refresh, failure and recovery flows run together.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import modules.remindarr as remindarr_module
from core.app_metrics import (
    remindarr_runs_total,
    remindarr_unmatched_series,
    remindarr_unwatched_episodes,
    scheduler_job_runs_total,
)
from core.clients.plex import PlexClient, PlexClientError
from core.context import SyncAlreadyRunning
from core.remindarr_api import create_remindarr_router
from modules.remindarr import engine as engine_module
from modules.remindarr import remindarr_job, setup
from modules.remindarr.client import (
    RemindarrClientError,
    RemindarrSonarrClient,
    client_for,
)
from modules.remindarr.engine import RemindarrService, RemindarrTagError
from tests.conftest import StubSettingsStore, make_ctx

_PLEX_SERVICE = {"url": "http://plex:32400", "api_key": "plex-token"}


def _series(
    series_id: int, tags: list[int], tvdb_id: int | None, **extra: Any
) -> dict[str, Any]:
    return {
        "id": series_id,
        "title": f"Series {series_id}",
        "titleSlug": f"series-{series_id}",
        "tags": tags,
        "tvdbId": tvdb_id,
        "monitored": True,
        **extra,
    }


def _ep(
    episode_id: int, season: int, number: int, file_id: int, **extra: Any
) -> dict[str, Any]:
    return {
        "id": episode_id,
        "seasonNumber": season,
        "episodeNumber": number,
        "episodeFileId": file_id,
        "title": f"Episode {number}",
        "airDateUtc": f"2026-11-{number:02d}T00:00:00Z",
        "monitored": True,
        **extra,
    }


class FakeSonarr:
    """Minimal read-only Sonarr v3 API: status, tags, series, episodes, files."""

    def __init__(self) -> None:
        self.status: dict[str, Any] = {"appName": "Sonarr", "version": "4.0.20"}
        self.tags: list[Any] = [
            {"id": 2, "label": "watch-together"},
            {"id": 1, "label": "anime"},
            {"id": 3, "label": "Kids"},
            {"id": 0, "label": "zero"},
            {"id": 4, "label": "  "},
            "bad",
        ]
        self.series = [
            _series(1, [1], 101),
            _series(2, [2], None),
            _series(3, [1, 3], 103),
            _series(4, [3], 104),
            _series(5, [1], 105, monitored=False),
            _series(6, [2], 106),
        ]
        self.episodes: dict[int, list[dict[str, Any]]] = {
            1: [
                _ep(11, 1, 1, 111),
                _ep(12, 1, 2, 112),
                _ep(13, 1, 3, 113),
                _ep(14, 1, 4, 0),
                _ep(15, 1, 5, 115, monitored=False),
            ],
            2: [_ep(21, 1, 1, 211)],
            3: [_ep(31, 1, 1, 311)],
            6: [_ep(61, 1, 1, 0)],
        }
        self.files: dict[int, list[dict[str, Any]]] = {
            1: [
                {"id": 111, "dateAdded": "2026-11-18T10:00:00Z"},
                {"id": 112, "dateAdded": "2026-11-21T06:00:00Z"},
                {"id": 113, "dateAdded": "2026-11-19T10:00:00Z"},
            ],
            2: [{"id": 211, "dateAdded": "2026-11-17T10:00:00Z"}],
            3: [{"id": 311, "dateAdded": "2026-11-20T10:00:00Z"}],
        }
        self.fail: dict[str, int] = {}
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        if code := self.fail.get(path):
            return httpx.Response(code)
        if path == "/api/v3/system/status":
            return httpx.Response(200, json=self.status)
        if path == "/api/v3/tag":
            return httpx.Response(200, json=self.tags)
        if path == "/api/v3/series":
            return httpx.Response(200, json=self.series)
        series_id = int(request.url.params["seriesId"])
        if path == "/api/v3/episode":
            return httpx.Response(200, json=self.episodes.get(series_id, []))
        return httpx.Response(200, json=self.files.get(series_id, []))

    def client(self) -> RemindarrSonarrClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return RemindarrSonarrClient(
            app="sonarr", base_url="http://sonarr", api_key="key", http_client=http
        )


def _leaf(season: int, number: int, views: int | None = None) -> dict[str, Any]:
    leaf: dict[str, Any] = {"parentIndex": season, "index": number}
    if views is not None:
        leaf["viewCount"] = views
    return leaf


class FakePlex:
    """Minimal Plex Media Server: sections, shows with GUIDs, ``allLeaves``."""

    def __init__(self) -> None:
        self.sections = [
            {"key": "1", "type": "show"},
            {"key": "2", "type": "movie"},
            {"key": "3", "type": "show"},
        ]
        self.shows: dict[str, list[dict[str, Any]]] = {
            "1": [
                {"ratingKey": "100", "title": "S1", "Guid": [{"id": "tvdb://101"}]},
                {"ratingKey": "400", "title": "S4", "Guid": [{"id": "tvdb://104"}]},
            ],
            # A 4K library holding the same show again.
            "3": [
                {"ratingKey": "200", "title": "S1 4K", "Guid": [{"id": "tvdb://101"}]}
            ],
        }
        self.leaves: dict[str, list[dict[str, Any]]] = {
            "100": [_leaf(1, 1), _leaf(1, 2, 0)],
            "200": [_leaf(1, 1, 2)],
            "400": [_leaf(1, 1)],
        }
        self.fail: int | None = None
        # Raw ``MediaContainer`` bodies served instead of the fake library.
        self.containers: dict[str, dict[str, Any]] = {}
        self.paths: list[str] = []
        self.tokens: set[str] = set()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        self.tokens.add(request.headers["X-Plex-Token"])
        if self.fail is not None:
            return httpx.Response(self.fail)
        if path in self.containers:
            return httpx.Response(200, json={"MediaContainer": self.containers[path]})
        if path == "/library/sections":
            return httpx.Response(
                200, json={"MediaContainer": {"Directory": self.sections}}
            )
        if path.endswith("/all"):
            key = path.split("/")[3]
            return httpx.Response(
                200, json={"MediaContainer": {"Metadata": self.shows[key]}}
            )
        key = path.split("/")[3]
        return httpx.Response(
            200, json={"MediaContainer": {"Metadata": self.leaves[key]}}
        )

    def client(self) -> PlexClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return PlexClient(
            base_url=_PLEX_SERVICE["url"],
            api_key=_PLEX_SERVICE["api_key"],
            http_client=http,
        )


@pytest.fixture
def sonarr(monkeypatch) -> FakeSonarr:
    fake = FakeSonarr()
    monkeypatch.setattr(engine_module, "client_for", lambda _ctx: fake.client())
    return fake


@pytest.fixture
def plex() -> FakePlex:
    return FakePlex()


@pytest.fixture
def frozen_now(monkeypatch) -> datetime:
    now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone(timedelta(hours=3)))
    monkeypatch.setattr(engine_module, "_local_now", lambda: now)
    return now


def _service(
    db, plex: FakePlex, *, plex_configured: bool = True, **settings: Any
) -> RemindarrService:
    merged = {"enabled": True, "tag_ids": [1, 2, 9], **settings}
    store = StubSettingsStore(
        remindarr_settings=merged,
        services={"plex": dict(_PLEX_SERVICE) if plex_configured else {"url": ""}},
    )
    return RemindarrService(make_ctx(db=db, settings_store=store, plex=plex.client()))


def _activity(service: RemindarrService) -> list[str]:
    return [row["action"] for row in service._ctx.db.recent_activity(50)]


def _value(metric, *labels: str) -> float:
    return (metric.labels(*labels) if labels else metric)._value.get()


# ---- client ----


def test_client_for_uses_context_sonarr_connection(db) -> None:
    client = client_for(make_ctx(db=db))
    assert client.base_url == "http://arr"
    assert client.api_key == "key"
    assert client.feature_name == "Remindarr"
    assert client.error_class is RemindarrClientError


# ---- refresh ----


async def test_successful_run_stores_unwatched_episodes(
    db, sonarr: FakeSonarr, plex: FakePlex, frozen_now: datetime
) -> None:
    del frozen_now
    service = _service(db, plex)
    before = _value(remindarr_runs_total, "success")

    result = await service.run_now()

    # Series 6 is tracked but has no downloaded episode and no Plex show.
    assert result == {
        "status": "success",
        "unwatched": 1,
        "series_with_unwatched": 1,
        "tracked_series": 4,
        "unmatched_series": 3,
    }
    results = await service.results()
    assert [group["series_id"] for group in results["series"]] == [1]
    group = results["series"][0]
    # S1E1 was watched in the 4K copy; S1E3 is not in Plex; S1E4 has no file
    # and S1E5 is unmonitored.
    assert [episode["label"] for episode in group["episodes"]] == ["S01E02"]
    assert group["episodes_not_in_plex"] == 1
    assert group["latest_added_at"] == "2026-11-21T06:00:00+00:00"
    assert group["episodes"][0]["new_today"] is True
    assert group["episodes"][0]["air_date_utc"] == "2026-11-02T00:00:00+00:00"
    assert group["new_today"] == 1
    assert group["series_slug"] == "series-1"
    assert [
        (series["series_id"], series["reason"], series["reason_label"])
        for series in results["unmatched"]
    ] == [
        (3, "not_in_plex", "No Plex show with this TVDB id"),
        (2, "no_tvdb_id", "No TVDB id in Sonarr"),
        (6, "not_in_plex", "No Plex show with this TVDB id"),
    ]
    status = await service.status()
    assert status["stale"] is False
    assert status["missing_tag_ids"] == [9]
    assert status["plex_configured"] is True
    assert status["counts"] == {
        "unwatched": 1,
        "series_with_unwatched": 1,
        "tracked_series": 4,
        "unmatched_series": 3,
    }
    assert status["last_success_at"] == status["last_attempt_at"]
    assert results["last_success_at"] == status["last_success_at"]
    assert _activity(service) == ["Remindarr reminders updated"]
    assert _value(remindarr_runs_total, "success") == before + 1
    assert _value(remindarr_unwatched_episodes) == 1
    assert _value(remindarr_unmatched_series) == 3
    # No episode files are read for a series without downloaded episodes, and
    # Plex is only asked for the matched tracked shows' episodes.
    assert sonarr.paths.count("/api/v3/episodefile") == 3
    assert sorted(path for path in plex.paths if path.endswith("allLeaves")) == [
        "/library/metadata/100/allLeaves",
        "/library/metadata/200/allLeaves",
    ]
    assert plex.tokens == {"plex-token"}


async def test_unchanged_count_writes_no_new_activity(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    service = _service(db, plex)
    await service.run_now()
    await service.run_now()
    assert _activity(service) == ["Remindarr reminders updated"]


async def test_no_selected_series_skips_plex_reads(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    service = _service(db, plex, tag_ids=[])
    result = await service.run_now()
    assert result["tracked_series"] == 0
    assert plex.paths == []
    assert "/api/v3/series" in sonarr.paths
    # Nothing changed from the empty start, so nothing is logged.
    assert _activity(service) == []


async def test_disabled_makes_no_upstream_calls(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    service = _service(db, plex, enabled=False)
    before = _value(remindarr_runs_total, "skipped")
    assert await service.run_now() == {
        "status": "disabled",
        "unwatched": 0,
        "series_with_unwatched": 0,
        "tracked_series": 0,
        "unmatched_series": 0,
    }
    assert await service.scheduled_run() is None
    assert sonarr.paths == []
    assert plex.paths == []
    assert _value(remindarr_runs_total, "skipped") == before + 2
    assert (await service.status())["last_attempt_at"] is None


async def _seed_success(service: RemindarrService) -> None:
    await service.run_now()
    assert (await service.status())["counts"]["unwatched"] == 1


@pytest.mark.parametrize(
    ("break_upstream", "error_type", "message"),
    [
        (
            lambda sonarr, plex: sonarr.fail.update({"/api/v3/system/status": 500}),
            RemindarrClientError,
            "sonarr API request failed",
        ),
        (
            lambda sonarr, plex: sonarr.fail.update({"/api/v3/episode": 503}),
            RemindarrClientError,
            "sonarr API request failed",
        ),
        (
            lambda sonarr, plex: setattr(plex, "fail", 401),
            PlexClientError,
            "Plex rejected the token",
        ),
        (
            lambda sonarr, plex: sonarr.status.update({"version": "3.0.10"}),
            RemindarrClientError,
            "Remindarr requires Sonarr 4+",
        ),
        (
            lambda sonarr, plex: plex.containers.update(
                {"/library/sections": {"size": 2, "Directory": "nope"}}
            ),
            PlexClientError,
            "invalid Directory list",
        ),
        (
            lambda sonarr, plex: plex.containers.update(
                {"/library/sections/1/all": {"size": 2}}
            ),
            PlexClientError,
            "incomplete Metadata list",
        ),
        (
            lambda sonarr, plex: plex.containers.update(
                {
                    f"/library/metadata/{key}/allLeaves": {
                        "size": 2,
                        "Metadata": "not a list",
                    }
                    for key in ("100", "200")
                }
            ),
            PlexClientError,
            "invalid Metadata list",
        ),
    ],
)
async def test_failures_keep_old_rows_and_mark_stale(
    db, sonarr: FakeSonarr, plex: FakePlex, break_upstream, error_type, message
) -> None:
    service = _service(db, plex)
    await _seed_success(service)
    old_success = (await service.status())["last_success_at"]
    before = _value(remindarr_runs_total, "error")
    break_upstream(sonarr, plex)

    with pytest.raises(error_type, match=message):
        await service.run_now()

    status = await service.status()
    assert status["stale"] is True
    assert message in status["last_error"]
    assert status["last_success_at"] == old_success
    assert status["last_attempt_at"] is not None
    assert status["missing_tag_ids"] == [9]
    assert status["counts"]["unwatched"] == 1
    assert len((await service.results())["series"]) == 1
    assert _value(remindarr_runs_total, "error") == before + 1
    assert _activity(service)[0] == "Remindarr refresh failed"


async def test_malformed_plex_collection_returns_502_and_keeps_old_rows(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    service = _service(db, plex)
    ctx = service._ctx
    ctx.remindarr_status = service.status
    ctx.remindarr_results = service.results
    ctx.remindarr_run_now = service.run_now
    app = FastAPI()
    app.include_router(create_remindarr_router(ctx))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
        assert (await api.post("/api/remindarr/run")).status_code == 200
        previous = (await api.get("/api/remindarr/results")).json()
        assert len(previous["series"]) == 1
        # Plex answers 200, but the episode list is not a list.
        for key in ("100", "200"):
            plex.containers[f"/library/metadata/{key}/allLeaves"] = {
                "size": 2,
                "Metadata": "not a list",
            }

        resp = await api.post("/api/remindarr/run")

        assert resp.status_code == 502
        assert "invalid Metadata list" in resp.json()["detail"]
        status = (await api.get("/api/remindarr/status")).json()
        assert status["stale"] is True
        assert status["counts"]["unwatched"] == 1
        assert status["last_success_at"] == previous["last_success_at"]
        assert (await api.get("/api/remindarr/results")).json() == previous


async def test_watched_series_keeps_its_episodes_not_in_plex(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    # Series 1: S1E1 watched in the 4K copy, S1E2 now watched, S1E3 not in Plex.
    plex.leaves["100"] = [_leaf(1, 1), _leaf(1, 2, 1)]
    service = _service(db, plex)

    result = await service.run_now()

    assert result["unwatched"] == 0
    assert result["series_with_unwatched"] == 0
    groups = (await service.results())["series"]
    assert [
        (group["series_id"], group["episodes"], group["episodes_not_in_plex"])
        for group in groups
    ] == [(1, [], 1)]
    assert groups[0]["new_today"] == 0
    assert groups[0]["latest_added_at"] == "2026-11-21T06:00:00+00:00"


async def test_series_with_every_episode_missing_from_plex(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    plex.leaves["100"] = []
    plex.leaves["200"] = []
    service = _service(db, plex)

    result = await service.run_now()

    # Unknown episodes are never counted as unwatched.
    assert result["unwatched"] == 0
    groups = (await service.results())["series"]
    assert [(group["episodes"], group["episodes_not_in_plex"]) for group in groups] == [
        ([], 3)
    ]


async def test_unmatched_only_results_have_no_series_groups(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    # Tag 2 selects series 2 (no TVDB id) and series 6 (not in Plex).
    service = _service(db, plex, tag_ids=[2])

    await service.run_now()

    results = await service.results()
    assert results["series"] == []
    assert [series["series_id"] for series in results["unmatched"]] == [2, 6]


async def test_plex_not_configured_is_a_recorded_failure(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    service = _service(db, plex, plex_configured=False)
    with pytest.raises(PlexClientError, match="Plex is not connected"):
        await service.run_now()
    status = await service.status()
    assert status["plex_configured"] is False
    assert status["last_error"] == "Plex is not connected"
    assert plex.paths == []


async def test_repeated_failure_logs_once_and_recovery_clears_stale(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    service = _service(db, plex)
    plex.fail = 500
    for _ in range(2):
        with pytest.raises(PlexClientError):
            await service.run_now()
    assert _activity(service) == ["Remindarr refresh failed"]

    plex.fail = None
    await service.run_now()
    status = await service.status()
    assert status["stale"] is False
    assert status["last_error"] is None
    assert _activity(service)[0] == "Remindarr refresh recovered"
    assert sonarr.paths


async def test_scheduled_failure_is_recorded_not_raised(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    sonarr.fail["/api/v3/series"] = 500
    service = _service(db, plex)
    assert await service.scheduled_run() is None
    assert (await service.status())["stale"] is True


async def test_scheduled_success(db, sonarr: FakeSonarr, plex: FakePlex) -> None:
    del sonarr
    service = _service(db, plex)
    await service.scheduled_run()
    assert (await service.status())["counts"]["unwatched"] == 1


async def test_manual_run_is_rejected_while_a_refresh_runs(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    service = _service(db, plex)
    release = asyncio.Event()
    started = asyncio.Event()
    order: list[str] = []

    async def slow_refresh() -> None:
        started.set()
        order.append("first:start")
        await release.wait()
        order.append("first:end")

    first = asyncio.create_task(service.gate.run(slow_refresh))
    await started.wait()
    assert (await service.status())["running"] is True
    with pytest.raises(SyncAlreadyRunning):
        await service.run_now()

    async def scheduled() -> None:
        order.append("scheduled")

    # A scheduled refresh waits for the running one instead of overlapping it.
    waiting = asyncio.create_task(service.gate.run(scheduled))
    await asyncio.sleep(0)
    assert order == ["first:start"]
    release.set()
    await asyncio.gather(first, waiting)
    assert order == ["first:start", "first:end", "scheduled"]
    assert (await service.status())["running"] is False


# ---- tags and settings ----


async def test_tags_are_sorted_and_filtered(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    assert await _service(db, plex).tags() == [
        {"id": 1, "label": "anime"},
        {"id": 3, "label": "Kids"},
        {"id": 2, "label": "watch-together"},
    ]


async def test_newly_added_unknown_tag_is_rejected(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    service = _service(db, plex, tag_ids=[1])
    with pytest.raises(RemindarrTagError, match="Unknown Sonarr tag ids: 8, 12"):
        await service.update_settings({"tag_ids": [1, 8, 12]})
    assert service.settings()["tag_ids"] == [1]
    assert _activity(service) == []


async def test_saved_stale_tag_is_accepted_without_asking_sonarr(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    # Tag 9 was saved earlier and has since been deleted in Sonarr.
    service = _service(db, plex, tag_ids=[1, 9])
    settings = await service.update_settings({"tag_ids": [9], "enabled": False})
    assert settings["tag_ids"] == [9]
    assert sonarr.paths == []
    assert _activity(service) == ["Remindarr settings saved"]


async def test_new_known_tag_is_validated_and_saved(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    service = _service(db, plex, tag_ids=[1, 9])
    settings = await service.update_settings({"tag_ids": [9, 1, 3]})
    assert settings["tag_ids"] == [9, 1, 3]
    assert sonarr.paths == ["/api/v3/tag"]


async def test_unreachable_sonarr_while_validating_new_tags(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    sonarr.fail["/api/v3/tag"] = 500
    service = _service(db, plex, tag_ids=[])
    with pytest.raises(RemindarrClientError):
        await service.update_settings({"tag_ids": [1]})
    assert service.settings()["tag_ids"] == []


# ---- module wiring ----


async def test_setup_registers_callables_and_reschedules_on_interval_change(
    db, sonarr: FakeSonarr, plex: FakePlex
) -> None:
    del sonarr
    store = StubSettingsStore(services={"plex": dict(_PLEX_SERVICE)})
    ctx = make_ctx(db=db, settings_store=store, plex=plex.client())
    ctx.db.remindarr_replace_results(
        [
            {
                "series_id": 1,
                "series_title": "S",
                "series_slug": None,
                "tvdb_id": None,
                "plex_match": "no_tvdb_id",
                "episodes_not_in_plex": 0,
                "latest_added_at": None,
            }
        ],
        [],
    )
    scheduler = AsyncMock()
    await setup(scheduler, FastAPI(), ctx)

    scheduler.add_interval.assert_awaited_once()
    assert scheduler.add_interval.await_args.args == (remindarr_job,)
    assert scheduler.add_interval.await_args.kwargs == {
        "minutes": 60,
        "id": "remindarr_poll",
    }
    # Gauges start from the stored results.
    assert _value(remindarr_unmatched_series) == 1
    for name in ("status", "results", "tags", "run_now", "update_settings"):
        assert getattr(ctx, f"remindarr_{name}") is not None

    status = await ctx.remindarr_update_settings({"enabled": True})
    assert status["settings"]["enabled"] is True
    scheduler.reschedule_interval.assert_not_awaited()

    await ctx.remindarr_update_settings({"interval_minutes": 120})
    scheduler.reschedule_interval.assert_awaited_once()
    assert scheduler.reschedule_interval.await_args.kwargs == {
        "minutes": 120,
        "id": "remindarr_poll",
    }

    before = _value(scheduler_job_runs_total, "remindarr_poll", "success")
    await remindarr_job()
    assert _value(scheduler_job_runs_total, "remindarr_poll", "success") == (before + 1)
    assert remindarr_module._require_service() is not None
