"""The shared application context passed to every module's ``setup``.

``AppContext`` carries the resolved settings, the database, the API clients,
the scheduler and the webhook registry, plus the live DRY_RUN flag that the
dashboard can flip at runtime.
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
from core.logging import get_logger
from core.scheduler import SchedulerService
from core.settings_store import SettingsStore
from core.trakt_auth import TraktAuthSession
from core.webhooks import WebhookRegistry


class DryRunFlag:
    """A mutable, callable boolean shared between the context and the clients.

    Clients are constructed before the context, so they receive this object as
    their ``dry_run_provider``; flipping it via :meth:`AppContext.set_dry_run`
    is reflected immediately at every call site.
    """

    def __init__(self, value: bool) -> None:
        self.value = value

    def __call__(self) -> bool:
        return self.value


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
    dry_run_flag: DryRunFlag
    settings_store: SettingsStore
    trakt_auth: TraktAuthSession = field(default_factory=TraktAuthSession)
    sync_now: Callable[[], Awaitable[Any]] | None = field(default=None)

    def __post_init__(self) -> None:
        self._log = get_logger("context")

    @property
    def dry_run(self) -> bool:
        """The live DRY_RUN flag value."""
        return self.dry_run_flag.value

    def set_dry_run(self, value: bool) -> bool:
        """Flip the live DRY_RUN flag and log the change. Returns the new value."""
        self.dry_run_flag.value = value
        self._log.info("dry_run set to %s", str(value).lower())
        return value
