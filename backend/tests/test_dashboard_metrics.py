"""Tests for core.dashboard_metrics (the metric catalogue)."""

from __future__ import annotations

from typing import get_args

from core import dashboard_metrics
from core.dashboard_metrics import (
    METRICS,
    MetricKind,
    MetricUnit,
    metrics_for_source,
    snapshot_metric_keys,
)


def test_catalogue_keys_are_unique_and_match_specs() -> None:
    assert len(METRICS) == len(dashboard_metrics._CATALOGUE)
    for key, spec in METRICS.items():
        assert spec.key == key
        assert key.startswith(f"{spec.source}.")


def test_every_spec_has_a_valid_unit_and_kind() -> None:
    for spec in METRICS.values():
        assert spec.unit in get_args(MetricUnit)
        assert spec.kind in get_args(MetricKind)
        assert spec.label


def test_snapshot_keys_exclude_live_only_metrics() -> None:
    keys = snapshot_metric_keys()
    assert "sabnzbd.speed_mbps" not in keys
    assert "qbittorrent.speed_mbps" not in keys
    assert "sabnzbd.active_downloads" not in keys
    assert "qbittorrent.active_downloads" not in keys
    assert "sabnzbd.queue_size" in keys
    assert set(keys) == {key for key, spec in METRICS.items() if spec.snapshot}


def test_metrics_for_source_filters_in_catalogue_order() -> None:
    seer = metrics_for_source("seer")
    assert [spec.key for spec in seer] == [
        "seer.requests_total",
        "seer.requests_pending",
        "seer.requests_approved",
        "seer.requests_processing",
        "seer.requests_available",
        "seer.requests_declined",
    ]
    assert metrics_for_source("trending") == ()


def test_findarr_totals_are_counters_and_the_rest_gauges() -> None:
    counters = {key for key, spec in METRICS.items() if spec.kind == "counter"}
    assert counters == {
        "findarr.sonarr.missing_total",
        "findarr.sonarr.upgrade_total",
        "findarr.radarr.missing_total",
        "findarr.radarr.upgrade_total",
    }
