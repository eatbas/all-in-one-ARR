"""Typed application configuration loaded from the environment.

All settings come from environment variables (and an optional ``.env`` file).
Secrets never appear in code; :meth:`Settings.masked` produces a dict safe to
log at start-up.
"""

from __future__ import annotations

from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

# Field names that must be masked whenever the configuration is logged.
_SECRET_FIELDS = frozenset(
    {
        "TRAKT_CLIENT_ID",
        "TRAKT_CLIENT_SECRET",
        "JELLYSEERR_API_KEY",
        "SONARR_API_KEY",
        "RADARR_API_KEY",
        "TMDB_API_KEY",
        "OMDB_API_KEY",
        "SABNZBD_API_KEY",
        "QBITTORRENT_PASSWORD",
    }
)


class Settings(BaseSettings):
    """Resolved, validated configuration for the service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- Trakt ----
    # Client credentials seed the runtime settings store on first run; thereafter
    # they are managed from the dashboard (see core.settings_store).
    TRAKT_CLIENT_ID: str = ""
    TRAKT_CLIENT_SECRET: str = ""
    TRAKT_USER: str = "me"
    # A single list slug (legacy) and/or a comma-separated set of slugs. Both seed
    # the settings store; TRAKT_LISTS takes precedence when set.
    TRAKT_LIST_ID: str = "watchlist"
    TRAKT_LISTS: str = ""

    # ---- Services (URL + API key; seed the store, then UI-managed) ----
    JELLYSEERR_URL: str = ""
    JELLYSEERR_API_KEY: str = ""
    SONARR_URL: str = ""
    SONARR_API_KEY: str = ""
    RADARR_URL: str = ""
    RADARR_API_KEY: str = ""

    # ---- TMDB / OMDb (API key only; fixed public endpoints) ----
    TMDB_API_KEY: str = ""
    OMDB_API_KEY: str = ""

    # ---- SABnzbd (URL + API key) ----
    SABNZBD_URL: str = ""
    SABNZBD_API_KEY: str = ""

    # ---- qBittorrent (URL + WebUI username/password) ----
    QBITTORRENT_URL: str = ""
    QBITTORRENT_USERNAME: str = ""
    QBITTORRENT_PASSWORD: str = ""

    # ---- Sync behaviour ----
    SYNC_INTERVAL_MIN: int = 15
    STATUS_CHECK_INTERVAL_SECONDS: int = 60
    WEBHOOK_PORT: int = 3223
    DRY_RUN: bool = True

    # ---- Runtime ----
    TZ: str = "Europe/Istanbul"
    LOG_LEVEL: str = "INFO"

    # ---- Persistence ----
    DB_PATH: str = "data/aio-arr.db"
    TOKEN_STORE_PATH: str = "data/trakt_tokens.json"
    SETTINGS_STORE_PATH: str = "data/app_settings.json"

    @property
    def is_watchlist(self) -> bool:
        """Whether the configured Trakt source is the user's watchlist."""
        return self.TRAKT_LIST_ID.strip().lower() == "watchlist"

    @property
    def trakt_lists(self) -> list[str]:
        """The configured list slugs used to seed the settings store.

        Parses the comma-separated ``TRAKT_LISTS`` (whitespace-trimmed, blanks
        dropped, order-preserving de-dup), falling back to the single
        ``TRAKT_LIST_ID`` when ``TRAKT_LISTS`` is empty.
        """
        raw = self.TRAKT_LISTS.strip()
        if not raw:
            return [self.TRAKT_LIST_ID]
        seen: set[str] = set()
        slugs: list[str] = []
        for part in raw.split(","):
            slug = part.strip()
            if slug and slug not in seen:
                seen.add(slug)
                slugs.append(slug)
        return slugs or [self.TRAKT_LIST_ID]

    @property
    def service_seeds(self) -> dict[str, dict[str, str]]:
        """Seed values for the settings store's service connections.

        Every service (Trakt and these URL/key services) is managed from the
        dashboard after start-up, so none of these are required in the
        environment; they only seed the store on first run.
        """
        return {
            "jellyseerr": {"url": self.JELLYSEERR_URL, "api_key": self.JELLYSEERR_API_KEY},
            "sonarr": {"url": self.SONARR_URL, "api_key": self.SONARR_API_KEY},
            "radarr": {"url": self.RADARR_URL, "api_key": self.RADARR_API_KEY},
            "tmdb": {"api_key": self.TMDB_API_KEY},
            "omdb": {"api_key": self.OMDB_API_KEY},
            "sabnzbd": {"url": self.SABNZBD_URL, "api_key": self.SABNZBD_API_KEY},
            "qbittorrent": {
                "url": self.QBITTORRENT_URL,
                "username": self.QBITTORRENT_USERNAME,
                "password": self.QBITTORRENT_PASSWORD,
            },
        }

    def masked(self) -> dict[str, Any]:
        """Return the configuration as a dict with secrets masked for logging."""
        result: dict[str, Any] = {}
        for name, value in self.model_dump().items():
            if name in _SECRET_FIELDS and value:
                result[name] = "***"
            else:
                result[name] = value
        return result
