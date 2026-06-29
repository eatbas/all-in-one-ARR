"""Tests for core.config."""

from __future__ import annotations

from core.config import Settings

_VALID = {
    "TRAKT_CLIENT_ID": "cid",
    "TRAKT_CLIENT_SECRET": "secret",
    "SEER_URL": "http://js:5055",
    "SEER_API_KEY": "key",
}


def test_valid_settings_defaults() -> None:
    settings = Settings(_env_file=None, **_VALID)
    assert settings.SYNC_INTERVAL_MIN == 15
    assert settings.POSTER_CACHE_PATH == "data/posters"
    assert settings.BANDWIDTH_CONTROL_ENABLED is False
    assert settings.BANDWIDTH_CHECK_INTERVAL_SEC == 15
    # Poster-cache churn defaults: TTL comfortably exceeds the 7-day browser cache.
    assert settings.POSTER_CACHE_TTL_DAYS == 30
    assert settings.POSTER_CACHE_MAX_MB == 256
    assert settings.POSTER_CACHE_CHURN_INTERVAL_MIN == 360


def test_poster_cache_churn_overrides_from_env() -> None:
    settings = Settings(
        _env_file=None,
        POSTER_CACHE_TTL_DAYS="14",
        POSTER_CACHE_MAX_MB="64",
        POSTER_CACHE_CHURN_INTERVAL_MIN="120",
        **_VALID,
    )
    assert settings.POSTER_CACHE_TTL_DAYS == 14
    assert settings.POSTER_CACHE_MAX_MB == 64
    assert settings.POSTER_CACHE_CHURN_INTERVAL_MIN == 120


def test_all_service_credentials_are_optional() -> None:
    # Every service (Trakt + the URL/key services + TMDB/OMDb/SABnzbd/qBittorrent)
    # is UI-managed, so an empty configuration must not fail start-up.
    settings = Settings(_env_file=None)
    assert settings.SEER_URL == ""
    assert settings.SONARR_URL == ""
    assert settings.RADARR_API_KEY == ""
    assert settings.TMDB_API_KEY == ""
    assert settings.OMDB_API_KEY == ""
    assert settings.SABNZBD_URL == ""
    assert settings.SABNZBD_API_KEY == ""
    assert settings.QBITTORRENT_URL == ""
    assert settings.QBITTORRENT_API_KEY == ""


def test_service_seeds_shape() -> None:
    settings = Settings(
        _env_file=None,
        SEER_URL="http://js:5055",
        SEER_API_KEY="jk",
        SONARR_URL="http://sonarr:8989",
        SONARR_API_KEY="sk",
        RADARR_URL="http://radarr:7878",
        RADARR_API_KEY="rk",
        TMDB_API_KEY="tk",
        OMDB_API_KEY="ok",
        SABNZBD_URL="http://sab:8080",
        SABNZBD_API_KEY="zk",
        QBITTORRENT_URL="http://qb:8080",
        QBITTORRENT_API_KEY="qbt_key",
    )
    seeds = settings.service_seeds
    assert seeds["seer"] == {"url": "http://js:5055", "api_key": "jk"}
    assert seeds["sonarr"] == {"url": "http://sonarr:8989", "api_key": "sk"}
    assert seeds["radarr"] == {"url": "http://radarr:7878", "api_key": "rk"}
    assert seeds["tmdb"] == {"api_key": "tk"}
    assert seeds["omdb"] == {"api_key": "ok"}
    assert seeds["sabnzbd"] == {"url": "http://sab:8080", "api_key": "zk"}
    assert seeds["qbittorrent"] == {"url": "http://qb:8080", "api_key": "qbt_key"}


def test_masked_hides_secrets() -> None:
    settings = Settings(
        _env_file=None,
        SONARR_API_KEY="sk",
        RADARR_API_KEY="rk",
        TMDB_API_KEY="tk",
        OMDB_API_KEY="ok",
        SABNZBD_API_KEY="zk",
        QBITTORRENT_API_KEY="qbt_key",
        **_VALID,
    )
    masked = settings.masked()
    assert masked["TRAKT_CLIENT_ID"] == "***"
    assert masked["SEER_API_KEY"] == "***"
    assert masked["SONARR_API_KEY"] == "***"
    assert masked["RADARR_API_KEY"] == "***"
    assert masked["TMDB_API_KEY"] == "***"
    assert masked["OMDB_API_KEY"] == "***"
    assert masked["SABNZBD_API_KEY"] == "***"
    assert masked["QBITTORRENT_API_KEY"] == "***"
    # A non-secret field is shown in clear.
    assert masked["WEBHOOK_PORT"] == 3223
