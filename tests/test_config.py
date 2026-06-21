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


def test_missing_secrets_raises() -> None:
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, TRAKT_CLIENT_ID="", TRAKT_CLIENT_SECRET="",
                 JELLYSEERR_URL="", JELLYSEERR_API_KEY="")
    message = str(exc.value)
    assert "TRAKT_CLIENT_ID" in message
    assert "JELLYSEERR_API_KEY" in message


def test_masked_hides_secrets() -> None:
    settings = Settings(_env_file=None, **_VALID)
    masked = settings.masked()
    assert masked["TRAKT_CLIENT_ID"] == "***"
    assert masked["JELLYSEERR_API_KEY"] == "***"
    assert masked["TRAKT_USER"] == "me"
    assert masked["DRY_RUN"] is True
