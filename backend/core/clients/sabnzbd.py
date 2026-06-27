"""Outbound SABnzbd client: validates a URL + API key against the SABnzbd API.

SABnzbd authenticates with the API key as an ``apikey`` query parameter. The
connection test queries the (authenticated) ``queue`` endpoint: a valid key
returns a ``queue`` object, while an invalid key returns HTTP 200 with
``"status": false`` and an ``"error"`` message, so the body is inspected.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger


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
        except httpx.HTTPError:
            return _offline_stats()
        if response.status_code != 200:
            return _offline_stats()
        try:
            data = response.json()
        except ValueError:
            return _offline_stats()

        if not isinstance(data, dict):
            return _offline_stats()
        queue = data.get("queue")
        if not isinstance(queue, dict):
            return _offline_stats()
        slots = queue.get("slots")
        if not isinstance(slots, list) or not all(
            isinstance(slot, dict) for slot in slots
        ):
            return _offline_stats()

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
    unit = text[len(numeric):].strip()
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


def _parse_sab_bool(value: Any) -> bool:
    """Normalise SABnzbd's various boolean representations to ``bool``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False
