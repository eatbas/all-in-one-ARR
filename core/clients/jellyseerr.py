"""Jellyseerr API client: media status checks and request creation.

Request creation honours the live DRY_RUN flag via the injected
``dry_run_provider`` callable.
"""

from __future__ import annotations

from typing import Any, Callable

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
        dry_run_provider: Callable[[], bool],
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._dry_run_provider = dry_run_provider
        self._log = get_logger("jellyseerr")
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=30.0,
        )

    async def get_status(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Return the Jellyseerr ``mediaInfo.status`` for an item.

        Returns ``None`` when the item is not yet known to Jellyseerr (no
        ``mediaInfo``) or when Jellyseerr reports it as not found (404).
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        try:
            response = await self._client.get(f"/api/v1/{endpoint}/{tmdb_id}")
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
        """Create a Jellyseerr request; honours DRY_RUN.

        Returns the new request id, or ``None`` in DRY_RUN mode.
        """
        body: dict[str, Any] = {"mediaType": media_type, "mediaId": tmdb_id}
        if media_type == "tv":
            body["seasons"] = "all"

        if self._dry_run_provider():
            log_action(
                self._log,
                "jellyseerr_request_skipped",
                dry_run=True,
                media_type=media_type,
                tmdb=tmdb_id,
            )
            return None

        try:
            response = await self._client.post("/api/v1/request", json=body)
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
            dry_run=False,
            media_type=media_type,
            tmdb=tmdb_id,
            request_id=request_id,
        )
        return request_id

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
