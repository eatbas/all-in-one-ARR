"""Tests for core.posters (poster disk cache)."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock

from core.posters import PosterCache, PosterEvictionResult


def _seed(cache_dir, name: str, data: bytes, *, mtime: float):
    """Write a cache file with a fixed mtime, creating the dir on demand."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / name
    path.write_bytes(data)
    os.utime(path, (mtime, mtime))
    return path


def _cache(tmp_path, *, tmdb_bytes=None, omdb_bytes=None) -> PosterCache:
    """Build a PosterCache with stubbed TMDB/OMDb clients and a temp cache dir."""
    tmdb = AsyncMock()
    tmdb.fetch_poster = AsyncMock(return_value=tmdb_bytes)
    omdb = AsyncMock()
    omdb.fetch_poster = AsyncMock(return_value=omdb_bytes)
    return PosterCache(cache_dir=str(tmp_path / "posters"), tmdb=tmdb, omdb=omdb)


async def test_cache_miss_fetches_tmdb_and_writes(tmp_path) -> None:
    cache = _cache(tmp_path, tmdb_bytes=b"IMG")
    path = await cache.get_poster(media_type="movie", tmdb_id=1)
    assert path is not None
    assert path.name == "movie-1.jpg"
    assert path.read_bytes() == b"IMG"


async def test_cache_hit_skips_clients(tmp_path) -> None:
    cache = _cache(tmp_path, tmdb_bytes=b"IMG")
    first = await cache.get_poster(media_type="movie", tmdb_id=1)
    second = await cache.get_poster(media_type="movie", tmdb_id=1)
    assert first == second
    # The cached file is served the second time without re-fetching.
    assert cache._tmdb.fetch_poster.await_count == 1


async def test_tmdb_miss_falls_back_to_omdb(tmp_path) -> None:
    cache = _cache(tmp_path, tmdb_bytes=None, omdb_bytes=b"OMDB")
    path = await cache.get_poster(media_type="movie", tmdb_id=1, imdb_id="tt1")
    assert path is not None
    assert path.read_bytes() == b"OMDB"
    cache._omdb.fetch_poster.assert_awaited_once_with(imdb_id="tt1")


async def test_both_sources_fail_returns_none(tmp_path) -> None:
    cache = _cache(tmp_path)
    assert await cache.get_poster(media_type="movie", tmdb_id=1, imdb_id="tt1") is None


async def test_no_imdb_skips_omdb_fallback(tmp_path) -> None:
    cache = _cache(tmp_path, tmdb_bytes=None, omdb_bytes=b"OMDB")
    assert await cache.get_poster(media_type="movie", tmdb_id=1) is None
    cache._omdb.fetch_poster.assert_not_awaited()


async def test_atomic_write_leaves_no_temp_file(tmp_path) -> None:
    cache = _cache(tmp_path, tmdb_bytes=b"IMG")
    path = await cache.get_poster(media_type="movie", tmdb_id=1)
    assert list(path.parent.glob("*.tmp")) == []


async def test_lock_discarded_after_caching(tmp_path) -> None:
    # Once a poster is on disk its per-key lock is no longer needed, so the lock
    # map must not grow without bound.
    cache = _cache(tmp_path, tmdb_bytes=b"IMG")
    await cache.get_poster(media_type="movie", tmdb_id=1)
    assert cache._locks == {}


async def test_concurrent_requests_fetch_once(tmp_path) -> None:
    # Force a genuine overlap: the second request must pass its first existence
    # check and block on the per-key lock while the first is still fetching, so
    # it resolves via the post-lock re-check rather than re-fetching upstream.
    cache = _cache(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_fetch(*, media_type, tmdb_id):
        started.set()
        await release.wait()
        return b"IMG"

    cache._tmdb.fetch_poster = AsyncMock(side_effect=slow_fetch)

    task_a = asyncio.create_task(cache.get_poster(media_type="movie", tmdb_id=1))
    await started.wait()  # A holds the lock and is suspended inside the fetch.
    task_b = asyncio.create_task(cache.get_poster(media_type="movie", tmdb_id=1))
    await asyncio.sleep(0)  # Let B pass the first check and block on the lock.
    release.set()  # A writes and releases; B re-checks and serves the cached file.

    results = await asyncio.gather(task_a, task_b)
    assert results[0] == results[1]
    # Only A fetched upstream; B served the freshly-cached file via the re-check.
    assert cache._tmdb.fetch_poster.await_count == 1


def test_total_size_bytes_empty_and_missing_dir(tmp_path) -> None:
    cache = _cache(tmp_path)
    assert cache.total_size_bytes() == 0


def test_total_size_bytes_sums_jpg_files(tmp_path) -> None:
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "movie-1.jpg").write_bytes(b"abc")
    (cache_dir / "show-2.jpg").write_bytes(b"def")
    (cache_dir / "ignore.tmp").write_bytes(b"xyz")
    assert cache.total_size_bytes() == 6


def test_clear_removes_jpg_files_and_returns_bytes_freed(tmp_path) -> None:
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "movie-1.jpg").write_bytes(b"abc")
    (cache_dir / "show-2.jpg").write_bytes(b"defghij")
    (cache_dir / "ignore.tmp").write_bytes(b"xyz")
    freed = cache.clear()
    assert freed == 10
    assert list(cache_dir.glob("*.jpg")) == []
    assert (cache_dir / "ignore.tmp").exists()


def test_clear_tolerates_missing_directory(tmp_path) -> None:
    cache = _cache(tmp_path)
    assert cache.clear() == 0


def test_clear_skips_non_file_matches(tmp_path) -> None:
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "movie-1.jpg").write_bytes(b"abc")
    # A directory whose name happens to match the glob pattern must be ignored.
    (cache_dir / "show-2.jpg").mkdir()
    assert cache.clear() == 3
    assert list(cache_dir.glob("*.jpg")) == [cache_dir / "show-2.jpg"]


async def test_cache_hit_touches_mtime(tmp_path) -> None:
    # A served poster's mtime is bumped to now so the churn pass treats it as
    # fresh; this is what keeps actively-viewed posters out of eviction.
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    poster = _seed(cache_dir, "movie-1.jpg", b"IMG", mtime=1_000.0)
    path = await cache.get_poster(media_type="movie", tmdb_id=1)
    assert path == poster
    assert poster.stat().st_mtime > 1_000.0
    cache._tmdb.fetch_poster.assert_not_awaited()


async def test_cache_hit_touch_failure_is_non_fatal(tmp_path, monkeypatch) -> None:
    # The mtime bump is best-effort: if it fails (e.g. the file is evicted mid-serve),
    # the cached poster is still returned rather than erroring the request.
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    poster = _seed(cache_dir, "movie-1.jpg", b"IMG", mtime=1_000.0)

    def _raise(*_args, **_kwargs):
        raise OSError("utime failed")

    monkeypatch.setattr("core.posters.os.utime", _raise)
    path = await cache.get_poster(media_type="movie", tmdb_id=1)
    assert path == poster


def test_evict_removes_aged_jpg_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    fresh = _seed(cache_dir, "movie-1.jpg", b"abc", mtime=1_000_000.0 - 100)
    stale = _seed(cache_dir, "show-2.jpg", b"defgh", mtime=1_000_000.0 - 10_000)
    result = cache.evict(max_age_seconds=1_000, max_total_bytes=0)
    assert result == PosterEvictionResult(removed_files=1, freed_bytes=5)
    assert fresh.exists()
    assert not stale.exists()


def test_evict_size_cap_deletes_oldest_first(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    # All within the TTL; the cap forces the two oldest (a, b) out, newest survives.
    a = _seed(cache_dir, "movie-1.jpg", b"aaaa", mtime=1_000_000.0 - 30)
    b = _seed(cache_dir, "movie-2.jpg", b"bbbb", mtime=1_000_000.0 - 20)
    c = _seed(cache_dir, "movie-3.jpg", b"cccc", mtime=1_000_000.0 - 10)
    result = cache.evict(max_age_seconds=0, max_total_bytes=5)
    assert result == PosterEvictionResult(removed_files=2, freed_bytes=8)
    assert not a.exists() and not b.exists()
    assert c.exists()


def test_evict_size_cap_below_smallest_clears_all(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    a = _seed(cache_dir, "movie-1.jpg", b"aaaa", mtime=1_000_000.0 - 20)
    b = _seed(cache_dir, "movie-2.jpg", b"bbbb", mtime=1_000_000.0 - 10)
    # A cap below the smallest file forces every poster out, so the size loop
    # exhausts naturally rather than breaking early.
    result = cache.evict(max_age_seconds=0, max_total_bytes=1)
    assert result == PosterEvictionResult(removed_files=2, freed_bytes=8)
    assert not a.exists() and not b.exists()


def test_evict_cleans_orphaned_tmp_without_counting(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    fresh_tmp = _seed(cache_dir, "movie-1.jpg.tmp", b"x", mtime=1_000_000.0 - 100)
    stale_tmp = _seed(cache_dir, "movie-2.jpg.tmp", b"y", mtime=1_000_000.0 - 10_000)
    result = cache.evict(max_age_seconds=1_000, max_total_bytes=0)
    # Temp cleanup is housekeeping: it never contributes to the result counters.
    assert result == PosterEvictionResult(removed_files=0, freed_bytes=0)
    assert fresh_tmp.exists()
    assert not stale_tmp.exists()


def test_evict_tolerates_missing_directory(tmp_path) -> None:
    cache = _cache(tmp_path)
    assert cache.evict(max_age_seconds=1, max_total_bytes=1) == PosterEvictionResult(
        removed_files=0, freed_bytes=0
    )


def test_evict_disabled_passes_are_noop(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    aged = _seed(cache_dir, "movie-1.jpg", b"abc", mtime=1_000_000.0 - 10_000)
    aged_tmp = _seed(cache_dir, "movie-1.jpg.tmp", b"z", mtime=1_000_000.0 - 10_000)
    result = cache.evict(max_age_seconds=0, max_total_bytes=0)
    assert result == PosterEvictionResult(removed_files=0, freed_bytes=0)
    assert aged.exists()
    # The tmp pass is gated on the age pass, so it is skipped when the TTL is off.
    assert aged_tmp.exists()


def test_evict_skips_non_file_matches(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("core.posters._now", lambda: 1_000_000.0)
    cache = _cache(tmp_path)
    cache_dir = tmp_path / "posters"
    cache_dir.mkdir(parents=True, exist_ok=True)
    # A directory whose name matches the glob must be ignored, not statted/deleted.
    (cache_dir / "movie-2.jpg").mkdir()
    result = cache.evict(max_age_seconds=1, max_total_bytes=0)
    assert result == PosterEvictionResult(removed_files=0, freed_bytes=0)
    assert (cache_dir / "movie-2.jpg").exists()
