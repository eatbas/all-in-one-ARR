"""Outbound TMDB client: validates an API key against the public API.

TMDB accepts either a v3 API key (sent as an ``api_key`` query parameter) or a
v4 read-access token (a JWT sent as an ``Authorization: Bearer`` header). The key
type is detected from its shape so a user can paste either. Only a connection
test is needed for now; metadata use is out of scope.

The base URL is TMDB's fixed public endpoint and is not user-configurable, so —
unlike :mod:`core.clients.arr_client` — only the API key is held and updatable.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger

# TMDB's public API base; not user-configurable.
_BASE_URL = "https://api.themoviedb.org"


def _is_v4_token(api_key: str) -> bool:
    """Whether a key looks like a v4 read-access token (a JWT)."""
    return api_key.startswith("eyJ") and api_key.count(".") == 2


class TmdbClient:
    """Async client for the TMDB ``/3/configuration`` connection test."""

    def __init__(
        self, *, api_key: str, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._api_key = api_key
        self._log = get_logger("tmdb")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, api_key: str) -> None:
        """Replace the in-use API key (set from the dashboard)."""
        self._api_key = api_key

    async def test_connection(self) -> dict[str, Any]:
        """Validate the API key against ``/3/configuration``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. A v4 JWT is sent as a bearer token; a v3
        key is sent as the ``api_key`` query parameter.
        """
        url = f"{_BASE_URL}/3/configuration"
        if _is_v4_token(self._api_key):
            request_kwargs: dict[str, Any] = {
                "headers": {"Authorization": f"Bearer {self._api_key}"}
            }
        else:
            request_kwargs = {"params": {"api_key": self._api_key}}
        try:
            response = await self._client.get(url, **request_kwargs)
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code == 200:
            return {"ok": True, "detail": "Connected to TMDB"}
        return {"ok": False, "detail": f"TMDB returned HTTP {response.status_code}"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
