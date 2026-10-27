"""Tests for core.dashboard_api (the /api/dashboard routes)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dashboard_api import create_dashboard_router
from tests.conftest import make_ctx

_SUMMARY: dict[str, Any] = {
    "generated_at": "2026-10-27T12:00:00+00:00",
    "refresh_seconds": 60,
    "latest_snapshot_at": "2026-10-26T23:55:00+00:00",
    "kpis": [
        {"key": "movies", "label": "Movies", "unit": "count", "value": 12},
        {
            "key": "pending_requests",
            "label": "Pending requests",
            "unit": "count",
            "value": None,
        },
    ],
    "sources": [
        {
            "key": "radarr",
            "label": "Radarr",
            "state": "ok",
            "detail": None,
            "stale_since": None,
            "updated_at": None,
            "link": "/settings",
            "metrics": [
                {
                    "key": "radarr.movies_total",
                    "label": "Movies",
                    "unit": "count",
                    "value": 12,
                }
            ],
        },
        {
            "key": "seer",
            "label": "Seer",
            "state": "offline",
            "detail": "Timed out after 8 s.",
            "stale_since": "2026-10-26T23:55:00+00:00",
            "updated_at": None,
            "link": "/settings",
            "metrics": [
                {
                    "key": "seer.requests_pending",
                    "label": "Pending",
                    "unit": "count",
                    "value": 4,
                }
            ],
        },
    ],
    "disks": [
        {
            "app": "radarr",
            "path": "/movies",
            "label": None,
            "free_bytes": 5,
            "total_bytes": 10,
        }
    ],
}


class _StubDashboard:
    """Stand-in for DashboardService recording the history range requested."""

    def __init__(self) -> None:
        self.history_days: list[int] = []

    async def summary(self) -> dict[str, Any]:
        return _SUMMARY

    def history(self, days: int) -> dict[str, Any]:
        self.history_days.append(days)
        return {
            "days": days,
            "start_day": "2026-10-21",
            "end_day": "2026-10-27",
            "latest_snapshot_at": None,
            "series": [
                {
                    "key": "findarr.sonarr.missing_total",
                    "label": "Sonarr missing searches",
                    "unit": "count",
                    "kind": "counter",
                    "points": [{"day": "2026-10-27", "value": 3}],
                }
            ],
        }


def _client(db, dashboard: Any) -> TestClient:
    ctx = make_ctx(db=db)
    ctx.dashboard = dashboard
    app = FastAPI()
    app.include_router(create_dashboard_router(ctx))
    return TestClient(app)


def test_summary_returns_schema_with_an_offline_source(db) -> None:
    response = _client(db, _StubDashboard()).get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["kpis"][1]["value"] is None
    assert body["sources"][1]["state"] == "offline"
    assert body["sources"][1]["stale_since"] == "2026-10-26T23:55:00+00:00"
    assert body["disks"][0]["app"] == "radarr"
    assert body["latest_snapshot_at"] == "2026-10-26T23:55:00+00:00"


@pytest.mark.parametrize("days", [7, 30, 90])
def test_history_accepts_supported_ranges(db, days: int) -> None:
    dashboard = _StubDashboard()
    response = _client(db, dashboard).get(f"/api/dashboard/history?days={days}")
    assert response.status_code == 200
    assert response.json()["days"] == days
    assert response.json()["series"][0]["kind"] == "counter"
    assert response.json()["latest_snapshot_at"] is None
    assert dashboard.history_days == [days]


def test_history_defaults_to_30_days(db) -> None:
    dashboard = _StubDashboard()
    response = _client(db, dashboard).get("/api/dashboard/history")
    assert response.status_code == 200
    assert dashboard.history_days == [30]


@pytest.mark.parametrize("days", ["14", "abc"])
def test_history_rejects_other_ranges(db, days: str) -> None:
    dashboard = _StubDashboard()
    response = _client(db, dashboard).get(f"/api/dashboard/history?days={days}")
    assert response.status_code == 422
    assert dashboard.history_days == []


@pytest.mark.parametrize("path", ["/summary", "/history"])
def test_routes_answer_503_without_a_service(db, path: str) -> None:
    response = _client(db, None).get(f"/api/dashboard{path}")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard unavailable"}
