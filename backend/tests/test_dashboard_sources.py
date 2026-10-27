"""Tests for core.dashboard_sources (per-source dashboard collectors)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from core import dashboard_sources
from core.clients.servarr_stats import ServarrStatsClient, ServarrStatsError
from core.dashboard_sources import (
    LIBRARY_TTL_SECONDS,
    LIVE_TTL_SECONDS,
    SOURCES,
    SourceUnavailableError,
    collect_bandwidth,
    collect_deletarr,
    collect_findarr,
    collect_languagarr,
    collect_list_syncarr,
    collect_qbittorrent,
    collect_radarr,
    collect_sabnzbd,
    collect_seer,
    collect_sonarr,
    collect_trending,
)
from tests.conftest import StubArr, StubSettingsStore, StubTrakt, make_ctx

_ARR = "http://arr"
_CONFIGURED = {"url": "http://svc", "api_key": "k"}


class _UnconfiguredArr(StubArr):
    def connection_fields(self) -> dict[str, str]:
        return {"base_url": "", "api_key": ""}


def _mock_servarr(app: str) -> None:
    library_path = "/api/v3/series" if app == "sonarr" else "/api/v3/movie"
    library = (
        [
            {
                "monitored": True,
                "statistics": {
                    "episodeCount": 10,
                    "episodeFileCount": 9,
                    "sizeOnDisk": 500,
                },
            }
        ]
        if app == "sonarr"
        else [{"monitored": True, "hasFile": True, "sizeOnDisk": 700}]
    )
    respx.get(f"{_ARR}{library_path}").mock(
        return_value=httpx.Response(200, json=library)
    )
    respx.get(f"{_ARR}/api/v3/diskspace").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"path": "/a", "label": "A", "freeSpace": 10, "totalSpace": 100},
                {"path": "/b", "label": "B", "freeSpace": 30, "totalSpace": 50},
            ],
        )
    )
    respx.get(f"{_ARR}/api/v3/queue").mock(
        return_value=httpx.Response(200, json={"totalRecords": 4})
    )
    respx.get(f"{_ARR}/api/v3/wanted/missing").mock(
        return_value=httpx.Response(200, json={"totalRecords": 1})
    )


# ---- List-Syncarr ----


async def test_list_syncarr_not_configured_without_lists(db) -> None:
    ctx = make_ctx(db=db, settings_store=StubSettingsStore(lists=[]))
    result = await collect_list_syncarr(ctx)
    assert result.state == "not_configured"
    assert result.detail == "No Trakt lists are tracked yet."
    assert result.metrics == {}
    assert result.link == "/list-syncarr"


async def test_list_syncarr_not_configured_without_trakt_auth(db) -> None:
    ctx = make_ctx(db=db, trakt=StubTrakt(authenticated=False))
    result = await collect_list_syncarr(ctx)
    assert result.state == "not_configured"
    assert result.detail == "Trakt is not connected."


async def test_list_syncarr_reports_counts_by_status(db) -> None:
    db.upsert_item(
        trakt_id=1,
        type="movie",
        title="Dune",
        year=2021,
        tmdb=1,
        tvdb=None,
        imdb=None,
        list_id="watchlist",
    )
    result = await collect_list_syncarr(make_ctx(db=db))
    assert result.state == "ok"
    assert result.metrics == {
        "list_syncarr.synced": 1.0,
        "list_syncarr.requested": 0.0,
        "list_syncarr.available": 0.0,
        "list_syncarr.removed": 0.0,
    }


# ---- Findarr ----


async def test_findarr_disabled_when_module_missing_still_reports_totals(db) -> None:
    db.findarr_increment_total(app="sonarr", mode="missing")
    ctx = make_ctx(db=db)
    result = await collect_findarr(ctx)
    assert result.state == "disabled"
    assert result.metrics["findarr.sonarr.missing_total"] == 1.0
    assert result.metrics["findarr.radarr.upgrade_total"] == 0.0


@pytest.mark.parametrize(("enabled", "state"), [(True, "ok"), (False, "disabled")])
async def test_findarr_state_follows_enabled_setting(db, enabled, state) -> None:
    ctx = make_ctx(db=db)
    ctx.findarr_status = AsyncMock(return_value={"settings": {"enabled": enabled}})
    result = await collect_findarr(ctx)
    assert result.state == state
    assert len(result.metrics) == 4


# ---- Deletarr ----


async def test_deletarr_disabled_when_module_missing(db) -> None:
    result = await collect_deletarr(make_ctx(db=db))
    assert result.state == "disabled"
    assert result.metrics == {}


async def test_deletarr_reports_junk_per_library(db) -> None:
    ctx = make_ctx(db=db)
    ctx.deletarr_status = AsyncMock(
        return_value={
            "libraries": {
                "movies": {
                    "stats": {"total_files": 3, "total_folders": 2, "total_size": 900}
                },
                "tv": None,
            }
        }
    )
    result = await collect_deletarr(ctx)
    assert result.state == "ok"
    assert result.metrics == {
        "deletarr.movies.junk_items": 5.0,
        "deletarr.movies.junk_bytes": 900.0,
        "deletarr.tv.junk_items": 0.0,
        "deletarr.tv.junk_bytes": 0.0,
    }


# ---- Languagarr ----


async def test_languagarr_disabled_when_module_missing(db) -> None:
    result = await collect_languagarr(make_ctx(db=db))
    assert result.state == "disabled"
    assert result.metrics == {}


@pytest.mark.parametrize(("enabled", "state"), [(True, "ok"), (False, "disabled")])
async def test_languagarr_reports_last_scan_and_queue(db, enabled, state) -> None:
    ctx = make_ctx(db=db)
    ctx.languagarr_status = AsyncMock(
        return_value={
            "settings": {"enabled": enabled},
            "scan": {"non_compliant": 7, "last_scan_at": "2026-10-27T10:00:00Z"},
            "queue": {"pending": 2, "searched": 5, "failed": 1},
        }
    )
    result = await collect_languagarr(ctx)
    assert result.state == state
    assert result.updated_at == "2026-10-27T10:00:00Z"
    assert result.metrics == {
        "languagarr.non_compliant": 7.0,
        "languagarr.queue_pending": 2.0,
        "languagarr.queue_failed": 1.0,
    }


# ---- Bandwidth-Controllarr ----


async def test_bandwidth_disabled_when_module_missing(db) -> None:
    ctx = make_ctx(
        db=db, settings_store=StubSettingsStore(bandwidth_control_enabled=True)
    )
    result = await collect_bandwidth(ctx)
    assert result.state == "disabled"


async def test_bandwidth_disabled_when_setting_off(db) -> None:
    ctx = make_ctx(db=db)
    ctx.bandwidth_status = AsyncMock()
    result = await collect_bandwidth(ctx)
    assert result.state == "disabled"
    assert result.link == "/bandwidth-controllarr"


@pytest.mark.parametrize(
    ("stats", "detail"),
    [
        ({"online": False}, "SABnzbd is offline."),
        (
            {"online": True, "paused": True},
            "SABnzbd is paused while torrents download.",
        ),
        ({"online": True, "paused": False}, "SABnzbd is downloading."),
    ],
)
async def test_bandwidth_enabled_reports_sab_state(db, stats, detail) -> None:
    ctx = make_ctx(
        db=db, settings_store=StubSettingsStore(bandwidth_control_enabled=True)
    )
    ctx.bandwidth_status = AsyncMock()
    ctx.sabnzbd.get_stats = AsyncMock(return_value=stats)
    result = await collect_bandwidth(ctx)
    assert result.state == "ok"
    assert result.detail == detail
    assert result.metrics == {}


# ---- Trending ----


async def test_trending_reports_last_refresh(db) -> None:
    ctx = make_ctx(db=db)
    result = await collect_trending(ctx)
    assert result.state == "ok"
    assert result.updated_at is None
    assert result.link == "/trending"


# ---- Sonarr / Radarr ----


@respx.mock
async def test_sonarr_reports_library_disks_queue_and_missing(db) -> None:
    _mock_servarr("sonarr")
    result = await collect_sonarr(make_ctx(db=db))
    assert result.state == "ok"
    assert result.link == "/settings"
    assert result.metrics == {
        "sonarr.series_total": 1.0,
        "sonarr.series_monitored": 1.0,
        "sonarr.episodes_total": 10.0,
        "sonarr.episodes_with_files": 9.0,
        "sonarr.size_on_disk_bytes": 500.0,
        "sonarr.episodes_missing": 1.0,
        "sonarr.queue_total": 4.0,
        "sonarr.disk_free_bytes": 40.0,
        "sonarr.disk_total_bytes": 150.0,
    }
    assert result.extra["disks"] == [
        {
            "app": "sonarr",
            "path": "/a",
            "label": "A",
            "free_bytes": 10,
            "total_bytes": 100,
        },
        {
            "app": "sonarr",
            "path": "/b",
            "label": "B",
            "free_bytes": 30,
            "total_bytes": 50,
        },
    ]


@respx.mock
async def test_radarr_reports_movies_missing(db) -> None:
    _mock_servarr("radarr")
    result = await collect_radarr(make_ctx(db=db))
    assert result.state == "ok"
    assert result.metrics["radarr.movies_total"] == 1.0
    assert result.metrics["radarr.movies_missing"] == 1.0
    assert result.extra["disks"][0]["app"] == "radarr"


async def test_servarr_not_configured_closes_client(db, monkeypatch) -> None:
    aclose = AsyncMock()
    monkeypatch.setattr(ServarrStatsClient, "aclose", aclose)
    ctx = make_ctx(db=db, sonarr=_UnconfiguredArr())
    result = await collect_sonarr(ctx)
    assert result.state == "not_configured"
    aclose.assert_awaited_once()


@respx.mock
async def test_servarr_closes_client_on_success(db, monkeypatch) -> None:
    _mock_servarr("radarr")
    aclose = AsyncMock()
    monkeypatch.setattr(ServarrStatsClient, "aclose", aclose)
    await collect_radarr(make_ctx(db=db))
    aclose.assert_awaited_once()


@respx.mock
async def test_servarr_error_raises_first_failure_and_closes_client(
    db, monkeypatch
) -> None:
    _mock_servarr("sonarr")
    respx.get(f"{_ARR}/api/v3/diskspace").mock(return_value=httpx.Response(500))
    aclose = AsyncMock()
    monkeypatch.setattr(ServarrStatsClient, "aclose", aclose)
    with pytest.raises(ServarrStatsError) as excinfo:
        await collect_sonarr(make_ctx(db=db))
    assert excinfo.value.status_code == 500
    aclose.assert_awaited_once()


# ---- Seer ----


async def test_seer_not_configured_without_url_or_key(db) -> None:
    store = StubSettingsStore(services={"seer": {"url": "", "api_key": ""}})
    result = await collect_seer(make_ctx(db=db, settings_store=store))
    assert result.state == "not_configured"


async def test_seer_reports_request_counts(db) -> None:
    ctx = make_ctx(db=db)
    ctx.seer.request_counts = AsyncMock(
        return_value={
            "total": 9,
            "movie": 5,
            "tv": 4,
            "pending": 1,
            "approved": 2,
            "declined": 3,
            "processing": 1,
            "available": 2,
        }
    )
    result = await collect_seer(ctx)
    assert result.state == "ok"
    assert result.metrics == {
        "seer.requests_total": 9.0,
        "seer.requests_pending": 1.0,
        "seer.requests_approved": 2.0,
        "seer.requests_processing": 1.0,
        "seer.requests_available": 2.0,
        "seer.requests_declined": 3.0,
    }


# ---- Download clients ----


@pytest.mark.parametrize(
    ("collector", "name"),
    [(collect_sabnzbd, "sabnzbd"), (collect_qbittorrent, "qbittorrent")],
)
async def test_download_client_not_configured(db, collector, name) -> None:
    result = await collector(make_ctx(db=db))
    assert result.state == "not_configured"
    assert result.key == name


@pytest.mark.parametrize(
    ("collector", "name"),
    [(collect_sabnzbd, "sabnzbd"), (collect_qbittorrent, "qbittorrent")],
)
async def test_download_client_reports_live_stats(db, collector, name) -> None:
    store = StubSettingsStore(services={name: dict(_CONFIGURED)})
    ctx = make_ctx(db=db, settings_store=store)
    getattr(ctx, name).get_stats = AsyncMock(
        return_value={
            "online": True,
            "speed_mbps": 12.5,
            "active_downloads": 2,
            "queue_size": 6,
        }
    )
    result = await collector(ctx)
    assert result.state == "ok"
    assert result.metrics == {
        f"{name}.queue_size": 6.0,
        f"{name}.speed_mbps": 12.5,
        f"{name}.active_downloads": 2.0,
    }


@pytest.mark.parametrize(
    ("collector", "name", "label"),
    [
        (collect_sabnzbd, "sabnzbd", "SABnzbd"),
        (collect_qbittorrent, "qbittorrent", "qBittorrent"),
    ],
)
async def test_download_client_offline_raises(db, collector, name, label) -> None:
    store = StubSettingsStore(services={name: dict(_CONFIGURED)})
    ctx = make_ctx(db=db, settings_store=store)
    getattr(ctx, name).get_stats = AsyncMock(return_value={"online": False})
    with pytest.raises(SourceUnavailableError, match=f"{label} is unreachable"):
        await collector(ctx)


# ---- registry ----


def test_sources_order_ttls_and_lookup() -> None:
    assert [spec.key for spec in SOURCES] == [
        "list_syncarr",
        "findarr",
        "deletarr",
        "languagarr",
        "bandwidth",
        "trending",
        "sonarr",
        "radarr",
        "seer",
        "sabnzbd",
        "qbittorrent",
    ]
    ttls = {spec.key: spec.ttl_seconds for spec in SOURCES}
    assert ttls.pop("sonarr") == LIBRARY_TTL_SECONDS == 900
    assert ttls.pop("radarr") == LIBRARY_TTL_SECONDS
    assert set(ttls.values()) == {LIVE_TTL_SECONDS}
    assert LIVE_TTL_SECONDS == 55
    assert dashboard_sources.SOURCES_BY_KEY["seer"].label == "Seer"
