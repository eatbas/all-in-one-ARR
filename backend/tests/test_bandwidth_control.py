"""Tests for the Bandwidth-Controllarr control loop and metrics."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import modules.bandwidth_controllarr as bandwidth_module
from core.bandwidth_metrics import (
    bw_check_status,
    bw_qbit_active_count,
    bw_qbit_queue_size,
    bw_qbit_speed_mbps,
    bw_sab_active_count,
    bw_sab_paused,
    bw_sab_queue_size,
    bw_sab_speed_mbps,
    update_bandwidth_metrics,
)
from modules.bandwidth_controllarr import _STATE, control_job, setup
from modules.bandwidth_controllarr.control import apply_control, gather_status
from tests.conftest import StubService, make_ctx


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset the module-level live state and context before each test."""
    previous_state = (
        _STATE.enabled,
        _STATE.status,
        _STATE.last_run_at,
        _STATE.sab_paused,
    )
    previous_context = bandwidth_module._CONTEXT
    _STATE.enabled = False
    _STATE.status = "Monitoring only"
    _STATE.last_run_at = None
    _STATE.sab_paused = False
    bandwidth_module._CONTEXT = None
    yield
    _STATE.enabled, _STATE.status, _STATE.last_run_at, _STATE.sab_paused = (
        previous_state
    )
    bandwidth_module._CONTEXT = previous_context


def _make_qbit_stub(*, online=True, speed_mbps=0, active_downloads=0, queue_size=0):
    stub = StubService()
    stub.get_stats = AsyncMock(
        return_value={
            "online": online,
            "speed_mbps": speed_mbps,
            "active_downloads": active_downloads,
            "queue_size": queue_size,
        }
    )
    return stub


def _make_sab_stub(
    *, online=True, speed_mbps=0, active_downloads=0, queue_size=0, paused=False
):
    stub = StubService()
    stub.get_stats = AsyncMock(
        return_value={
            "online": online,
            "speed_mbps": speed_mbps,
            "active_downloads": active_downloads,
            "queue_size": queue_size,
            "paused": paused,
        }
    )
    return stub


async def test_gather_status_merges_state_and_stats(db) -> None:
    qbit = _make_qbit_stub(
        online=True, speed_mbps=5.5, active_downloads=2, queue_size=1
    )
    sab = _make_sab_stub(online=True, speed_mbps=1.2, active_downloads=1, paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)

    _STATE.enabled = True
    _STATE.status = "Active torrents — SABnzbd paused"
    _STATE.last_run_at = "2024-01-01T00:00:00Z"

    result = await gather_status(ctx)

    assert result["enabled"] is True
    assert result["status"] == "Active torrents — SABnzbd paused"
    assert result["last_run_at"] == "2024-01-01T00:00:00Z"
    assert result["check_interval_seconds"] == 15
    assert result["qbittorrent"]["active_downloads"] == 2
    assert result["sabnzbd"]["paused"] is True


async def test_apply_control_disabled_resumes_sab(db) -> None:
    qbit = _make_qbit_stub(active_downloads=5)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(False)

    await apply_control(ctx)

    sab.resume.assert_awaited_once()
    sab.pause.assert_not_awaited()
    assert _STATE.status == "Monitoring only"
    assert _STATE.sab_paused is False
    assert _STATE.last_run_at is not None


async def test_apply_control_disabled_no_change_when_sab_already_resumed(db) -> None:
    qbit = _make_qbit_stub(active_downloads=5)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)

    await apply_control(ctx)

    sab.resume.assert_not_awaited()
    sab.pause.assert_not_awaited()
    assert _STATE.status == "Monitoring only"


async def test_apply_control_active_torrents_pauses_sab(db) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.pause.assert_awaited_once()
    sab.resume.assert_not_awaited()
    assert _STATE.status == "Active torrents — SABnzbd paused"
    assert _STATE.sab_paused is True


async def test_apply_control_active_torrents_no_change_when_sab_already_paused(
    db,
) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.pause.assert_not_awaited()
    sab.resume.assert_not_awaited()
    assert _STATE.status == "Active torrents — SABnzbd paused"
    assert _STATE.sab_paused is False  # unchanged because no command issued


async def test_apply_control_idle_resumes_sab(db) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.resume.assert_awaited_once()
    sab.pause.assert_not_awaited()
    assert _STATE.status == "No active torrents"
    assert _STATE.sab_paused is False


async def test_apply_control_idle_no_change_when_sab_already_resumed(db) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.resume.assert_not_awaited()
    sab.pause.assert_not_awaited()
    assert _STATE.status == "No active torrents"


async def test_apply_control_command_failure_does_not_update_cached_state(db) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=False)
    sab.pause = AsyncMock(return_value=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.pause.assert_awaited_once()
    assert _STATE.sab_paused is False


async def test_apply_control_disabled_resume_failure_keeps_state(db) -> None:
    qbit = _make_qbit_stub(active_downloads=5)
    sab = _make_sab_stub(paused=True)
    sab.resume = AsyncMock(return_value=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)

    await apply_control(ctx)

    sab.resume.assert_awaited_once()
    assert _STATE.sab_paused is False


async def test_apply_control_idle_resume_failure_keeps_state(db) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=True)
    sab.resume = AsyncMock(return_value=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.resume.assert_awaited_once()
    assert _STATE.sab_paused is False


async def test_apply_control_logs_activity_on_transition(db) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    activities = ctx.db.recent_activity(limit=1)
    assert activities[0]["action"] == "SABnzbd paused"


async def test_apply_control_no_activity_without_transition(db) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    before = len(ctx.db.recent_activity(limit=10))
    await apply_control(ctx)
    after = len(ctx.db.recent_activity(limit=10))

    assert after == before


async def test_apply_control_offline_sab_does_not_issue_commands(db) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(online=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    sab.pause.assert_not_awaited()
    sab.resume.assert_not_awaited()
    assert _STATE.status == "Active torrents — SABnzbd paused"


async def test_apply_control_sets_metrics_check_ok(db, monkeypatch) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    assert bw_check_status._value.get() == 1.0


async def test_apply_control_metrics_reflect_paused_after_pause_transition(
    db,
) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=False)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    assert bw_sab_paused._value.get() == 1.0


async def test_apply_control_metrics_reflect_resumed_after_resume_transition(
    db,
) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    await apply_control(ctx)

    assert bw_sab_paused._value.get() == 0.0


async def test_apply_control_metrics_reflect_resumed_after_disabled_transition(
    db,
) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(False)

    await apply_control(ctx)

    assert bw_sab_paused._value.get() == 0.0


async def test_apply_control_sets_metrics_check_failed_on_exception(
    db, monkeypatch
) -> None:
    qbit = _make_qbit_stub(active_downloads=0)
    sab = _make_sab_stub(paused=False)
    sab.get_stats = AsyncMock(side_effect=RuntimeError("boom"))
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)

    with pytest.raises(RuntimeError):
        await apply_control(ctx)

    assert bw_check_status._value.get() == 0.0
    assert bw_qbit_active_count._value.get() == 0.0


async def test_update_bandwidth_metrics_online_clients() -> None:
    qb = {
        "online": True,
        "speed_mbps": 12.34,
        "active_downloads": 3,
        "queue_size": 1,
    }
    sab = {
        "online": True,
        "speed_mbps": 4.56,
        "active_downloads": 2,
        "queue_size": 5,
        "paused": True,
    }
    update_bandwidth_metrics(qb, sab, check_ok=True)

    assert bw_qbit_active_count._value.get() == 3.0
    assert bw_qbit_speed_mbps._value.get() == 12.34
    assert bw_qbit_queue_size._value.get() == 1.0
    assert bw_sab_active_count._value.get() == 2.0
    assert bw_sab_speed_mbps._value.get() == 4.56
    assert bw_sab_queue_size._value.get() == 5.0
    assert bw_sab_paused._value.get() == 1.0
    assert bw_check_status._value.get() == 1.0


async def test_update_bandwidth_metrics_offline_qb() -> None:
    qb = {"online": False}
    sab = {
        "online": True,
        "speed_mbps": 4.56,
        "active_downloads": 2,
        "queue_size": 5,
        "paused": False,
    }
    update_bandwidth_metrics(qb, sab, check_ok=False)

    assert bw_qbit_active_count._value.get() == 0.0
    assert bw_qbit_speed_mbps._value.get() == 0.0
    assert bw_qbit_queue_size._value.get() == 0.0
    assert bw_sab_active_count._value.get() == 2.0
    assert bw_sab_paused._value.get() == 0.0
    assert bw_check_status._value.get() == 0.0


async def test_update_bandwidth_metrics_offline_sab() -> None:
    qb = {
        "online": True,
        "speed_mbps": 12.34,
        "active_downloads": 3,
        "queue_size": 1,
    }
    sab = {"online": False}
    update_bandwidth_metrics(qb, sab, check_ok=True)

    assert bw_qbit_active_count._value.get() == 3.0
    assert bw_sab_active_count._value.get() == 0.0
    assert bw_sab_speed_mbps._value.get() == 0.0
    assert bw_sab_queue_size._value.get() == 0.0
    assert bw_sab_paused._value.get() == 0.0
    assert bw_check_status._value.get() == 1.0


async def test_update_bandwidth_metrics_both_offline() -> None:
    update_bandwidth_metrics({"online": False}, {"online": False}, check_ok=False)

    assert bw_qbit_active_count._value.get() == 0.0
    assert bw_sab_active_count._value.get() == 0.0
    assert bw_sab_paused._value.get() == 0.0
    assert bw_check_status._value.get() == 0.0


async def test_setup_wires_callables_and_schedules_job(db) -> None:
    ctx = make_ctx(db=db)
    ctx.settings_store.update_bandwidth_control_enabled(True)
    ctx.settings_store.update_bandwidth_check_interval(30)

    await setup(ctx.scheduler, None, ctx)

    ctx.scheduler.add_interval.assert_awaited_once()
    call = ctx.scheduler.add_interval.await_args
    assert call.kwargs["seconds"] == 30
    assert call.kwargs["id"] == "bandwidth_control"

    assert ctx.bandwidth_status is not None
    status = await ctx.bandwidth_status()
    assert status["enabled"] is True
    assert status["check_interval_seconds"] == 30

    assert ctx.bandwidth_update_settings is not None


async def test_update_settings_disable_resumes_sab_immediately(db) -> None:
    qbit = _make_qbit_stub(active_downloads=3)
    sab = _make_sab_stub(paused=True)
    ctx = make_ctx(db=db, qbittorrent=qbit, sabnzbd=sab)
    ctx.settings_store.update_bandwidth_control_enabled(True)
    _STATE.enabled = True
    _STATE.sab_paused = True
    _STATE.status = "Active torrents — SABnzbd paused"

    await setup(ctx.scheduler, None, ctx)
    result = await ctx.bandwidth_update_settings(enabled=False)

    sab.resume.assert_awaited_once()
    assert _STATE.enabled is False
    assert _STATE.sab_paused is False
    assert _STATE.status == "Monitoring only"
    assert result["sabnzbd"]["paused"] is False


async def test_update_settings_interval_reschedules_job(db) -> None:
    ctx = make_ctx(db=db)
    ctx.settings_store.update_bandwidth_check_interval(15)

    await setup(ctx.scheduler, None, ctx)
    result = await ctx.bandwidth_update_settings(check_interval_seconds=30)

    ctx.scheduler.reschedule_interval.assert_awaited_once_with(
        control_job, seconds=30, id="bandwidth_control"
    )
    assert result["check_interval_seconds"] == 30


async def test_require_context_raises_when_unset() -> None:
    bandwidth_module._CONTEXT = None
    with pytest.raises(RuntimeError):
        bandwidth_module._require_context()


async def test_control_job_runs_apply_control(db) -> None:
    ctx = make_ctx(db=db)
    bandwidth_module.register_context(ctx)
    assert _STATE.last_run_at is None
    await bandwidth_module.control_job()
    # If control_job reached apply_control, the live state timestamp is updated.
    assert _STATE.last_run_at is not None
