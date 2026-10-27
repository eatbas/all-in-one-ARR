"""Aggregated, cached dashboard statistics and the daily snapshot.

:class:`DashboardService` resolves every source in :data:`core.dashboard_sources.SOURCES`
concurrently. Each source has its own cache lifetime, its own single-flight lock
(so concurrent polls share one upstream round) and its own timeout, so a slow or
dead service only degrades its own card: it is reported ``offline`` with the
values of its newest daily snapshot.

The cache and locks are instance state on the one service held by
``AppContext.dashboard`` (mirroring ``status_checker``) — the justified
alternative to a module-level cache, which would be hidden global state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core import dashboard_sources
from core.dashboard_metrics import METRICS, metrics_for_source, snapshot_metric_keys
from core.dashboard_sources import SourceResult, SourceSpec
from core.db_dashboard import DASHBOARD_SNAPSHOT_RETENTION_DAYS
from core.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

# Upper bound on one source's collection; a slower source is reported offline.
_SOURCE_TIMEOUT_SECONDS = 8.0
# How often the frontend polls the summary (echoed to the client).
DASHBOARD_REFRESH_SECONDS = 60

# Headline figures in display order: (KPI key, label, unit). Values are derived
# from the live source metrics in ``_kpis``.
_KPIS: tuple[tuple[str, str, str], ...] = (
    ("movies", "Movies", "count"),
    ("series", "Series", "count"),
    ("missing_episodes", "Missing episodes", "count"),
    ("missing_movies", "Missing movies", "count"),
    ("free_disk", "Free disk space", "bytes"),
    ("pending_requests", "Pending requests", "count"),
    ("active_downloads", "Active downloads", "count"),
    ("non_compliant_anime", "Non-compliant anime files", "count"),
)
# Sources whose ``<key>.active_downloads`` add up to the Active downloads KPI.
_DOWNLOAD_CLIENTS: tuple[str, ...] = ("sabnzbd", "qbittorrent")

_log = get_logger("dashboard")


def _local_now() -> datetime:
    """Return the current time in the container's local zone (``TZ``)."""
    return datetime.now().astimezone()


@dataclass(frozen=True)
class _CacheEntry:
    """One source's cached result and when it was fetched."""

    result: SourceResult
    fetched_at: datetime


class DashboardService:
    """Resolve, cache and snapshot the dashboard's per-source statistics."""

    def __init__(
        self,
        ctx: AppContext,
        *,
        clock: Callable[[], datetime] = _local_now,
        timeout_seconds: float = _SOURCE_TIMEOUT_SECONDS,
    ) -> None:
        self._ctx = ctx
        self._clock = clock
        self._timeout = timeout_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ---- resolution ----

    def _lock_for(self, key: str) -> asyncio.Lock:
        """Return the source's lock, created lazily inside the running loop."""
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    def _fresh(self, spec: SourceSpec) -> SourceResult | None:
        """Return the cached result while it is younger than the source's TTL."""
        entry = self._cache.get(spec.key)
        if entry is None:
            return None
        age = (self._clock() - entry.fetched_at).total_seconds()
        return entry.result if age < spec.ttl_seconds else None

    async def _resolve(
        self, spec: SourceSpec, *, use_cache: bool = True
    ) -> SourceResult:
        """Return a source's result, collecting it at most once per TTL.

        Failures are cached for the same TTL, so a dead service is not retried on
        every poll. ``use_cache=False`` forces a fresh collection (the snapshot).
        """
        if use_cache and (cached := self._fresh(spec)) is not None:
            return cached
        async with self._lock_for(spec.key):
            if use_cache and (cached := self._fresh(spec)) is not None:
                return cached
            result = await self._collect(spec)
            self._cache[spec.key] = _CacheEntry(result=result, fetched_at=self._clock())
            return result

    async def _collect(self, spec: SourceSpec) -> SourceResult:
        """Run a collector under the timeout, degrading any failure to offline.

        ``asyncio.CancelledError`` is a ``BaseException`` and propagates.
        """
        try:
            return await asyncio.wait_for(spec.collector(self._ctx), self._timeout)
        except TimeoutError:
            detail = f"Timed out after {self._timeout:g} s."
        except Exception as exc:  # noqa: BLE001 - one source must not break the page
            detail = str(exc) or type(exc).__name__
        _log.warning("dashboard source %s unavailable: %s", spec.key, detail)
        return self._offline(spec, detail)

    def _offline(self, spec: SourceSpec, detail: str) -> SourceResult:
        """Build an offline result carrying the source's newest snapshot values."""
        keys = [m.key for m in metrics_for_source(spec.key) if m.snapshot]
        latest = self._ctx.db.dashboard_snapshot_latest(keys)
        stale_since = max((row["recorded_at"] for row in latest.values()), default=None)
        return SourceResult(
            key=spec.key,
            label=spec.label,
            state="offline",
            link=spec.link,
            detail=detail,
            metrics={key: float(row["value"]) for key, row in latest.items()},
            stale_since=stale_since,
        )

    async def _resolve_all(self, *, use_cache: bool = True) -> list[SourceResult]:
        """Resolve every source concurrently, in display order."""
        return list(
            await asyncio.gather(
                *(
                    self._resolve(spec, use_cache=use_cache)
                    for spec in dashboard_sources.SOURCES
                )
            )
        )

    # ---- summary ----

    async def summary(self) -> dict[str, Any]:
        """Return the live summary: KPIs, per-source cards and disk rows.

        ``latest_snapshot_at`` lets a polling client notice a new daily snapshot
        and refresh the trends it fetched earlier.
        """
        results = await self._resolve_all()
        return {
            "generated_at": self._clock().isoformat(),
            "refresh_seconds": DASHBOARD_REFRESH_SECONDS,
            "latest_snapshot_at": self._ctx.db.dashboard_snapshot_last_recorded_at(),
            "kpis": _kpis(results),
            "sources": [_serialise_source(result) for result in results],
            "disks": _disks(results),
        }

    # ---- snapshot ----

    async def take_snapshot(self) -> int:
        """Store today's snapshot metrics from every ``ok`` source; prune old days.

        Bypasses the cache so the stored values are current. Offline sources
        write nothing, so a stale value is never re-stored as a fresh day.
        Returns the number of rows written.
        """
        results = await self._resolve_all(use_cache=False)
        keys = set(snapshot_metric_keys())
        values = {
            metric: value
            for result in results
            if result.state == "ok"
            for metric, value in result.metrics.items()
            if metric in keys
        }
        now = self._clock()
        today = now.date()
        written = self._ctx.db.dashboard_snapshot_upsert(
            day=today.isoformat(), values=values, recorded_at=now.isoformat()
        )
        cutoff = today - timedelta(days=DASHBOARD_SNAPSHOT_RETENTION_DAYS)
        self._ctx.db.dashboard_snapshot_prune(before_day=cutoff.isoformat())
        return written

    def today(self) -> str:
        """Return today's local day key (``YYYY-MM-DD``)."""
        return self._clock().date().isoformat()

    # ---- history ----

    def history(self, days: int) -> dict[str, Any]:
        """Return one series per snapshot metric for the last ``days`` days.

        Rows are read from one day before the window so each counter's first
        in-window delta can be computed. Gauges are returned as stored; counters
        become per-day deltas clamped at 0, and a counter point whose previous
        day is missing is omitted rather than invented.

        ``latest_snapshot_at`` is read before the rows: a snapshot landing in
        between leaves it older than the rows, which only costs the client one
        extra refresh, never a missed one.
        """
        today = self._clock().date()
        window_start = today - timedelta(days=days - 1)
        latest_snapshot_at = self._ctx.db.dashboard_snapshot_last_recorded_at()
        rows = self._ctx.db.dashboard_snapshot_range(
            start_day=(window_start - timedelta(days=1)).isoformat(),
            end_day=today.isoformat(),
        )
        by_metric: dict[str, dict[date, float]] = {}
        for row in rows:
            by_metric.setdefault(row["metric"], {})[date.fromisoformat(row["day"])] = (
                float(row["value"])
            )
        series = [
            _history_series(key, by_metric.get(key, {}), window_start)
            for key in snapshot_metric_keys()
        ]
        return {
            "days": days,
            "start_day": window_start.isoformat(),
            "end_day": today.isoformat(),
            "latest_snapshot_at": latest_snapshot_at,
            "series": series,
        }


def _history_series(
    key: str, values: dict[date, float], window_start: date
) -> dict[str, Any]:
    """Build one metric's chart series from its ``{day: value}`` rows."""
    spec = METRICS[key]
    points: list[dict[str, Any]] = []
    for day in sorted(values):
        if day < window_start:
            continue
        value = values[day]
        if spec.kind == "counter":
            previous = values.get(day - timedelta(days=1))
            if previous is None:
                continue
            value = max(0.0, value - previous)
        points.append({"day": day.isoformat(), "value": value})
    return {
        "key": key,
        "label": spec.label,
        "unit": spec.unit,
        "kind": spec.kind,
        "points": points,
    }


def _serialise_source(result: SourceResult) -> dict[str, Any]:
    """Serialise a result with each catalogue metric's label and unit.

    Offline sources list every catalogue metric (``None`` where no snapshot
    exists); other states list the catalogue only when they reported values.
    """
    specs = metrics_for_source(result.key)
    if not result.metrics and result.state != "offline":
        specs = ()
    return {
        "key": result.key,
        "label": result.label,
        "state": result.state,
        "detail": result.detail,
        "stale_since": result.stale_since,
        "updated_at": result.updated_at,
        "link": result.link,
        "metrics": [
            {
                "key": spec.key,
                "label": spec.label,
                "unit": spec.unit,
                "value": result.metrics.get(spec.key),
            }
            for spec in specs
        ],
    }


def _live_metrics(results: list[SourceResult]) -> dict[str, float]:
    """Return the metrics of sources whose values are current (not offline)."""
    return {
        key: value
        for result in results
        if result.state in ("ok", "disabled")
        for key, value in result.metrics.items()
    }


def _kpis(results: list[SourceResult]) -> list[dict[str, Any]]:
    """Derive the headline figures; a KPI whose source is unavailable is ``None``."""
    live = _live_metrics(results)
    values: dict[str, float | None] = {
        "movies": live.get("radarr.movies_total"),
        "series": live.get("sonarr.series_total"),
        "missing_episodes": live.get("sonarr.episodes_missing"),
        "missing_movies": live.get("radarr.movies_missing"),
        "free_disk": _tightest_free_bytes(results),
        "pending_requests": live.get("seer.requests_pending"),
        "active_downloads": _active_downloads(results),
        "non_compliant_anime": live.get("languagarr.non_compliant"),
    }
    return [
        {"key": key, "label": label, "unit": unit, "value": values[key]}
        for key, label, unit in _KPIS
    ]


def _active_downloads(results: list[SourceResult]) -> float | None:
    """Sum active downloads over the configured download clients.

    An unconfigured client is left out, but a configured client that is not
    ``ok`` makes the total unknown (``None``): a partial sum would understate it.
    With no configured client at all the KPI is ``None`` too.
    """
    by_key = {result.key: result for result in results}
    total: float | None = None
    for source in _DOWNLOAD_CLIENTS:
        result = by_key.get(source)
        if result is None or result.state == "not_configured":
            continue
        metric = f"{source}.active_downloads"
        if result.state != "ok" or metric not in result.metrics:
            return None
        total = (total or 0.0) + result.metrics[metric]
    return total


def _tightest_free_bytes(results: list[SourceResult]) -> float | None:
    """Return the free bytes of the disk with the smallest free fraction."""
    disks = [disk for disk in _disks(results) if disk["total_bytes"] > 0]
    if not disks:
        return None
    tightest = min(disks, key=lambda disk: disk["free_bytes"] / disk["total_bytes"])
    return float(tightest["free_bytes"])


def _disks(results: list[SourceResult]) -> list[dict[str, Any]]:
    """Return the disk rows reported by ``ok`` Sonarr/Radarr results."""
    return [
        dict(disk)
        for result in results
        if result.state == "ok"
        for disk in result.extra.get("disks", [])
    ]
