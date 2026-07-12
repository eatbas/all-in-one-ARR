"""Outbound qBittorrent client: validates the WebUI API key (≥ v5.2.0).

Since qBittorrent v5.2.0 (WebAPI v2.14.1) the WebUI accepts a stateless API key
instead of a username/password login: the 32-character key (``qbt_`` prefix plus
28 random characters) is sent in an ``Authorization: Bearer <key>`` header and no
session cookie is involved. API keys cannot reach the ``auth`` endpoints, so the
connection test authenticates directly against a normal endpoint — the
application version — rather than ``auth/login``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from core.bandwidth_types import DOWNLOAD_HISTORY_LIMIT
from core.logging import get_logger

_QUEUE_ITEM_LIMIT = 12

_ACTIVE_STATES = {
    "downloading",
    "stalledDL",
    "forcedDL",
    "metaDL",
    "allocating",
}
_QUEUED_STATES = {"queuedDL"}
_DOWNLOAD_QUEUE_STATES = (
    _ACTIVE_STATES
    | _QUEUED_STATES
    | {
        "pausedDL",
        "checkingDL",
    }
)
_QUEUE_STATE_PRIORITY = {
    "downloading": 0,
    "forcedDL": 0,
    "metaDL": 1,
    "allocating": 1,
    "stalledDL": 2,
    "checkingDL": 3,
    "queuedDL": 4,
    "pausedDL": 5,
}


class QbittorrentClient:
    """Async client for the qBittorrent WebUI API-key connection test."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._log = get_logger("qbittorrent")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and API key (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def test_connection(self) -> dict[str, Any]:
        """Validate the base URL + API key against ``/api/v2/app/version``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. An invalid key is answered with
        HTTP 401/403; a valid key returns the version text. A matching ``Referer``
        is sent defensively for deployments that still enforce the WebUI's
        host/CSRF checks on authenticated requests.

        A blank key is reported directly rather than sent: an empty Bearer value
        is an illegal HTTP header, so building the request would raise before any
        round-trip. The key is also stripped of stray whitespace (e.g. a trailing
        newline from a paste) for the same reason.
        """
        api_key = self._api_key.strip()
        if not api_key:
            return {"ok": False, "detail": "qBittorrent API key is not set"}
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v2/app/version",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Referer": self._base_url,
                },
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code in (401, 403):
            return {"ok": False, "detail": "qBittorrent rejected the API key"}
        if response.status_code != 200:
            return {
                "ok": False,
                "detail": f"qBittorrent returned HTTP {response.status_code}",
            }
        version = response.text.strip()
        return {
            "ok": True,
            "detail": (
                f"Connected to qBittorrent {version}"
                if version
                else "Connected to qBittorrent"
            ),
        }

    async def get_stats(self) -> dict[str, Any]:
        """Return qBittorrent transfer/torrent statistics for the dashboard.

        Fetches ``/api/v2/transfer/info`` for the current download speed and
        ``/api/v2/torrents/info`` for active/queued counts. Active states are
        ``downloading``, ``stalledDL``, ``forcedDL``, ``metaDL`` and ``allocating``;
        queued is ``queuedDL``. Returns zeros and ``online: False`` on any failure
        so the control loop never crashes because a client is temporarily down.
        """
        api_key = self._api_key.strip()
        if not api_key:
            return _offline_stats()
        payload = await self._fetch_status_payload(api_key)
        if payload is None:
            return _offline_stats()
        transfer_data, torrent_data = payload
        return _stats_from_payload(transfer_data, torrent_data)

    async def get_status_snapshot(
        self,
        *,
        history_limit: int = DOWNLOAD_HISTORY_LIMIT,
        queue_limit: int = _QUEUE_ITEM_LIMIT,
    ) -> dict[str, Any]:
        """Return aggregate stats and activity from a single torrent payload."""
        api_key = self._api_key.strip()
        if not api_key:
            return _offline_snapshot()
        payload = await self._fetch_status_payload(api_key)
        if payload is None:
            return _offline_snapshot()
        transfer_data, torrent_data = payload
        return {
            "stats": _stats_from_payload(transfer_data, torrent_data),
            "activity": _activity_from_torrents(
                torrent_data,
                history_limit=history_limit,
                queue_limit=queue_limit,
            ),
        }

    async def get_download_activity(
        self,
        *,
        history_limit: int = DOWNLOAD_HISTORY_LIMIT,
        queue_limit: int = _QUEUE_ITEM_LIMIT,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return display-safe queue and completed-download history."""
        api_key = self._api_key.strip()
        if not api_key:
            return _empty_activity()
        torrent_data = await self._fetch_torrents(api_key)
        if torrent_data is None:
            return _empty_activity()
        return _activity_from_torrents(
            torrent_data,
            history_limit=history_limit,
            queue_limit=queue_limit,
        )

    async def pause(self) -> bool:
        """Stop all torrents; return whether qBittorrent accepted the command."""
        return await self._send_torrent_command("stop")

    async def resume(self) -> bool:
        """Start all torrents; return whether qBittorrent accepted the command."""
        return await self._send_torrent_command("start")

    async def _send_torrent_command(self, command: str) -> bool:
        """Send an authenticated all-torrents command without raising."""
        api_key = self._api_key.strip()
        if not api_key:
            return False
        try:
            response = await self._client.post(
                f"{self._base_url}/api/v2/torrents/{command}",
                headers=self._headers(api_key),
                data={"hashes": "all"},
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _fetch_status_payload(
        self, api_key: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        """Fetch transfer and torrent data once for status rendering."""
        try:
            transfer = await self._client.get(
                f"{self._base_url}/api/v2/transfer/info",
                headers=self._headers(api_key),
            )
            torrents = await self._client.get(
                f"{self._base_url}/api/v2/torrents/info",
                headers=self._headers(api_key),
            )
        except httpx.HTTPError:
            return None
        if transfer.status_code != 200 or torrents.status_code != 200:
            return None
        try:
            transfer_data = transfer.json()
            torrent_data = torrents.json()
        except ValueError:
            return None
        if not isinstance(transfer_data, dict):
            return None
        if not isinstance(torrent_data, list) or not all(
            isinstance(torrent, dict) for torrent in torrent_data
        ):
            return None
        return transfer_data, torrent_data

    async def _fetch_torrents(self, api_key: str) -> list[dict[str, Any]] | None:
        """Fetch the torrent list used by standalone activity callers."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v2/torrents/info",
                headers=self._headers(api_key),
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            torrent_data = response.json()
        except ValueError:
            return None
        if not isinstance(torrent_data, list) or not all(
            isinstance(torrent, dict) for torrent in torrent_data
        ):
            return None
        return torrent_data

    def _headers(self, api_key: str) -> dict[str, str]:
        """Return the authenticated headers shared by qBittorrent requests."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Referer": self._base_url,
        }

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def _offline_stats() -> dict[str, Any]:
    """Return the zero/offline payload used by every failure branch."""
    return {
        "online": False,
        "speed_mbps": 0,
        "active_downloads": 0,
        "queue_size": 0,
    }


def _empty_activity() -> dict[str, list[dict[str, Any]]]:
    """Return an empty queue/history payload for offline or invalid responses."""
    return {"queue": [], "history": []}


def _offline_snapshot() -> dict[str, Any]:
    """Return the zero/offline aggregate plus empty activity payload."""
    return {"stats": _offline_stats(), "activity": _empty_activity()}


def _stats_from_payload(
    transfer_data: dict[str, Any], torrent_data: list[dict[str, Any]]
) -> dict[str, Any]:
    """Derive aggregate qBittorrent stats from validated API payloads."""
    speed_bps = transfer_data.get("dl_info_speed", 0) or 0
    if not isinstance(speed_bps, (int, float)):
        return _offline_stats()
    speed_mbps = round(speed_bps / 1_000_000, 2)

    active_downloads = 0
    queue_size = 0
    for torrent in torrent_data:
        state = torrent.get("state")
        if state in _ACTIVE_STATES:
            active_downloads += 1
        elif state in _QUEUED_STATES:
            queue_size += 1

    return {
        "online": True,
        "speed_mbps": speed_mbps,
        "active_downloads": active_downloads,
        "queue_size": queue_size,
    }


def _activity_from_torrents(
    torrent_data: list[dict[str, Any]],
    *,
    history_limit: int,
    queue_limit: int,
) -> dict[str, list[dict[str, Any]]]:
    """Derive display-safe activity rows from a validated torrent list."""
    queue_items = [
        _torrent_item(torrent, include_completed=False)
        for torrent in sorted(
            (
                torrent
                for torrent in torrent_data
                if torrent.get("state") in _DOWNLOAD_QUEUE_STATES
            ),
            key=_torrent_queue_sort_key,
        )
    ][: max(queue_limit, 0)]
    history_items = [
        _torrent_item(torrent, include_completed=True)
        for torrent in sorted(
            (
                torrent
                for torrent in torrent_data
                if _number_value(torrent.get("completion_on")) > 0
            ),
            key=lambda torrent: _number_value(torrent.get("completion_on")),
            reverse=True,
        )
    ][: max(history_limit, 0)]
    return {"queue": queue_items, "history": history_items}


def _torrent_queue_sort_key(torrent: dict[str, Any]) -> tuple[int, float, str]:
    """Sort active torrents before queued or paused entries, then oldest first."""
    state = torrent.get("state")
    priority = (
        _QUEUE_STATE_PRIORITY.get(state, len(_QUEUE_STATE_PRIORITY))
        if isinstance(state, str)
        else len(_QUEUE_STATE_PRIORITY)
    )
    return (
        priority,
        _number_value(torrent.get("added_on")),
        _string_value(torrent.get("name")),
    )


def _torrent_item(
    torrent: dict[str, Any], *, include_completed: bool
) -> dict[str, Any]:
    """Map a qBittorrent torrent row to the dashboard's safe display shape."""
    size_bytes = _optional_int(torrent.get("size"))
    speed_bps = _number_value(torrent.get("dlspeed"))
    speed_mbps = round(speed_bps / 1_000_000, 2) if speed_bps > 0 else None
    eta_seconds = _optional_int(torrent.get("eta"))
    if eta_seconds is not None and eta_seconds >= 8_640_000:
        eta_seconds = None
    completed_at = (
        _unix_to_iso(torrent.get("completion_on")) if include_completed else None
    )
    return {
        "client": "qbittorrent",
        "id": _string_value(torrent.get("hash")) or _string_value(torrent.get("name")),
        "name": _string_value(torrent.get("name")) or "Untitled torrent",
        "status": _string_value(torrent.get("state")) or "unknown",
        "progress": _progress_percent(torrent.get("progress")),
        "size_bytes": size_bytes,
        "size_label": _format_bytes(size_bytes) if size_bytes is not None else None,
        "speed_mbps": speed_mbps,
        "eta_seconds": eta_seconds,
        "added_at": _unix_to_iso(torrent.get("added_on")),
        "completed_at": completed_at,
    }


def _string_value(value: Any) -> str:
    """Return a stripped string for display or identifiers."""
    return value.strip() if isinstance(value, str) else ""


def _number_value(value: Any) -> float:
    """Return a numeric value, treating unsupported values as zero."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return value
    return 0


def _optional_int(value: Any) -> int | None:
    """Return a non-negative integer if the value is numeric."""
    number = _number_value(value)
    if number < 0:
        return None
    return int(number)


def _progress_percent(value: Any) -> float | None:
    """Convert qBittorrent's 0-1 progress fraction to a 0-100 percentage."""
    number = _number_value(value)
    if number <= 0:
        return 0
    return min(round(number * 100, 1), 100)


def _unix_to_iso(value: Any) -> str | None:
    """Convert a Unix timestamp to an ISO UTC string."""
    number = _number_value(value)
    if number <= 0:
        return None
    return datetime.fromtimestamp(number, UTC).isoformat().replace("+00:00", "Z")


def _format_bytes(value: int) -> str:
    """Format bytes with binary units for compact dashboard display."""
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(amount)} {units[unit_index]}"
    return f"{amount:.1f} {units[unit_index]}"
