"""Outbound TMDB client: validates an API key against the public API.

TMDB accepts either a v3 API key (sent as an ``api_key`` query parameter) or a
v4 read-access token (a JWT sent as an ``Authorization: Bearer`` header). The key
type is detected from its shape so a user can paste either. Only a connection
test is needed for now; metadata use is out of scope.

The base URL is TMDB's fixed public endpoint and is not user-configurable, so —
unlike :mod:`core.clients.arr_client` — only the API key is held and updatable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from core.logging import get_logger

# TMDB's public API base; not user-configurable.
_BASE_URL = "https://api.themoviedb.org"
# TMDB's image CDN base and the poster size used for thumbnails.
_IMAGE_BASE = "https://image.tmdb.org/t/p"
_POSTER_SIZE = "w342"
# Discover filter for anime: the Animation genre (16) limited to Japanese
# productions. TMDB's /trending endpoints cannot be genre-filtered, so the
# anime feeds are built from /discover with an explicit sort instead.
_ANIME_DISCOVER_PARAMS = {"with_genres": "16", "with_origin_country": "JP"}
# TMDB's Animation genre id, used by the anime search post-filter.
_ANIMATION_GENRE_ID = 16


def _is_anime_result(item: dict[str, Any]) -> bool:
    """Whether a raw TMDB search result looks like anime.

    TMDB's text search accepts no genre or origin filters, so search results
    are filtered client-side: the Animation genre plus a Japanese original
    language — the closest text-searchable equivalent of
    :data:`_ANIME_DISCOVER_PARAMS` (movie search results carry no origin
    country to match on).
    """
    genre_ids = item.get("genre_ids") or []
    return _ANIMATION_GENRE_ID in genre_ids and item.get("original_language") == "ja"


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

    @staticmethod
    def _discovery_row(item: dict[str, Any], media_type: str) -> dict[str, Any]:
        """Normalise a TMDB result into a uniform discovery row.

        Movies carry ``title``/``release_date``; TV carries ``name``/
        ``first_air_date``. The shape matches the Trakt and Seer clients' rows so
        :mod:`core.trending` maps every source the same way. TMDB results carry only
        a TMDB id, so ``imdb``/``tvdb``/``trakt`` are absent here.
        """
        date = item.get("release_date") or item.get("first_air_date") or ""
        year = int(date[:4]) if date[:4].isdigit() else None
        return {
            "media_type": media_type,
            "tmdb": item.get("id"),
            "title": item.get("title") or item.get("name"),
            "year": year,
        }

    async def _discover(
        self,
        url: str,
        *,
        media_type: str,
        limit: int,
        pages: int = 1,
        extra_params: dict[str, str] | None = None,
        result_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and normalise a TMDB discovery endpoint's ``results`` array.

        ``pages`` consecutive pages (1-indexed) are fetched and concatenated before
        the ``limit`` cap, so the scheduled refresh can build a deeper grid than a
        single page; an empty page short-circuits the rest. ``pages=1`` preserves
        the original single-page behaviour for live calls. ``extra_params`` are
        merged into every page request (used for the /discover filters).
        ``result_filter`` drops raw results before normalisation (used where the
        endpoint cannot filter server-side); paging stops on an empty *response*
        page, not an all-filtered one.
        """
        results: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            kwargs = self._auth_kwargs()
            params = {**kwargs.get("params", {}), **(extra_params or {}), "page": page}
            response = await self._client.get(url, **{**kwargs, "params": params})
            response.raise_for_status()
            page_results = response.json().get("results") or []
            if result_filter is None:
                results.extend(page_results)
            else:
                results.extend(item for item in page_results if result_filter(item))
            if not page_results:
                break
        return [self._discovery_row(item, media_type) for item in results[:limit]]

    async def get_trending(
        self, *, media_type: str, window: str = "week", limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return TMDB trending movies or shows as uniform discovery rows.

        ``media_type`` is ``movie`` or ``show``; ``window`` is ``day`` or ``week``;
        ``pages`` is the number of result pages to fetch (see :meth:`_discover`).
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/trending/{endpoint}/{window}"
        return await self._discover(
            url, media_type=media_type, limit=limit, pages=pages
        )

    async def get_popular(
        self, *, media_type: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return TMDB popular movies or shows as uniform discovery rows.

        ``pages`` is the number of result pages to fetch (see :meth:`_discover`).
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/{endpoint}/popular"
        return await self._discover(
            url, media_type=media_type, limit=limit, pages=pages
        )

    async def get_anime_trending(
        self, *, media_type: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return currently-buzzing TMDB anime as uniform discovery rows.

        Built from ``/discover`` with the anime filters sorted by
        ``popularity.desc`` — TMDB's recency-weighted popularity is the closest
        genre-filterable proxy for its trending feed (see
        :data:`_ANIME_DISCOVER_PARAMS`).
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/discover/{endpoint}"
        return await self._discover(
            url,
            media_type=media_type,
            limit=limit,
            pages=pages,
            extra_params={**_ANIME_DISCOVER_PARAMS, "sort_by": "popularity.desc"},
        )

    async def get_anime_popular(
        self, *, media_type: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return all-time popular TMDB anime as uniform discovery rows.

        Built from ``/discover`` with the anime filters sorted by
        ``vote_count.desc`` — a long-term popularity proxy, distinct from the
        recency-weighted sort used by :meth:`get_anime_trending`.
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/discover/{endpoint}"
        return await self._discover(
            url,
            media_type=media_type,
            limit=limit,
            pages=pages,
            extra_params={**_ANIME_DISCOVER_PARAMS, "sort_by": "vote_count.desc"},
        )

    async def _search(
        self,
        *,
        media_type: str,
        query: str,
        limit: int,
        pages: int,
        result_filter: Callable[[dict[str, Any]], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch one TMDB title-search feed (shared by both search variants).

        Adult titles are excluded, matching the discovery feeds' defaults.
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/search/{endpoint}"
        return await self._discover(
            url,
            media_type=media_type,
            limit=limit,
            pages=pages,
            extra_params={"query": query, "include_adult": "false"},
            result_filter=result_filter,
        )

    async def search(
        self, *, media_type: str, query: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return TMDB title-search results as uniform discovery rows.

        ``media_type`` is ``movie`` or ``show``; ``pages`` is the number of
        result pages to fetch (see :meth:`_discover`).
        """
        return await self._search(
            media_type=media_type, query=query, limit=limit, pages=pages
        )

    async def search_anime(
        self, *, media_type: str, query: str, limit: int = 20, pages: int = 1
    ) -> list[dict[str, Any]]:
        """Return TMDB title-search results filtered to anime.

        Same request as :meth:`search`, with the raw results post-filtered by
        :func:`_is_anime_result` because the search endpoints accept none of
        the ``/discover`` anime filters.
        """
        return await self._search(
            media_type=media_type,
            query=query,
            limit=limit,
            pages=pages,
            result_filter=_is_anime_result,
        )

    async def fetch_external_ids(self, *, media_type: str, tmdb_id: int) -> str | None:
        """Return the IMDb id for a TMDB item, or ``None`` if unavailable.

        Used to resolve an IMDb id for the rating overlay on items that only carry a
        TMDB id (TMDB/Seer sources). Never raises: any error (network, non-200,
        missing id) degrades to ``None`` so the caller can fall back.
        """
        endpoint = "movie" if media_type == "movie" else "tv"
        url = f"{_BASE_URL}/3/{endpoint}/{tmdb_id}/external_ids"
        try:
            response = await self._client.get(url, **self._auth_kwargs())
        except httpx.HTTPError as exc:
            self._log.debug("TMDB external ids fetch failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            return None
        return response.json().get("imdb_id") or None

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
