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
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json={"dl_info_speed": 0}))
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
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json={"dl_info_speed": "fast"}))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=[]))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_list_torrents_returns_offline() -> None:
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json={"dl_info_speed": 0}))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json={"bad": True}))
    result = await make_client().get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_dict_torrent_entry_returns_offline() -> None:
    respx.get(_TRANSFER).mock(return_value=httpx.Response(200, json={"dl_info_speed": 0}))
    respx.get(_TORRENTS).mock(return_value=httpx.Response(200, json=["not-a-dict"]))
    result = await make_client().get_stats()
    assert result["online"] is False
