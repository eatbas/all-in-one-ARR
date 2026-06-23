"""Outbound qBittorrent client: validates the WebUI API key (≥ v5.2.0).

Since qBittorrent v5.2.0 (WebAPI v2.14.1) the WebUI accepts a stateless API key
instead of a username/password login: the 32-character key (``qbt_`` prefix plus
28 random characters) is sent in an ``Authorization: Bearer <key>`` header and no
session cookie is involved. API keys cannot reach the ``auth`` endpoints, so the
connection test authenticates directly against a normal endpoint — the
application version — rather than ``auth/login``.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger


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
        dashboard can show the reason. A missing or invalid key is answered with
        HTTP 401/403; a valid key returns the version text. A matching ``Referer``
        is sent defensively for deployments that still enforce the WebUI's
        host/CSRF checks on authenticated requests.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v2/app/version",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
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

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
