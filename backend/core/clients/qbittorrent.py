"""Outbound qBittorrent client: validates WebUI credentials via login.

qBittorrent's WebUI authenticates with a username/password login that sets a
session cookie; there is no API key. The connection test performs the login
(qBittorrent requires a matching ``Referer`` header for CSRF protection) and, on
success, reads the application version using the session cookie carried by the
shared HTTP client.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger


class QbittorrentClient:
    """Async client for the qBittorrent WebUI login connection test."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._log = get_logger("qbittorrent")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(
        self, *, base_url: str, username: str, password: str
    ) -> None:
        """Replace the in-use base URL and login (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password

    async def test_connection(self) -> dict[str, Any]:
        """Validate the base URL + login against ``/api/v2/auth/login``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. qBittorrent answers the login with the
        text ``Ok.`` (cookie set) or ``Fails.`` and rejects a missing/mismatched
        ``Referer`` with HTTP 403.
        """
        try:
            response = await self._client.post(
                f"{self._base_url}/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
                headers={"Referer": self._base_url},
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code == 403:
            return {
                "ok": False,
                "detail": "qBittorrent refused the request (HTTP 403)",
            }
        if response.status_code != 200:
            return {
                "ok": False,
                "detail": f"qBittorrent returned HTTP {response.status_code}",
            }
        if response.text.strip() != "Ok.":
            return {"ok": False, "detail": "Invalid username or password"}
        return {"ok": True, "detail": await self._version_detail()}

    async def _version_detail(self) -> str:
        """Read the app version after a successful login; degrade gracefully."""
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v2/app/version",
                headers={"Referer": self._base_url},
            )
        except httpx.HTTPError:
            return "Connected to qBittorrent"
        if response.status_code == 200 and response.text:
            return f"Connected to qBittorrent {response.text.strip()}"
        return "Connected to qBittorrent"

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
