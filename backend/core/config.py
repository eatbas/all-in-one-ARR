"""Typed application configuration loaded from the environment.

All settings come from environment variables (and an optional ``.env`` file).
Secrets never appear in code; :meth:`Settings.masked` produces a dict safe to
log at start-up.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Field names that must be masked whenever the configuration is logged.
_SECRET_FIELDS = frozenset(
    {"TRAKT_CLIENT_ID", "TRAKT_CLIENT_SECRET", "JELLYSEERR_API_KEY"}
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
    TRAKT_CLIENT_ID: str = ""
    TRAKT_CLIENT_SECRET: str = ""
    TRAKT_USER: str = "me"
    TRAKT_LIST_ID: str = "watchlist"

    # ---- Jellyseerr ----
    JELLYSEERR_URL: str = ""
    JELLYSEERR_API_KEY: str = ""

    # ---- Sync behaviour ----
    SYNC_INTERVAL_MIN: int = 15
    WEBHOOK_PORT: int = 3223
    DRY_RUN: bool = True

    # ---- Runtime ----
    TZ: str = "Europe/Istanbul"
    LOG_LEVEL: str = "INFO"

    # ---- Persistence ----
    DB_PATH: str = "data/aio-arr.db"
    TOKEN_STORE_PATH: str = "data/trakt_tokens.json"

    @property
    def is_watchlist(self) -> bool:
        """Whether the configured Trakt source is the user's watchlist."""
        return self.TRAKT_LIST_ID.strip().lower() == "watchlist"

    @model_validator(mode="after")
    def _require_secrets(self) -> "Settings":
        """Fail fast when mandatory credentials are missing."""
        required = {
            "TRAKT_CLIENT_ID": self.TRAKT_CLIENT_ID,
            "TRAKT_CLIENT_SECRET": self.TRAKT_CLIENT_SECRET,
            "JELLYSEERR_URL": self.JELLYSEERR_URL,
            "JELLYSEERR_API_KEY": self.JELLYSEERR_API_KEY,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(
                "Missing required configuration: " + ", ".join(sorted(missing))
            )
        return self

    def masked(self) -> dict[str, Any]:
        """Return the configuration as a dict with secrets masked for logging."""
        result: dict[str, Any] = {}
        for name, value in self.model_dump().items():
            if name in _SECRET_FIELDS and value:
                result[name] = "***"
            else:
                result[name] = value
        return result
