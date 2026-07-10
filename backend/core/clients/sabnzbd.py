"""Outbound SABnzbd client: validates a URL + API key against the SABnzbd API.

SABnzbd authenticates with the API key as an ``apikey`` query parameter. The
connection test queries the (authenticated) ``queue`` endpoint: a valid key
returns a ``queue`` object, while an invalid key returns HTTP 200 with
``"status": false`` and an ``"error"`` message, so the body is inspected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from core.logging import get_logger

_RECENT_DOWNLOAD_LIMIT = 8
_QUEUE_ITEM_LIMIT = 12
_BYTES_PER_MB = 1024 * 1024


class SabnzbdClient:
    """Async client for the SABnzbd connection test."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._log = get_logger("sabnzbd")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and API key (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def test_connection(self) -> dict[str, Any]:
        """Validate the base URL + API key against the ``queue`` endpoint.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. SABnzbd reports a bad key in the body with
        HTTP 200, so a ``queue`` object (success) vs an ``error`` is inspected.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api",
                params={
                    "mode": "queue",
                    "output": "json",
                    "limit": "0",
                    "apikey": self._api_key,
                },
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code != 200:
            return {
                "ok": False,
                "detail": f"SABnzbd returned HTTP {response.status_code}",
            }
        try:
            data = response.json()
        except ValueError:
            # A 200 with a non-JSON body (e.g. a reverse-proxy interstitial)
            # must still degrade gracefully rather than raise.
            return {"ok": False, "detail": "Unexpected response from SABnzbd"}
        if not isinstance(data, dict):
            return {"ok": False, "detail": "Unexpected response from SABnzbd"}
        if data.get("queue") is not None:
            return {"ok": True, "detail": "Connected to SABnzbd"}
        return {
            "ok": False,
            "detail": data.get("error") or "SABnzbd rejected the API key",
        }

    async def get_stats(self) -> dict[str, Any]:
        """Return SABnzbd queue statistics for the dashboard.

        Queries ``mode=queue`` and parses the speed string (e.g. ``"1.2 M"`` or
        ``"500 K"``) into MB/s. Active downloads are slots whose ``status`` is
        ``"Downloading"``. Returns zeros and ``online: False`` on any failure.
        """
        queue = await self._queue_payload(limit=0)
        if queue is None:
            return _offline_stats()
        return _stats_from_queue(queue)

    async def get_status_snapshot(
        self,
        *,
        recent_limit: int = _RECENT_DOWNLOAD_LIMIT,
        queue_limit: int = _QUEUE_ITEM_LIMIT,
    ) -> dict[str, Any]:
        """Return aggregate stats and activity from one queue request."""
        queue = await self._queue_payload(limit=0)
        history_slots = await self._history_slots(limit=max(recent_limit, 0))
        if queue is None:
            return {
                "stats": _offline_stats(),
                "activity": {
                    "queue": [],
                    "recent": [_history_item(slot) for slot in history_slots],
                },
            }
        return {
            "stats": _stats_from_queue(queue),
            "activity": {
                "queue": [
                    _queue_item(slot)
                    for slot in _queue_slots_from_payload(
                        queue, limit=max(queue_limit, 0)
                    )
                ],
                "recent": [_history_item(slot) for slot in history_slots],
            },
        }

    async def get_download_activity(
        self,
        *,
        recent_limit: int = _RECENT_DOWNLOAD_LIMIT,
        queue_limit: int = _QUEUE_ITEM_LIMIT,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return display-safe queue and recent history entries."""
        queue = await self._queue_payload(limit=max(queue_limit, 0))
        queue_slots = (
            []
            if queue is None
            else _queue_slots_from_payload(queue, limit=max(queue_limit, 0))
        )
        history_slots = await self._history_slots(limit=max(recent_limit, 0))
        return {
            "queue": [_queue_item(slot) for slot in queue_slots],
            "recent": [_history_item(slot) for slot in history_slots],
        }

    async def _queue_slots(self, *, limit: int) -> list[dict[str, Any]]:
        """Fetch SABnzbd queue slots, returning an empty list on failure."""
        queue = await self._queue_payload(limit=limit)
        if queue is None:
            return []
        return _queue_slots_from_payload(queue, limit=limit)

    async def _queue_payload(self, *, limit: int) -> dict[str, Any] | None:
        """Fetch and validate a SABnzbd queue payload."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api",
                params={
                    "mode": "queue",
                    "output": "json",
                    "start": "0",
                    "limit": str(limit),
                    "apikey": self._api_key,
                },
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        queue = data.get("queue")
        if not isinstance(queue, dict):
            return None
        slots = queue.get("slots")
        if not isinstance(slots, list) or not all(
            isinstance(slot, dict) for slot in slots
        ):
            return None
        return queue

    async def _history_slots(self, *, limit: int) -> list[dict[str, Any]]:
        """Fetch SABnzbd history slots, returning an empty list on failure."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api",
                params={
                    "mode": "history",
                    "output": "json",
                    "start": "0",
                    "limit": str(limit),
                    "apikey": self._api_key,
                },
            )
        except httpx.HTTPError:
            return []
        if response.status_code != 200:
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        if not isinstance(data, dict):
            return []
        history = data.get("history")
        if not isinstance(history, dict):
            return []
        slots = history.get("slots")
        if not isinstance(slots, list) or not all(
            isinstance(slot, dict) for slot in slots
        ):
            return []
        return slots[:limit]

    async def pause(self) -> bool:
        """Pause the SABnzbd queue. Returns ``True`` if the command succeeded."""
        return await self._send_mode_command("pause")

    async def resume(self) -> bool:
        """Resume the SABnzbd queue. Returns ``True`` if the command succeeded."""
        return await self._send_mode_command("resume")

    async def _send_mode_command(self, mode: str) -> bool:
        """Send a mode command (pause/resume) and return whether it was accepted."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api",
                params={
                    "mode": mode,
                    "output": "json",
                    "apikey": self._api_key,
                },
            )
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        try:
            data = response.json()
        except ValueError:
            return False
        if not isinstance(data, dict):
            return False
        return bool(data.get("status", False))

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


def _parse_sab_speed(value: Any) -> float:
    """Convert a SABnzbd speed string such as ``"1.2 M"`` into MB/s."""
    if not isinstance(value, str) or not value.strip():
        return 0.0
    text = value.strip().upper()
    numeric = ""
    for char in text:
        if char.isdigit() or char == ".":
            numeric += char
        else:
            break
    if not numeric:
        return 0.0
    try:
        number = float(numeric)
    except ValueError:
        return 0.0
    unit = text[len(numeric) :].strip()
    if unit.startswith("K"):
        return round(number / 1024, 2)
    if unit.startswith("B"):
        return round(number / (1024 * 1024), 2)
    # "M" or no unit: treat as MB/s.
    return round(number, 2)


def _offline_stats() -> dict[str, Any]:
    """Return the zero/offline payload used by every failure branch."""
    return {
        "online": False,
        "speed_mbps": 0,
        "active_downloads": 0,
        "queue_size": 0,
        "paused": False,
    }


def _stats_from_queue(queue: dict[str, Any]) -> dict[str, Any]:
    """Derive aggregate SABnzbd stats from a validated queue payload."""
    slots = _queue_slots_from_payload(queue, limit=None)
    speed_mbps = _parse_sab_speed(queue.get("speed"))
    active_downloads = sum(1 for slot in slots if slot.get("status") == "Downloading")
    paused = _parse_sab_bool(queue.get("paused"))

    return {
        "online": True,
        "speed_mbps": speed_mbps,
        "active_downloads": active_downloads,
        "queue_size": len(slots),
        "paused": paused,
    }


def _queue_slots_from_payload(
    queue: dict[str, Any], *, limit: int | None
) -> list[dict[str, Any]]:
    """Return validated queue slots, applying an optional activity limit."""
    slots = queue.get("slots")
    if not isinstance(slots, list) or not all(isinstance(slot, dict) for slot in slots):
        return []
    if limit is None:
        return slots
    if limit <= 0:
        return []
    return slots[:limit]


def _queue_item(slot: dict[str, Any]) -> dict[str, Any]:
    """Map a SABnzbd queue slot to the dashboard's safe display shape."""
    size_bytes = _slot_size_bytes(slot)
    return {
        "client": "sabnzbd",
        "id": _string_value(slot.get("nzo_id")) or _string_value(slot.get("filename")),
        "name": _string_value(slot.get("filename")) or "Untitled NZB",
        "status": _string_value(slot.get("status")) or "unknown",
        "progress": _percent_value(slot.get("percentage")),
        "size_bytes": size_bytes,
        "size_label": _string_value(slot.get("size")) or _format_bytes(size_bytes),
        "speed_mbps": None,
        "eta_seconds": _timeleft_seconds(slot.get("timeleft")),
        "added_at": _unix_to_iso(slot.get("time_added")),
        "completed_at": None,
    }


def _history_item(slot: dict[str, Any]) -> dict[str, Any]:
    """Map a SABnzbd history slot to the dashboard's safe display shape."""
    size_bytes = _slot_size_bytes(slot)
    return {
        "client": "sabnzbd",
        "id": _string_value(slot.get("nzo_id")) or _string_value(slot.get("name")),
        "name": _string_value(slot.get("name"))
        or _string_value(slot.get("nzb_name"))
        or "Untitled NZB",
        "status": _string_value(slot.get("status")) or "unknown",
        "progress": 100 if _string_value(slot.get("status")) == "Completed" else None,
        "size_bytes": size_bytes,
        "size_label": _string_value(slot.get("size")) or _format_bytes(size_bytes),
        "speed_mbps": None,
        "eta_seconds": None,
        "added_at": _unix_to_iso(slot.get("time_added")),
        "completed_at": _unix_to_iso(slot.get("completed")),
    }


def _parse_sab_bool(value: Any) -> bool:
    """Normalise SABnzbd's various boolean representations to ``bool``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False


def _string_value(value: Any) -> str:
    """Return a stripped string for display or identifiers."""
    return value.strip() if isinstance(value, str) else ""


def _slot_size_bytes(slot: dict[str, Any]) -> int | None:
    """Return the best available SABnzbd slot size as bytes."""
    for key in ("bytes", "downloaded"):
        value = slot.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
    for key in ("mb", "mbleft"):
        value = _float_from_text(slot.get(key))
        if value is not None:
            return int(value * _BYTES_PER_MB)
    return None


def _float_from_text(value: Any) -> float | None:
    """Parse SABnzbd numeric string fragments without raising."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _percent_value(value: Any) -> float | None:
    """Parse a 0-100 percentage from SABnzbd's string fields."""
    number = _float_from_text(value)
    if number is None:
        return None
    return min(max(round(number, 1), 0), 100)


def _timeleft_seconds(value: Any) -> int | None:
    """Parse SABnzbd ``H:MM:SS`` style time-left strings."""
    if not isinstance(value, str) or not value.strip():
        return None
    parts = value.strip().split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds
    hours, minutes, seconds = numbers
    return hours * 3600 + minutes * 60 + seconds


def _unix_to_iso(value: Any) -> str | None:
    """Convert a Unix timestamp to an ISO UTC string."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def _format_bytes(value: int | None) -> str | None:
    """Format bytes with binary units for compact dashboard display."""
    if value is None:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    unit_index = 0
    while amount >= 1024 and unit_index < len(units) - 1:
        amount /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(amount)} {units[unit_index]}"
    return f"{amount:.1f} {units[unit_index]}"
