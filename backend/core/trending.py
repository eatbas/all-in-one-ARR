"""Trending discovery: normalisation, an IMDb-rating cache and a library index.

The Trakt, TMDB and Seer clients each emit a *uniform discovery row*
(``{media_type, tmdb, [imdb, tvdb, trakt], title, year, [seer_status]}``).
:func:`to_trending_items` tags those rows with their source, an ``already_tracked``
flag, and an ``in_library`` flag (present in Radarr/Sonarr), producing the
``TrendingItem`` shape the dashboard consumes. :class:`RatingCache` and
:class:`LibraryCache` are bounded/TTL caches so a poster grid does not hammer OMDb
or the Arr APIs on every render.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

# Default per-tab item cap and IMDb-rating cache bounds.
TRENDING_ITEM_LIMIT = 20
_RATING_TTL_SECONDS = 24 * 60 * 60
_RATING_CACHE_MAX = 512
# The combined Radarr/Sonarr library is re-listed at most this often.
_LIBRARY_TTL_SECONDS = 60

# Indirection point so tests can control time deterministically.
_now: Callable[[], float] = time.time


@dataclass(frozen=True)
class LibraryIndex:
    """The set of media already present in Radarr/Sonarr, for in-library matching.

    Movies match by TMDB id (Radarr exposes ``tmdbId``); shows match by TVDB id
    (Sonarr's primary key) or by TMDB id when the Sonarr series carries one. A
    trending show that only has a TMDB id (the TMDB/Seer tabs) therefore matches
    Sonarr only when Sonarr exposes a ``tmdbId`` for it.
    """

    radarr_tmdb: frozenset[int] = field(default_factory=frozenset)
    sonarr_tvdb: frozenset[int] = field(default_factory=frozenset)
    sonarr_tmdb: frozenset[int] = field(default_factory=frozenset)

    def contains(
        self, *, media_type: str | None, tmdb: int | None, tvdb: int | None
    ) -> bool:
        """Whether an item is already in the relevant Arr library."""
        if media_type == "movie":
            return tmdb is not None and tmdb in self.radarr_tmdb
        return (tvdb is not None and tvdb in self.sonarr_tvdb) or (
            tmdb is not None and tmdb in self.sonarr_tmdb
        )


def _int_ids(items: Iterable[dict[str, Any]], field_name: str) -> frozenset[int]:
    """Collect the integer values of ``field_name`` across Arr library items."""
    return frozenset(
        item[field_name]
        for item in items
        if isinstance(item.get(field_name), int)
    )


def build_library_index(
    *, radarr_items: list[dict[str, Any]], sonarr_items: list[dict[str, Any]]
) -> LibraryIndex:
    """Build a :class:`LibraryIndex` from raw Radarr/Sonarr library payloads."""
    return LibraryIndex(
        radarr_tmdb=_int_ids(radarr_items, "tmdbId"),
        sonarr_tvdb=_int_ids(sonarr_items, "tvdbId"),
        sonarr_tmdb=_int_ids(sonarr_items, "tmdbId"),
    )


def to_trending_items(
    rows: Iterable[dict[str, Any]],
    *,
    source: str,
    tracked_tmdbs: set[int],
    library: LibraryIndex | None = None,
) -> list[dict[str, Any]]:
    """Map uniform discovery rows onto ``TrendingItem`` dicts.

    ``source`` tags every row with the tab that produced it; ``tracked_tmdbs`` is
    the set of TMDB ids already mirrored in a tracked list (``already_tracked``);
    ``library`` flags items already present in Radarr/Sonarr (``in_library``).
    Fields a source does not provide (e.g. ``imdb`` for TMDB, ``seer_status``
    outside Seer) default to ``None``.
    """
    library = library or LibraryIndex()
    items: list[dict[str, Any]] = []
    for row in rows:
        tmdb = row.get("tmdb")
        tvdb = row.get("tvdb")
        media_type = row.get("media_type")
        items.append(
            {
                "source": source,
                "media_type": media_type,
                "tmdb": tmdb,
                "imdb": row.get("imdb"),
                "tvdb": tvdb,
                "trakt": row.get("trakt"),
                "slug": row.get("slug"),
                "title": row.get("title"),
                "year": row.get("year"),
                "seer_status": row.get("seer_status"),
                "already_tracked": tmdb is not None and tmdb in tracked_tmdbs,
                "in_library": library.contains(
                    media_type=media_type, tmdb=tmdb, tvdb=tvdb
                ),
            }
        )
    return items


class RatingCache:
    """Bounded, time-to-live cache for IMDb ratings keyed by IMDb id.

    Entries expire after ``ttl_seconds``; when ``max_entries`` is reached the
    oldest entry (insertion order) is evicted before a new id is stored. Kept
    deliberately small — no external dependency, single-process only.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = _RATING_TTL_SECONDS,
        max_entries: int = _RATING_CACHE_MAX,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, imdb_id: str) -> dict[str, Any] | None:
        """Return the cached rating for an id, or ``None`` if absent/expired."""
        entry = self._store.get(imdb_id)
        if entry is None:
            return None
        expires_at, value = entry
        if _now() >= expires_at:
            del self._store[imdb_id]
            return None
        return value

    def set(self, imdb_id: str, value: dict[str, Any]) -> None:
        """Store a rating for an id, evicting the oldest entry when full."""
        if imdb_id not in self._store and len(self._store) >= self._max:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[imdb_id] = (_now() + self._ttl, value)


class LibraryCache:
    """Short-TTL cache of the combined Radarr/Sonarr :class:`LibraryIndex`.

    Listing a full Arr library is O(library size), so the index is reused for
    ``ttl_seconds`` rather than refetched on every trending request.
    """

    def __init__(self, *, ttl_seconds: int = _LIBRARY_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._value: LibraryIndex | None = None
        self._expires_at = 0.0

    def get(self) -> LibraryIndex | None:
        """Return the cached index, or ``None`` when absent or expired."""
        if self._value is None or _now() >= self._expires_at:
            return None
        return self._value

    def set(self, value: LibraryIndex) -> None:
        """Cache an index until ``ttl_seconds`` from now."""
        self._value = value
        self._expires_at = _now() + self._ttl
