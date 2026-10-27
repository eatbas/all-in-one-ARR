"""Per-source statistics collectors for the dashboard.

Each collector reads one module or upstream service and returns a
:class:`SourceResult` holding only that source's catalogue metrics
(:mod:`core.dashboard_metrics`). Collectors decide the ``not_configured`` and
``disabled`` states themselves; a failure (an upstream error, or a download
client reporting itself offline) is raised and turned into an ``offline``
result, with last-snapshot fallback values, by :class:`core.dashboard.DashboardService`.

Collectors are read-only: they never trigger a sync, scan or search.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from core.clients.servarr_stats import ServarrStatsClient, stats_client_for

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext

SourceState = Literal["ok", "offline", "not_configured", "disabled"]

# Seconds a library source (whole Sonarr series / Radarr movie list) stays
# cached; those endpoints scale with library size.
LIBRARY_TTL_SECONDS = 900
# Seconds every other source stays cached; just under the 60 s frontend poll so
# each poll is served fresh figures.
LIVE_TTL_SECONDS = 55

_SETTINGS_LINK = "/settings"


class SourceUnavailableError(RuntimeError):
    """Raised by a collector whose source answered but reports itself offline."""


@dataclass(frozen=True)
class SourceResult:
    """One source's statistics and state at a point in time."""

    key: str
    label: str
    state: SourceState
    link: str
    detail: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
    # Source-specific structured data; Sonarr/Radarr carry ``disks`` rows here.
    extra: dict[str, Any] = field(default_factory=dict)
    # When the source's own data last refreshed (Trending's snapshot time).
    updated_at: str | None = None
    # For an offline source: when the fallback snapshot values were recorded.
    stale_since: str | None = None


Collector = Callable[["AppContext"], Awaitable[SourceResult]]


@dataclass(frozen=True)
class SourceSpec:
    """A dashboard source: its display label, collector and cache lifetime."""

    key: str
    label: str
    collector: Collector
    ttl_seconds: int
    link: str


def _spec_result(spec_key: str, state: SourceState, **fields: Any) -> SourceResult:
    """Build a result for ``spec_key`` using its label and link from ``SOURCES``."""
    spec = SOURCES_BY_KEY[spec_key]
    return SourceResult(
        key=spec.key, label=spec.label, state=state, link=spec.link, **fields
    )


def _service_configured(ctx: AppContext, name: str) -> bool:
    """Return whether a URL/API-key service has both fields stored."""
    url, api_key = ctx.settings_store.service_connection(name)
    return bool(url and api_key)


async def collect_list_syncarr(ctx: AppContext) -> SourceResult:
    """List-Syncarr tracked items per lifecycle state."""
    if not ctx.settings_store.tracked_lists():
        return _spec_result(
            "list_syncarr", "not_configured", detail="No Trakt lists are tracked yet."
        )
    if not ctx.trakt.is_authenticated():
        return _spec_result(
            "list_syncarr", "not_configured", detail="Trakt is not connected."
        )
    counts = ctx.db.counts_by_status()
    metrics = {f"list_syncarr.{status}": float(n) for status, n in counts.items()}
    return _spec_result("list_syncarr", "ok", metrics=metrics)


async def collect_findarr(ctx: AppContext) -> SourceResult:
    """Findarr all-time search totals; reported even while Findarr is disabled."""
    totals = ctx.db.findarr_totals()
    metrics = {
        f"findarr.{app}.{mode}_total": float(count)
        for app, modes in totals.items()
        for mode, count in modes.items()
    }
    if ctx.findarr_status is None:
        return _spec_result("findarr", "disabled", metrics=metrics)
    status = await ctx.findarr_status()
    enabled = bool(status.get("settings", {}).get("enabled"))
    return _spec_result("findarr", "ok" if enabled else "disabled", metrics=metrics)


def _deletarr_library_metrics(library: str, payload: Any) -> dict[str, float]:
    """Return one Deletarr library's junk item count and size."""
    stats = payload.get("stats", {}) if isinstance(payload, dict) else {}
    items = int(stats.get("total_files", 0)) + int(stats.get("total_folders", 0))
    return {
        f"deletarr.{library}.junk_items": float(items),
        f"deletarr.{library}.junk_bytes": float(stats.get("total_size", 0)),
    }


async def collect_deletarr(ctx: AppContext) -> SourceResult:
    """Deletarr flagged items and their size, per library, from the last scan."""
    if ctx.deletarr_status is None:
        return _spec_result("deletarr", "disabled")
    libraries = (await ctx.deletarr_status()).get("libraries", {})
    metrics: dict[str, float] = {}
    for library in ("movies", "tv"):
        metrics.update(_deletarr_library_metrics(library, libraries.get(library)))
    return _spec_result("deletarr", "ok", metrics=metrics)


async def collect_languagarr(ctx: AppContext) -> SourceResult:
    """Languagarr's last scan and queue; reported even while it is disabled."""
    if ctx.languagarr_status is None:
        return _spec_result("languagarr", "disabled")
    status = await ctx.languagarr_status()
    scan = status.get("scan", {})
    queue = status.get("queue", {})
    metrics = {
        "languagarr.non_compliant": float(scan.get("non_compliant", 0)),
        "languagarr.queue_pending": float(queue.get("pending", 0)),
        "languagarr.queue_failed": float(queue.get("failed", 0)),
    }
    enabled = bool(status.get("settings", {}).get("enabled"))
    return _spec_result(
        "languagarr",
        "ok" if enabled else "disabled",
        metrics=metrics,
        updated_at=scan.get("last_scan_at"),
    )


async def collect_bandwidth(ctx: AppContext) -> SourceResult:
    """Bandwidth-Controllarr: whether it currently holds SABnzbd paused."""
    if (
        ctx.bandwidth_status is None
        or not ctx.settings_store.bandwidth_control_enabled()
    ):
        return _spec_result("bandwidth", "disabled")
    stats = await ctx.sabnzbd.get_stats()
    if not stats.get("online"):
        detail = "SABnzbd is offline."
    elif stats.get("paused"):
        detail = "SABnzbd is paused while torrents download."
    else:
        detail = "SABnzbd is downloading."
    return _spec_result("bandwidth", "ok", detail=detail)


async def collect_trending(ctx: AppContext) -> SourceResult:
    """Trending: when the in-process snapshot last refreshed."""
    return _spec_result(
        "trending", "ok", updated_at=ctx.trending_store.last_synced_at()
    )


async def _servarr_figures(
    client: ServarrStatsClient,
) -> tuple[dict[str, int], list[dict[str, Any]], int, int]:
    """Fetch library stats, disk space, queue and missing totals concurrently.

    A failing request cancels its siblings; the first error is re-raised on its
    own so the offline detail stays readable.
    """
    try:
        async with asyncio.TaskGroup() as group:
            library = group.create_task(client.library_stats())
            disks = group.create_task(client.disk_space())
            queue = group.create_task(client.queue_total())
            missing = group.create_task(client.missing_total())
    except ExceptionGroup as failure:
        raise failure.exceptions[0] from None
    return library.result(), disks.result(), queue.result(), missing.result()


async def _collect_servarr(
    ctx: AppContext, app: Literal["sonarr", "radarr"]
) -> SourceResult:
    """Sonarr/Radarr library, queue, missing and disk figures."""
    client = stats_client_for(ctx.sonarr if app == "sonarr" else ctx.radarr, app=app)
    try:
        if not client.configured:
            return _spec_result(app, "not_configured")
        library, disks, queue, missing = await _servarr_figures(client)
    finally:
        await client.aclose()
    metrics = {f"{app}.{name}": float(value) for name, value in library.items()}
    missing_key = "episodes_missing" if app == "sonarr" else "movies_missing"
    metrics[f"{app}.{missing_key}"] = float(missing)
    metrics[f"{app}.queue_total"] = float(queue)
    metrics[f"{app}.disk_free_bytes"] = float(sum(d["free_bytes"] for d in disks))
    metrics[f"{app}.disk_total_bytes"] = float(sum(d["total_bytes"] for d in disks))
    rows = [{"app": app, **disk} for disk in disks]
    return _spec_result(app, "ok", metrics=metrics, extra={"disks": rows})


async def collect_sonarr(ctx: AppContext) -> SourceResult:
    """Sonarr library, queue, missing episodes and disk space."""
    return await _collect_servarr(ctx, "sonarr")


async def collect_radarr(ctx: AppContext) -> SourceResult:
    """Radarr library, queue, missing movies and disk space."""
    return await _collect_servarr(ctx, "radarr")


async def collect_seer(ctx: AppContext) -> SourceResult:
    """Seer request counts by status."""
    if not _service_configured(ctx, "seer"):
        return _spec_result("seer", "not_configured")
    counts = await ctx.seer.request_counts()
    metrics = {
        "seer.requests_total": float(counts["total"]),
        "seer.requests_pending": float(counts["pending"]),
        "seer.requests_approved": float(counts["approved"]),
        "seer.requests_processing": float(counts["processing"]),
        "seer.requests_available": float(counts["available"]),
        "seer.requests_declined": float(counts["declined"]),
    }
    return _spec_result("seer", "ok", metrics=metrics)


async def _collect_download_client(
    ctx: AppContext, name: Literal["sabnzbd", "qbittorrent"]
) -> SourceResult:
    """SABnzbd/qBittorrent queue size, live speed and active downloads."""
    if not _service_configured(ctx, name):
        return _spec_result(name, "not_configured")
    client = ctx.sabnzbd if name == "sabnzbd" else ctx.qbittorrent
    stats = await client.get_stats()
    if not stats.get("online"):
        raise SourceUnavailableError(f"{SOURCES_BY_KEY[name].label} is unreachable.")
    metrics = {
        f"{name}.queue_size": float(stats.get("queue_size", 0)),
        f"{name}.speed_mbps": float(stats.get("speed_mbps", 0)),
        f"{name}.active_downloads": float(stats.get("active_downloads", 0)),
    }
    return _spec_result(name, "ok", metrics=metrics)


async def collect_sabnzbd(ctx: AppContext) -> SourceResult:
    """SABnzbd queue and live speed."""
    return await _collect_download_client(ctx, "sabnzbd")


async def collect_qbittorrent(ctx: AppContext) -> SourceResult:
    """qBittorrent queue and live speed."""
    return await _collect_download_client(ctx, "qbittorrent")


# Every dashboard source, in display order.
SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "list_syncarr",
        "List-Syncarr",
        collect_list_syncarr,
        LIVE_TTL_SECONDS,
        "/list-syncarr",
    ),
    SourceSpec("findarr", "Findarr", collect_findarr, LIVE_TTL_SECONDS, "/findarr"),
    SourceSpec("deletarr", "Deletarr", collect_deletarr, LIVE_TTL_SECONDS, "/deletarr"),
    SourceSpec(
        "languagarr", "Languagarr", collect_languagarr, LIVE_TTL_SECONDS, "/languagarr"
    ),
    SourceSpec(
        "bandwidth",
        "Bandwidth-Controllarr",
        collect_bandwidth,
        LIVE_TTL_SECONDS,
        "/bandwidth-controllarr",
    ),
    SourceSpec("trending", "Trending", collect_trending, LIVE_TTL_SECONDS, "/trending"),
    SourceSpec("sonarr", "Sonarr", collect_sonarr, LIBRARY_TTL_SECONDS, _SETTINGS_LINK),
    SourceSpec("radarr", "Radarr", collect_radarr, LIBRARY_TTL_SECONDS, _SETTINGS_LINK),
    SourceSpec("seer", "Seer", collect_seer, LIVE_TTL_SECONDS, _SETTINGS_LINK),
    SourceSpec("sabnzbd", "SABnzbd", collect_sabnzbd, LIVE_TTL_SECONDS, _SETTINGS_LINK),
    SourceSpec(
        "qbittorrent",
        "qBittorrent",
        collect_qbittorrent,
        LIVE_TTL_SECONDS,
        _SETTINGS_LINK,
    ),
)

SOURCES_BY_KEY: Mapping[str, SourceSpec] = MappingProxyType(
    {spec.key: spec for spec in SOURCES}
)
