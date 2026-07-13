"""AniList/MAL to TMDB/TVDB/IMDb id mapping backed by Fribb's anime-lists.

AniList rows carry no TMDB/TVDB/IMDb ids, which the trending pipeline needs for
the library overlays, posters and the Trakt add. Fribb's ``anime-list-mini.json``
(a community-maintained merge of the anime-offline-database and the TheTVDB
scudlee lists) maps AniList/MAL ids onto those id spaces, so it is cached on
disk under the gitignored ``data/`` volume and refreshed on the configured TTL
(Settings → General, 1/3/5 days) rather than queried per request.

Verified source shape (2026-07-12): entries are dicts where ``anilist_id`` /
``mal_id`` / ``tvdb_id`` are ints when present, ``imdb_id`` is a **list** of
strings, and ``themoviedb_id`` is an **object** of ``{"tv": int|list}`` /
``{"movie": int|list}``. All of it is parsed defensively — an unknown shape
degrades to ``None``, never raises — so an upstream format change cannot break
the Trending page.

Ambiguity rule: a field carrying **two or more valid ids** (franchise and
compilation entries list several films under one AniList id) yields ``None``
rather than an arbitrary first pick — a wrong id mis-rates the card and can
add the wrong title to a Trakt list, whereas a dropped one falls back to the
unambiguous ids (TMDB resolves the authoritative IMDb id downstream).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.logging import get_logger
from core.settings_normalisers import (
    DEFAULT_ANIME_IDS_REFRESH_DAYS,
    normalise_anime_ids_refresh_days,
)

# Fribb's regenerated mini mapping (the full variant only adds id spaces the
# app does not use); not user-configurable.
_SOURCE_URL = (
    "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-mini.json"
)
_SECONDS_PER_DAY = 24 * 60 * 60
# After a failed download, do not retry before this long has passed, so a dead
# upstream cannot be hammered by every cold-store live fetch.
_RETRY_SECONDS = 10 * 60
# The mapping file is ~6 MB; allow a generous single-download budget.
_DOWNLOAD_TIMEOUT_SECONDS = 60.0

# Indirection point so tests can control time deterministically (mirrors
# ``core.trending`` / ``core.posters``).
_now: Callable[[], float] = time.time


@dataclass(frozen=True)
class MappedIds:
    """The external ids one AniList/MAL title maps onto."""

    tmdb_movie: int | None = None
    tmdb_tv: int | None = None
    tvdb: int | None = None
    imdb: str | None = None


def _valid_ints(value: Any) -> list[int]:
    """Collect the valid int ids in a scalar-or-list value (junk skipped).

    ``bool`` is excluded explicitly (it subclasses ``int`` but is never an id).
    """
    candidates = value if isinstance(value, list) else [value]
    return [
        candidate
        for candidate in candidates
        if isinstance(candidate, int) and not isinstance(candidate, bool)
    ]


def _valid_strs(value: Any) -> list[str]:
    """Collect the valid non-empty string ids in a scalar-or-list value."""
    candidates = value if isinstance(value, list) else [value]
    return [
        candidate
        for candidate in candidates
        if isinstance(candidate, str) and candidate
    ]


def _single_int(value: Any) -> int | None:
    """Return the sole valid int id, or ``None`` when absent or ambiguous.

    Junk entries around one real id (``[None, 7]``) still resolve; two or
    more valid ids are ambiguous per the module's ambiguity rule.
    """
    valid = _valid_ints(value)
    return valid[0] if len(valid) == 1 else None


def _single_str(value: Any) -> str | None:
    """Return the sole valid string id, or ``None`` when absent or ambiguous."""
    valid = _valid_strs(value)
    return valid[0] if len(valid) == 1 else None


def _ambiguous_field_count(entry: dict[str, Any]) -> int:
    """Count this entry's id fields that carry more than one valid id."""
    values: list[Any] = [entry.get("tvdb_id")]
    tmdb = entry.get("themoviedb_id")
    if isinstance(tmdb, dict):
        values.extend((tmdb.get("movie"), tmdb.get("tv")))
    else:
        values.append(tmdb)
    ambiguous = sum(1 for value in values if len(_valid_ints(value)) > 1)
    if len(_valid_strs(entry.get("imdb_id"))) > 1:
        ambiguous += 1
    return ambiguous


def _mapped_ids(entry: dict[str, Any]) -> MappedIds | None:
    """Extract a :class:`MappedIds` from one raw mapping entry, or ``None``.

    ``themoviedb_id`` is normally ``{"tv": ...}`` / ``{"movie": ...}``; a bare
    int (defensive) is assigned per the entry's ``type``. Entries mapping to no
    known id space yield ``None`` so they never occupy the index.
    """
    tmdb = entry.get("themoviedb_id")
    tmdb_movie: int | None = None
    tmdb_tv: int | None = None
    if isinstance(tmdb, dict):
        tmdb_movie = _single_int(tmdb.get("movie"))
        tmdb_tv = _single_int(tmdb.get("tv"))
    elif _single_int(tmdb) is not None:
        if entry.get("type") == "MOVIE":
            tmdb_movie = _single_int(tmdb)
        else:
            tmdb_tv = _single_int(tmdb)
    mapped = MappedIds(
        tmdb_movie=tmdb_movie,
        tmdb_tv=tmdb_tv,
        tvdb=_single_int(entry.get("tvdb_id")),
        imdb=_single_str(entry.get("imdb_id")),
    )
    if mapped == MappedIds():
        return None
    return mapped


def _build_indexes(
    raw_text: str,
) -> tuple[dict[int, MappedIds], dict[int, MappedIds]]:
    """Parse the mapping file into ``anilist_id`` and ``mal_id`` indexes.

    The first entry seen for an id wins (seasons of one series share ids); a
    top-level shape other than a list of dicts yields empty indexes.
    """
    try:
        entries = json.loads(raw_text)
    except ValueError:
        return {}, {}
    if not isinstance(entries, list):
        return {}, {}
    by_anilist: dict[int, MappedIds] = {}
    by_mal: dict[int, MappedIds] = {}
    ambiguous_fields = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ambiguous_fields += _ambiguous_field_count(entry)
        mapped = _mapped_ids(entry)
        if mapped is None:
            continue
        anilist_id = entry.get("anilist_id")
        if isinstance(anilist_id, int) and anilist_id not in by_anilist:
            by_anilist[anilist_id] = mapped
        mal_id = entry.get("mal_id")
        if isinstance(mal_id, int) and mal_id not in by_mal:
            by_mal[mal_id] = mapped
    if ambiguous_fields:
        # Visibility for a future source-format shift: a sudden surge here
        # means coverage is silently shrinking under the ambiguity rule.
        get_logger("anime_ids").debug(
            "anime id mapping: %d ambiguous multi-id fields ignored",
            ambiguous_fields,
        )
    return by_anilist, by_mal


class AnimeIdMap:
    """Disk-cached AniList/MAL id mapping with TTL refresh and enrichment."""

    def __init__(
        self,
        *,
        path: str,
        refresh_days: int = DEFAULT_ANIME_IDS_REFRESH_DAYS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._path = Path(path)
        self._log = get_logger("anime_ids")
        self._client = http_client or httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT_SECONDS
        )
        # Cached-file staleness threshold, dashboard-configurable in whole days
        # (Settings -> General); normalised so an out-of-range value can never
        # produce a degenerate TTL.
        self._refresh_ttl_seconds = (
            normalise_anime_ids_refresh_days(refresh_days) * _SECONDS_PER_DAY
        )
        self._lock = asyncio.Lock()
        self._by_anilist: dict[int, MappedIds] = {}
        self._by_mal: dict[int, MappedIds] = {}
        # mtime of the file the in-memory indexes were parsed from; None until
        # the first successful parse.
        self._loaded_mtime: float | None = None
        # When a failed download may next be retried (0.0 = immediately).
        self._retry_at = 0.0

    def update_refresh_days(self, days: int) -> None:
        """Re-point the staleness threshold (set from the dashboard).

        Takes effect at the next :meth:`enrich` staleness check — the download
        itself still happens on the first trending refresh cycle (or cold
        anilist fetch) after the new TTL expires.
        """
        self._refresh_ttl_seconds = (
            normalise_anime_ids_refresh_days(days) * _SECONDS_PER_DAY
        )

    def _file_mtime(self) -> float | None:
        """Return the cache file's mtime, or ``None`` when it does not exist."""
        try:
            return self._path.stat().st_mtime
        except OSError:
            return None

    def _write_atomic(self, payload: bytes) -> None:
        """Write the mapping file atomically (temp file + replace)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_bytes(payload)
        os.replace(tmp_path, self._path)

    async def _download(self) -> bool:
        """Fetch the mapping to disk atomically; ``False`` on any failure.

        The ~6 MB write runs off the event loop, like the parse path.
        """
        try:
            response = await self._client.get(_SOURCE_URL, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            self._log.warning("anime id mapping download failed: %s", exc)
            return False
        await asyncio.to_thread(self._write_atomic, response.content)
        self._log.info("anime id mapping refreshed (%d bytes)", len(response.content))
        return True

    async def _parse_file(self) -> None:
        """(Re)build the in-memory indexes from the on-disk file, off the loop."""
        mtime = self._file_mtime()
        if mtime is None or mtime == self._loaded_mtime:
            return
        try:
            raw_text = await asyncio.to_thread(self._path.read_text, "utf-8")
        except OSError as exc:  # pragma: no cover - racy delete between stat/read
            self._log.warning("anime id mapping unreadable: %s", exc)
            return
        self._by_anilist, self._by_mal = await asyncio.to_thread(
            _build_indexes, raw_text
        )
        self._loaded_mtime = mtime
        self._log.info(
            "anime id mapping loaded (%d anilist / %d mal entries)",
            len(self._by_anilist),
            len(self._by_mal),
        )

    async def _ensure_loaded(self) -> None:
        """Refresh the file when missing/stale and load it into memory.

        A failed download falls back to the stale file when one exists; with no
        file at all the indexes stay empty (enrichment becomes a no-op) and the
        next attempt is deferred by :data:`_RETRY_SECONDS`.
        """
        async with self._lock:
            mtime = self._file_mtime()
            stale = mtime is None or _now() - mtime >= self._refresh_ttl_seconds
            if stale and _now() >= self._retry_at:
                if await self._download():
                    self._retry_at = 0.0
                else:
                    self._retry_at = _now() + _RETRY_SECONDS
            await self._parse_file()

    async def ensure_fresh(self) -> None:
        """Refresh the mapping when stale and load it — the boot/scheduled entry.

        Public alias of :meth:`_ensure_loaded` for the start-up hook and the
        hourly ``anime_ids_refresh`` job, so the configured cadence is honoured
        even when no AniList feed has been fetched since the server started.
        A fresh file makes this a single ``stat()`` no-op.
        """
        await self._ensure_loaded()

    def _lookup(self, anilist_id: Any, mal_id: Any) -> MappedIds | None:
        """Resolve a row's mapping by AniList id, falling back to MAL id."""
        if isinstance(anilist_id, int):
            mapped = self._by_anilist.get(anilist_id)
            if mapped is not None:
                return mapped
        if isinstance(mal_id, int):
            return self._by_mal.get(mal_id)
        return None

    async def enrich(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fill ``tmdb``/``tvdb``/``imdb`` on rows carrying AniList/MAL ids.

        Rows are mutated in place and returned. Ids a row already carries are
        never overwritten; unmapped rows pass through untouched so the caller
        can still render them (title, year and ``poster_url`` survive).
        """
        await self._ensure_loaded()
        for row in rows:
            mapped = self._lookup(row.get("anilist"), row.get("mal"))
            if mapped is None:
                continue
            if row.get("tmdb") is None:
                row["tmdb"] = (
                    mapped.tmdb_movie
                    if row.get("media_type") == "movie"
                    else mapped.tmdb_tv
                )
            if row.get("media_type") != "movie" and row.get("tvdb") is None:
                row["tvdb"] = mapped.tvdb
            if row.get("imdb") is None:
                row["imdb"] = mapped.imdb
        return rows

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
