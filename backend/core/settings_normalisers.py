"""Default values and normalisation helpers for ``SettingsStore``."""

from __future__ import annotations

import copy
from typing import Any

from core.service_registry import ServiceDescriptor

# Allowed status-check intervals offered by the dashboard.
VALID_STATUS_INTERVALS: frozenset[int] = frozenset({30, 45, 60})

# Allowed Trakt sync (poll) intervals in minutes offered by the dashboard.
VALID_SYNC_INTERVALS: frozenset[int] = frozenset({15, 30, 45, 60})

# Allowed Bandwidth-Controllarr check intervals in seconds offered by the dashboard.
VALID_BANDWIDTH_INTERVALS: frozenset[int] = frozenset({10, 15, 30, 60})

# Allowed trending-sync intervals in minutes offered by the dashboard's App
# scheduler — whole-day multiples (1/2/3 days). Legacy sub-day values from
# earlier releases normalise to the default.
VALID_TRENDING_SYNC_INTERVALS: frozenset[int] = frozenset({1440, 2880, 4320})
DEFAULT_TRENDING_SYNC_INTERVAL = 1440

# Allowed anime id-mapping refresh cadences in days offered by the dashboard's
# App scheduler (the cached Fribb anime-lists file used by the anilist source).
VALID_ANIME_IDS_REFRESH_DAYS: frozenset[int] = frozenset({1, 3, 5})
DEFAULT_ANIME_IDS_REFRESH_DAYS = 3

# Allowed Findarr scheduler intervals in minutes offered by the dashboard.
VALID_FINDARR_INTERVALS: frozenset[int] = frozenset({15, 30, 45, 60})

# Allowed Sonarr search-mode granularities (Radarr ignores them — movies only).
VALID_FINDARR_SEARCH_MODES: frozenset[str] = frozenset({"episodes", "seasons", "shows"})

_FINDARR_LIMIT_MAX = 100
_FINDARR_SLEEP_MAX = 60
_FINDARR_RESET_HOURS_MIN = 1
_FINDARR_RESET_HOURS_MAX = 8760

DEFAULT_FINDARR_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "interval_minutes": 30,
    "hourly_cap": 20,
    "queue_limit": -1,
    "command_sleep_seconds": 0,
    "state_reset_hours": 168,
    "apps": {
        "sonarr": {
            "enabled": True,
            "missing_limit": 5,
            "upgrade_limit": 5,
            "monitored_only": True,
            "skip_future": True,
            "missing_mode": "episodes",
            "upgrade_mode": "episodes",
        },
        "radarr": {
            "enabled": True,
            "missing_limit": 5,
            "upgrade_limit": 5,
            "monitored_only": True,
            "skip_future": True,
            "missing_mode": "episodes",
            "upgrade_mode": "episodes",
        },
    },
}

DEFAULT_DELETARR_SETTINGS: dict[str, Any] = {
    "movies_path": "/media/movies",
    "tv_path": "/media/tv",
    # When true, Deletarr consults Radarr/Sonarr as the source of truth for which
    # files belong on disk; it falls back to the heuristic scan when the matching
    # app is unconfigured or unreachable.
    "use_arr_source": True,
}


def service_seed(
    desc: ServiceDescriptor, seed: dict[str, str] | None
) -> dict[str, str]:
    """Normalise a seed entry (or ``None``) into this service's field dict."""
    seed = seed or {}
    return {field: (seed.get(field) or "").strip() for field in desc.fields}


def normalise_interval(value: int) -> int:
    """Return a valid status-check interval, defaulting to 60 seconds."""
    return value if value in VALID_STATUS_INTERVALS else 60


def normalise_sync_interval(value: int) -> int:
    """Return a valid Trakt sync interval in minutes, defaulting to 15."""
    return value if value in VALID_SYNC_INTERVALS else 15


def normalise_bandwidth_interval(value: int) -> int:
    """Return a valid Bandwidth-Controllarr interval in seconds, defaulting to 15."""
    return value if value in VALID_BANDWIDTH_INTERVALS else 15


def normalise_trending_sync_interval(value: int) -> int:
    """Return a valid trending-sync interval in minutes, defaulting to one day."""
    return (
        value
        if value in VALID_TRENDING_SYNC_INTERVALS
        else DEFAULT_TRENDING_SYNC_INTERVAL
    )


def normalise_anime_ids_refresh_days(value: int) -> int:
    """Return a valid anime id-mapping refresh cadence in days, defaulting to 3."""
    return (
        value
        if value in VALID_ANIME_IDS_REFRESH_DAYS
        else DEFAULT_ANIME_IDS_REFRESH_DAYS
    )


def normalise_findarr_interval(value: int) -> int:
    """Return a valid Findarr interval in minutes, defaulting to 30."""
    return value if value in VALID_FINDARR_INTERVALS else 30


def _normalise_findarr_limit(value: Any, *, default: int) -> int:
    """Return a bounded non-negative Findarr per-cycle/API limit."""
    try:
        parsed = int(value)
    except TypeError, ValueError:
        parsed = default
    return max(0, min(parsed, _FINDARR_LIMIT_MAX))


def _normalise_findarr_queue_limit(value: Any) -> int:
    """Return a Findarr queue limit, where ``-1`` means no queue guard."""
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return -1
    return -1 if parsed < 0 else min(parsed, _FINDARR_LIMIT_MAX)


def _normalise_findarr_search_mode(value: Any, *, default: str = "episodes") -> str:
    """Return a valid Sonarr search-mode granularity, defaulting to episodes."""
    return value if value in VALID_FINDARR_SEARCH_MODES else default


def _normalise_findarr_sleep_seconds(value: Any) -> int:
    """Return a bounded inter-command sleep in seconds, defaulting to 0."""
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return 0
    return max(0, min(parsed, _FINDARR_SLEEP_MAX))


def _normalise_findarr_reset_hours(value: Any) -> int:
    """Return a bounded stateful-reset window in hours, defaulting to 168."""
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return 168
    return max(_FINDARR_RESET_HOURS_MIN, min(parsed, _FINDARR_RESET_HOURS_MAX))


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def normalise_findarr_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge and validate persisted Findarr settings with safe defaults."""
    raw = raw or {}
    defaults = copy.deepcopy(DEFAULT_FINDARR_SETTINGS)
    apps_raw = raw.get("apps")
    apps = apps_raw if isinstance(apps_raw, dict) else {}

    normalised_apps: dict[str, dict[str, Any]] = {}
    for app_name, app_defaults in defaults["apps"].items():
        raw_app_value = apps.get(app_name)
        raw_app = raw_app_value if isinstance(raw_app_value, dict) else {}
        normalised_apps[app_name] = {
            "enabled": bool(raw_app.get("enabled", app_defaults["enabled"])),
            "missing_limit": _normalise_findarr_limit(
                raw_app.get("missing_limit", app_defaults["missing_limit"]),
                default=app_defaults["missing_limit"],
            ),
            "upgrade_limit": _normalise_findarr_limit(
                raw_app.get("upgrade_limit", app_defaults["upgrade_limit"]),
                default=app_defaults["upgrade_limit"],
            ),
            "monitored_only": bool(
                raw_app.get("monitored_only", app_defaults["monitored_only"])
            ),
            "skip_future": bool(
                raw_app.get("skip_future", app_defaults["skip_future"])
            ),
            "missing_mode": _normalise_findarr_search_mode(
                raw_app.get("missing_mode", app_defaults["missing_mode"])
            ),
            "upgrade_mode": _normalise_findarr_search_mode(
                raw_app.get("upgrade_mode", app_defaults["upgrade_mode"])
            ),
        }

    normalised = {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "interval_minutes": normalise_findarr_interval(
            _coerce_int(raw.get("interval_minutes"), defaults["interval_minutes"])
        ),
        "hourly_cap": _normalise_findarr_limit(
            raw.get("hourly_cap", defaults["hourly_cap"]),
            default=defaults["hourly_cap"],
        ),
        "queue_limit": _normalise_findarr_queue_limit(
            raw.get("queue_limit", defaults["queue_limit"])
        ),
        "command_sleep_seconds": _normalise_findarr_sleep_seconds(
            raw.get("command_sleep_seconds", defaults["command_sleep_seconds"])
        ),
        "state_reset_hours": _normalise_findarr_reset_hours(
            raw.get("state_reset_hours", defaults["state_reset_hours"])
        ),
        "apps": normalised_apps,
    }
    return normalised


def _normalise_deletarr_path(value: Any, *, default: str) -> str:
    """Return a non-empty Deletarr path string, falling back to ``default``."""
    path = str(value).strip() if value is not None else ""
    return path or default


def normalise_deletarr_settings(
    raw: dict[str, Any] | None = None,
    *,
    movies_path: str = DEFAULT_DELETARR_SETTINGS["movies_path"],
    tv_path: str = DEFAULT_DELETARR_SETTINGS["tv_path"],
    use_arr_source: bool = DEFAULT_DELETARR_SETTINGS["use_arr_source"],
) -> dict[str, Any]:
    """Merge and validate persisted Deletarr settings with environment seeds."""
    raw = raw or {}
    return {
        "movies_path": _normalise_deletarr_path(
            raw.get("movies_path", movies_path), default=movies_path
        ),
        "tv_path": _normalise_deletarr_path(
            raw.get("tv_path", tv_path), default=tv_path
        ),
        "use_arr_source": bool(raw.get("use_arr_source", use_arr_source)),
    }
