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
        if data.get("queue") is not None:
            return {"ok": True, "detail": "Connected to SABnzbd"}
        return {
            "ok": False,
            "detail": data.get("error") or "SABnzbd rejected the API key",
        }

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
