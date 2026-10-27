"""Tests for core.clients.servarr_stats (dashboard Sonarr/Radarr statistics)."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.servarr_stats import (
    ServarrStatsClient,
    ServarrStatsError,
    stats_client_for,
)

_BASE = "http://arr:8989"


def _client(app: str = "sonarr", *, api_key: str = "key") -> ServarrStatsClient:
    return ServarrStatsClient(app=app, base_url=_BASE + "/", api_key=api_key)


@respx.mock
async def test_sonarr_library_stats_aggregates_series() -> None:
    route = respx.get(f"{_BASE}/api/v3/series").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "monitored": True,
                    "statistics": {
                        "episodeCount": 10,
                        "episodeFileCount": 8,
                        "sizeOnDisk": 1000,
                    },
                },
                {
                    "monitored": False,
                    "statistics": {"episodeCount": "5", "sizeOnDisk": None},
                },
                {"monitored": True},
                "not-a-row",
            ],
        )
    )
    client = _client()

    stats = await client.library_stats()

    assert stats == {
        "series_total": 3,
        "series_monitored": 2,
        "episodes_total": 15,
        "episodes_with_files": 8,
        "size_on_disk_bytes": 1000,
    }
    assert route.calls.last.request.headers["X-Api-Key"] == "key"
    await client.aclose()


@respx.mock
async def test_radarr_library_stats_aggregates_movies() -> None:
    respx.get(f"{_BASE}/api/v3/movie").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"monitored": True, "hasFile": True, "sizeOnDisk": 700},
                {"monitored": True, "hasFile": False, "sizeOnDisk": 0},
                {"monitored": False, "hasFile": True},
            ],
        )
    )
    client = _client("radarr")

    assert await client.library_stats() == {
        "movies_total": 3,
        "movies_monitored": 2,
        "movies_with_files": 2,
        "size_on_disk_bytes": 700,
    }


@respx.mock
async def test_disk_space_maps_fields_and_deduplicates_paths() -> None:
    respx.get(f"{_BASE}/api/v3/diskspace").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "path": "/data",
                    "label": "Media",
                    "freeSpace": 100,
                    "totalSpace": 400,
                },
                {"path": "/data", "label": "Dup", "freeSpace": 1, "totalSpace": 2},
                {"path": "/config", "label": "", "freeSpace": "x"},
                {"label": "no path"},
                {"path": ""},
                42,
            ],
        )
    )

    disks = await _client().disk_space()

    assert disks == [
        {"path": "/data", "label": "Media", "free_bytes": 100, "total_bytes": 400},
        {"path": "/config", "label": None, "free_bytes": 0, "total_bytes": 0},
    ]


@respx.mock
async def test_queue_and_missing_totals_read_total_records() -> None:
    queue = respx.get(f"{_BASE}/api/v3/queue").mock(
        return_value=httpx.Response(200, json={"totalRecords": 7, "records": [{}]})
    )
    missing = respx.get(f"{_BASE}/api/v3/wanted/missing").mock(
        return_value=httpx.Response(200, json={"totalRecords": "bad"})
    )
    client = _client()

    assert await client.queue_total() == 7
    assert await client.missing_total() == 0
    assert queue.calls.last.request.url.params["pageSize"] == "1"
    assert missing.calls.last.request.url.params["page"] == "1"


@respx.mock
async def test_total_records_falls_back_to_list_length() -> None:
    respx.get(f"{_BASE}/api/v3/queue").mock(
        return_value=httpx.Response(200, json=[{}, {}, {}])
    )
    assert await _client().queue_total() == 3


@respx.mock
@pytest.mark.parametrize(
    ("path", "call"),
    [
        ("/api/v3/series", "library_stats"),
        ("/api/v3/diskspace", "disk_space"),
        ("/api/v3/queue", "queue_total"),
    ],
)
async def test_malformed_payload_raises(path: str, call: str) -> None:
    respx.get(f"{_BASE}{path}").mock(return_value=httpx.Response(200, json="nope"))
    with pytest.raises(ServarrStatsError, match="invalid"):
        await getattr(_client(), call)()


@respx.mock
async def test_http_error_raises_with_status_code() -> None:
    respx.get(f"{_BASE}/api/v3/diskspace").mock(return_value=httpx.Response(500))
    with pytest.raises(ServarrStatsError) as excinfo:
        await _client().disk_space()
    assert excinfo.value.status_code == 500
    assert "key" not in str(excinfo.value).replace("/api/", "")


@respx.mock
async def test_transport_error_raises_without_status_code() -> None:
    respx.get(f"{_BASE}/api/v3/queue").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(ServarrStatsError) as excinfo:
        await _client().queue_total()
    assert excinfo.value.status_code is None


@respx.mock(assert_all_called=False)
async def test_unconfigured_client_raises_before_any_request() -> None:
    route = respx.get(f"{_BASE}/api/v3/series")
    with pytest.raises(ServarrStatsError, match="not configured"):
        await _client(api_key="").library_stats()
    assert not route.called


def test_stats_client_for_copies_connection_fields() -> None:
    class _Source:
        def connection_fields(self) -> dict[str, str]:
            return {"base_url": "http://radarr:7878", "api_key": "secret"}

    client = stats_client_for(_Source(), app="radarr")  # type: ignore[arg-type]

    assert isinstance(client, ServarrStatsClient)
    assert client.app == "radarr"
    assert client.base_url == "http://radarr:7878"
    assert client.api_key == "secret"
    assert client.feature_name == "Dashboard"
