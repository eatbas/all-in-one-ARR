"""Jellyseerr API client: media status checks and request creation.

The base URL and API key are held as attributes (not baked into the HTTP client)
so they can be reconfigured from the dashboard at runtime via
:meth:`update_credentials`.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger, log_action

# Jellyseerr media availability states.
UNKNOWN = 1
PENDING = 2
PROCESSING = 3
PARTIALLY_AVAILABLE = 4
AVAILABLE = 5


class JellyseerrError(RuntimeError):
    """Raised when a Jellyseerr call fails in a way the loop should record."""


class JellyseerrClient:
    """Async client for the subset of the Jellyseerr API the service needs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._log = get_logger("jellyseerr")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and API key (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key}

    async def get_status(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Return the Jellyseerr ``mediaInfo.status`` for an item.

        Returns ``None`` when the item is not yet known to Jellyseerr (no
        ``mediaInfo``) or when Jellyseerr reports it as not found (404).
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/{endpoint}/{tmdb_id}", headers=self._headers
            )
        except httpx.HTTPError as exc:  # network/timeout
            raise JellyseerrError(f"Jellyseerr status request failed: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise JellyseerrError(
                f"Jellyseerr status returned {response.status_code} for {tmdb_id}"
            )
        media_info = response.json().get("mediaInfo")
        if not media_info:
            return None
        return media_info.get("status")

    async def create_request(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Create a Jellyseerr request.

        Returns the new request id, or ``None`` when the response carries no id.
        """
        body: dict[str, Any] = {"mediaType": media_type, "mediaId": tmdb_id}
        if media_type == "tv":
            body["seasons"] = "all"

        try:
            response = await self._client.post(
                f"{self._base_url}/api/v1/request", json=body, headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise JellyseerrError(f"Jellyseerr request failed: {exc}") from exc
        if response.status_code not in (200, 201):
            raise JellyseerrError(
                f"Jellyseerr request returned {response.status_code} for {tmdb_id}"
            )
        request_id = response.json().get("id")
        log_action(
            self._log,
            "jellyseerr_request",
            media_type=media_type,
            tmdb=tmdb_id,
            request_id=request_id,
        )
        return request_id

    async def delete_request(self, *, request_id: int) -> None:
        """Delete a Jellyseerr request without touching Radarr/Sonarr media."""
        try:
            response = await self._client.delete(
                f"{self._base_url}/api/v1/request/{request_id}",
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise JellyseerrError(
                f"Jellyseerr request delete failed: {exc}"
            ) from exc
        if response.status_code == 404:
            log_action(
                self._log,
                "jellyseerr_request_missing",
                request_id=request_id,
            )
            return
        if response.status_code not in (200, 202, 204):
            raise JellyseerrError(
                f"Jellyseerr request delete returned {response.status_code} "
                f"for request {request_id}"
            )
        log_action(
            self._log,
            "jellyseerr_request_deleted",
            request_id=request_id,
        )

    async def test_connection(self) -> dict[str, Any]:
        """Validate the base URL + API key against ``/api/v1/auth/me``.

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/auth/me", headers=self._headers
            )
        except httpx.HTTPError as exc:
            return {"ok": False, "detail": f"Connection failed: {exc}"}
        if response.status_code == 200:
            data = response.json()
            user = data.get("displayName") or data.get("username") or data.get("email")
            return {"ok": True, "detail": f"Connected as {user}" if user else "Connected"}
        return {"ok": False, "detail": f"Jellyseerr returned HTTP {response.status_code}"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


from core.logging import log_action  # noqa: E402  (kept next to get_logger usage)
