"""Prometheus metrics shared across All-in-One ARR features."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter, time

from prometheus_client import Counter, Gauge, Histogram

sync_runs_total = Counter(
    "aio_arr_sync_runs_total",
    "List-Syncarr runs by trigger and outcome",
    ("trigger", "status"),
)
sync_run_duration_seconds = Histogram(
    "aio_arr_sync_run_duration_seconds",
    "List-Syncarr run duration in seconds",
    ("trigger", "status"),
)
sync_last_success_timestamp_seconds = Gauge(
    "aio_arr_sync_last_success_timestamp_seconds",
    "Unix timestamp of the last successful List-Syncarr run",
)

service_status = Gauge(
    "aio_arr_service_status",
    "Integration health status: 1 for OK, 0 for failing or unknown",
    ("service",),
)
service_last_check_timestamp_seconds = Gauge(
    "aio_arr_service_last_check_timestamp_seconds",
    "Unix timestamp of the last integration health check",
    ("service",),
)

scheduler_job_runs_total = Counter(
    "aio_arr_scheduler_job_runs_total",
    "Scheduled job executions by job id and outcome",
    ("job_id", "status"),
)
scheduler_job_last_run_timestamp_seconds = Gauge(
    "aio_arr_scheduler_job_last_run_timestamp_seconds",
    "Unix timestamp of the last scheduled job execution",
    ("job_id", "status"),
)
scheduler_job_duration_seconds = Histogram(
    "aio_arr_scheduler_job_duration_seconds",
    "Scheduled job execution duration in seconds",
    ("job_id", "status"),
)

findarr_runs_total = Counter(
    "aio_arr_findarr_runs_total",
    "Findarr runs by app scope and outcome",
    ("app", "status"),
)
findarr_searches_total = Counter(
    "aio_arr_findarr_searches_total",
    "Findarr search commands by app, mode, and outcome",
    ("app", "mode", "status"),
)
findarr_hourly_capacity_remaining = Gauge(
    "aio_arr_findarr_hourly_capacity_remaining",
    "Remaining Findarr search capacity in the current hour",
)

deletarr_scans_total = Counter(
    "aio_arr_deletarr_scans_total",
    "Deletarr scans by library, scan mode, and outcome",
    ("library", "mode", "status"),
)
deletarr_scan_results = Gauge(
    "aio_arr_deletarr_scan_results",
    "Number of Deletarr scan candidates by library and scan mode",
    ("library", "mode"),
)
deletarr_deleted_items_total = Counter(
    "aio_arr_deletarr_deleted_items_total",
    "Deletarr deletion results by library and outcome",
    ("library", "status"),
)
deletarr_freed_bytes_total = Counter(
    "aio_arr_deletarr_freed_bytes_total",
    "Bytes freed by Deletarr deletions",
    ("library",),
)


def initialise_metrics() -> None:
    """Initialise known low-cardinality metric label sets."""
    for trigger in ("scheduled", "manual"):
        for status in ("success", "error", "skipped"):
            sync_runs_total.labels(trigger, status)
            sync_run_duration_seconds.labels(trigger, status)
    for service in (
        "trakt",
        "seer",
        "sonarr",
        "radarr",
        "tmdb",
        "omdb",
        "sabnzbd",
        "qbittorrent",
    ):
        service_status.labels(service).set(0)
        service_last_check_timestamp_seconds.labels(service).set(0)
    for job_id in (
        "list_syncarr_poll",
        "bandwidth_control",
        "findarr_poll",
        "trending_sync",
        "poster_cache_churn",
    ):
        for status in ("success", "error"):
            scheduler_job_runs_total.labels(job_id, status)
            scheduler_job_last_run_timestamp_seconds.labels(job_id, status).set(0)
            scheduler_job_duration_seconds.labels(job_id, status)
    for app in ("all", "sonarr", "radarr"):
        for status in ("completed", "skipped", "error"):
            findarr_runs_total.labels(app, status)
    for app in ("sonarr", "radarr"):
        for mode in ("missing", "upgrade"):
            for status in ("success", "error"):
                findarr_searches_total.labels(app, mode, status)
    for library in ("movies", "tv"):
        deletarr_freed_bytes_total.labels(library)
        for status in ("success", "failed"):
            deletarr_deleted_items_total.labels(library, status)
        for mode in ("heuristic", "arr"):
            deletarr_scan_results.labels(library, mode).set(0)
            for status in ("success", "error"):
                deletarr_scans_total.labels(library, mode, status)


def record_sync_run(*, trigger: str, status: str, duration_seconds: float) -> None:
    """Record one List-Syncarr run."""
    sync_runs_total.labels(trigger, status).inc()
    sync_run_duration_seconds.labels(trigger, status).observe(duration_seconds)
    if status == "success":
        sync_last_success_timestamp_seconds.set(time())


def update_service_metrics(
    name: str, *, ok: bool, checked_at: float | None = None
) -> None:
    """Update cached health metrics for one integration."""
    service_status.labels(name).set(1 if ok else 0)
    service_last_check_timestamp_seconds.labels(name).set(checked_at or time())


async def observe_scheduler_job[T](job_id: str, job: Callable[[], Awaitable[T]]) -> T:
    """Run ``job`` and record bounded scheduler metrics around it."""
    started = perf_counter()
    status = "success"
    try:
        return await job()
    except Exception:
        status = "error"
        raise
    finally:
        duration = perf_counter() - started
        scheduler_job_runs_total.labels(job_id, status).inc()
        scheduler_job_duration_seconds.labels(job_id, status).observe(duration)
        scheduler_job_last_run_timestamp_seconds.labels(job_id, status).set(time())


def record_findarr_run(*, app: str, status: str) -> None:
    """Record one Findarr run outcome."""
    findarr_runs_total.labels(app, status).inc()


def record_findarr_search(*, app: str, mode: str, status: str) -> None:
    """Record one attempted Findarr search command."""
    findarr_searches_total.labels(app, mode, status).inc()


def update_findarr_capacity(remaining: int) -> None:
    """Set the current remaining Findarr hourly capacity."""
    findarr_hourly_capacity_remaining.set(max(0, remaining))


def record_deletarr_scan(
    *, library: str, mode: str, status: str, results_count: int | None = None
) -> None:
    """Record a Deletarr scan outcome."""
    deletarr_scans_total.labels(library, mode, status).inc()
    if results_count is not None:
        deletarr_scan_results.labels(library, mode).set(results_count)


def record_deletarr_delete(
    *, library: str, deleted: int, failed: int, freed_bytes: int
) -> None:
    """Record Deletarr deletion counters."""
    if deleted:
        deletarr_deleted_items_total.labels(library, "success").inc(deleted)
    if failed:
        deletarr_deleted_items_total.labels(library, "failed").inc(failed)
    if freed_bytes:
        deletarr_freed_bytes_total.labels(library).inc(freed_bytes)


initialise_metrics()
