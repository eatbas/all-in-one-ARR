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
# TMDB's image CDN base and the poster size used for thumbnails.
_IMAGE_BASE = "https://image.tmdb.org/t/p"
_POSTER_SIZE = "w342"


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

    def _auth_kwargs(self) -> dict[str, Any]:
        """Build the request kwargs that authenticate the call.

        A v4 JWT is sent as a bearer token; a v3 key is sent as the ``api_key``
        query parameter. Shared by the connection test and metadata lookups.
        """
        if _is_v4_token(self._api_key):
            return {"headers": {"Authorization": f"Bearer {self._api_key}"}}
        return {"params": {"api_key": self._api_key}}

    async def test_connection(self) -> dict[str, Any]:
        """Validate the API key against ``/3/configuration``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason.
        """
        url = f"{_BASE_URL}/3/configuration"
        try:
            response = await self._client.get(url, **self._auth_kwargs())
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code == 200:
            return {"ok": True, "detail": "Connected to TMDB"}
        return {"ok": False, "detail": f"TMDB returned HTTP {response.status_code}"}

    async def fetch_poster(self, *, media_type: str, tmdb_id: int) -> bytes | None:
        """Return poster image bytes for an item, or ``None`` if unavailable.

        Resolves the ``poster_path`` from the movie/TV details endpoint, then
        downloads the image from TMDB's CDN. Never raises: any error (network,
        non-200, missing poster) degrades to ``None`` so the caller can fall back.
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        details_url = f"{_BASE_URL}/3/{endpoint}/{tmdb_id}"
        try:
            response = await self._client.get(details_url, **self._auth_kwargs())
        except httpx.HTTPError as exc:
            self._log.debug("TMDB details fetch failed for %s: %s", details_url, exc)
            return None
        if response.status_code != 200:
            return None
        poster_path = response.json().get("poster_path")
        if not poster_path:
            return None
        image_url = f"{_IMAGE_BASE}/{_POSTER_SIZE}{poster_path}"
        try:
            image = await self._client.get(image_url)
        except httpx.HTTPError as exc:
            self._log.debug("TMDB poster download failed for %s: %s", image_url, exc)
            return None
        if image.status_code != 200:
            return None
        return image.content

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
