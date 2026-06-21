"""Shared test fixtures and lightweight stubs."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.context import AppContext, DryRunFlag
from core.db import Database
from core.webhooks import WebhookRegistry


@pytest.fixture
def db() -> Database:
    """An initialised in-memory database."""
    database = Database(":memory:")
    database.init_db()
    yield database
    database.close()


class StubTrakt:
    """Minimal stand-in for :class:`TraktClient`."""

    def __init__(self, *, items: list[dict] | None = None, authenticated: bool = True):
        self._items = items or []
        self._authenticated = authenticated
        self.read_list_items = AsyncMock(return_value=self._items)
        self.remove_items = AsyncMock(return_value={"ok": True})
        self.aclose = AsyncMock()

    def is_authenticated(self) -> bool:
        return self._authenticated


class StubJellyseerr:
    """Minimal stand-in for :class:`JellyseerrClient`."""

    def __init__(self, *, status: int | None = None, request_id: int | None = 99):
        self.get_status = AsyncMock(return_value=status)
        self.create_request = AsyncMock(return_value=request_id)
        self.aclose = AsyncMock()


def make_ctx(
    *,
    db: Database,
    trakt: Any | None = None,
    jellyseerr: Any | None = None,
    dry_run: bool = True,
    settings: Any | None = None,
) -> AppContext:
    """Build an :class:`AppContext` wired with stubs for unit tests."""
    flag = DryRunFlag(dry_run)
    scheduler = AsyncMock()
    return AppContext(
        settings=settings or _StubSettings(),
        db=db,
        trakt=trakt or StubTrakt(),
        jellyseerr=jellyseerr or StubJellyseerr(),
        scheduler=scheduler,
        webhooks=WebhookRegistry(),
        dry_run_flag=flag,
    )


class _StubSettings:
    """A tiny settings object exposing only what modules read."""

    TRAKT_LIST_ID = "watchlist"
    SYNC_INTERVAL_MIN = 15


@pytest.fixture
def make_context():
    """Expose :func:`make_ctx` as a fixture."""
    return make_ctx
