"""Tests for core.clients.qbittorrent (qBittorrent WebUI API-key test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.qbittorrent import QbittorrentClient

_BASE = "http://qb:8080"
_VERSION = f"{_BASE}/api/v2/app/version"
_TRANSFER = f"{_BASE}/api/v2/transfer/info"
_TORRENTS = f"{_BASE}/api/v2/torrents/info"
_KEY = "qbt_0123456789abcdefghijklmnop"


def make_client(*, base_url=_BASE, api_key=_KEY):
    return QbittorrentClient(base_url=base_url, api_key=api_key)


@respx.mock
async def test_connection_ok_with_version() -> None:
    version = respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v5.2.0"))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.2.0"}
    # The key is sent as a Bearer token; a matching Referer is sent defensively.
    request = version.calls.last.request
    assert request.headers["Authorization"] == f"Bearer {_KEY}"
    assert request.headers["Referer"] == _BASE


@respx.mock
async def test_connection_ok_empty_version_falls_back() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(200, text=""))
    result = await make_client().test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent"}


@respx.mock
async def test_blank_key_reports_not_set_without_request() -> None:
    # An empty Bearer value is an illegal header, so no round-trip is attempted.
    route = respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v5.2.0"))
    result = await make_client(api_key="   ").test_connection()
    assert result == {"ok": False, "detail": "qBittorrent API key is not set"}
    assert not route.called


@respx.mock
async def test_key_whitespace_is_stripped_in_header() -> None:
    # A stray trailing newline from a paste would otherwise be an illegal header.
    version = respx.get(_VERSION).mock(return_value=httpx.Response(200, text="v5.2.0"))
    result = await make_client(api_key=f"  {_KEY}\n").test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.2.0"}
    assert version.calls.last.request.headers["Authorization"] == f"Bearer {_KEY}"


@respx.mock
async def test_invalid_key_401_reports_rejected() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(401))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "qBittorrent rejected the API key"}


@respx.mock
async def test_invalid_key_403_reports_rejected() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(403))
    result = await make_client().test_connection()
    assert result == {"ok": False, "detail": "qBittorrent rejected the API key"}


@respx.mock
async def test_other_status_reports_http() -> None:
    respx.get(_VERSION).mock(return_value=httpx.Response(500))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "500" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_VERSION).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_update_credentials_changes_target() -> None:
    new_version = "http://other:9090/api/v2/app/version"
    route = respx.get(new_version).mock(return_value=httpx.Response(200, text="v5.2.1"))
    client = make_client()
    client.update_credentials(base_url="http://other:9090/", api_key="qbt_new")
    result = await client.test_connection()
    assert result == {"ok": True, "detail": "Connected to qBittorrent v5.2.1"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer qbt_new"


async def test_aclose() -> None:
    await make_client().aclose()


@respx.mock
async def test_get_stats_success() -> None:
    transfer = respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": 12_500_000})
    )
    torrents = respx.get(_TORRENTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"state": "downloading"},
                {"state": "stalledDL"},
                {"state": "forcedDL"},
                {"state": "metaDL"},
                {"state": "allocating"},
                {"state": "queuedDL"},
                {"state": "uploading"},
            ],
        )
    )
    result = await make_client().get_stats()
    assert result == {
        "online": True,
        "speed_mbps": 12.5,
        "active_downloads": 5,
        "queue_size": 1,
    }
    assert transfer.calls.last.request.headers["Authorization"] == f"Bearer {_KEY}"
    assert transfer.calls.last.request.headers["Referer"] == _BASE
    assert torrents.calls.last.request.headers["Authorization"] == f"Bearer {_KEY}"


@respx.mock
async def test_get_stats_blank_key_returns_offline() -> None:
    transfer = respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json={}))
    torrents = respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client(api_key="   ").get_stats()
    assert result["online"] is False
    assert result["active_downloads"] == 0
    assert not transfer.called
    assert not torrents.called


@respx.mock
async def test_get_stats_network_error_returns_offline() -> None:
    respx.get(_TRANSFER).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_200_returns_offline() -> None:
    respx.get(_TRANSFER).mock(return_value=httpx.Response(500))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_invalid_json_returns_offline() -> None:
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, text="not json"))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_zero_speed_rounded() -> None:
    respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": 0})
    )
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is True
    assert result["speed_mbps"] == 0.0


@respx.mock
async def test_get_stats_non_dict_transfer_returns_offline() -> None:
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json=["bad"]))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_numeric_speed_returns_offline() -> None:
    respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": "fast"})
    )
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_list_torrents_returns_offline() -> None:
    respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": 0})
    )
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json={"bad": True}))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_dict_torrent_entry_returns_offline() -> None:
    respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": 0})
    )
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=["not-a-dict"]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_status_snapshot_reuses_single_torrent_response() -> None:
    transfer = respx.get(_TRANSFER).mock(
        return_value=httpx.Response(200, json={"dl_info_speed": 1_500_000})
    )
    torrents = respx.get(_TORRENTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "hash": "active",
                    "name": "Active.Movie",
                    "state": "downloading",
                    "progress": 0.5,
                    "size": 2 * 1024 * 1024,
                    "dlspeed": 1_500_000,
                    "eta": 600,
                    "added_on": 1_704_067_200,
                    "completion_on": 0,
                },
                {
                    "hash": "done",
                    "name": "Finished.Movie",
                    "state": "pausedUP",
                    "progress": 1,
                    "size": 1024,
                    "completion_on": 1_704_068_000,
                },
            ],
        )
    )

    result = await make_client().get_status_snapshot()

    assert len(transfer.calls) == 1
    assert len(torrents.calls) == 1
    assert result["stats"] == {
        "online": True,
        "speed_mbps": 1.5,
        "active_downloads": 1,
        "queue_size": 0,
    }
    assert [item["name"] for item in result["activity"]["queue"]] == ["Active.Movie"]
    assert [item["name"] for item in result["activity"]["recent"]] == ["Finished.Movie"]


@respx.mock
async def test_get_download_activity_parses_queue_and_recent_items() -> None:
    route = respx.get(_TORRENTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "hash": "queued",
                    "name": "Queued.Movie",
                    "state": "queuedDL",
                    "progress": 0.25,
                    "size": 2 * 1024 * 1024,
                    "dlspeed": 500_000,
                    "eta": -1,
                    "added_on": 1_704_067_200,
                    "completion_on": 0,
                    "content_path": "/downloads/Queued.Movie",
                },
                {
                    "hash": "bool-completion",
                    "name": "Bool.Completion",
                    "state": "uploading",
                    "completion_on": True,
                },
                {
                    "hash": "done-new",
                    "name": "Finished.New",
                    "state": "uploading",
                    "progress": 1,
                    "size": 4 * 1024 * 1024,
                    "dlspeed": 0,
                    "eta": 8_640_000,
                    "added_on": 1_704_060_000,
                    "completion_on": 1_704_068_000,
                    "save_path": "/downloads",
                },
                {
                    "hash": "done-old",
                    "name": "Finished.Old",
                    "state": "pausedUP",
                    "progress": 1,
                    "size": 1024,
                    "dlspeed": 0,
                    "eta": 0,
                    "added_on": 1_704_050_000,
                    "completion_on": 1_704_055_000,
                },
            ],
        )
    )

    result = await make_client().get_download_activity()

    assert route.calls.last.request.headers["Authorization"] == f"Bearer {_KEY}"
    assert result["queue"] == [
        {
            "client": "qbittorrent",
            "id": "queued",
            "name": "Queued.Movie",
            "status": "queuedDL",
            "progress": 25,
            "size_bytes": 2 * 1024 * 1024,
            "size_label": "2.0 MB",
            "speed_mbps": 0.5,
            "eta_seconds": None,
            "added_at": "2024-01-01T00:00:00Z",
            "completed_at": None,
        }
    ]
    assert [item["name"] for item in result["recent"]] == [
        "Finished.New",
        "Finished.Old",
    ]
    assert result["recent"][0]["completed_at"] == "2024-01-01T00:13:20Z"
    assert "content_path" not in result["queue"][0]
    assert "save_path" not in result["recent"][0]


@respx.mock
async def test_get_download_activity_applies_limits_and_queue_order() -> None:
    respx.get(_TORRENTS).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "hash": "paused",
                    "name": "Paused",
                    "state": "pausedDL",
                    "added_on": 1,
                },
                {
                    "hash": "active",
                    "name": "Active",
                    "state": "downloading",
                    "added_on": 2,
                    "completion_on": 10,
                },
                {
                    "hash": "queued",
                    "name": "Queued",
                    "state": "queuedDL",
                    "added_on": 0,
                    "completion_on": 20,
                },
            ],
        )
    )

    result = await make_client().get_download_activity(recent_limit=1, queue_limit=2)

    assert [item["name"] for item in result["queue"]] == ["Active", "Queued"]
    assert [item["name"] for item in result["recent"]] == ["Queued"]


@respx.mock
async def test_get_download_activity_blank_key_returns_empty_without_request() -> None:
    route = respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client(api_key=" ").get_download_activity()
    assert result == {"queue": [], "recent": []}
    assert not route.called


@respx.mock
async def test_get_download_activity_invalid_payload_returns_empty() -> None:
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json={"bad": True}))
    result = await make_client().get_download_activity()
    assert result == {"queue": [], "recent": []}


@respx.mock
async def test_get_download_activity_network_error_returns_empty() -> None:
    respx.get(_TORRENTS).mock(side_effect=httpx.ConnectError("down"))
    result = await make_client().get_download_activity()
    assert result == {"queue": [], "recent": []}


@respx.mock
async def test_get_download_activity_non_200_returns_empty() -> None:
    respx.get(_TORRENTS).mock(return_value=httpx.Response(500))
    result = await make_client().get_download_activity()
    assert result == {"queue": [], "recent": []}


@respx.mock
async def test_get_download_activity_invalid_json_returns_empty() -> None:
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, text="not json"))
    result = await make_client().get_download_activity()
    assert result == {"queue": [], "recent": []}
