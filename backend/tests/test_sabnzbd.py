"""Tests for core.clients.sabnzbd (SABnzbd connection test)."""

from __future__ import annotations

import httpx
import pytest
import respx

from core.clients.sabnzbd import (
    SabnzbdClient,
    _format_bytes,
    _percent_value,
    _queue_activity,
    _queue_slots_from_payload,
    _slot_size_bytes,
    _timeleft_seconds,
    _unix_to_iso,
)

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
async def test_get_status_snapshot_reuses_single_queue_response() -> None:
    route = respx.get(_API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "queue": {
                        "speed": "2 M",
                        "paused": False,
                        "slots": [
                            {
                                "nzo_id": "active",
                                "filename": "Active.Show",
                                "status": "Downloading",
                                "percentage": "50",
                            },
                            {
                                "nzo_id": "queued",
                                "filename": "Queued.Show",
                                "status": "Queued",
                                "percentage": "0",
                            },
                        ],
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "history": {
                        "slots": [
                            {
                                "nzo_id": "done",
                                "name": "Finished.Show",
                                "status": "Completed",
                                "completed": 1_704_068_000,
                            }
                        ]
                    }
                },
            ),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_status_snapshot(
        queue_limit=1
    )

    assert len(route.calls) == 2
    assert route.calls[0].request.url.params["mode"] == "queue"
    assert route.calls[0].request.url.params["limit"] == "0"
    assert route.calls[1].request.url.params["mode"] == "history"
    assert route.calls[1].request.url.params["archive"] == "1"
    assert result["stats"] == {
        "online": True,
        "speed_mbps": 2.0,
        "active_downloads": 1,
        "queue_size": 2,
        "paused": False,
    }
    assert [item["name"] for item in result["activity"]["queue"]] == ["Active.Show"]
    assert [item["name"] for item in result["activity"]["history"]] == ["Finished.Show"]


@respx.mock
async def test_get_status_snapshot_offline_queue_still_returns_history() -> None:
    # A failed queue request yields offline stats and an empty queue, but the
    # The history request is independent and its completions still surface.
    respx.get(_API).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(
                200,
                json={
                    "history": {
                        "slots": [
                            {
                                "nzo_id": "done",
                                "name": "Finished.Show",
                                "status": "Completed",
                                "completed": 1_704_068_000,
                            }
                        ]
                    }
                },
            ),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_status_snapshot()

    assert result["stats"]["online"] is False
    assert result["stats"]["paused"] is False
    assert result["activity"]["queue"] == []
    assert [item["name"] for item in result["activity"]["history"]] == ["Finished.Show"]


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
        return_value=httpx.Response(
            200, json={"status": False, "error": "API Key Incorrect"}
        )
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
    respx.get(_API).mock(
        return_value=httpx.Response(200, json={"queue": {"slots": "bad"}})
    )
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
async def test_get_download_activity_parses_queue_and_history() -> None:
    route = respx.get(_API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "queue": {
                        "speed": "2.5 M",
                        "slots": [
                            {
                                "nzo_id": "SABnzbd_nzo_queue",
                                "filename": "Queued.Show.S01E01",
                                "status": "Downloading",
                                "percentage": "42",
                                "mb": "2048",
                                "size": "2.0 GB",
                                "timeleft": "0:10:30",
                                "time_added": 1_704_067_200,
                                "path": "/downloads/incomplete",
                            }
                        ],
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "history": {
                        "slots": [
                            {
                                "nzo_id": "SABnzbd_nzo_done",
                                "name": "Finished.Show.S01E01",
                                "nzb_name": "Finished.Show.S01E01.nzb",
                                "status": "Completed",
                                "size": "1.5 GB",
                                "bytes": 1_610_612_736,
                                "time_added": 1_704_060_000,
                                "completed": 1_704_068_000,
                                "storage": "/downloads/complete",
                                "url": "https://indexer.example/nzb",
                            }
                        ]
                    }
                },
            ),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_download_activity()

    assert route.calls[0].request.url.params["mode"] == "queue"
    # The queue is fetched unlimited so the uncapped depth can be counted.
    assert route.calls[0].request.url.params["limit"] == "0"
    assert route.calls[1].request.url.params["mode"] == "history"
    assert route.calls[1].request.url.params["limit"] == "10"
    assert route.calls[1].request.url.params["archive"] == "1"
    assert result["queue"] == [
        {
            "client": "sabnzbd",
            "id": "SABnzbd_nzo_queue",
            "name": "Queued.Show.S01E01",
            "status": "Downloading",
            "progress": 42,
            "size_bytes": 2 * 1024 * 1024 * 1024,
            "size_label": "2.0 GB",
            # SABnzbd exposes no per-slot speed; the queue-level speed belongs to
            # the one slot that is actually downloading.
            "speed_mbps": 2.5,
            "eta_seconds": 630,
            "added_at": "2024-01-01T00:00:00Z",
            "completed_at": None,
        }
    ]
    assert result["queue_total"] == 1
    assert result["history"] == [
        {
            "client": "sabnzbd",
            "id": "SABnzbd_nzo_done",
            "name": "Finished.Show.S01E01",
            "status": "Completed",
            "progress": 100,
            "size_bytes": 1_610_612_736,
            "size_label": "1.5 GB",
            "speed_mbps": None,
            "eta_seconds": None,
            "added_at": "2023-12-31T22:00:00Z",
            "completed_at": "2024-01-01T00:13:20Z",
        }
    ]
    assert "path" not in result["queue"][0]
    assert "storage" not in result["history"][0]
    assert "url" not in result["history"][0]


@respx.mock
async def test_get_download_activity_applies_limits() -> None:
    route = respx.get(_API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "queue": {
                        "slots": [
                            {"nzo_id": "first", "filename": "First"},
                            {"nzo_id": "second", "filename": "Second"},
                        ]
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "history": {
                        "slots": [
                            {"nzo_id": "done-1", "name": "Done 1"},
                            {"nzo_id": "done-2", "name": "Done 2"},
                        ]
                    }
                },
            ),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_download_activity(
        history_limit=1, queue_limit=1
    )

    # The queue limit is applied to the rows, not to the SABnzbd request: the
    # full queue is fetched so the cumulative total stays truthful above the cap.
    assert route.calls[0].request.url.params["limit"] == "0"
    assert route.calls[1].request.url.params["limit"] == "1"
    assert [item["name"] for item in result["queue"]] == ["First"]
    assert result["queue_total"] == 2
    assert [item["name"] for item in result["history"]] == ["Done 1"]


def _queue_payload(speed: str, *statuses: str) -> dict:
    """Build a SABnzbd queue payload with one slot per status."""
    return {
        "queue": {
            "speed": speed,
            "slots": [
                {
                    "nzo_id": f"nzo-{index}",
                    "filename": f"Job {index}",
                    "status": status,
                }
                for index, status in enumerate(statuses)
            ],
        }
    }


def test_queue_activity_credits_the_queue_speed_to_the_downloading_slot() -> None:
    # SABnzbd reports one speed for the whole queue and downloads sequentially,
    # so only the downloading slot may claim it; the idle ones report no speed.
    payload = _queue_payload("2.5 M", "Queued", "Downloading", "Queued")

    items, total = _queue_activity(payload["queue"], limit=10)

    assert [item["speed_mbps"] for item in items] == [None, 2.5, None]
    assert total == 3


def test_queue_activity_reports_no_speed_when_nothing_is_downloading() -> None:
    payload = _queue_payload("2.5 M", "Queued", "Paused")

    items, _ = _queue_activity(payload["queue"], limit=10)

    assert [item["speed_mbps"] for item in items] == [None, None]


@pytest.mark.parametrize("speed", ["0", "", "fast"])
def test_queue_activity_reports_no_speed_for_zero_or_unparseable_speed(
    speed: str,
) -> None:
    # A stalled or unreadable speed must read as "—" rather than a bogus 0.0.
    payload = _queue_payload(speed, "Downloading")

    items, _ = _queue_activity(payload["queue"], limit=10)

    assert items[0]["speed_mbps"] is None


def test_queue_activity_credits_only_the_first_of_several_downloading_slots() -> None:
    # Duplicating one figure across rows would imply twice the real throughput.
    payload = _queue_payload("2.5 M", "Downloading", "Downloading")

    items, _ = _queue_activity(payload["queue"], limit=10)

    assert [item["speed_mbps"] for item in items] == [2.5, None]


def test_queue_activity_counts_the_whole_queue_beyond_the_row_cap() -> None:
    payload = _queue_payload("1 M", "Downloading", "Queued", "Queued", "Queued")

    items, total = _queue_activity(payload["queue"], limit=2)

    assert [item["name"] for item in items] == ["Job 0", "Job 1"]
    assert total == 4


def test_queue_activity_handles_a_non_positive_row_cap() -> None:
    payload = _queue_payload("1 M", "Downloading", "Queued")

    items, total = _queue_activity(payload["queue"], limit=0)

    assert items == []
    assert total == 2


@respx.mock
async def test_get_download_activity_invalid_queue_still_returns_history() -> None:
    respx.get(_API).mock(
        side_effect=[
            httpx.Response(200, json={"queue": {"slots": "bad"}}),
            httpx.Response(
                200,
                json={"history": {"slots": [{"nzo_id": "done", "name": "Done"}]}},
            ),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_download_activity()

    assert result["queue"] == []
    assert [item["name"] for item in result["history"]] == ["Done"]


@respx.mock
async def test_get_download_activity_invalid_history_returns_empty_history() -> None:
    respx.get(_API).mock(
        side_effect=[
            httpx.Response(
                200,
                json={"queue": {"slots": [{"nzo_id": "queued", "filename": "Queued"}]}},
            ),
            httpx.Response(200, json={"history": {"slots": "bad"}}),
        ]
    )

    result = await SabnzbdClient(base_url=_BASE, api_key="x").get_download_activity()

    assert [item["name"] for item in result["queue"]] == ["Queued"]
    assert result["history"] == []


def test_queue_slots_from_payload_guards_bad_slots_and_limits() -> None:
    # `_queue_payload` already validates slots before this helper sees them, so
    # these guards are defensive; exercise them directly. Malformed slots and a
    # non-positive limit both collapse to an empty list.
    assert _queue_slots_from_payload({"slots": "bad"}, limit=5) == []
    assert _queue_slots_from_payload({"slots": [1, 2]}, limit=5) == []
    payload = {"slots": [{"nzo_id": "a"}, {"nzo_id": "b"}]}
    assert _queue_slots_from_payload(payload, limit=None) == payload["slots"]
    assert _queue_slots_from_payload(payload, limit=0) == []
    assert _queue_slots_from_payload(payload, limit=1) == [{"nzo_id": "a"}]


@respx.mock
@pytest.mark.parametrize(
    "response",
    [
        httpx.ConnectError("down"),
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json=["bad"]),
        httpx.Response(200, json={"history": "bad"}),
        httpx.Response(200, json={"history": {"slots": ["bad"]}}),
    ],
)
async def test_history_slots_failure_branches_return_empty(response) -> None:
    route = respx.get(_API)
    if isinstance(response, Exception):
        route.mock(side_effect=response)
    else:
        route.mock(return_value=response)
    result = await SabnzbdClient(base_url=_BASE, api_key="x")._history_slots(limit=1)
    assert result == []


def test_download_activity_helpers_handle_edge_cases() -> None:
    assert _slot_size_bytes({"bytes": True, "downloaded": 42}) == 42
    assert _slot_size_bytes({"bytes": -1, "mb": True, "mbleft": "bad"}) is None
    assert _percent_value(True) is None
    assert _percent_value(150) == 100
    assert _percent_value(-5) == 0
    assert _timeleft_seconds("") is None
    assert _timeleft_seconds("bad") is None
    assert _timeleft_seconds("1:bad") is None
    assert _timeleft_seconds("05:06") == 306
    assert _unix_to_iso(True) is None
    assert _format_bytes(None) is None
    assert _format_bytes(512) == "512 B"
    assert _format_bytes(1024 * 1024 * 1024 * 1024) == "1.0 TB"


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
