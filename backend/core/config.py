"""Typed application configuration loaded from the environment.

All settings come from environment variables (and an optional ``.env`` file).
Secrets never appear in code; :meth:`Settings.masked` produces a dict safe to
log at start-up.
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Field names that must be masked whenever the configuration is logged.
_SECRET_FIELDS = frozenset(
    {
        "TRAKT_CLIENT_ID",
        "TRAKT_CLIENT_SECRET",
        "SEER_API_KEY",
        "SONARR_API_KEY",
        "RADARR_API_KEY",
        "TMDB_API_KEY",
        "OMDB_API_KEY",
        "SABNZBD_API_KEY",
        "QBITTORRENT_API_KEY",
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
    # they are managed from the dashboard (see core.settings_store). The connected
    # account is always addressed as ``me``, and the lists to sync are chosen from
    # the dashboard (discovered from the account, or added by URL), so neither the
    # account user nor the list set is configured here.
    TRAKT_CLIENT_ID: str = ""
    TRAKT_CLIENT_SECRET: str = ""

    # ---- Services (URL + API key; seed the store, then UI-managed) ----
    SEER_URL: str = ""
    SEER_API_KEY: str = ""
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

    # ---- qBittorrent (URL + WebUI API key; requires qBittorrent >= 5.2.0) ----
    QBITTORRENT_URL: str = ""
    QBITTORRENT_API_KEY: str = ""

    # ---- Sync behaviour ----
    SYNC_INTERVAL_MIN: int = 15
    STATUS_CHECK_INTERVAL_SECONDS: int = 60

    # ---- Bandwidth-Controllarr ----
    BANDWIDTH_CONTROL_ENABLED: bool = False
    BANDWIDTH_CHECK_INTERVAL_SEC: int = 15

    # ---- Trending discovery ----
    # The background App scheduler refreshes the trending/popular feeds on this
    # interval (minutes, whole-day multiples — Settings -> General: 1/2/3 days);
    # seeds the store on first run, then UI-managed.
    TRENDING_SYNC_INTERVAL_MIN: int = 1440
    # How often (days) the cached Fribb anime id mapping is re-downloaded; seeds
    # the store on first run, then UI-managed (Settings -> General: 1/3/5).
    ANIME_IDS_REFRESH_DAYS: int = 3

    # ---- Deletarr ----
    # Seed the media-library roots on first run; thereafter they are managed from
    # the dashboard and persisted in the settings store.
    DELETARR_MOVIES_PATH: str = "/media/movies"
    DELETARR_TV_PATH: str = "/media/tv"
    # When true, Deletarr uses Radarr/Sonarr as the source of truth for which files
    # belong on disk (falling back to the heuristic scan when they are unreachable).
    # Seeds the store on first run, then becomes UI-managed.
    DELETARR_USE_ARR_SOURCE: bool = True

    # Whether the poll removes an item from its Trakt list once Seer reports
    # it available (the list entry only — media files are untouched). Off by default
    # so removal is fully manual (via the dashboard); seeds the store on first run,
    # then becomes UI-managed. The legacy ``AUTO_REMOVE_ON_IMPORT`` env var is still
    # accepted so existing ``.env`` files keep working.
    AUTO_REMOVE_WHEN_AVAILABLE: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "AUTO_REMOVE_WHEN_AVAILABLE", "AUTO_REMOVE_ON_IMPORT"
        ),
    )
    WEBHOOK_PORT: int = 3223

    # ---- Runtime ----
    TZ: str = "Europe/Istanbul"
    LOG_LEVEL: str = "INFO"

    # ---- Persistence ----
    DB_PATH: str = "data/aio-arr.db"
    TOKEN_STORE_PATH: str = "data/trakt_tokens.json"
    SETTINGS_STORE_PATH: str = "data/app_settings.json"
    # Disk cache for fetched poster thumbnails; lives inside the gitignored
    # data/ volume so each poster is downloaded from TMDB/OMDb at most once.
    POSTER_CACHE_PATH: str = "data/posters"
    # Cached copy of Fribb's anime-list-mini id mapping (AniList/MAL ->
    # TMDB/TVDB/IMDb), inside the gitignored data/ volume; refreshed on a TTL
    # by core.anime_ids so the Trending anime tab never fetches it per request.
    ANIME_IDS_PATH: str = "data/anime_ids.json"
    # Poster-cache churn: a scheduled job evicts posters not served within the TTL
    # (by file mtime, bumped on each cache hit) and caps the total cache size,
    # evicting oldest-first. The TTL must exceed the 7-day browser cache
    # (posters are served with ``Cache-Control: max-age=604800``) so a
    # continuously-viewed poster is not evicted mid-use. Set TTL or the size cap
    # to ``0`` to disable that pass; both ``0`` makes the job a no-op.
    POSTER_CACHE_TTL_DAYS: int = 30
    POSTER_CACHE_MAX_MB: int = 256
    POSTER_CACHE_CHURN_INTERVAL_MIN: int = 360

    @property
    def service_seeds(self) -> dict[str, dict[str, str]]:
        """Seed values for the settings store's service connections.

        Every service (Trakt and these URL/key services) is managed from the
        dashboard after start-up, so none of these are required in the
        environment; they only seed the store on first run.
        """
        return {
            "seer": {"url": self.SEER_URL, "api_key": self.SEER_API_KEY},
            "sonarr": {"url": self.SONARR_URL, "api_key": self.SONARR_API_KEY},
            "radarr": {"url": self.RADARR_URL, "api_key": self.RADARR_API_KEY},
            "tmdb": {"api_key": self.TMDB_API_KEY},
            "omdb": {"api_key": self.OMDB_API_KEY},
            "sabnzbd": {"url": self.SABNZBD_URL, "api_key": self.SABNZBD_API_KEY},
            "qbittorrent": {
                "url": self.QBITTORRENT_URL,
                "api_key": self.QBITTORRENT_API_KEY,
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
