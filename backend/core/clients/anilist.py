"""Outbound AniList client: keyless GraphQL discovery for the anime feeds.

AniList's public GraphQL API needs no credentials for read-only queries, so —
unlike the other clients — nothing here is user-configurable. Trending uses
AniList's ``TRENDING_DESC`` sort (what the community is watching right now) and
popular uses ``POPULARITY_DESC`` (all-time list membership).

Rows are emitted in the uniform discovery shape (see :mod:`core.trending`) but
carry only AniList/MAL ids plus a ``poster_url`` (AniList cover art); the
TMDB/TVDB/IMDb ids are filled in afterwards by :mod:`core.anime_ids` so the
library overlays and the Trakt add keep working.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.logging import get_logger

# AniList's public GraphQL endpoint; not user-configurable.
_BASE_URL = "https://graphql.anilist.co"
# AniList caps Page.perPage at 50.
_PER_PAGE = 50

# Maps the app's media type onto AniList format filters. Everything episodic
# (including originals and specials) is a Sonarr-side "show"; only theatrical
# features are Radarr-side "movie"s.
_FORMATS = {
    "movie": ["MOVIE"],
    "show": ["TV", "TV_SHORT", "ONA", "OVA", "SPECIAL"],
}

# One query serves both browse feeds; the sort and format filter arrive as
# variables.
_MEDIA_QUERY = """
query ($page: Int, $perPage: Int, $sort: [MediaSort], $formats: [MediaFormat]) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, sort: $sort, format_in: $formats) {
      id
      idMal
      title { romaji english }
      format
      seasonYear
      startDate { year }
      coverImage { large }
    }
  }
}
"""

# The title-search variant, relevance-ordered by SEARCH_MATCH. Kept separate
# from _MEDIA_QUERY because AniList treats an explicit ``search: null``
# argument as a filter, unlike an absent one.
_SEARCH_QUERY = """
query ($page: Int, $perPage: Int, $search: String, $formats: [MediaFormat]) {
  Page(page: $page, perPage: $perPage) {
    media(type: ANIME, search: $search, sort: [SEARCH_MATCH], format_in: $formats) {
      id
      idMal
      title { romaji english }
      format
      seasonYear
      startDate { year }
      coverImage { large }
    }
  }
}
"""


class AnilistClient:
    """Async client for AniList's trending/popular anime discovery."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._log = get_logger("anilist")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    @staticmethod
    def _discovery_row(item: dict[str, Any], media_type: str) -> dict[str, Any]:
        """Normalise an AniList media object into a uniform discovery row.

        The shape matches the other clients' rows so :mod:`core.trending` maps
        every source the same way. AniList knows nothing of TMDB/TVDB/IMDb, so
        those keys are absent here — :mod:`core.anime_ids` fills them in where
        Fribb's mapping has an entry. ``anilist``/``mal`` ids and the cover-art
        ``poster_url`` are carried so unmapped rows still render and deep-link.
        """
        title = item.get("title") or {}
        start_date = item.get("startDate") or {}
        cover = item.get("coverImage") or {}
        return {
            "media_type": media_type,
            "anilist": item.get("id"),
            "mal": item.get("idMal"),
            "title": title.get("english") or title.get("romaji"),
            "year": item.get("seasonYear") or start_date.get("year"),
            "poster_url": cover.get("large"),
        }

    async def _discover(
        self,
        *,
        media_type: str,
        limit: int,
        sort: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and normalise pages of one AniList feed.

        With ``sort`` set the browse query is used; with ``search`` set the
        title-search query (relevance-ordered by ``SEARCH_MATCH``) is used
        instead — exactly one of the two must be given. Pages of
        :data:`_PER_PAGE` are fetched and concatenated until ``limit`` rows are
        collected; an empty page short-circuits the rest (mirrors the TMDB
        client's paging).
        """
        if (sort is None) == (search is None):
            raise ValueError("exactly one of sort or search must be set")
        variables: dict[str, Any] = {"formats": _FORMATS[media_type]}
        if search is None:
            document = _MEDIA_QUERY
            variables["sort"] = [sort]
        else:
            document = _SEARCH_QUERY
            variables["search"] = search
        results: list[dict[str, Any]] = []
        page = 1
        while len(results) < limit:
            response = await self._client.post(
                _BASE_URL,
                json={
                    "query": document,
                    "variables": {
                        **variables,
                        "page": page,
                        "perPage": _PER_PAGE,
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            page_results = ((payload.get("data") or {}).get("Page") or {}).get(
                "media"
            ) or []
            results.extend(page_results)
            if not page_results:
                break
            page += 1
        return [self._discovery_row(item, media_type) for item in results[:limit]]

    async def get_trending(
        self, *, media_type: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return AniList trending anime as uniform discovery rows.

        ``media_type`` is ``movie`` or ``show``; the AniList format filter maps
        it onto theatrical features versus episodic formats.
        """
        return await self._discover(
            media_type=media_type, sort="TRENDING_DESC", limit=limit
        )

    async def get_popular(
        self, *, media_type: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return AniList all-time popular anime as uniform discovery rows."""
        return await self._discover(
            media_type=media_type, sort="POPULARITY_DESC", limit=limit
        )

    async def search(
        self, *, media_type: str, query: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Return AniList title-search results as uniform discovery rows.

        Results follow AniList's ``SEARCH_MATCH`` relevance order; ``media_type``
        maps onto the same format filters as the browse feeds.
        """
        return await self._discover(media_type=media_type, search=query, limit=limit)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
