"""Tests for core.registry."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock

from fastapi import FastAPI

from core import registry
from tests.conftest import make_ctx


def test_discover_includes_list_syncarr() -> None:
    assert "list_syncarr" in registry.discover_module_names()


async def test_load_real_list_syncarr(db) -> None:
    scheduler = AsyncMock()
    ctx = make_ctx(db=db)
    loaded = await registry.load_modules(scheduler, FastAPI(), ctx)
    assert "list_syncarr" in loaded
    # setup wired the manual-sync callable; the arr import webhook is retired (the
    # poll itself now drives availability-based removal).
    assert "arr" not in ctx.webhooks._handlers
    assert ctx.sync_now is not None
    assert ctx.remove_available is not None
    scheduler.add_interval.assert_awaited()
    # Removal is no longer autonomous: no reconcile cron is scheduled.
    scheduler.add_cron.assert_not_awaited()


async def test_load_handles_missing_setup_errors_and_sync_setup(db, monkeypatch) -> None:
    calls: list[str] = []

    def sync_setup(scheduler, app, ctx):
        calls.append("good")  # non-awaitable result branch

    fakes = {
        "modules.nosetup": types.SimpleNamespace(),  # no setup attribute
        "modules.good": types.SimpleNamespace(setup=sync_setup),
    }

    def fake_import(name):
        if name == "modules.broken":
            raise RuntimeError("boom")
        return fakes[name]

    monkeypatch.setattr(
        registry, "discover_module_names", lambda: ["nosetup", "broken", "good"]
    )
    monkeypatch.setattr(registry.importlib, "import_module", fake_import)

    loaded = await registry.load_modules(AsyncMock(), FastAPI(), make_ctx(db=db))
    assert loaded == ["good"]
    assert calls == ["good"]
