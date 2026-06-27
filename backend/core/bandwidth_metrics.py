"""Prometheus-compatible gauges for the Bandwidth-Controllarr feature.

These gauge names are kept identical to the standalone source service so existing
scrapes can be pointed at this application without changing dashboards or alerts.
"""

from __future__ import annotations

from prometheus_client import Gauge

bw_qbit_active_count = Gauge(
    "bw_qbit_active_count",
    "Number of active qBittorrent downloads",
)

bw_qbit_speed_mbps = Gauge(
    "bw_qbit_speed_mbps",
    "qBittorrent download speed in MB/s",
)

bw_qbit_queue_size = Gauge(
    "bw_qbit_queue_size",
    "Number of queued qBittorrent downloads",
)

bw_sab_active_count = Gauge(
    "bw_sab_active_count",
    "Number of active SABnzbd downloads",
)

bw_sab_paused = Gauge(
    "bw_sab_paused",
    "Whether the SABnzbd queue is paused (1) or not (0)",
)

bw_sab_speed_mbps = Gauge(
    "bw_sab_speed_mbps",
    "SABnzbd download speed in MB/s",
)

bw_sab_queue_size = Gauge(
    "bw_sab_queue_size",
    "Total number of slots in the SABnzbd queue",
)

bw_check_status = Gauge(
    "bw_check_status",
    "Whether the last bandwidth control check completed successfully",
)


def update_bandwidth_metrics(
    qb_stats: dict,
    sab_stats: dict,
    *,
    check_ok: bool,
) -> None:
    """Write client statistics to the Bandwidth-Controllarr gauges.

    Offline or failed clients are reported as zeros so the metrics remain
    present and scrape-friendly even when a download client is temporarily
    unreachable.
    """
    if qb_stats.get("online"):
        bw_qbit_active_count.set(qb_stats.get("active_downloads", 0) or 0)
        bw_qbit_speed_mbps.set(qb_stats.get("speed_mbps", 0) or 0)
        bw_qbit_queue_size.set(qb_stats.get("queue_size", 0) or 0)
    else:
        bw_qbit_active_count.set(0)
        bw_qbit_speed_mbps.set(0)
        bw_qbit_queue_size.set(0)

    if sab_stats.get("online"):
        bw_sab_active_count.set(sab_stats.get("active_downloads", 0) or 0)
        bw_sab_speed_mbps.set(sab_stats.get("speed_mbps", 0) or 0)
        bw_sab_queue_size.set(sab_stats.get("queue_size", 0) or 0)
        bw_sab_paused.set(1 if sab_stats.get("paused") else 0)
    else:
        bw_sab_active_count.set(0)
        bw_sab_speed_mbps.set(0)
        bw_sab_queue_size.set(0)
        bw_sab_paused.set(0)

    bw_check_status.set(1 if check_ok else 0)
