"""Outbound OMDb client: validates an API key against the public API.

OMDb returns HTTP 200 even for an invalid key, signalling failure via the JSON
body (``"Response": "False"`` plus an ``"Error"`` message), so the test inspects
the body rather than the status alone. The base URL is OMDb's fixed public
endpoint and is not user-configurable, so only the API key is held and updatable.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger

# OMDb's public API base; not user-configurable.
_BASE_URL = "https://www.omdbapi.com"
# A stable, well-known IMDb id used only to probe the key (Ready Player One).
_PROBE_IMDB_ID = "tt3896198"


class OmdbClient:
    """Async client for the OMDb connection test."""

    def __init__(
        self, *, api_key: str, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._log = get_logger("omdb")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, api_key: str) -> None:
        """Replace the in-use API key (set from the dashboard)."""
        self._api_key = api_key

    async def test_connection(self) -> dict[str, Any]:
        """Validate the API key with a probe lookup.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. OMDb reports an invalid key in the body
        with HTTP 200, so the ``Response`` field is inspected.
        """
        try:
            response = await self._client.get(
                _BASE_URL, params={"apikey": self._api_key, "i": _PROBE_IMDB_ID}
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code != 200:
            return {"ok": False, "detail": f"OMDb returned HTTP {response.status_code}"}
        try:
            data = response.json()
        except ValueError:
            # A 200 with a non-JSON body must still degrade gracefully.
            return {"ok": False, "detail": "Unexpected response from OMDb"}
        if data.get("Response") == "True":
            return {"ok": True, "detail": "Connected to OMDb"}
        return {"ok": False, "detail": data.get("Error") or "OMDb rejected the API key"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
