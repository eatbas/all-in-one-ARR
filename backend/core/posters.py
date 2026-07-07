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
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.clients.omdb import OmdbClient
    from core.clients.tmdb import TmdbClient

# Indirection point so tests can control time deterministically (mirrors
# ``core.trending``); the churn pass compares this against each file's mtime.
_now: Callable[[], float] = time.time


@dataclass(frozen=True)
class PosterEvictionResult:
    """Outcome of one churn pass: how many poster files went and bytes freed."""

    removed_files: int
    freed_bytes: int


class PosterCache:
    """Fetch-once disk cache for poster thumbnails."""

    def __init__(self, *, cache_dir: str, tmdb: TmdbClient, omdb: OmdbClient) -> None:
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
            self._touch_access(path)
            return path
        async with self._lock_for(path.name):
            # Re-check after acquiring: a concurrent request may have cached it
            # while we were waiting for the lock.
            if path.exists():
                self._touch_access(path)
                return path
            data = await self._tmdb.fetch_poster(media_type=media_type, tmdb_id=tmdb_id)
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

    def _touch_access(self, path: Path) -> None:
        """Bump a poster's mtime to now so the churn pass treats it as fresh.

        Called on every cache hit, making mtime an access-time proxy (atime is
        unreliable under relatime/Windows). Failures are non-fatal: a poster that
        cannot be touched simply ages from its last successful touch.
        """
        try:
            os.utime(path, None)
        except OSError:  # filesystem race (e.g. evicted mid-serve); treat as a no-op
            self._log.debug("could not touch poster %s", path.name)

    def total_size_bytes(self) -> int:
        """Return the total size of cached ``*.jpg`` files in bytes."""
        if not self._cache_dir.exists():
            return 0
        return sum(
            file_path.stat().st_size
            for file_path in self._cache_dir.glob("*.jpg")
            if file_path.is_file()
        )

    def clear(self) -> int:
        """Delete every cached ``*.jpg`` file and return the bytes freed.

        Tolerates a missing cache directory by returning ``0``.
        """
        if not self._cache_dir.exists():
            return 0
        freed = 0
        for file_path in list(self._cache_dir.glob("*.jpg")):
            if file_path.is_file():
                freed += file_path.stat().st_size
                file_path.unlink()
        return freed

    def evict(
        self, *, max_age_seconds: float, max_total_bytes: int
    ) -> PosterEvictionResult:
        """Prune the cache by age then by total size, returning what was freed.

        Two independent passes, each opted out of by a non-positive bound:

        * **Age** — when ``max_age_seconds > 0``, delete any cached ``*.jpg`` whose
          mtime is older than the TTL, plus any orphaned ``*.tmp`` from an
          interrupted write. Posters are touched on every cache hit, so this
          evicts only titles nobody has viewed within the window — e.g. ones that
          have dropped off the trending/popular feeds.
        * **Size** — when ``max_total_bytes > 0`` and the survivors still exceed the
          cap, delete oldest-mtime-first until the total is within bounds.

        Tolerates a missing cache directory by returning an empty result. Only
        ``*.jpg`` removals count towards the result; ``*.tmp`` cleanup is
        housekeeping, mirroring how :meth:`total_size_bytes`/:meth:`clear` ignore
        temp files.
        """
        if not self._cache_dir.exists():
            return PosterEvictionResult(removed_files=0, freed_bytes=0)
        now = _now()
        removed_files = 0
        freed_bytes = 0
        # (path, mtime, size) for every surviving poster, feeding the size pass.
        survivors: list[tuple[Path, float, int]] = []
        for file_path in list(self._cache_dir.glob("*.jpg")):
            if not file_path.is_file():
                continue
            stat = file_path.stat()
            if max_age_seconds > 0 and now - stat.st_mtime > max_age_seconds:
                file_path.unlink()
                removed_files += 1
                freed_bytes += stat.st_size
            else:
                survivors.append((file_path, stat.st_mtime, stat.st_size))
        if max_age_seconds > 0:
            for tmp_path in list(self._cache_dir.glob("*.tmp")):
                if (
                    tmp_path.is_file()
                    and now - tmp_path.stat().st_mtime > max_age_seconds
                ):
                    tmp_path.unlink()
        if max_total_bytes > 0:
            total = sum(size for _, _, size in survivors)
            # Oldest (least-recently-served) first, until back within the cap.
            for file_path, _, size in sorted(survivors, key=lambda item: item[1]):
                if total <= max_total_bytes:
                    break
                file_path.unlink()
                removed_files += 1
                freed_bytes += size
                total -= size
        if freed_bytes:
            self._log.info(
                "poster churn evicted %d files (%d bytes)", removed_files, freed_bytes
            )
        else:
            self._log.debug("poster churn evicted nothing")
        return PosterEvictionResult(
            removed_files=removed_files, freed_bytes=freed_bytes
        )
