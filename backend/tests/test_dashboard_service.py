"""Tests for core.dashboard (DashboardService: cache, snapshot, history)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from core import dashboard_sources
from core.dashboard import DashboardService
from core.dashboard_sources import SourceResult, SourceSpec, SourceState
from tests.conftest import make_ctx

_START = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


class _Clock:
    """A settable clock injected into the service."""

    def __init__(self) -> None:
        self.now = _START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Collector:
    """A fake collector that counts calls and yields to the loop once."""

    def __init__(
        self,
        key: str,
        *,
        state: SourceState = "ok",
        metrics: dict[str, float] | None = None,
        extra: dict[str, Any] | None = None,
        behaviour: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.key = key
        self.state = state
        self.metrics = metrics or {}
        self.extra = extra or {}
        self.behaviour = behaviour
        self.calls = 0

    async def __call__(self, ctx: Any) -> SourceResult:
        self.calls += 1
        await asyncio.sleep(0)
        if self.behaviour is not None:
            await self.behaviour()
        return SourceResult(
            key=self.key,
            label=self.key.title(),
            state=self.state,
            link=f"/{self.key}",
            metrics=dict(self.metrics),
            extra=dict(self.extra),
        )


def _spec(collector: _Collector, ttl: int = 55) -> SourceSpec:
    return SourceSpec(
        key=collector.key,
        label=collector.key.title(),
        collector=collector,
        ttl_seconds=ttl,
        link=f"/{collector.key}",
    )


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def _service(db, clock: _Clock, monkeypatch, *specs: SourceSpec, **kwargs: Any):
    monkeypatch.setattr(dashboard_sources, "SOURCES", tuple(specs))
    return DashboardService(make_ctx(db=db), clock=clock, **kwargs)


def _source(summary: dict[str, Any], key: str) -> dict[str, Any]:
    return next(source for source in summary["sources"] if source["key"] == key)


def _kpis(summary: dict[str, Any]) -> dict[str, float | None]:
    return {kpi["key"]: kpi["value"] for kpi in summary["kpis"]}


# ---- caching and single flight ----


async def test_concurrent_summaries_share_one_collection(
    db, clock, monkeypatch
) -> None:
    seer = _Collector("seer", metrics={"seer.requests_pending": 1})
    sab = _Collector("sabnzbd")
    service = _service(db, clock, monkeypatch, _spec(seer), _spec(sab))

    first, second = await asyncio.gather(service.summary(), service.summary())

    assert seer.calls == 1
    assert sab.calls == 1
    assert first["sources"] == second["sources"]
    assert [source["key"] for source in first["sources"]] == ["seer", "sabnzbd"]
    assert first["refresh_seconds"] == 60
    assert first["generated_at"] == _START.isoformat()


async def test_cache_serves_within_ttl_and_refetches_after(
    db, clock, monkeypatch
) -> None:
    seer = _Collector("seer")
    service = _service(db, clock, monkeypatch, _spec(seer))

    await service.summary()
    clock.advance(54)
    await service.summary()
    assert seer.calls == 1

    clock.advance(1)
    await service.summary()
    assert seer.calls == 2


async def test_library_sources_keep_their_longer_ttl(db, clock, monkeypatch) -> None:
    sonarr = _Collector("sonarr")
    seer = _Collector("seer")
    service = _service(db, clock, monkeypatch, _spec(sonarr, 900), _spec(seer))

    await service.summary()
    clock.advance(60)
    await service.summary()

    assert seer.calls == 2
    assert sonarr.calls == 1

    clock.advance(840)
    await service.summary()
    assert sonarr.calls == 2


# ---- failures ----


async def test_timeout_yields_offline_with_last_snapshot_and_is_cached(
    db, clock, monkeypatch
) -> None:
    db.dashboard_snapshot_upsert(
        day="2026-10-25",
        values={"seer.requests_pending": 3, "seer.requests_total": 10},
        recorded_at="2026-10-25T23:55:00+01:00",
    )
    db.dashboard_snapshot_upsert(
        day="2026-10-26",
        values={"seer.requests_pending": 4},
        recorded_at="2026-10-26T23:55:00+00:00",
    )

    async def hang() -> None:
        await asyncio.sleep(10)

    seer = _Collector("seer", behaviour=hang)
    service = _service(db, clock, monkeypatch, _spec(seer), timeout_seconds=0.01)

    summary = await service.summary()

    card = _source(summary, "seer")
    assert card["state"] == "offline"
    assert card["detail"] == "Timed out after 0.01 s."
    assert card["stale_since"] == "2026-10-26T23:55:00+00:00"
    values = {metric["key"]: metric["value"] for metric in card["metrics"]}
    assert values["seer.requests_pending"] == 4.0
    assert values["seer.requests_total"] == 10.0
    assert values["seer.requests_declined"] is None
    # The KPI never shows a stale value.
    assert _kpis(summary)["pending_requests"] is None

    await service.summary()
    assert seer.calls == 1


async def test_error_without_snapshot_yields_none_values(
    db, clock, monkeypatch
) -> None:
    async def boom() -> None:
        raise RuntimeError

    seer = _Collector("seer", behaviour=boom)
    service = _service(db, clock, monkeypatch, _spec(seer))

    card = _source(await service.summary(), "seer")

    assert card["state"] == "offline"
    assert card["detail"] == "RuntimeError"
    assert card["stale_since"] is None
    assert card["metrics"]
    assert all(metric["value"] is None for metric in card["metrics"])


async def test_error_message_becomes_the_detail(db, clock, monkeypatch) -> None:
    async def boom() -> None:
        raise ValueError("Seer request count returned 502")

    seer = _Collector("seer", behaviour=boom)
    service = _service(db, clock, monkeypatch, _spec(seer))

    card = _source(await service.summary(), "seer")
    assert card["detail"] == "Seer request count returned 502"


async def test_cancellation_propagates(db, clock, monkeypatch) -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError

    seer = _Collector("seer", behaviour=cancelled)
    service = _service(db, clock, monkeypatch, _spec(seer))

    with pytest.raises(asyncio.CancelledError):
        await service.summary()


# ---- serialisation and KPIs ----


async def test_states_without_values_list_no_metrics(db, clock, monkeypatch) -> None:
    bandwidth = _Collector("bandwidth", state="disabled")
    seer = _Collector("seer", state="not_configured")
    service = _service(db, clock, monkeypatch, _spec(bandwidth), _spec(seer))

    summary = await service.summary()

    assert _source(summary, "bandwidth")["metrics"] == []
    seer_card = _source(summary, "seer")
    assert seer_card == {
        "key": "seer",
        "label": "Seer",
        "state": "not_configured",
        "detail": None,
        "stale_since": None,
        "updated_at": None,
        "link": "/seer",
        "metrics": [],
    }


async def test_kpis_are_derived_from_live_sources(db, clock, monkeypatch) -> None:
    sonarr = _Collector(
        "sonarr",
        metrics={"sonarr.series_total": 40, "sonarr.episodes_missing": 6},
        extra={
            "disks": [
                {
                    "app": "sonarr",
                    "path": "/tv",
                    "label": None,
                    "free_bytes": 50,
                    "total_bytes": 100,
                },
                {
                    "app": "sonarr",
                    "path": "/empty",
                    "label": None,
                    "free_bytes": 0,
                    "total_bytes": 0,
                },
            ]
        },
    )
    radarr = _Collector(
        "radarr",
        metrics={"radarr.movies_total": 90, "radarr.movies_missing": 2},
        extra={
            "disks": [
                {
                    "app": "radarr",
                    "path": "/movies",
                    "label": "M",
                    "free_bytes": 300,
                    "total_bytes": 1000,
                }
            ]
        },
    )
    seer = _Collector("seer", metrics={"seer.requests_pending": 5})
    sab = _Collector("sabnzbd", metrics={"sabnzbd.active_downloads": 1})
    qbit = _Collector("qbittorrent", metrics={"qbittorrent.active_downloads": 3})
    languagarr = _Collector(
        "languagarr", state="disabled", metrics={"languagarr.non_compliant": 7}
    )
    service = _service(
        db,
        clock,
        monkeypatch,
        *(_spec(c) for c in (sonarr, radarr, seer, sab, qbit, languagarr)),
    )

    summary = await service.summary()

    assert [kpi["key"] for kpi in summary["kpis"]] == [
        "movies",
        "series",
        "missing_episodes",
        "missing_movies",
        "free_disk",
        "pending_requests",
        "active_downloads",
        "non_compliant_anime",
    ]
    assert _kpis(summary) == {
        "movies": 90,
        "series": 40,
        "missing_episodes": 6,
        "missing_movies": 2,
        # /movies is 30 % free, tighter than /tv at 50 %.
        "free_disk": 300.0,
        "pending_requests": 5,
        "active_downloads": 4,
        "non_compliant_anime": 7,
    }
    assert [disk["path"] for disk in summary["disks"]] == ["/tv", "/empty", "/movies"]


async def test_kpis_are_none_when_sources_are_unavailable(
    db, clock, monkeypatch
) -> None:
    async def boom() -> None:
        raise RuntimeError("down")

    sonarr = _Collector("sonarr", behaviour=boom)
    sab = _Collector("sabnzbd", state="not_configured")
    service = _service(db, clock, monkeypatch, _spec(sonarr), _spec(sab))

    summary = await service.summary()

    assert all(value is None for value in _kpis(summary).values())
    assert summary["disks"] == []


async def _boom() -> None:
    raise RuntimeError("unreachable")


def _download_client(key: str, state: SourceState, active: float) -> _Collector:
    """A download-client collector; ``state="offline"`` makes it raise."""
    if state == "offline":
        return _Collector(key, behaviour=_boom)
    metrics = {f"{key}.active_downloads": active} if state == "ok" else {}
    return _Collector(key, state=state, metrics=metrics)


@pytest.mark.parametrize(
    ("sab_state", "qbit_state", "expected"),
    [
        # Both online: the counts add up.
        ("ok", "ok", 4.0),
        # A configured client offline makes the total unknown, either way round,
        # even when the other one reports zero.
        ("ok", "offline", None),
        ("offline", "ok", None),
        ("offline", "offline", None),
        # An unconfigured client is left out of the total.
        ("ok", "not_configured", 1.0),
        ("not_configured", "ok", 3.0),
        ("not_configured", "not_configured", None),
    ],
)
async def test_active_downloads_kpi_is_none_during_a_configured_outage(
    db,
    clock,
    monkeypatch,
    sab_state: SourceState,
    qbit_state: SourceState,
    expected: float | None,
) -> None:
    sab = _download_client("sabnzbd", sab_state, 1)
    qbit = _download_client("qbittorrent", qbit_state, 3)
    service = _service(db, clock, monkeypatch, _spec(sab), _spec(qbit))

    summary = await service.summary()

    assert _kpis(summary)["active_downloads"] == expected


async def test_active_downloads_kpi_is_none_when_sabnzbd_idle_and_qbit_offline(
    db, clock, monkeypatch
) -> None:
    # The audit's reproduction: SABnzbd online at zero must not read as "0 total".
    sab = _download_client("sabnzbd", "ok", 0)
    qbit = _download_client("qbittorrent", "offline", 0)
    service = _service(db, clock, monkeypatch, _spec(sab), _spec(qbit))

    assert _kpis(await service.summary())["active_downloads"] is None


async def test_active_downloads_kpi_ignores_an_ok_client_without_the_metric(
    db, clock, monkeypatch
) -> None:
    sab = _Collector("sabnzbd", metrics={"sabnzbd.queue_size": 2})
    service = _service(db, clock, monkeypatch, _spec(sab))

    assert _kpis(await service.summary())["active_downloads"] is None


async def test_summary_reports_the_latest_snapshot_version(
    db, clock, monkeypatch
) -> None:
    service = _service(db, clock, monkeypatch)
    assert (await service.summary())["latest_snapshot_at"] is None

    db.dashboard_snapshot_upsert(
        day="2026-10-26", values={"m": 1}, recorded_at="2026-10-26T23:55:00+00:00"
    )
    assert (await service.summary())["latest_snapshot_at"] == (
        "2026-10-26T23:55:00+00:00"
    )


# ---- snapshot ----


async def test_take_snapshot_stores_ok_snapshot_metrics_only(
    db, clock, monkeypatch
) -> None:
    sab = _Collector(
        "sabnzbd",
        metrics={"sabnzbd.queue_size": 4, "sabnzbd.speed_mbps": 9.5},
    )
    findarr = _Collector(
        "findarr", state="disabled", metrics={"findarr.sonarr.missing_total": 3}
    )

    async def boom() -> None:
        raise RuntimeError

    seer = _Collector("seer", behaviour=boom)
    service = _service(db, clock, monkeypatch, _spec(sab), _spec(findarr), _spec(seer))

    assert await service.take_snapshot() == 1
    assert await service.take_snapshot() == 1
    assert sab.calls == 2  # the snapshot bypasses the cache

    rows = db.dashboard_snapshot_range(start_day="2026-10-27", end_day="2026-10-27")
    assert [(row["metric"], row["value"]) for row in rows] == [
        ("sabnzbd.queue_size", 4.0)
    ]
    assert rows[0]["recorded_at"] == _START.isoformat()


async def test_take_snapshot_prunes_rows_older_than_retention(
    db, clock, monkeypatch
) -> None:
    db.dashboard_snapshot_upsert(day="2025-10-26", values={"m": 1}, recorded_at="r")
    db.dashboard_snapshot_upsert(day="2025-10-27", values={"m": 1}, recorded_at="r")
    service = _service(db, clock, monkeypatch)

    assert await service.take_snapshot() == 0

    days = [
        row["day"]
        for row in db.dashboard_snapshot_range(
            start_day="2000-01-01", end_day="2100-01-01"
        )
    ]
    assert days == ["2025-10-27"]
    assert service.today() == "2026-10-27"


# ---- history ----


def _seed(db, metric: str, values: dict[str, float]) -> None:
    for day, value in values.items():
        db.dashboard_snapshot_upsert(day=day, values={metric: value}, recorded_at=day)


def _series(history: dict[str, Any], key: str) -> list[tuple[str, float]]:
    series = next(item for item in history["series"] if item["key"] == key)
    return [(point["day"], point["value"]) for point in series["points"]]


async def test_history_returns_gauges_as_stored_in_window(
    db, clock, monkeypatch
) -> None:
    _seed(
        db,
        "sonarr.series_total",
        {"2026-10-20": 1, "2026-10-21": 5, "2026-10-27": 7, "2026-10-23": 6},
    )
    service = _service(db, clock, monkeypatch)

    history = service.history(7)

    assert history["days"] == 7
    assert history["start_day"] == "2026-10-21"
    assert history["end_day"] == "2026-10-27"
    # _seed records each row at its own day, so the newest day is the version.
    assert history["latest_snapshot_at"] == "2026-10-27"
    assert _series(history, "sonarr.series_total") == [
        ("2026-10-21", 5.0),
        ("2026-10-23", 6.0),
        ("2026-10-27", 7.0),
    ]
    series = next(s for s in history["series"] if s["key"] == "sonarr.series_total")
    assert series["kind"] == "gauge"
    assert series["label"] == "Series"
    assert series["unit"] == "count"
    keys = [item["key"] for item in history["series"]]
    assert "sabnzbd.speed_mbps" not in keys
    assert "sabnzbd.queue_size" in keys


async def test_history_reads_the_snapshot_version_before_the_rows(
    db, clock, monkeypatch
) -> None:
    service = _service(db, clock, monkeypatch)
    assert service.history(7)["latest_snapshot_at"] is None

    calls: list[str] = []
    original_version = db.dashboard_snapshot_last_recorded_at
    original_range = db.dashboard_snapshot_range

    def version() -> str | None:
        calls.append("version")
        return original_version()

    def rows(**kwargs: str) -> list[dict[str, Any]]:
        calls.append("rows")
        return original_range(**kwargs)

    monkeypatch.setattr(db, "dashboard_snapshot_last_recorded_at", version)
    monkeypatch.setattr(db, "dashboard_snapshot_range", rows)

    service.history(30)

    assert calls == ["version", "rows"]


async def test_history_turns_counters_into_clamped_daily_deltas(
    db, clock, monkeypatch
) -> None:
    _seed(
        db,
        "findarr.sonarr.missing_total",
        {
            # The day before the window feeds the first delta.
            "2026-10-20": 10,
            "2026-10-21": 14,
            "2026-10-22": 20,
            # 2026-10-23 is missing, so 2026-10-24 has no delta.
            "2026-10-24": 25,
            "2026-10-25": 27,
            # A reset is clamped to 0 rather than plotted negative.
            "2026-10-26": 3,
        },
    )
    service = _service(db, clock, monkeypatch)

    history = service.history(7)

    assert _series(history, "findarr.sonarr.missing_total") == [
        ("2026-10-21", 4.0),
        ("2026-10-22", 6.0),
        ("2026-10-25", 2.0),
        ("2026-10-26", 0.0),
    ]
