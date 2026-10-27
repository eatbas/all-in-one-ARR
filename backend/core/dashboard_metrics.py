"""Fixed catalogue of the statistics the dashboard reports and snapshots.

Every figure the dashboard shows is declared here once, keyed by a dotted
``<source>.<name>`` string. The catalogue is the only source of metric keys:
the daily snapshot stores rows under these keys, so user-defined values (root
folder paths, list names) never become keys and the table stays bounded.

``unit`` drives frontend formatting. ``kind`` tells the history endpoint how to
chart a series: a ``gauge`` is plotted as stored, a ``counter`` (an all-time
running total) is turned into per-day deltas. ``snapshot=False`` marks live-only
figures such as download speeds, whose 23:55 value would be meaningless.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

MetricUnit = Literal["count", "bytes", "mbps"]
MetricKind = Literal["gauge", "counter"]


@dataclass(frozen=True)
class MetricSpec:
    """Declarative description of one dashboard metric."""

    key: str
    label: str
    unit: MetricUnit
    kind: MetricKind
    # The ``SOURCES`` key (core.dashboard_sources) whose collector reports it.
    source: str
    # Whether the daily snapshot stores this metric (False for live-only values).
    snapshot: bool = True


def _gauge(key: str, label: str, unit: MetricUnit = "count") -> MetricSpec:
    return MetricSpec(
        key=key, label=label, unit=unit, kind="gauge", source=key.split(".")[0]
    )


def _counter(key: str, label: str) -> MetricSpec:
    return MetricSpec(
        key=key, label=label, unit="count", kind="counter", source=key.split(".")[0]
    )


def _live(key: str, label: str, unit: MetricUnit = "count") -> MetricSpec:
    return MetricSpec(
        key=key,
        label=label,
        unit=unit,
        kind="gauge",
        source=key.split(".")[0],
        snapshot=False,
    )


# Display order within each source card follows declaration order.
_CATALOGUE: tuple[MetricSpec, ...] = (
    # List-Syncarr: tracked items per lifecycle state.
    _gauge("list_syncarr.synced", "Synced"),
    _gauge("list_syncarr.requested", "Requested"),
    _gauge("list_syncarr.available", "Available"),
    _gauge("list_syncarr.removed", "Removed"),
    # Findarr: all-time search commands sent (reset-proof findarr_totals).
    _counter("findarr.sonarr.missing_total", "Sonarr missing searches"),
    _counter("findarr.sonarr.upgrade_total", "Sonarr upgrade searches"),
    _counter("findarr.radarr.missing_total", "Radarr missing searches"),
    _counter("findarr.radarr.upgrade_total", "Radarr upgrade searches"),
    # Deletarr: flagged files and folders from the last scan of each library.
    _gauge("deletarr.movies.junk_items", "Junk items (movies)"),
    _gauge("deletarr.tv.junk_items", "Junk items (TV)"),
    _gauge("deletarr.movies.junk_bytes", "Junk size (movies)", "bytes"),
    _gauge("deletarr.tv.junk_bytes", "Junk size (TV)", "bytes"),
    # Languagarr: last scan's non-compliant files and the replacement queue.
    _gauge("languagarr.non_compliant", "Non-compliant files"),
    _gauge("languagarr.queue_pending", "Queue pending"),
    _gauge("languagarr.queue_failed", "Queue failed"),
    # Sonarr library, queue and disk space.
    _gauge("sonarr.series_total", "Series"),
    _gauge("sonarr.series_monitored", "Monitored series"),
    _gauge("sonarr.episodes_total", "Episodes"),
    _gauge("sonarr.episodes_with_files", "Episodes with files"),
    _gauge("sonarr.episodes_missing", "Missing episodes"),
    _gauge("sonarr.size_on_disk_bytes", "Size on disk", "bytes"),
    _gauge("sonarr.queue_total", "Queue"),
    _gauge("sonarr.disk_free_bytes", "Disk free", "bytes"),
    _gauge("sonarr.disk_total_bytes", "Disk total", "bytes"),
    # Radarr library, queue and disk space.
    _gauge("radarr.movies_total", "Movies"),
    _gauge("radarr.movies_monitored", "Monitored movies"),
    _gauge("radarr.movies_with_files", "Movies with files"),
    _gauge("radarr.movies_missing", "Missing movies"),
    _gauge("radarr.size_on_disk_bytes", "Size on disk", "bytes"),
    _gauge("radarr.queue_total", "Queue"),
    _gauge("radarr.disk_free_bytes", "Disk free", "bytes"),
    _gauge("radarr.disk_total_bytes", "Disk total", "bytes"),
    # Seer request counts by status.
    _gauge("seer.requests_total", "Requests"),
    _gauge("seer.requests_pending", "Pending"),
    _gauge("seer.requests_approved", "Approved"),
    _gauge("seer.requests_processing", "Processing"),
    _gauge("seer.requests_available", "Available"),
    _gauge("seer.requests_declined", "Declined"),
    # Download clients: queue sizes are snapshotted, speeds and active counts
    # are live-only.
    _gauge("sabnzbd.queue_size", "Queue"),
    _live("sabnzbd.speed_mbps", "Speed", "mbps"),
    _live("sabnzbd.active_downloads", "Active downloads"),
    _gauge("qbittorrent.queue_size", "Queue"),
    _live("qbittorrent.speed_mbps", "Speed", "mbps"),
    _live("qbittorrent.active_downloads", "Active downloads"),
)

METRICS: Mapping[str, MetricSpec] = MappingProxyType(
    {spec.key: spec for spec in _CATALOGUE}
)


def snapshot_metric_keys() -> tuple[str, ...]:
    """Return the keys the daily snapshot stores, in catalogue order."""
    return tuple(spec.key for spec in METRICS.values() if spec.snapshot)


def metrics_for_source(source: str) -> tuple[MetricSpec, ...]:
    """Return the catalogue entries reported by ``source``, in display order."""
    return tuple(spec for spec in METRICS.values() if spec.source == source)
