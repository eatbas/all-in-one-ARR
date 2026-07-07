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

# A dead or unreachable Seer host must fail fast: the OS-level connect retry can
# take 20+ seconds per call, so the connect phase gets a tight explicit budget
# while slow-but-alive responses keep the generous overall timeout.
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# httpx errors meaning the connection itself failed — Seer was never reached.
_CONNECT_FAILURES = (httpx.ConnectError, httpx.ConnectTimeout)


class SeerError(RuntimeError):
    """Raised when a Seer call fails in a way the loop should record."""


class SeerUnavailableError(SeerError):
    """Raised when Seer cannot be reached at all (connection failure or timeout).

    Distinguished from the base :class:`SeerError` so callers looping over many
    items can stop hammering a dead Seer for the rest of a cycle instead of
    paying the connect timeout for every remaining item.
    """


def _request_failed(message: str, exc: httpx.HTTPError) -> SeerError:
    """Wrap an httpx error, classifying connection-level failures as unavailable."""
    if isinstance(exc, _CONNECT_FAILURES):
        return SeerUnavailableError(f"{message}: {exc}")
    return SeerError(f"{message}: {exc}")


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
        self._client = http_client or httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)

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
            raise _request_failed("Seer status request failed", exc) from exc
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

    @staticmethod
    def _normalise_discover(
        result: dict[str, Any], default_media_type: str | None = None
    ) -> dict[str, Any] | None:
        """Normalise a Seer discover result into a uniform discovery row.

        Returns ``None`` for entries that are not movies or TV shows (the trending
        feed also includes people). Field names are read defensively (camelCase or
        snake_case) so the parser survives Overseerr/Jellyseerr response variants.
        The shape matches the Trakt and TMDB clients' rows.
        """
        media_type = result.get("mediaType") or default_media_type
        if media_type not in ("movie", "tv"):
            return None
        media_info = result.get("mediaInfo") or {}
        date = (
            result.get("releaseDate")
            or result.get("release_date")
            or result.get("firstAirDate")
            or result.get("first_air_date")
            or ""
        )
        year = int(date[:4]) if date[:4].isdigit() else None
        return {
            "media_type": "movie" if media_type == "movie" else "show",
            "tmdb": result.get("id"),
            "title": result.get("title") or result.get("name"),
            "year": year,
            "seer_status": media_info.get("status"),
        }

    async def _discover(
        self, path: str, *, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Fetch a Seer discover endpoint's raw ``results`` array.

        Raises :class:`SeerError` on a network failure or any non-200 status, so a
        dead Seer connection surfaces to the caller (the router degrades it to an
        empty feed).
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/{path}", headers=self._headers, params=params
            )
        except httpx.HTTPError as exc:
            raise _request_failed("Seer discover request failed", exc) from exc
        if response.status_code != 200:
            raise SeerError(f"Seer discover returned {response.status_code} for {path}")
        return response.json().get("results") or []

    async def discover_trending(
        self, *, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return Seer's trending feed (mixed movies and shows) as discovery rows.

        People entries are dropped; each row carries its own ``media_type`` from the
        ``mediaType`` discriminator, so the caller can filter by type. ``pages``
        consecutive pages are fetched and concatenated before the ``limit`` cap (an
        empty page short-circuits the rest); ``pages=1`` is the single-page default.
        """
        rows: list[dict[str, Any] | None] = []
        for page in range(1, pages + 1):
            results = await self._discover("discover/trending", params={"page": page})
            if not results:
                break
            rows.extend(self._normalise_discover(result) for result in results)
        return [row for row in rows if row is not None][:limit]

    async def discover_trending_buckets(
        self, *, limit_per_media: int = 20, pages: int = 1
    ) -> dict[str, list[dict[str, Any]]]:
        """Return Seer's mixed trending feed split into movie and show buckets.

        The upstream endpoint is mixed, so a caller that wants ``N`` movies and
        ``N`` shows must not cap the aggregate list before filtering. This fetches
        bounded pages until both media buckets are full or the endpoint is
        exhausted. Duplicate TMDB ids are counted once per media type.
        """
        buckets: dict[str, list[dict[str, Any]]] = {"movie": [], "show": []}
        if limit_per_media <= 0 or pages <= 0:
            return buckets

        seen: set[tuple[str, int]] = set()
        for page in range(1, pages + 1):
            results = await self._discover("discover/trending", params={"page": page})
            if not results:
                break
            for result in results:
                row = self._normalise_discover(result)
                if row is None:
                    continue
                media_type = row["media_type"]
                bucket = buckets[media_type]
                if len(bucket) >= limit_per_media:
                    continue
                tmdb = row.get("tmdb")
                if isinstance(tmdb, int):
                    key = (media_type, tmdb)
                    if key in seen:
                        continue
                    seen.add(key)
                bucket.append(row)
            if all(len(bucket) >= limit_per_media for bucket in buckets.values()):
                break
        return buckets

    async def discover_popular(
        self, *, media_type: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return Seer's popular movies or shows (sorted by popularity) as rows.

        ``pages`` consecutive pages are fetched and concatenated before the ``limit``
        cap (an empty page short-circuits the rest); ``pages=1`` is the default.
        """
        endpoint = "movies" if media_type == "movie" else "tv"
        default = "movie" if media_type == "movie" else "tv"
        rows: list[dict[str, Any] | None] = []
        for page in range(1, pages + 1):
            results = await self._discover(
                f"discover/{endpoint}",
                params={"sortBy": "popularity.desc", "page": page},
            )
            if not results:
                break
            rows.extend(
                self._normalise_discover(result, default_media_type=default)
                for result in results
            )
        return [row for row in rows if row is not None][:limit]

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
            raise _request_failed("Seer request failed", exc) from exc
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
            raise _request_failed("Seer request delete failed", exc) from exc
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
            return {
                "ok": True,
                "detail": f"Connected as {user}" if user else "Connected",
            }
        return {"ok": False, "detail": f"Seer returned HTTP {response.status_code}"}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
