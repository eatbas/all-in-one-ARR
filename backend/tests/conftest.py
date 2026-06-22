"""Shared test fixtures and lightweight stubs."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.context import AppContext, DryRunFlag
from core.db import Database
from core.settings_store import TrackedList
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
        self.update_credentials = MagicMock()
        self.request_device_code = AsyncMock(
            return_value={
                "user_code": "ABCD-1234",
                "verification_url": "https://trakt.tv/activate",
                "device_code": "dev",
                "interval": 0,
                "expires_in": 600,
            }
        )
        self.poll_for_token = AsyncMock(return_value=True)
        self.get_user_lists = AsyncMock(return_value=[])
        self.get_list_summary = AsyncMock(
            return_value={
                "name": "My List",
                "slug": "my-list",
                "owner_user": "me",
                "item_count": 3,
            }
        )
        self.test_connection = AsyncMock(return_value={"username": "me"})
        self.aclose = AsyncMock()

    def is_authenticated(self) -> bool:
        return self._authenticated


class StubSettingsStore:
    """Minimal stand-in for :class:`SettingsStore` for module unit tests."""

    def __init__(
        self,
        *,
        lists: list[TrackedList] | None = None,
        client_id: str = "cid",
        client_secret: str = "secret",
        user: str = "me",
    ) -> None:
        self._lists = (
            lists
            if lists is not None
            else [TrackedList(owner_user="me", slug="watchlist", name="watchlist")]
        )
        self._creds = (client_id, client_secret, user)

    def tracked_lists(self) -> list[TrackedList]:
        return list(self._lists)

    def owner_for(self, slug: str) -> str:
        for item in self._lists:
            if item.slug == slug:
                return item.owner_user
        return self._creds[2]

    def trakt_credentials(self) -> tuple[str, str, str]:
        return self._creds


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
    settings_store: Any | None = None,
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
        settings_store=settings_store or StubSettingsStore(),
    )


class _StubSettings:
    """A tiny settings object exposing only what modules read."""

    TRAKT_LIST_ID = "watchlist"
    SYNC_INTERVAL_MIN = 15


@pytest.fixture
def make_context():
    """Expose :func:`make_ctx` as a fixture."""
    return make_ctx
