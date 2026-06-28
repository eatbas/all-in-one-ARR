"""Seer API client: media status checks and request creation.

The base URL and API key are held as attributes (not baked into the HTTP client)
so they can be reconfigured from the dashboard at runtime via
:meth:`update_credentials`.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger, log_action

# Seer media availability states.
UNKNOWN = 1
PENDING = 2
PROCESSING = 3
PARTIALLY_AVAILABLE = 4
AVAILABLE = 5


class SeerError(RuntimeError):
    """Raised when a Seer call fails in a way the loop should record."""


class SeerClient:
    """Async client for the subset of the Seer API the service needs."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._log = get_logger("seer")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and API key (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key}

    async def _media_info(
        self, *, media_type: str, tmdb_id: int
    ) -> dict[str, Any] | None:
        """Fetch an item's ``mediaInfo`` block (``None`` when Seer has no record).

        Shared by :meth:`get_status` and :meth:`get_request_ids`. Returns ``None``
        on a 404 or when the response carries no ``mediaInfo``; raises
        :class:`SeerError` on a network failure or any other non-200 status.
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/{endpoint}/{tmdb_id}", headers=self._headers
            )
        except httpx.HTTPError as exc:  # network/timeout
            raise SeerError(f"Seer status request failed: {exc}") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SeerError(
                f"Seer status returned {response.status_code} for {tmdb_id}"
            )
        return response.json().get("mediaInfo")

    async def get_status(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Return the Seer ``mediaInfo.status`` for an item.

        Returns ``None`` when the item is not yet known to Seer (no
        ``mediaInfo``) or when Seer reports it as not found (404).
        """
        media_info = await self._media_info(media_type=media_type, tmdb_id=tmdb_id)
        if not media_info:
            return None
        return media_info.get("status")

    async def get_request_ids(self, *, media_type: str, tmdb_id: int) -> list[int]:
        """Return the ids of every Seer request recorded for an item.

        Used to clean up a request this app did not create (so no id was stored):
        the ids are read from ``mediaInfo.requests``. Returns an empty list when
        Seer has no record of the item or it carries no requests.
        """
        media_info = await self._media_info(media_type=media_type, tmdb_id=tmdb_id)
        if not media_info:
            return []
        return [
            request["id"]
            for request in (media_info.get("requests") or [])
            if request.get("id") is not None
        ]

    async def create_request(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Create a Seer request.

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
            raise SeerError(f"Seer request failed: {exc}") from exc
        if response.status_code not in (200, 201, 202):
            raise SeerError(
                f"Seer request returned {response.status_code} for {tmdb_id}"
            )
        request_id = response.json().get("id") if response.content else None
        log_action(
            self._log,
            "seer_request",
            media_type=media_type,
            tmdb=tmdb_id,
            request_id=request_id,
        )
        return request_id

    async def delete_request(self, *, request_id: int) -> None:
        """Delete a Seer request without touching Radarr/Sonarr media."""
        try:
            response = await self._client.delete(
                f"{self._base_url}/api/v1/request/{request_id}",
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            raise SeerError(
                f"Seer request delete failed: {exc}"
            ) from exc
        if response.status_code == 404:
            log_action(
                self._log,
                "seer_request_missing",
                request_id=request_id,
            )
            return
        if response.status_code not in (200, 202, 204):
            raise SeerError(
                f"Seer request delete returned {response.status_code} "
                f"for request {request_id}"
            )
        log_action(
            self._log,
            "seer_request_deleted",
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
        return {"ok": False, "detail": f"Seer returned HTTP {response.status_code}"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
