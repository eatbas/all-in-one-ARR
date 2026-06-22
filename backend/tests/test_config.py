"""Tests for core.config."""

from __future__ import annotations

from core.config import Settings

_VALID = {
    "TRAKT_CLIENT_ID": "cid",
    "TRAKT_CLIENT_SECRET": "secret",
    "JELLYSEERR_URL": "http://js:5055",
    "JELLYSEERR_API_KEY": "key",
}


def test_valid_settings_defaults() -> None:
    settings = Settings(_env_file=None, **_VALID)
    assert settings.DRY_RUN is True
    assert settings.SYNC_INTERVAL_MIN == 15
    assert settings.is_watchlist is True


def test_non_watchlist_list_id() -> None:
    settings = Settings(_env_file=None, TRAKT_LIST_ID="my-list", **_VALID)
    assert settings.is_watchlist is False


def test_default_trakt_lists_falls_back_to_list_id() -> None:
    settings = Settings(_env_file=None, TRAKT_LIST_ID="my-list", **_VALID)
    assert settings.trakt_lists == ["my-list"]


def test_trakt_lists_parses_dedupes_and_trims() -> None:
    settings = Settings(
        _env_file=None, TRAKT_LISTS="movies, tv ,anime,, movies", **_VALID
    )
    assert settings.trakt_lists == ["movies", "tv", "anime"]


def test_trakt_lists_blank_falls_back_to_list_id() -> None:
    settings = Settings(_env_file=None, TRAKT_LISTS="  , ", **_VALID)
    assert settings.trakt_lists == ["watchlist"]


def test_all_service_credentials_are_optional() -> None:
    # Every service (Trakt + Jellyseerr/Sonarr/Radarr) is UI-managed, so an empty
    # configuration must not fail start-up.
    settings = Settings(_env_file=None)
    assert settings.JELLYSEERR_URL == ""
    assert settings.SONARR_URL == ""
    assert settings.RADARR_API_KEY == ""


def test_service_seeds_shape() -> None:
    settings = Settings(
        _env_file=None,
        JELLYSEERR_URL="http://js:5055",
        JELLYSEERR_API_KEY="jk",
        SONARR_URL="http://sonarr:8989",
        SONARR_API_KEY="sk",
        RADARR_URL="http://radarr:7878",
        RADARR_API_KEY="rk",
    )
    seeds = settings.service_seeds
    assert seeds["jellyseerr"] == {"url": "http://js:5055", "api_key": "jk"}
    assert seeds["sonarr"] == {"url": "http://sonarr:8989", "api_key": "sk"}
    assert seeds["radarr"] == {"url": "http://radarr:7878", "api_key": "rk"}


def test_masked_hides_secrets() -> None:
    settings = Settings(
        _env_file=None, SONARR_API_KEY="sk", RADARR_API_KEY="rk", **_VALID
    )
    masked = settings.masked()
    assert masked["TRAKT_CLIENT_ID"] == "***"
    assert masked["JELLYSEERR_API_KEY"] == "***"
    assert masked["SONARR_API_KEY"] == "***"
    assert masked["RADARR_API_KEY"] == "***"
    assert masked["TRAKT_USER"] == "me"
    assert masked["DRY_RUN"] is True
