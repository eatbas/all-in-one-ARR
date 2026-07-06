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
# The scheduled refresh fetches a deeper grid than a single live page, since it
# runs off the request path. ``TRENDING_SYNC_PAGES`` bounds the upstream paging so
# the deeper fetch stays predictable (TMDB/Seer return ~20 rows per page).
SCHEDULED_TRENDING_LIMIT = 40
TRENDING_SYNC_PAGES = 2
# Seer trending is a mixed movie/show feed. Fetch extra pages so both media buckets
# can fill to the same per-tab limit before the mixed feed is exhausted.
SEER_TRENDING_SYNC_PAGES = 6
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
    # The subset of the above that is actually downloaded (a movie with a file, or a
    # show with at least one episode file) — used to colour an "in library but the
    # media is still missing" item differently from a downloaded one.
    radarr_available_tmdb: frozenset[int] = field(default_factory=frozenset)
    sonarr_available_tvdb: frozenset[int] = field(default_factory=frozenset)
    sonarr_available_tmdb: frozenset[int] = field(default_factory=frozenset)

    def contains(
        self, *, media_type: str | None, tmdb: int | None, tvdb: int | None
    ) -> bool:
        """Whether an item is already present (by id) in the relevant Arr library."""
        if media_type == "movie":
            return tmdb is not None and tmdb in self.radarr_tmdb
        return (tvdb is not None and tvdb in self.sonarr_tvdb) or (
            tmdb is not None and tmdb in self.sonarr_tmdb
        )

    def is_available(
        self, *, media_type: str | None, tmdb: int | None, tvdb: int | None
    ) -> bool:
        """Whether the item's media is downloaded in the relevant Arr library.

        Parallels :meth:`contains` but matches only the *available* id sets (Radarr
        ``hasFile``; Sonarr ``episodeFileCount > 0``), so a monitored-but-not-yet-
        downloaded title is ``in library`` without being available.
        """
        if media_type == "movie":
            return tmdb is not None and tmdb in self.radarr_available_tmdb
        return (tvdb is not None and tvdb in self.sonarr_available_tvdb) or (
            tmdb is not None and tmdb in self.sonarr_available_tmdb
        )


def _int_ids(
    items: Iterable[dict[str, Any]],
    field_name: str,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> frozenset[int]:
    """Collect the integer ``field_name`` values across Arr items.

    When ``predicate`` is given, only items it accepts contribute their id — used to
    build the "available" (downloaded) subsets from the same raw payloads.
    """
    return frozenset(
        item[field_name]
        for item in items
        if isinstance(item.get(field_name), int)
        and (predicate is None or predicate(item))
    )


def _radarr_has_file(item: dict[str, Any]) -> bool:
    """Whether a raw Radarr movie has its file downloaded."""
    return item.get("hasFile") is True


def _sonarr_has_episode(item: dict[str, Any]) -> bool:
    """Whether a raw Sonarr series has at least one downloaded episode file.

    ``statistics`` is read defensively (a series payload may omit it).
    """
    statistics = item.get("statistics")
    if not isinstance(statistics, dict):
        return False
    count = statistics.get("episodeFileCount")
    return isinstance(count, int) and count > 0


def build_library_index(
    *, radarr_items: list[dict[str, Any]], sonarr_items: list[dict[str, Any]]
) -> LibraryIndex:
    """Build a :class:`LibraryIndex` from raw Radarr/Sonarr library payloads.

    Each list is scanned for both presence ids (every item) and availability ids
    (only downloaded items), so a single pass yields the in-library and
    truly-available sets.
    """
    return LibraryIndex(
        radarr_tmdb=_int_ids(radarr_items, "tmdbId"),
        sonarr_tvdb=_int_ids(sonarr_items, "tvdbId"),
        sonarr_tmdb=_int_ids(sonarr_items, "tmdbId"),
        radarr_available_tmdb=_int_ids(radarr_items, "tmdbId", _radarr_has_file),
        sonarr_available_tvdb=_int_ids(sonarr_items, "tvdbId", _sonarr_has_episode),
        sonarr_available_tmdb=_int_ids(sonarr_items, "tmdbId", _sonarr_has_episode),
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
                "in_library_available": library.is_available(
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

    def peek(self) -> LibraryIndex | None:
        """Return the latest cached index, even when it is stale."""
        return self._value

    def set(self, value: LibraryIndex) -> None:
        """Cache an index until ``ttl_seconds`` from now."""
        self._value = value
        self._expires_at = _now() + self._ttl


class TrendingStore:
    """In-process snapshot of discovery rows per feed, filled by the scheduler.

    Keyed by ``(source, media, category, window)``. It deliberately holds the raw
    discovery rows — not built ``TrendingItem``s — so the API re-applies the
    ``already_tracked``/``in_library`` overlay with fresh local state on every read
    (those flags change independently of the upstream feed). The Trending page is
    served from this snapshot rather than calling a provider on each request; the
    scheduled refresh keeps it warm. Single-process, single-event-loop use only
    (like :class:`RatingCache`/:class:`LibraryCache`), so no lock is needed.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        self._last_synced_at: str | None = None

    def get(
        self, *, source: str, media: str, category: str, window: str
    ) -> list[dict[str, Any]] | None:
        """Return the stored rows for a feed, or ``None`` if it was never synced.

        A feed that synced successfully but returned nothing yields ``[]`` (a valid
        snapshot); an absent key yields ``None`` so the API can fall back to a live
        fetch for a feed the scheduler does not keep warm (e.g. the ``day`` window).
        """
        return self._rows.get((source, media, category, window))

    def set(
        self,
        *,
        source: str,
        media: str,
        category: str,
        window: str,
        rows: Iterable[dict[str, Any]],
    ) -> None:
        """Replace the stored rows for a feed."""
        self._rows[(source, media, category, window)] = list(rows)

    def all_rows(self) -> list[dict[str, Any]]:
        """Return every stored row across all feeds (for poster pre-warming)."""
        return [row for rows in self._rows.values() for row in rows]

    def mark_synced(self, when: str) -> None:
        """Record the ISO-8601 timestamp at which a refresh cycle completed."""
        self._last_synced_at = when

    def last_synced_at(self) -> str | None:
        """Return the last refresh-cycle timestamp, or ``None`` before the first."""
        return self._last_synced_at
