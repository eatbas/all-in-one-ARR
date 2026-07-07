"""Tests for shared Prometheus metric helpers."""

from __future__ import annotations

import pytest

from core.app_metrics import (
    deletarr_deleted_items_total,
    deletarr_freed_bytes_total,
    deletarr_scan_results,
    findarr_hourly_capacity_remaining,
    findarr_runs_total,
    findarr_searches_total,
    record_deletarr_delete,
    record_deletarr_scan,
    record_findarr_run,
    record_findarr_search,
    record_sync_run,
    scheduler_job_runs_total,
    service_status,
    sync_runs_total,
    update_findarr_capacity,
    update_service_metrics,
    observe_scheduler_job,
)


def _counter_value(metric, *labels: str) -> float:
    return metric.labels(*labels)._value.get()


def test_sync_and_service_metrics_update() -> None:
    before = _counter_value(sync_runs_total, "manual", "success")
    record_sync_run(trigger="manual", status="success", duration_seconds=0.01)
    assert _counter_value(sync_runs_total, "manual", "success") == before + 1

    update_service_metrics("trakt", ok=True, checked_at=123)
    assert service_status.labels("trakt")._value.get() == 1


@pytest.mark.asyncio
async def test_scheduler_job_metrics_update() -> None:
    before = _counter_value(scheduler_job_runs_total, "findarr_poll", "success")

    async def job() -> str:
        return "done"

    assert await observe_scheduler_job("findarr_poll", job) == "done"
    assert _counter_value(scheduler_job_runs_total, "findarr_poll", "success") == before + 1


def test_findarr_metrics_update() -> None:
    run_before = _counter_value(findarr_runs_total, "sonarr", "completed")
    search_before = _counter_value(findarr_searches_total, "sonarr", "missing", "success")

    record_findarr_run(app="sonarr", status="completed")
    record_findarr_search(app="sonarr", mode="missing", status="success")
    update_findarr_capacity(12)

    assert _counter_value(findarr_runs_total, "sonarr", "completed") == run_before + 1
    assert (
        _counter_value(findarr_searches_total, "sonarr", "missing", "success")
        == search_before + 1
    )
    assert findarr_hourly_capacity_remaining._value.get() == 12


def test_deletarr_metrics_update() -> None:
    deleted_before = _counter_value(deletarr_deleted_items_total, "movies", "success")
    failed_before = _counter_value(deletarr_deleted_items_total, "movies", "failed")
    freed_before = _counter_value(deletarr_freed_bytes_total, "movies")

    record_deletarr_scan(
        library="movies", mode="arr", status="success", results_count=4
    )
    record_deletarr_delete(
        library="movies", deleted=2, failed=1, freed_bytes=2048
    )

    assert deletarr_scan_results.labels("movies", "arr")._value.get() == 4
    assert (
        _counter_value(deletarr_deleted_items_total, "movies", "success")
        == deleted_before + 2
    )
    assert (
        _counter_value(deletarr_deleted_items_total, "movies", "failed")
        == failed_before + 1
    )
    assert _counter_value(deletarr_freed_bytes_total, "movies") == freed_before + 2048
