"""Tests for core.clients.sabnzbd (SABnzbd connection test)."""

from __future__ import annotations

import httpx
import respx

from core.clients.sabnzbd import SabnzbdClient

_BASE = "http://sab:8080"
_API = f"{_BASE}/api"


@respx.mock
async def test_valid_key_succeeds() -> None:
    route = respx.get(_API).mock(
        return_value=httpx.Response(200, json={"queue": {"status": "Idle"}})
    )
    # Trailing slash in the base URL must be normalised away.
    result = await SabnzbdClient(base_url=_BASE + "/", api_key="zk").test_connection()
    assert result == {"ok": True, "detail": "Connected to SABnzbd"}
    assert route.calls.last.request.url.params["apikey"] == "zk"


@respx.mock
async def test_invalid_key_reports_error_body() -> None:
    # SABnzbd answers a bad key with HTTP 200 and the reason in the body.
    respx.get(_API).mock(
        return_value=httpx.Response(
            200, json={"status": False, "error": "API Key Incorrect"}
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="bad").test_connection()
    assert result == {"ok": False, "detail": "API Key Incorrect"}


@respx.mock
async def test_non_200_reports_http_status() -> None:
    respx.get(_API).mock(return_value=httpx.Response(500))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result["ok"] is False
    assert "500" in result["detail"]


@respx.mock
async def test_network_error_is_reported() -> None:
    respx.get(_API).mock(side_effect=httpx.ConnectError("down"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result["ok"] is False
    assert "down" in result["detail"]


@respx.mock
async def test_non_json_body_is_handled() -> None:
    # A 200 whose body is not JSON must degrade gracefully, not raise.
    respx.get(_API).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result == {"ok": False, "detail": "Unexpected response from SABnzbd"}


@respx.mock
async def test_non_dict_json_body_is_handled() -> None:
    # A 200 whose body is JSON but not a dict must also degrade gracefully.
    respx.get(_API).mock(return_value=httpx.Response(200, json=["unexpected"]))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").test_connection()
    assert result == {"ok": False, "detail": "Unexpected response from SABnzbd"}


@respx.mock
async def test_update_credentials_changes_target() -> None:
    new_api = "http://other:9090/api"
    route = respx.get(new_api).mock(
        return_value=httpx.Response(200, json={"queue": {}})
    )
    client = SabnzbdClient(base_url=_BASE, api_key="x")
    client.update_credentials(base_url="http://other:9090/", api_key="k2")
    result = await client.test_connection()
    assert result["ok"] is True
    assert route.calls.last.request.url.params["apikey"] == "k2"


async def test_aclose() -> None:
    await SabnzbdClient(base_url=_BASE, api_key="x").aclose()


@respx.mock
async def test_get_stats_success_m_speed() -> None:
    route = respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "2.5 M",
                    "paused": False,
                    "slots": [
                        {"status": "Downloading"},
                        {"status": "Downloading"},
                        {"status": "Queued"},
                    ],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result == {
        "online": True,
        "speed_mbps": 2.5,
        "active_downloads": 2,
        "queue_size": 3,
        "paused": False,
    }
    assert route.calls.last.request.url.params["mode"] == "queue"


@respx.mock
async def test_get_stats_k_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "512 K",
                    "paused": "True",
                    "slots": [{"status": "Downloading"}],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 0.5
    assert result["paused"] is True


@respx.mock
async def test_get_stats_b_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "1048576 B",
                    "paused": True,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 1.0
    assert result["paused"] is True


@respx.mock
async def test_get_stats_no_unit_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "3",
                    "paused": False,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 3.0


@respx.mock
async def test_get_stats_empty_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "",
                    "paused": False,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 0.0


@respx.mock
async def test_get_stats_non_numeric_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "fast",
                    "paused": False,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 0.0


@respx.mock
async def test_get_stats_invalid_float_speed() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "1.2.3 M",
                    "paused": False,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["speed_mbps"] == 0.0


@respx.mock
async def test_get_stats_numeric_paused() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "1 M",
                    "paused": 1,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["paused"] is True


@respx.mock
async def test_get_stats_unsupported_paused_type() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "queue": {
                    "speed": "1 M",
                    "paused": None,
                    "slots": [],
                }
            },
        )
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["paused"] is False


@respx.mock
async def test_get_stats_network_error_returns_offline() -> None:
    respx.get(_API).mock(side_effect=httpx.ConnectError("down"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False
    assert result["paused"] is False


@respx.mock
async def test_get_stats_non_200_returns_offline() -> None:
    respx.get(_API).mock(return_value=httpx.Response(500))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_json_returns_offline() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_invalid_key_json_returns_offline() -> None:
    # SABnzbd returns HTTP 200 with status=False for an invalid API key.
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"status": False, "error": "API Key Incorrect"})
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_dict_json_returns_offline() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json=["not", "a", "dict"]))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_dict_queue_returns_offline() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json={"queue": "bad"}))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_list_slots_returns_offline() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json={"queue": {"slots": "bad"}}))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_get_stats_non_dict_slot_returns_offline() -> None:
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"queue": {"slots": ["not-a-dict"]}})
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_stats()
    assert result["online"] is False


@respx.mock
async def test_pause_success() -> None:
    route = respx.get(_API).mock(
        return_value=httpx.Response(200, json={"status": True})
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is True
    assert route.calls.last.request.url.params["mode"] == "pause"


@respx.mock
async def test_pause_failure_non_200() -> None:
    respx.get(_API).mock(return_value=httpx.Response(500))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is False


@respx.mock
async def test_pause_failure_status_false() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json={"status": False}))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is False


@respx.mock
async def test_pause_never_raises_on_network_error() -> None:
    respx.get(_API).mock(side_effect=httpx.ConnectError("down"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is False


@respx.mock
async def test_pause_non_json_response_returns_false() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, text="not json"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is False


@respx.mock
async def test_pause_non_dict_json_response_returns_false() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json=["unexpected"]))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").pause()
    assert result is False


@respx.mock
async def test_resume_non_json_response_returns_false() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, text="not json"))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").resume()
    assert result is False


@respx.mock
async def test_resume_non_dict_json_response_returns_false() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json=["unexpected"]))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").resume()
    assert result is False


@respx.mock
async def test_resume_success() -> None:
    route = respx.get(_API).mock(
        return_value=httpx.Response(200, json={"status": True})
    )
    result = await SabnzbdClient(base_url=_BASE, api_key="x").resume()
    assert result is True
    assert route.calls.last.request.url.params["mode"] == "resume"


@respx.mock
async def test_resume_failure() -> None:
    respx.get(_API).mock(return_value=httpx.Response(200, json={"status": False}))
    result = await SabnzbdClient(base_url=_BASE, api_key="x").resume()
    assert result is False
