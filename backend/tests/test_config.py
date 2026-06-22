"""Tests for core.config."""

from __future__ import annotations

import pytest

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


def test_missing_jellyseerr_secrets_raises() -> None:
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, JELLYSEERR_URL="", JELLYSEERR_API_KEY="")
    message = str(exc.value)
    assert "JELLYSEERR_URL" in message
    assert "JELLYSEERR_API_KEY" in message


def test_trakt_credentials_are_optional() -> None:
    # Trakt creds may be configured later from the dashboard, so an empty pair
    # must not fail start-up.
    settings = Settings(
        _env_file=None,
        TRAKT_CLIENT_ID="",
        TRAKT_CLIENT_SECRET="",
        JELLYSEERR_URL="http://js:5055",
        JELLYSEERR_API_KEY="key",
    )
    assert settings.TRAKT_CLIENT_ID == ""


def test_masked_hides_secrets() -> None:
    settings = Settings(_env_file=None, **_VALID)
    masked = settings.masked()
    assert masked["TRAKT_CLIENT_ID"] == "***"
    assert masked["JELLYSEERR_API_KEY"] == "***"
    assert masked["TRAKT_USER"] == "me"
    assert masked["DRY_RUN"] is True
