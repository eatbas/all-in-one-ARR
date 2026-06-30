"""The shared application context passed to every module's ``setup``.

``AppContext`` carries the resolved settings, the database, the API clients,
the scheduler and the webhook registry.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from core.clients.arr_client import ArrClient
from core.clients.seer import SeerClient
from core.clients.omdb import OmdbClient
from core.clients.qbittorrent import QbittorrentClient
from core.clients.sabnzbd import SabnzbdClient
from core.clients.tmdb import TmdbClient
from core.clients.trakt import TraktClient
from core.config import Settings
from core.db import Database
from core.posters import PosterCache
from core.scheduler import SchedulerService
from core.settings_store import SettingsStore
from core.status_checker import StatusChecker
from core.trakt_auth import TraktAuthSession
from core.webhooks import WebhookRegistry

T = TypeVar("T")


class SyncAlreadyRunning(Exception):
    """Raised when a sync is requested while another sync is already running."""


class SyncGate:
    """Coordinates manual and scheduled sync runs so they never overlap.

    The gate owns a single ``asyncio.Lock`` created lazily inside the running
    event loop. Scheduled runs wait for the lock; manual runs try to acquire it
    without blocking and are rejected if it is held.
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        """Return the gate's lock, creating it in the current running loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def is_running(self) -> bool:
        return self._lock is not None and self._lock.locked()

    async def run(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Run a sync factory, waiting for any in-progress sync to finish."""
        async with self._get_lock():
            return await factory()

    async def try_run(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Run a sync factory, raising ``SyncAlreadyRunning`` if one is in progress."""
        if not await self._try_acquire():
            raise SyncAlreadyRunning()
        try:
            return await factory()
        finally:
            self._get_lock().release()

    async def _try_acquire(self) -> bool:
        """Try to acquire the lock without blocking; return True on success.

        The check and acquire are performed without an intervening ``await`` in
        the same task, so in the single-threaded event loop this is effectively
        atomic: no other task can claim the lock between the check and acquire.
        """
        lock = self._get_lock()
        if lock.locked():
            return False
        await lock.acquire()
        return True


@dataclass
class AppContext:
    """Shared services handed to modules during ``setup``."""

    settings: Settings
    db: Database
    trakt: TraktClient
    seer: SeerClient
    sonarr: ArrClient
    radarr: ArrClient
    tmdb: TmdbClient
    omdb: OmdbClient
    sabnzbd: SabnzbdClient
    qbittorrent: QbittorrentClient
    scheduler: SchedulerService
    webhooks: WebhookRegistry
    settings_store: SettingsStore
    status_checker: StatusChecker = field(default_factory=lambda: None)  # type: ignore[arg-type]
    poster_cache: PosterCache | None = field(default=None)
    trakt_auth: TraktAuthSession = field(default_factory=TraktAuthSession)
    sync_now: Callable[[], Awaitable[Any]] | None = field(default=None)
    # Coordinates manual and scheduled list-syncarr sync runs so they do not
    # process the same lists concurrently. Created once per process; both the
    # scheduled poll_job and the manual sync endpoint use it.
    sync_gate: SyncGate = field(default_factory=SyncGate)
    # Manual removal actions, set by the list_syncarr module during setup(); the
    # API calls these so core stays decoupled from the module (mirrors sync_now).
    remove_available: Callable[[], Awaitable[Any]] | None = field(default=None)
    remove_item: Callable[[str, int], Awaitable[bool]] | None = field(default=None)
    reschedule_sync: Callable[[int], Awaitable[Any]] | None = field(default=None)
    # Bandwidth-Controllarr callables, set by the module during setup(); the API
    # router uses them so the core stays decoupled from the module.
    bandwidth_status: Callable[[], Awaitable[dict]] | None = field(default=None)
    bandwidth_update_settings: Callable[..., Awaitable[dict]] | None = field(
        default=None
    )
    # Findarr callables, set by the module during setup(); the core router uses
    # these so API routes are registered before the SPA catch-all while the
    # scheduler-specific implementation remains module-owned.
    findarr_status: Callable[[], Awaitable[dict]] | None = field(default=None)
    findarr_run_now: Callable[..., Awaitable[dict]] | None = field(default=None)
    findarr_history: Callable[[], Awaitable[list[dict]]] | None = field(default=None)
    findarr_update_settings: Callable[..., Awaitable[dict]] | None = field(default=None)
    findarr_reset_state: Callable[[], Awaitable[dict]] | None = field(default=None)
    findarr_clear_history: Callable[[], Awaitable[dict]] | None = field(default=None)
    findarr_reschedule: Callable[[int], Awaitable[Any]] | None = field(default=None)
    findarr_gate: SyncGate = field(default_factory=SyncGate)
