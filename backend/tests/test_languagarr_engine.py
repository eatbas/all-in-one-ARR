"""Tests for the Languagarr engine, client and module wiring.

A small in-process fake Sonarr (served through ``httpx.MockTransport``) backs a
real :class:`LanguagarrSonarrClient`, so the client endpoints and the engine's
guarded flows are exercised together.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import modules.languagarr as languagarr_module
from core.context import SyncAlreadyRunning
from modules.languagarr import engine as engine_module
from modules.languagarr import languagarr_job, setup
from modules.languagarr.client import (
    LanguagarrClientError,
    LanguagarrSonarrClient,
    client_for,
)
from modules.languagarr.engine import (
    NO_SEARCHABLE_EPISODES,
    LanguagarrScopeError,
    LanguagarrService,
)
from tests.conftest import StubSettingsStore, make_ctx


def _file(
    file_id: int,
    audio: str | None,
    *,
    score: int,
    series_id: int = 1,
    group: str | None = "Grp",
) -> dict[str, Any]:
    media = {"audioLanguages": audio} if audio is not None else None
    return {
        "id": file_id,
        "seriesId": series_id,
        "seasonNumber": 1,
        "relativePath": f"Season 01/file-{file_id}.mkv",
        "path": f"/tv/Show/Season 01/file-{file_id}.mkv",
        "languages": [{"id": 8, "name": "Japanese"}, {"name": ""}, "bad"],
        "mediaInfo": media,
        "releaseGroup": group,
        "customFormatScore": score,
    }


def _episode(episode_id: int, number: int, file_id: int) -> dict[str, Any]:
    return {"id": episode_id, "episodeNumber": number, "episodeFileId": file_id}


class FakeSonarr:
    """Minimal Sonarr v3 API: profiles, series, files, episodes, delete, command."""

    def __init__(self) -> None:
        self.status = {"appName": "Sonarr", "version": "4.0.20.3014"}
        self.profiles = [
            {"id": 9, "name": "Anime", "cutoffFormatScore": 10000},
            {"id": 8, "name": "HD", "cutoffFormatScore": 0},
        ]
        self.series = [
            {"id": 1, "title": "Show", "qualityProfileId": 9},
            {"id": 2, "title": "Live", "qualityProfileId": 8},
        ]
        self.files: dict[int, list[dict[str, Any]]] = {
            1: [
                _file(101, "jpn/por", score=-8000, group="Anitsu"),
                _file(102, "eng", score=-10000),
                _file(103, "jpn/eng", score=12100),
                _file(104, "jpn/jpn", score=12000, group=""),
                _file(105, None, score=0),
                _file(106, "jpn", score=0),
            ],
            2: [_file(201, "eng", score=0, series_id=2)],
        }
        self.episodes: dict[int, list[dict[str, Any]]] = {
            1: [
                _episode(1001, 1, 101),
                _episode(1002, 2, 102),
                _episode(1003, 3, 103),
                _episode(1005, 5, 104),
                _episode(1004, 4, 104),
                _episode(1007, 7, 105),
                {"id": 1099, "episodeNumber": 9, "episodeFileId": 0},
            ],
            2: [_episode(2001, 1, 201)],
        }
        self.fail: dict[str, int] = {}
        self.calls: list[tuple[str, str, Any]] = []
        self.urls: list[str] = []

    def _status_for(self, key: str) -> int | None:
        return self.fail.get(key)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        self.urls.append(str(request.url))
        if path == "/api/v3/system/status":
            return httpx.Response(200, json=self.status)
        if path == "/api/v3/qualityprofile":
            return httpx.Response(200, json=self.profiles)
        if path == "/api/v3/series":
            return httpx.Response(200, json=self.series)
        if path.startswith("/api/v3/series/"):
            if code := self._status_for("series_by_id"):
                return httpx.Response(code, json=[] if code == 200 else None)
            if code := self._status_for("series_by_id_error"):
                return httpx.Response(code)
            series_id = int(path.rsplit("/", 1)[1])
            for item in self.series:
                if item["id"] == series_id:
                    return httpx.Response(200, json=item)
            return httpx.Response(404)
        if path == "/api/v3/episodefile":
            series_id = int(request.url.params["seriesId"])
            if code := self._status_for(f"files:{series_id}"):
                return httpx.Response(code)
            return httpx.Response(200, json=self.files.get(series_id, []))
        if path == "/api/v3/episode":
            if "episodeFileId" in request.url.params:
                file_id = int(request.url.params["episodeFileId"])
                return httpx.Response(
                    200,
                    json=[
                        episode
                        for episodes in self.episodes.values()
                        for episode in episodes
                        if episode.get("episodeFileId") == file_id
                    ],
                )
            series_id = int(request.url.params["seriesId"])
            return httpx.Response(200, json=self.episodes.get(series_id, []))
        if path.startswith("/api/v3/episodefile/"):
            file_id = int(path.rsplit("/", 1)[1])
            if request.method == "DELETE":
                if code := self._status_for("delete"):
                    return httpx.Response(code)
                return httpx.Response(200, content=b"")
            if code := self._status_for(f"file:{file_id}"):
                return httpx.Response(code, json=[] if code == 200 else None)
            for files in self.files.values():
                for item in files:
                    if item["id"] == file_id:
                        return httpx.Response(200, json=item)
            return httpx.Response(404)
        if path == "/api/v3/command":
            if code := self._status_for("command"):
                return httpx.Response(code)
            return httpx.Response(201, json={"id": 1})
        return httpx.Response(404)  # pragma: no cover - defensive

    def client(self) -> LanguagarrSonarrClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return LanguagarrSonarrClient(
            app="sonarr", base_url="http://sonarr", api_key="key", http_client=http
        )

    def calls_to(self, method: str, prefix: str) -> list[tuple[str, str, Any]]:
        return [
            call
            for call in self.calls
            if call[0] == method and call[1].startswith(prefix)
        ]


@pytest.fixture
def sonarr(monkeypatch) -> FakeSonarr:
    fake = FakeSonarr()
    monkeypatch.setattr(engine_module, "client_for", lambda _ctx: fake.client())
    return fake


def _service(db, **settings: Any) -> LanguagarrService:
    store = StubSettingsStore(languagarr_settings=settings or None)
    return LanguagarrService(make_ctx(db=db, settings_store=store))


def _activity(service: LanguagarrService) -> list[str]:
    return [row["action"] for row in service._ctx.db.recent_activity(50)]


# ---- client ----


def test_client_for_uses_context_sonarr_connection(db) -> None:
    client = client_for(make_ctx(db=db))
    assert client.base_url == "http://arr"
    assert client.api_key == "key"
    assert client.feature_name == "Languagarr"


async def test_client_rejects_invalid_payloads_and_propagates_errors(
    sonarr: FakeSonarr,
) -> None:
    client = sonarr.client()
    sonarr.fail["series_by_id"] = 200
    with pytest.raises(LanguagarrClientError, match="invalid series"):
        await client.series_by_id(1)
    sonarr.fail["file:101"] = 200
    with pytest.raises(LanguagarrClientError, match="invalid episode file"):
        await client.episode_file(101)
    sonarr.fail["file:101"] = 500
    with pytest.raises(LanguagarrClientError):
        await client.episode_file(101)
    assert await client.episode_file(999) is None
    await client.aclose()


async def test_client_compatibility_names_languagarr(sonarr: FakeSonarr) -> None:
    sonarr.status = {"appName": "Sonarr", "version": "3.0.10"}
    client = sonarr.client()
    result = await client.compatibility()
    assert result.ok is False
    assert (
        result.detail == "Sonarr 3.0.10 is unsupported; Languagarr requires Sonarr 4+"
    )
    await client.aclose()


# ---- scan ----


async def test_scan_flags_only_non_compliant_in_scope_files(db, sonarr) -> None:
    service = _service(db)
    service._ctx.db.languagarr_enqueue(
        [
            {
                "episode_file_id": 999,
                "series_id": 1,
                "title": "stale",
                "episode_ids": [1],
                "reason": "missing_english",
            }
        ],
        retry_before_iso="0",
    )

    payload = await service.scan()

    items = {item["episode_file_id"]: item for item in payload["results"]}
    assert sorted(items) == [101, 102, 104, 106]
    assert [item["episode_file_id"] for item in payload["unknown"]] == [105]
    assert items[101]["verdict"] == "missing_english"
    assert items[101]["recommended_action"] == "search"
    assert items[101]["release_group"] == "Anitsu"
    assert items[101]["sonarr_languages"] == ["Japanese"]
    assert items[102]["verdict"] == "single_language"
    assert items[104]["episode_ids"] == [1004, 1005]
    assert items[104]["episode_label"] == "S01E04-E05"
    assert items[104]["recommended_action"] == "delete_and_search"
    assert items[104]["release_group"] is None
    assert items[106]["episode_ids"] == []
    assert items[106]["episode_label"] == "Episode"
    assert items[101]["queue_status"] == "none"

    scan = payload["scan"]
    assert scan["series_scanned"] == 1
    assert scan["files_scanned"] == 6
    assert scan["non_compliant"] == 4
    assert scan["missing_english"] == 3
    assert scan["single_language"] == 1
    assert scan["unknown"] == 1
    assert scan["profiles_in_scope"] == ["Anime"]
    assert scan["last_scan_at"]
    assert scan["is_scanning"] is False
    # The HD-profile series is never read.
    assert any("seriesId=1" in url for url in sonarr.urls)
    assert not any("seriesId=2" in url for url in sonarr.urls)
    assert service._ctx.db.languagarr_queue_status_map() == {}
    assert "Languagarr scan completed" in _activity(service)

    status = await service.status()
    assert status["running"] is False
    assert status["queue"] == {"pending": 0, "searched": 0, "failed": 0}
    assert status["settings"]["quality_profile_names"] == ["Anime"]


async def test_scan_reports_singular_prune_message(db, sonarr) -> None:
    service = _service(db)
    service._ctx.db.languagarr_enqueue(
        [
            {
                "episode_file_id": 999,
                "series_id": 1,
                "title": "stale",
                "episode_ids": [1],
                "reason": "missing_english",
            }
        ],
        retry_before_iso="0",
    )
    await service.scan()
    details = [row["detail"] for row in service._ctx.db.recent_activity(5)]
    assert any("Removed 1 resolved queue entry." in detail for detail in details)


async def test_scan_handles_missing_season_and_media_info_shapes(db, sonarr) -> None:
    odd = _file(107, "jpn", score=5)
    odd["seasonNumber"] = None
    odd["mediaInfo"] = "not-a-dict"
    odd["languages"] = None
    sonarr.files[1] = [odd]
    # A series without a usable profile id is never in scope.
    sonarr.series.append({"id": 4, "title": "No profile", "qualityProfileId": None})
    service = _service(db)
    payload = await service.scan()
    assert payload["results"] == []
    unknown = payload["unknown"][0]
    assert unknown["season_number"] is None
    assert unknown["audio_languages"] == ""
    assert unknown["sonarr_languages"] == []
    assert not any("seriesId=4" in url for url in sonarr.urls)


async def test_scan_sorts_episodes_numerically(db, sonarr) -> None:
    sonarr.files[1] = [_file(108, "jpn", score=0), _file(109, "jpn", score=0)]
    sonarr.episodes[1] = [_episode(1100, 100, 108), _episode(1011, 11, 109)]
    payload = await _service(db).scan()
    assert [item["episode_label"] for item in payload["results"]] == [
        "S01E11",
        "S01E100",
    ]


async def test_monitored_only_skips_unmonitored_series_and_episodes(db, sonarr) -> None:
    sonarr.series.append(
        {"id": 3, "title": "Frozen", "qualityProfileId": 9, "monitored": False}
    )
    sonarr.files[3] = [_file(301, "jpn", score=0, series_id=3)]
    sonarr.episodes[3] = [_episode(3001, 1, 301)]
    # The only episode in file 101 is unmonitored.
    sonarr.episodes[1][0]["monitored"] = False

    service = _service(db)
    payload = await service.scan()

    items = {item["episode_file_id"]: item for item in payload["results"]}
    assert 301 not in items
    assert payload["scan"]["series_scanned"] == 1
    assert items[101]["episode_ids"] == []
    assert items[101]["episode_label"] == "S01E01"
    result = await service.enqueue([101])
    assert result["errors"] == [
        {"episode_file_id": 101, "error": NO_SEARCHABLE_EPISODES}
    ]

    everything = _service(db, monitored_only=False)
    payload = await everything.scan()
    items = {item["episode_file_id"]: item for item in payload["results"]}
    assert items[301]["episode_ids"] == [3001]
    assert items[101]["episode_ids"] == [1001]


async def test_delete_refuses_a_series_unmonitored_since_the_scan(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.series[0]["monitored"] = False
    result = await service.delete_and_search([104])
    assert result["errors"] == [
        {"episode_file_id": 104, "error": "Series no longer in scope"}
    ]
    assert sonarr.calls_to("DELETE", "/api/v3/episodefile") == []


async def test_scan_rejects_unknown_profile_name(db, sonarr) -> None:
    service = _service(db, quality_profile_names=["Anime", "Missing"])
    with pytest.raises(LanguagarrScopeError, match="Missing"):
        await service.scan()
    assert service._state.last_error == "Sonarr has no quality profile named Missing"
    assert "Languagarr scan failed" in _activity(service)
    assert service._state.is_scanning is False


async def test_scan_rejects_incompatible_service(db, sonarr) -> None:
    sonarr.status = {"appName": "Radarr", "version": "6.0.0"}
    service = _service(db)
    with pytest.raises(LanguagarrClientError, match="Languagarr expected Sonarr"):
        await service.scan()


async def test_scan_failure_in_one_series_publishes_nothing(db, sonarr) -> None:
    sonarr.series.append({"id": 3, "title": "Broken", "qualityProfileId": 9})
    sonarr.fail["files:3"] = 500
    service = _service(db)
    with pytest.raises(LanguagarrClientError):
        await service.scan()
    assert service._state.results == []
    assert service._state.last_scan_at is None


async def test_scan_is_rejected_while_running(db, sonarr) -> None:
    service = _service(db)
    lock = service.gate._get_lock()
    await lock.acquire()
    try:
        with pytest.raises(SyncAlreadyRunning):
            await service.scan()
    finally:
        lock.release()


# ---- queue ----


async def test_enqueue_validates_and_joins_queue_status(db, sonarr) -> None:
    service = _service(db)
    await service.scan()

    result = await service.enqueue([101, 101, 104, 106, 555])

    assert result["queued"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == [
        {"episode_file_id": 106, "error": NO_SEARCHABLE_EPISODES},
        {"episode_file_id": 555, "error": "Not in scan results"},
    ]
    assert (await service.enqueue([101]))["skipped"] == 1
    items = {
        item["episode_file_id"]: item for item in (await service.results())["results"]
    }
    assert items[101]["queue_status"] == "pending"
    assert items[102]["queue_status"] == "none"
    queue = await service.queue()
    assert queue["counts"]["pending"] == 2
    assert {row["title"] for row in queue["rows"]} == {
        "Show - S01E01",
        "Show - S01E04-E05",
    }
    assert "Languagarr searches queued" in _activity(service)


async def test_enqueue_rejects_oversized_request(db) -> None:
    service = _service(db)
    with pytest.raises(ValueError, match="At most 500"):
        await service.enqueue(list(range(501)))


async def test_enqueue_with_nothing_valid_records_no_activity(db, sonarr) -> None:
    service = _service(db)
    result = await service.enqueue([1])
    assert result["queued"] == 0
    assert "Languagarr searches queued" not in _activity(service)


async def test_run_now_sends_bounded_searches_and_records_failures(db, sonarr) -> None:
    service = _service(db, searches_per_run=2)
    await service.scan()
    await service.enqueue([101, 102, 104])

    first = await service.run_now()
    assert first == {"status": "completed", "searched": 2, "failed": 0, "resolved": 0}
    searches = sonarr.calls_to("POST", "/api/v3/command")
    assert [call[2] for call in searches] == [
        {"name": "EpisodeSearch", "episodeIds": [1001]},
        {"name": "EpisodeSearch", "episodeIds": [1002]},
    ]

    sonarr.fail["command"] = 503
    second = await service.run_now()
    assert second == {"status": "completed", "searched": 0, "failed": 1, "resolved": 0}
    counts = service._ctx.db.languagarr_queue_counts()
    assert counts == {"pending": 0, "searched": 2, "failed": 1}

    assert await service.run_now() == {
        "status": "idle",
        "searched": 0,
        "failed": 0,
        "resolved": 0,
    }
    assert "Languagarr searches sent" in _activity(service)


async def test_run_now_drops_rows_that_no_longer_need_a_search(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101, 102, 104])
    # 101 was replaced (gone), 102 is now compliant, 104 cannot be re-read.
    sonarr.files[1] = [f for f in sonarr.files[1] if f["id"] != 101]
    sonarr.files[1][0]["mediaInfo"] = {"audioLanguages": "eng/jpn"}
    sonarr.fail["file:104"] = 500

    result = await service.run_now()

    assert result == {"status": "completed", "searched": 0, "failed": 1, "resolved": 2}
    assert sonarr.calls_to("POST", "/api/v3/command") == []
    assert sorted(service._ctx.db.languagarr_queue_status_map()) == [104]
    details = [row["detail"] for row in service._ctx.db.recent_activity(5)]
    assert any("2 already resolved" in detail for detail in details)


async def test_worker_resolves_rows_whose_series_left_scope(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101, 102])
    sonarr.series[0]["monitored"] = False

    result = await service.run_now()

    assert result == {"status": "completed", "searched": 0, "failed": 0, "resolved": 2}
    assert sonarr.calls_to("POST", "/api/v3/command") == []
    assert service._ctx.db.languagarr_queue_status_map() == {}


async def test_worker_resolves_rows_whose_series_was_deleted(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101])
    sonarr.series = [item for item in sonarr.series if item["id"] != 1]

    result = await service.run_now()

    assert result["resolved"] == 1
    assert sonarr.calls_to("POST", "/api/v3/command") == []


async def test_worker_searches_only_episodes_still_monitored(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101, 104])
    # File 101's only episode and one of file 104's two episodes were unmonitored.
    for episode in sonarr.episodes[1]:
        if episode["id"] in {1001, 1005}:
            episode["monitored"] = False

    result = await service.run_now()

    assert result == {"status": "completed", "searched": 1, "failed": 0, "resolved": 1}
    assert [call[2] for call in sonarr.calls_to("POST", "/api/v3/command")] == [
        {"name": "EpisodeSearch", "episodeIds": [1004]}
    ]
    assert sorted(service._ctx.db.languagarr_queue_status_map()) == [104]


async def test_worker_without_monitored_only_skips_the_episode_lookup(
    db, sonarr
) -> None:
    service = _service(db, monitored_only=False)
    await service.scan()
    await service.enqueue([104])
    sonarr.episodes[1][3]["monitored"] = False

    result = await service.run_now()

    assert result["searched"] == 1
    assert not any("episodeFileId" in url for url in sonarr.urls)
    assert [call[2] for call in sonarr.calls_to("POST", "/api/v3/command")] == [
        {"name": "EpisodeSearch", "episodeIds": [1004, 1005]}
    ]


async def test_worker_records_series_lookup_errors_as_failures(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101])
    sonarr.fail["series_by_id_error"] = 500

    result = await service.run_now()

    assert result == {"status": "completed", "searched": 0, "failed": 1, "resolved": 0}
    assert service._ctx.db.languagarr_queue_status_map()[101]["status"] == "failed"


async def test_worker_skips_the_batch_when_scope_cannot_be_resolved(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101])
    sonarr.profiles = [{"id": 8, "name": "HD", "cutoffFormatScore": 0}]

    result = await service.run_now()

    assert result == {"status": "error", "searched": 0, "failed": 0, "resolved": 0}
    assert sonarr.calls_to("POST", "/api/v3/command") == []
    assert service._ctx.db.languagarr_queue_status_map()[101]["status"] == "pending"
    assert "Languagarr searches skipped" in _activity(service)


async def test_delete_refuses_when_series_no_longer_exists(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.series = [item for item in sonarr.series if item["id"] != 1]
    result = await service.delete_and_search([104])
    assert result["errors"] == [
        {"episode_file_id": 104, "error": "Series no longer in scope"}
    ]


async def test_failed_rows_can_be_queued_again_immediately(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    await service.enqueue([101])
    sonarr.fail["command"] = 503
    await service.run_now()
    assert service._ctx.db.languagarr_queue_status_map()[101]["status"] == "failed"
    assert (await service.enqueue([101]))["queued"] == 1


async def test_clear_pending(db, sonarr) -> None:
    service = _service(db)
    assert await service.clear_pending() == {"removed": 0}
    await service.scan()
    await service.enqueue([101])
    assert await service.clear_pending() == {"removed": 1}
    assert "Languagarr queue cleared" in _activity(service)


async def test_scheduled_run_disabled_is_a_no_op(db, sonarr) -> None:
    service = _service(db)
    assert await service.scheduled_run() == {
        "status": "disabled",
        "searched": 0,
        "failed": 0,
        "resolved": 0,
    }
    assert sonarr.calls == []


async def test_scheduled_run_auto_queue_never_queues_deletes(db, sonarr) -> None:
    service = _service(db, enabled=True, auto_queue=True, searches_per_run=10)
    result = await service.scheduled_run()
    assert result == {"status": "completed", "searched": 2, "failed": 0, "resolved": 0}
    statuses = service._ctx.db.languagarr_queue_status_map()
    assert sorted(statuses) == [101, 102]
    assert 104 not in statuses


async def test_scheduled_run_stops_when_auto_scan_fails(db, sonarr) -> None:
    sonarr.status = {"appName": "Sonarr", "version": "3.0.0"}
    service = _service(db, enabled=True, auto_queue=True)
    assert await service.scheduled_run() == {
        "status": "error",
        "searched": 0,
        "failed": 0,
        "resolved": 0,
    }
    assert sonarr.calls_to("POST", "/api/v3/command") == []


async def test_scheduled_run_without_auto_queue_only_processes_queue(
    db, sonarr
) -> None:
    service = _service(db, enabled=True)
    assert (await service.scheduled_run())["status"] == "idle"


# ---- reviewed delete ----


async def test_delete_rejects_oversized_request(db) -> None:
    service = _service(db)
    with pytest.raises(ValueError, match="At most 25"):
        await service.delete_and_search(list(range(26)))


async def test_delete_success_deletes_then_searches(db, sonarr) -> None:
    service = _service(db)
    await service.scan()

    result = await service.delete_and_search([104, 104])

    assert result == {
        "deleted": 1,
        "searched": 1,
        "failed": 0,
        "deleted_ids": [104],
        "errors": [],
    }
    mutations = [
        (method, path, body)
        for method, path, body in sonarr.calls
        if method in {"DELETE", "POST"}
    ]
    assert mutations == [
        ("DELETE", "/api/v3/episodefile/104", None),
        (
            "POST",
            "/api/v3/command",
            {"name": "EpisodeSearch", "episodeIds": [1004, 1005]},
        ),
    ]
    assert 104 not in {item.episode_file_id for item in service._state.results}
    assert service._ctx.db.languagarr_queue_status_map()[104]["status"] == "searched"
    assert "Languagarr delete completed" in _activity(service)


async def test_delete_guards_never_delete(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.files[1][0]["path"] = "/tv/Show/moved.mkv"  # 101 changed
    sonarr.files[1][1]["mediaInfo"] = {"audioLanguages": "eng/jpn"}  # 102 fixed
    sonarr.files[1] = [f for f in sonarr.files[1] if f["id"] != 104] + [
        _file(104, "jpn/jpn", score=12000)
    ]
    sonarr.series[0]["qualityProfileId"] = 8  # out of scope for 104

    result = await service.delete_and_search([101, 102, 104, 106, 555])

    errors = {entry["episode_file_id"]: entry["error"] for entry in result["errors"]}
    assert errors == {
        101: "File changed since scan",
        102: "No longer non-compliant",
        104: "Series no longer in scope",
        106: NO_SEARCHABLE_EPISODES,
        555: "Not in scan results",
    }
    assert result["deleted"] == 0
    assert result["failed"] == 5
    assert sonarr.calls_to("DELETE", "/api/v3/episodefile") == []
    assert sonarr.calls_to("POST", "/api/v3/command") == []


async def test_delete_guards_missing_file_and_recheck_errors(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.files[1] = [f for f in sonarr.files[1] if f["id"] != 101]
    sonarr.fail["file:102"] = 500

    result = await service.delete_and_search([101, 102])

    errors = {entry["episode_file_id"]: entry["error"] for entry in result["errors"]}
    assert errors[101] == "File no longer exists"
    assert errors[102].startswith("Could not re-check file:")
    assert sonarr.calls_to("DELETE", "/api/v3/episodefile") == []


async def test_delete_failure_skips_search(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.fail["delete"] = 500

    result = await service.delete_and_search([104])

    assert result["deleted"] == 0
    assert result["errors"][0]["error"].startswith("Delete failed:")
    assert sonarr.calls_to("POST", "/api/v3/command") == []
    assert 104 in {item.episode_file_id for item in service._state.results}


async def test_delete_then_search_failure_is_reported(db, sonarr) -> None:
    service = _service(db)
    await service.scan()
    sonarr.fail["command"] = 500

    result = await service.delete_and_search([104])

    assert result["deleted"] == 1
    assert result["searched"] == 0
    assert result["failed"] == 0
    assert result["errors"][0]["error"].startswith("Deleted, but the search failed:")
    assert service._ctx.db.languagarr_queue_status_map()[104]["status"] == "failed"


async def test_delete_with_unknown_profile_raises(db, sonarr) -> None:
    service = _service(db, quality_profile_names=["Gone"])
    with pytest.raises(LanguagarrScopeError):
        await service.delete_and_search([104])


# ---- settings and module wiring ----


async def test_setup_registers_callables_and_reschedules_on_interval_change(
    db, sonarr
) -> None:
    ctx = make_ctx(db=db, settings_store=StubSettingsStore())
    scheduler = AsyncMock()
    await setup(scheduler, FastAPI(), ctx)

    scheduler.add_interval.assert_awaited_once()
    assert scheduler.add_interval.await_args.kwargs == {
        "minutes": 60,
        "id": "languagarr_poll",
    }
    for name in (
        "status",
        "scan",
        "results",
        "enqueue",
        "delete",
        "queue",
        "clear_pending",
        "run_now",
        "update_settings",
    ):
        assert getattr(ctx, f"languagarr_{name}") is not None

    status = await ctx.languagarr_update_settings({"enabled": True})
    assert status["settings"]["enabled"] is True
    scheduler.reschedule_interval.assert_not_awaited()

    await ctx.languagarr_update_settings({"interval_minutes": 120})
    scheduler.reschedule_interval.assert_awaited_once()
    assert scheduler.reschedule_interval.await_args.kwargs == {
        "minutes": 120,
        "id": "languagarr_poll",
    }
    assert "Languagarr settings saved" in [
        row["action"] for row in ctx.db.recent_activity(10)
    ]

    # The scheduled job runs the worker under the gate; disabled -> no Sonarr calls.
    await ctx.languagarr_update_settings({"enabled": False})
    await languagarr_job()
    assert sonarr.calls == []
    assert languagarr_module._SERVICE is not None
