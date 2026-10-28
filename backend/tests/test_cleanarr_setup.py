"""Tests for the Cleanarr module wiring: scheduler job, ctx callables, reschedule."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

import modules.cleanarr as cleanarr_module
from modules.cleanarr import cleanarr_job, setup
from modules.cleanarr import engine as engine_module
from tests.conftest import StubSettingsStore, make_ctx
from tests.test_cleanarr_engine import FakeArr, FakeSab


@pytest.fixture
def arrs(monkeypatch) -> dict[str, FakeArr]:
    fakes = {"sonarr": FakeArr("sonarr"), "radarr": FakeArr("radarr")}
    monkeypatch.setattr(
        engine_module, "client_for", lambda _ctx, app: fakes[app].client()
    )
    return fakes


@pytest.fixture
def sab() -> FakeSab:
    return FakeSab()


async def test_setup_registers_callables_and_reschedules(
    db, arrs: dict[str, FakeArr], sab: FakeSab
) -> None:
    ctx = make_ctx(db=db, settings_store=StubSettingsStore(), sabnzbd=sab)
    scheduler = AsyncMock()
    await setup(scheduler, FastAPI(), ctx)

    scheduler.add_interval.assert_awaited_once()
    assert scheduler.add_interval.await_args.kwargs == {
        "minutes": 10,
        "id": "cleanarr_poll",
    }
    for name in (
        "status",
        "queue",
        "history",
        "run_now",
        "clear_strikes",
        "ignore",
        "update_settings",
    ):
        assert getattr(ctx, f"cleanarr_{name}") is not None

    status = await ctx.cleanarr_update_settings({"enabled": True})
    assert status["settings"]["enabled"] is True
    scheduler.reschedule_interval.assert_not_awaited()

    await ctx.cleanarr_update_settings({"interval_minutes": 30})
    scheduler.reschedule_interval.assert_awaited_once()
    assert scheduler.reschedule_interval.await_args.kwargs == {
        "minutes": 30,
        "id": "cleanarr_poll",
    }

    # The scheduled job runs under the gate; enabled -> the Arrs are contacted.
    await cleanarr_job()
    assert arrs["sonarr"].calls
    assert cleanarr_module._SERVICE is not None
    state = ctx.db.cleanarr_run_state()
    assert json.loads(state["connections"])[0]["app"] == "sabnzbd"

    # Disabled -> a silent no-op.
    await ctx.cleanarr_update_settings({"enabled": False})
    arrs["sonarr"].calls.clear()
    await cleanarr_job()
    assert arrs["sonarr"].calls == []
