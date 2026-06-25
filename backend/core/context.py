"""The shared application context passed to every module's ``setup``.

``AppContext`` carries the resolved settings, the database, the API clients,
the scheduler and the webhook registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.clients.arr_client import ArrClient
from core.clients.jellyseerr import JellyseerrClient
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


@dataclass
class AppContext:
    """Shared services handed to modules during ``setup``."""

    settings: Settings
    db: Database
    trakt: TraktClient
    jellyseerr: JellyseerrClient
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
    # Manual removal actions, set by the list_syncarr module during setup(); the
    # API calls these so core stays decoupled from the module (mirrors sync_now).
    remove_available: Callable[[], Awaitable[Any]] | None = field(default=None)
    remove_item: Callable[[str, int], Awaitable[bool]] | None = field(default=None)
    reschedule_sync: Callable[[int], Awaitable[Any]] | None = field(default=None)
