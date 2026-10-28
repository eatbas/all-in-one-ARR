"""Tests for the Cleanarr Servarr API helper."""

from __future__ import annotations

import httpx
import pytest
import respx

from modules.cleanarr.client import (
    CleanarrArrClient,
    CleanarrClientError,
    _flatten_messages,
)
from modules.cleanarr.models import ArrDownloadHandling, QueueItem

_SONARR = "http://sonarr"
_RADARR = "http://radarr"


def _client(app: str = "sonarr") -> CleanarrArrClient:
    return CleanarrArrClient(
        app=app, base_url=_SONARR if app == "sonarr" else _RADARR, api_key="k"
    )


def _record(record_id: int, download_id: str = "nzo", **overrides) -> dict:
    record = {
        "id": record_id,
        "downloadId": f"{download_id}{record_id}",
        "protocol": "Usenet",
        "downloadClient": "SABnzbd",
        "title": f"Release {record_id}",
        "status": "completed",
        "trackedDownloadStatus": "Warning",
        "trackedDownloadState": "importBlocked",
        "statusMessages": [
            {"title": "Release 1.mkv", "messages": ["Episode was not found"]}
        ],
        "outputPath": f"/downloads/complete/tv/Release {record_id}",
    }
    record.update(overrides)
    return record


def test_client_identity() -> None:
    client = _client()
    assert client.feature_name == "Cleanarr"
    assert client.error_class is CleanarrClientError


@respx.mock
async def test_read_queue_pages_until_total_records() -> None:
    route = respx.get(f"{_SONARR}/api/v3/queue").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"totalRecords": 3, "records": [_record(1), _record(2)]},
            ),
            httpx.Response(200, json={"totalRecords": 3, "records": [_record(3)]}),
        ]
    )
    queue = await _client().read_queue()
    assert queue.references_complete is True
    assert queue.downloads_complete is True
    assert queue.unparsed_output_paths == ()
    items = queue.items
    assert [item.queue_id for item in items] == [1, 2, 3]
    assert items[0] == QueueItem(
        app="sonarr",
        queue_id=1,
        download_id="nzo1",
        protocol="usenet",
        download_client="SABnzbd",
        title="Release 1",
        status="completed",
        tracked_status="warning",
        tracked_state="importBlocked",
        messages=("Release 1.mkv", "Episode was not found"),
        output_path="/downloads/complete/tv/Release 1",
    )
    first = route.calls[0].request.url.params
    assert first["page"] == "1"
    assert first["pageSize"] == "100"
    assert first["includeUnknownSeriesItems"] == "true"
    assert route.calls[1].request.url.params["page"] == "2"


@respx.mock
async def test_read_queue_without_total_stops_on_empty_page() -> None:
    route = respx.get(f"{_RADARR}/api/v3/queue").mock(
        side_effect=[
            httpx.Response(200, json={"records": [_record(1)]}),
            httpx.Response(200, json={"records": []}),
        ]
    )
    queue = await _client("radarr").read_queue()
    assert [item.app for item in queue.items] == ["radarr"]
    assert queue.references_complete is True
    assert route.call_count == 2
    assert route.calls[0].request.url.params["includeUnknownMovieItems"] == "true"


@pytest.mark.parametrize("queue_id", ["7", True, 1.5, None, "missing"])
@respx.mock
async def test_read_queue_keeps_records_without_a_usable_id_with_their_download(
    queue_id: object,
) -> None:
    companion = _record(
        2,
        downloadId="nzo1",
        title="Keep.This.S01E02",
        trackedDownloadState="importing",
        outputPath=" /dl/Two ",
    )
    if queue_id == "missing":
        del companion["id"]
    else:
        companion["id"] = queue_id
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        return_value=httpx.Response(
            200, json={"totalRecords": 2, "records": [_record(1), companion]}
        )
    )
    queue = await _client().read_queue()
    # The companion cannot be removed itself, but its download protection is kept.
    assert [(item.queue_id, item.download_id) for item in queue.items] == [
        (1, "nzo1"),
        (None, "nzo1"),
    ]
    assert queue.items[1].title == "Keep.This.S01E02"
    assert queue.items[1].tracked_state == "importing"
    assert queue.items[1].protocol == "usenet"
    assert queue.items[1].output_path == "/dl/Two"
    assert queue.unparsed_output_paths == ()
    assert queue.references_complete is True
    assert queue.downloads_complete is True


@respx.mock
async def test_read_queue_keeps_references_of_records_without_a_download_id() -> None:
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalRecords": 3,
                "records": [
                    {"id": 8, "downloadId": "  ", "outputPath": " /dl/Eight "},
                    {"id": 10, "outputPath": "/dl/Ten"},
                    _record(9, statusMessages=None, protocol=None),
                ],
            },
        )
    )
    queue = await _client().read_queue()
    assert len(queue.items) == 1
    assert queue.items[0].messages == ()
    assert queue.items[0].protocol == ""
    # They belong to no known download but still reference their folders.
    assert queue.unparsed_output_paths == ("/dl/Eight", "/dl/Ten")
    assert queue.references_complete is True
    assert queue.downloads_complete is True


@pytest.mark.parametrize(
    "unmatched",
    [
        {"id": 8, "downloadId": "  "},
        {"id": 8, "downloadId": None, "outputPath": None},
        {"id": 8, "outputPath": ""},
        # Paths that name no folder are no association either.
        {"id": 8, "outputPath": "/"},
        {"id": 8, "outputPath": " // "},
        {"id": 8, "outputPath": "."},
        {"id": 8, "outputPath": "/downloads/complete/.."},
        "not a dict",
    ],
)
@respx.mock
async def test_read_queue_marks_records_tied_to_nothing_incomplete(
    unmatched: object,
) -> None:
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        side_effect=[
            httpx.Response(200, json={"totalRecords": 2, "records": [_record(1)]}),
            httpx.Response(200, json={"totalRecords": 2, "records": [unmatched]}),
        ]
    )
    queue = await _client().read_queue()
    assert [item.queue_id for item in queue.items] == [1]
    assert queue.unparsed_output_paths == ()
    assert queue.downloads_complete is False


@pytest.mark.parametrize(
    "malformed",
    ["not a dict", {"id": 7, "downloadId": "nzo7", "outputPath": 42}],
)
@respx.mock
async def test_read_queue_marks_unreadable_references_incomplete(
    malformed: object,
) -> None:
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        side_effect=[
            httpx.Response(200, json={"totalRecords": 2, "records": [_record(1)]}),
            httpx.Response(200, json={"totalRecords": 2, "records": [malformed]}),
        ]
    )
    queue = await _client().read_queue()
    assert [item.queue_id for item in queue.items] == [1] + (
        [7] if isinstance(malformed, dict) else []
    )
    assert queue.references_complete is False
    # A record with a downloadId is still tied to its download.
    assert queue.downloads_complete is isinstance(malformed, dict)


@respx.mock
async def test_read_queue_empty_page_short_of_the_total_is_incomplete() -> None:
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        side_effect=[
            httpx.Response(200, json={"totalRecords": 3, "records": [_record(1)]}),
            httpx.Response(200, json={"totalRecords": 3, "records": []}),
        ]
    )
    queue = await _client().read_queue()
    assert len(queue.items) == 1
    assert queue.references_complete is False
    assert queue.downloads_complete is False


@pytest.mark.parametrize(
    "payload",
    [[_record(1)], {"records": "bad"}, None, {"totalRecords": 1}],
)
@respx.mock
async def test_read_queue_rejects_invalid_payloads(payload: object) -> None:
    respx.get(f"{_SONARR}/api/v3/queue").mock(
        return_value=httpx.Response(200, json=payload)
    )
    with pytest.raises(CleanarrClientError, match="queue payload is invalid"):
        await _client().read_queue()


def test_flatten_messages_tolerates_bad_shapes() -> None:
    assert _flatten_messages(
        [
            {"title": "A", "messages": ["one", 2, " ", "two"]},
            {"title": None, "messages": "not a list"},
            "junk",
        ]
    ) == ("A", "one", "two")
    assert _flatten_messages("junk") == ()


@respx.mock
async def test_remove_sends_blocklist_and_search_parameters() -> None:
    route = respx.delete(f"{_SONARR}/api/v3/queue/42").mock(
        return_value=httpx.Response(200)
    )
    assert await _client().remove(42) is True
    request = route.calls.last.request
    assert request.url.query == (
        b"removeFromClient=true&blocklist=true&skipRedownload=false"
    )
    assert request.headers["X-Api-Key"] == "k"


@respx.mock
async def test_remove_treats_404_as_already_gone() -> None:
    respx.delete(f"{_SONARR}/api/v3/queue/42").mock(return_value=httpx.Response(404))
    assert await _client().remove(42) is False


@respx.mock
async def test_remove_raises_on_other_errors() -> None:
    respx.delete(f"{_SONARR}/api/v3/queue/42").mock(return_value=httpx.Response(500))
    with pytest.raises(CleanarrClientError) as caught:
        await _client().remove(42)
    assert caught.value.status_code == 500


@respx.mock
async def test_download_handling_reads_config_and_sab_clients() -> None:
    respx.get(f"{_SONARR}/api/v3/config/downloadclient").mock(
        return_value=httpx.Response(
            200,
            json={
                "enableCompletedDownloadHandling": True,
                "autoRedownloadFailed": False,
            },
        )
    )
    respx.get(f"{_SONARR}/api/v3/downloadclient").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "implementation": "Sabnzbd",
                    "removeFailedDownloads": True,
                    "removeCompletedDownloads": True,
                },
                {
                    "implementation": "Sabnzbd",
                    "removeFailedDownloads": False,
                    "removeCompletedDownloads": "yes",
                },
                {"implementation": "QBittorrent", "removeFailedDownloads": False},
            ],
        )
    )
    assert await _client().download_handling() == ArrDownloadHandling(
        completed_handling=True,
        redownload_failed=False,
        remove_failed=False,
        remove_completed=True,
    )


@respx.mock
async def test_download_handling_unknown_when_fields_are_missing() -> None:
    respx.get(f"{_RADARR}/api/v3/config/downloadclient").mock(
        return_value=httpx.Response(200, json=["wrong shape"])
    )
    respx.get(f"{_RADARR}/api/v3/downloadclient").mock(
        return_value=httpx.Response(200, json={"wrong": "shape"})
    )
    assert await _client("radarr").download_handling() == ArrDownloadHandling(
        completed_handling=None,
        redownload_failed=None,
        remove_failed=None,
        remove_completed=None,
    )
