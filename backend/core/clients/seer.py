"""Seer API client: media status checks and request creation.

The base URL and API key are held as attributes (not baked into the HTTP client)
so they can be reconfigured from the dashboard at runtime via
:meth:`update_credentials`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import httpx

from core.animation import ANIMATION_GENRE_ID, keeps_discover_row, keeps_search_row
from core.coerce import coerce_int
from core.logging import get_logger, log_action

# Seer media availability states.
UNKNOWN = 1
PENDING = 2
PROCESSING = 3
PARTIALLY_AVAILABLE = 4
AVAILABLE = 5

# Seer request state: a person or rule refused the request.
REQUEST_DECLINED = 3

# A dead or unreachable Seer host must fail fast: the OS-level connect retry can
# take 20+ seconds per call, so the connect phase gets a tight explicit budget
# while slow-but-alive responses keep the generous overall timeout.
_DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Status buckets returned by ``GET /api/v1/request/count``.
REQUEST_COUNT_KEYS = (
    "total",
    "movie",
    "tv",
    "pending",
    "approved",
    "declined",
    "processing",
    "available",
)

# httpx errors meaning the connection itself failed — Seer was never reached.
_CONNECT_FAILURES = (httpx.ConnectError, httpx.ConnectTimeout)

# ``sortBy`` values for the Animation genre view's discover feeds, mirroring the
# TMDB client's trending (recency-weighted popularity) and popular (all-time
# vote count) proxies. Seer forwards ``sortBy`` to TMDB, but an older or
# stricter Seer may reject ``vote_count.desc``; the plan's manual verification
# checks it and names the fallback (see the "Seer sortBy" risk).
SEER_ANIMATION_TRENDING_SORT: Final = "popularity.desc"
SEER_ANIMATION_POPULAR_SORT: Final = "vote_count.desc"


def _first_present(result: dict[str, Any], *keys: str) -> Any:
    """Return the first of ``keys`` present (not ``None``) in a raw Seer result.

    Overseerr/Jellyseerr variants spell fields in camelCase or snake_case, so
    the filters read both spellings.
    """
    for key in keys:
        value = result.get(key)
        if value is not None:
            return value
    return None


def _is_non_anime_discover_result(result: dict[str, Any]) -> bool:
    """Whether a raw Animation discover result is kept (anime excluded).

    The request already filters to the Animation genre, so only a positive
    Japanese original language drops the row (see
    :func:`core.animation.keeps_discover_row`).
    """
    return keeps_discover_row(
        _first_present(result, "originalLanguage", "original_language")
    )


def _is_non_anime_animation_result(result: dict[str, Any]) -> bool:
    """Whether a raw Seer search result belongs in the Animation view.

    Search applies no genre filter, so the result must positively carry the
    Animation genre id and must not be Japanese-language (see
    :func:`core.animation.keeps_search_row`).
    """
    return keeps_search_row(
        _first_present(result, "genreIds", "genre_ids"),
        _first_present(result, "originalLanguage", "original_language"),
    )


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

    async def latest_request_declined(self, *, media_type: str, tmdb_id: int) -> bool:
        """Return whether the newest Seer request recorded for an item was declined.

        A declined request leaves the media state unknown, so Seer would accept a
        new request; callers use this to respect the refusal instead.
        """
        media_info = await self._media_info(media_type=media_type, tmdb_id=tmdb_id)
        requests = [
            request
            for request in ((media_info or {}).get("requests") or [])
            if request.get("id") is not None
        ]
        if not requests:
            return False
        latest = max(requests, key=lambda request: request["id"])
        return latest.get("status") == REQUEST_DECLINED

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
        ``mediaType`` discriminator, so the caller can filter by type. Up to
        ``pages`` consecutive pages are fetched until ``limit`` rows are held (see
        :meth:`_discover_pages`); ``pages=1`` is the single-page default.
        """
        return await self._discover_pages(
            "discover/trending",
            params={},
            default_media_type=None,
            limit=limit,
            pages=pages,
        )

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

    @classmethod
    def _accepted_rows(
        cls,
        results: list[dict[str, Any]],
        *,
        default_media_type: str | None,
        wanted_media_type: str | None,
        result_filter: Callable[[dict[str, Any]], bool] | None,
    ) -> list[dict[str, Any]]:
        """Return the discovery rows one raw Seer page contributes.

        ``result_filter`` runs on each raw result before normalisation (used
        where Seer cannot filter server-side); rows the normaliser rejects are
        dropped, and so is any row whose media type is not
        ``wanted_media_type`` when one is given (the mixed ``/search`` feed).
        """
        accepted: list[dict[str, Any]] = []
        for result in results:
            if result_filter is not None and not result_filter(result):
                continue
            row = cls._normalise_discover(result, default_media_type=default_media_type)
            if row is None:
                continue
            if wanted_media_type is not None and row["media_type"] != wanted_media_type:
                continue
            accepted.append(row)
        return accepted

    async def _discover_pages(
        self,
        path: str,
        *,
        params: dict[str, Any],
        default_media_type: str | None,
        limit: int,
        pages: int,
        wanted_media_type: str | None = None,
        result_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch up to ``pages`` consecutive pages of a Seer feed as discovery rows.

        ``params`` are sent with every page request alongside ``page``. Each
        page's rows pass through :meth:`_accepted_rows` as it arrives, and
        paging stops at the first empty *response* page (a page the filters
        empty does not stop it) or as soon as ``limit`` accepted rows are held,
        so a later page that would fail can never discard a full result set.
        Returns at most ``limit`` rows.
        """
        rows: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            results = await self._discover(path, params={**params, "page": page})
            if not results:
                break
            rows.extend(
                self._accepted_rows(
                    results,
                    default_media_type=default_media_type,
                    wanted_media_type=wanted_media_type,
                    result_filter=result_filter,
                )
            )
            if len(rows) >= limit:
                break
        return rows[:limit]

    async def discover_popular(
        self, *, media_type: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return Seer's popular movies or shows (sorted by popularity) as rows.

        Up to ``pages`` consecutive pages are fetched until ``limit`` rows are
        held (see :meth:`_discover_pages`); ``pages=1`` is the default.
        """
        endpoint = "movies" if media_type == "movie" else "tv"
        return await self._discover_pages(
            f"discover/{endpoint}",
            params={"sortBy": "popularity.desc"},
            default_media_type="movie" if media_type == "movie" else "tv",
            limit=limit,
            pages=pages,
        )

    async def discover_animation(
        self, *, media_type: str, sort_by: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return Seer's animated movies or shows, anime excluded, as rows.

        Requests ``discover/{movies|tv}`` filtered to the Animation genre and
        sorted by ``sort_by`` (:data:`SEER_ANIMATION_TRENDING_SORT` or
        :data:`SEER_ANIMATION_POPULAR_SORT`). Seer has no origin-exclusion
        filter, so Japanese-language results are dropped client-side by
        :func:`_is_non_anime_discover_result`; paging continues past a page the
        filter empties and stops once ``limit`` kept rows are held. Raises
        :class:`SeerError` like the other discover calls.
        """
        endpoint = "movies" if media_type == "movie" else "tv"
        return await self._discover_pages(
            f"discover/{endpoint}",
            params={"genre": ANIMATION_GENRE_ID, "sortBy": sort_by},
            default_media_type="movie" if media_type == "movie" else "tv",
            limit=limit,
            pages=pages,
            result_filter=_is_non_anime_discover_result,
        )

    async def search(
        self,
        *,
        media_type: str,
        query: str,
        limit: int = 20,
        pages: int = 1,
        result_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Return Seer title-search results for one media type as rows.

        Seer's ``/search`` endpoint mixes movies, shows and people in one feed:
        people are dropped by the normaliser and the other media type is
        filtered out, so fewer than ``limit`` rows can come back even when more
        matches exist. Up to ``pages`` consecutive pages are fetched until
        ``limit`` matching rows are held (see :meth:`_discover_pages`).
        ``result_filter`` drops raw results before normalisation.
        """
        return await self._discover_pages(
            "search",
            params={"query": query},
            default_media_type=None,
            limit=limit,
            pages=pages,
            wanted_media_type="movie" if media_type == "movie" else "show",
            result_filter=result_filter,
        )

    async def search_animation(
        self, *, media_type: str, query: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return Seer title-search results filtered to animation, anime excluded.

        Same request as :meth:`search`, with the raw results post-filtered by
        :func:`_is_non_anime_animation_result`: a result must carry the
        Animation genre id and must not be Japanese-language. Results without
        genre ids are dropped.
        """
        return await self.search(
            media_type=media_type,
            query=query,
            limit=limit,
            pages=pages,
            result_filter=_is_non_anime_animation_result,
        )

    async def create_request(self, *, media_type: str, tmdb_id: int) -> int | None:
        """Create a Seer request.

        Returns the new request id, or ``None`` when the response carries no id.
        ``None`` means no lasting request exists, even on a success status: Seer
        answers 202 when no seasons can be requested, and 201 with the id stripped
        when it deletes a request it could not send to Sonarr (no TVDB id).
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
        payload = response.json() if response.content else {}
        request_id = payload.get("id")
        log_action(
            self._log,
            "seer_request",
            media_type=media_type,
            tmdb=tmdb_id,
            request_id=request_id,
            status=response.status_code,
            message=payload.get("message"),
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

    async def request_counts(self) -> dict[str, int]:
        """Return request counts by status from ``/api/v1/request/count``.

        The keys are :data:`REQUEST_COUNT_KEYS` (Overseerr, Jellyseerr and Seer
        share the endpoint); a key the response omits counts as 0. Raises
        :class:`SeerUnavailableError` when Seer cannot be reached and
        :class:`SeerError` on any other failure or non-200 status.
        """
        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/request/count", headers=self._headers
            )
        except httpx.HTTPError as exc:
            raise _request_failed("Seer request count failed", exc) from exc
        if response.status_code != 200:
            raise SeerError(f"Seer request count returned {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise SeerError("Seer request count returned a non-JSON response") from exc
        if not isinstance(data, dict):
            raise SeerError("Seer request count returned an invalid payload")
        return {key: coerce_int(data.get(key), 0) for key in REQUEST_COUNT_KEYS}

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
