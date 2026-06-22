"""Outbound client for a Servarr application (Sonarr or Radarr).

Distinct from :mod:`core.clients.arr`, which only *parses* inbound webhook
payloads. This is the *outbound* client: it holds a base URL + API key (managed
from the dashboard at runtime) and validates them with a connection test.

Sonarr and Radarr share the Servarr API contract, so one class serves both —
each is instantiated with its own ``name``/``base_url``/``api_key``.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger


class ArrClient:
    """Async client for the Sonarr/Radarr ``system/status`` connection test."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._name = name
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._log = get_logger(f"arr.{name}")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and API key (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def test_connection(self) -> dict[str, Any]:
        """Validate the base URL + API key against ``/api/v3/system/status``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v3/system/status",
                headers={"X-Api-Key": self._api_key},
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code == 200:
            data = response.json()
            app = data.get("appName") or self._name
            version = data.get("version")
            detail = f"Connected to {app}"
            if version:
                detail += f" {version}"
            return {"ok": True, "detail": detail}
        return {"ok": False, "detail": f"{self._name} returned HTTP {response.status_code}"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
