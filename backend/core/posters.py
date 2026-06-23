"""Disk cache for poster thumbnails.

Resolves an item's poster from TMDB (preferred) or OMDb (fallback by IMDb id),
caches the image bytes under the gitignored ``data/`` volume keyed by
``(media_type, tmdb_id)``, and returns the cached path. Each poster is fetched
from upstream **at most once**: concurrent requests for the same poster are
de-duplicated by a per-key lock, and writes are atomic (temp file + replace) so
a reader never observes a half-written file.
"""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.clients.omdb import OmdbClient
    from core.clients.tmdb import TmdbClient


class PosterCache:
    """Fetch-once disk cache for poster thumbnails."""

    def __init__(
        self, *, cache_dir: str, tmdb: "TmdbClient", omdb: "OmdbClient"
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._tmdb = tmdb
        self._omdb = omdb
        self._log = get_logger("posters")
        # Per-key asyncio locks so concurrent requests for the same poster
        # resolve it once; the dict itself is guarded by a sync lock.
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_guard = threading.Lock()

    def _path_for(self, media_type: str, tmdb_id: int) -> Path:
        """Return the cache path for a poster (one file per title)."""
        return self._cache_dir / f"{media_type}-{tmdb_id}.jpg"

    def _lock_for(self, key: str) -> asyncio.Lock:
        """Return the lock guarding a single cache key, creating it on demand."""
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            return lock

    def _discard_lock(self, key: str) -> None:
        """Forget a per-key lock once its poster is cached, bounding the map."""
        with self._locks_guard:
            self._locks.pop(key, None)

    async def get_poster(
        self, *, media_type: str, tmdb_id: int, imdb_id: str | None = None
    ) -> Path | None:
        """Return the cached poster path, fetching it on first use.

        Tries TMDB first; falls back to OMDb (by IMDb id) when TMDB has no
        poster. Returns ``None`` when neither source yields an image.
        """
        path = self._path_for(media_type, tmdb_id)
        if path.exists():
            return path
        async with self._lock_for(path.name):
            # Re-check after acquiring: a concurrent request may have cached it
            # while we were waiting for the lock.
            if path.exists():
                return path
            data = await self._tmdb.fetch_poster(
                media_type=media_type, tmdb_id=tmdb_id
            )
            if data is None and imdb_id:
                data = await self._omdb.fetch_poster(imdb_id=imdb_id)
            if data is None:
                return None
            self._write_atomic(path, data)
            self._log.debug("cached poster %s", path.name)
        # The poster is now on disk, so every future call returns at the
        # existence check above before taking a lock; drop this key's lock to
        # keep the map bounded by the number of still-uncached posters.
        self._discard_lock(path.name)
        return path

    def _write_atomic(self, path: Path, data: bytes) -> None:
        """Write ``data`` to ``path`` atomically via a temp file + replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
