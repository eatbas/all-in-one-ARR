"""Default values and normalisation helpers for ``SettingsStore``."""

from __future__ import annotations

import copy
import posixpath
import re
from typing import Any

from core.audio_languages import (
    DEFAULT_AUDIO_LANGUAGE,
    canonical_language,
    is_known_language,
)
from core.coerce import bounded_int, coerce_int
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

# Allowed IMDb-rating refresh windows in days offered by the dashboard's App
# scheduler: a stored rating older than this is re-fetched by the OMDb backfill.
VALID_RATING_TTL_DAYS: frozenset[int] = frozenset({5, 7, 10})
DEFAULT_RATING_TTL_DAYS = 7

# Per-key daily OMDb request budget for the rating backfill. OMDb's free tier
# allows 1000 requests per key per day; the default leaves headroom for the
# poster fallback and the compat rating route. User-editable within bounds.
DEFAULT_OMDB_DAILY_BUDGET_PER_KEY = 800
OMDB_DAILY_BUDGET_PER_KEY_MIN = 100
OMDB_DAILY_BUDGET_PER_KEY_MAX = 1000

# Bounds for the SABnzbd download limiter in MB/s. The dashboard accepts
# decimal values (e.g. 7.5); stored values are rounded to two decimal places.
DEFAULT_SAB_LIMIT_MBPS = 5.0
SAB_LIMIT_MBPS_MIN = 0.1
SAB_LIMIT_MBPS_MAX = 1024.0

# Allowed Findarr scheduler intervals in minutes offered by the dashboard.
VALID_FINDARR_INTERVALS: frozenset[int] = frozenset({15, 30, 45, 60})

# Allowed Sonarr search-mode granularities (Radarr ignores them — movies only).
VALID_FINDARR_SEARCH_MODES: frozenset[str] = frozenset({"episodes", "seasons", "shows"})

_FINDARR_LIMIT_MAX = 100
_FINDARR_SLEEP_MAX = 60
_FINDARR_RESET_HOURS_MIN = 1
_FINDARR_RESET_HOURS_MAX = 8760

# Languagarr bounds.
LANGUAGARR_INTERVAL_MIN = 15
LANGUAGARR_INTERVAL_MAX = 1440
LANGUAGARR_SEARCHES_PER_RUN_MIN = 1
LANGUAGARR_SEARCHES_PER_RUN_MAX = 100
LANGUAGARR_RETRY_HOURS_MIN = 24
LANGUAGARR_RETRY_HOURS_MAX = 2160
LANGUAGARR_PROFILE_NAMES_MAX = 20
LANGUAGARR_LANGUAGES_MAX = 10

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
        # Radarr has no season/show concept: it always searches whole movies,
        # so it carries no search-mode settings.
        "radarr": {
            "enabled": True,
            "missing_limit": 5,
            "upgrade_limit": 5,
            "monitored_only": True,
            "skip_future": True,
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


# Languagarr: audits Sonarr anime episode files for an audio track in one of the
# target languages (English by default) and queues bounded replacement searches. ``enabled`` gates the scheduled search
# worker only; scans and reviewed actions are always available from the page.
DEFAULT_LANGUAGARR_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "interval_minutes": 60,
    "searches_per_run": 10,
    "retry_after_hours": 168,
    "auto_queue": False,
    # Like Findarr's monitored-only default: unmonitored series and episodes are
    # never searched, because Sonarr runs API-triggered searches as user-invoked
    # and would otherwise replace files the user deliberately froze.
    "monitored_only": True,
    "quality_profile_names": ["Anime"],
    # Canonical audio-language codes (core.audio_languages); a file passes when
    # it carries at least one of them.
    "target_audio_languages": [DEFAULT_AUDIO_LANGUAGE],
    # Browser-facing Sonarr address for the series links. Empty falls back to
    # the Sonarr service URL, which is often a Docker hostname the browser
    # cannot resolve (``http://sonarr:8989``).
    "sonarr_link_url": "",
}


def service_seed(
    desc: ServiceDescriptor, seed: dict[str, str] | None
) -> dict[str, str]:
    """Normalise a seed entry (or ``None``) into this service's field dict."""
    seed = seed or {}
    return {field: (seed.get(field) or "").strip() for field in desc.fields}


def normalise_service_url(url: str) -> str:
    """Normalise a service base URL for storage and browser deep-links.

    - Trims whitespace.
    - Default to ``http://`` when no scheme is present.
    - Reject schemes other than ``http`` and ``https``.
    - Strip trailing slashes while preserving any path.

    Raises ``ValueError`` when the scheme is unsupported.
    """
    url = url.strip()
    if not url:
        return ""
    if "://" not in url:
        url = "http://" + url
    scheme, remainder = url.split("://", 1)
    if scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    # Preserve any path but remove trailing slashes.
    remainder = remainder.rstrip("/")
    return f"{scheme}://{remainder}"


def normalise_interval(value: int) -> int:
    """Return a valid status-check interval, defaulting to 60 seconds."""
    return value if value in VALID_STATUS_INTERVALS else 60


def normalise_sync_interval(value: int) -> int:
    """Return a valid Trakt sync interval in minutes, defaulting to 15."""
    return value if value in VALID_SYNC_INTERVALS else 15


def normalise_bandwidth_interval(value: int) -> int:
    """Return a valid Bandwidth-Controllarr interval in seconds, defaulting to 15."""
    return value if value in VALID_BANDWIDTH_INTERVALS else 15


def normalise_sab_limit_mbps(value: Any) -> float:
    """Return a bounded SABnzbd download limit in MB/s, defaulting to 5.0.

    Out-of-range values clamp to the 0.1–1024 bounds; unparseable input falls
    back to the default.
    """
    try:
        parsed = float(value)
    except TypeError, ValueError:
        return DEFAULT_SAB_LIMIT_MBPS
    return round(max(SAB_LIMIT_MBPS_MIN, min(parsed, SAB_LIMIT_MBPS_MAX)), 2)


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


def normalise_rating_ttl_days(value: int) -> int:
    """Return a valid IMDb-rating refresh window in days, defaulting to 7."""
    return value if value in VALID_RATING_TTL_DAYS else DEFAULT_RATING_TTL_DAYS


def normalise_omdb_daily_budget_per_key(value: Any) -> int:
    """Return a bounded per-key OMDb daily budget, defaulting to 800.

    Out-of-range values clamp to the 100–1000 bounds (OMDb's free tier is
    1000/day per key); unparseable input falls back to the default.
    """
    try:
        parsed = int(value)
    except TypeError, ValueError:
        return DEFAULT_OMDB_DAILY_BUDGET_PER_KEY
    return max(
        OMDB_DAILY_BUDGET_PER_KEY_MIN,
        min(parsed, OMDB_DAILY_BUDGET_PER_KEY_MAX),
    )


def normalise_findarr_interval(value: int) -> int:
    """Return a valid Findarr interval in minutes, defaulting to 30."""
    return value if value in VALID_FINDARR_INTERVALS else 30


def _normalise_findarr_limit(value: Any, *, default: int) -> int:
    """Return a bounded non-negative Findarr per-cycle/API limit."""
    return bounded_int(value, default=default, minimum=0, maximum=_FINDARR_LIMIT_MAX)


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
    return bounded_int(value, default=0, minimum=0, maximum=_FINDARR_SLEEP_MAX)


def _normalise_findarr_reset_hours(value: Any) -> int:
    """Return the bounded base retry delay in hours, defaulting to 168.

    Persisted as ``state_reset_hours``: it is the wait before a searched item may
    be searched again, which Findarr's backoff doubles after each search that
    finds nothing.
    """
    return bounded_int(
        value,
        default=168,
        minimum=_FINDARR_RESET_HOURS_MIN,
        maximum=_FINDARR_RESET_HOURS_MAX,
    )


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
        normalised_app: dict[str, Any] = {
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
        }
        # Only apps whose defaults declare search modes (Sonarr) keep them; a
        # stale Radarr mode from an older settings file is dropped here.
        for mode_key in ("missing_mode", "upgrade_mode"):
            if mode_key in app_defaults:
                normalised_app[mode_key] = _normalise_findarr_search_mode(
                    raw_app.get(mode_key, app_defaults[mode_key])
                )
        normalised_apps[app_name] = normalised_app

    normalised = {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "interval_minutes": normalise_findarr_interval(
            coerce_int(raw.get("interval_minutes"), defaults["interval_minutes"])
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


def _normalise_languagarr_profile_names(value: Any) -> list[str]:
    """Return a non-empty, de-duplicated list of stripped quality-profile names.

    Order is preserved. Anything that is not a list of non-blank strings falls
    back to the default (``["Anime"]``) so a corrupt store never widens the scope
    to every series.
    """
    default = list(DEFAULT_LANGUAGARR_SETTINGS["quality_profile_names"])
    if not isinstance(value, list):
        return default
    names: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        name = entry.strip()
        if name and name not in names:
            names.append(name)
    return names[:LANGUAGARR_PROFILE_NAMES_MAX] or default


def _normalise_languagarr_languages(value: Any) -> list[str]:
    """Return a non-empty, de-duplicated list of canonical target language codes.

    Each entry is folded to its canonical code (``deu`` becomes ``ger``); codes
    outside the catalogue are dropped. Order is preserved. Anything that leaves
    no language falls back to the default (``["eng"]``), so a corrupt store never
    makes every file look non-compliant.
    """
    default = list(DEFAULT_LANGUAGARR_SETTINGS["target_audio_languages"])
    if not isinstance(value, list):
        return default
    codes: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not is_known_language(entry):
            continue
        code = canonical_language(entry)
        if code not in codes:
            codes.append(code)
    return codes[:LANGUAGARR_LANGUAGES_MAX] or default


def _normalise_link_url(value: Any) -> str:
    """Return a normalised ``http(s)`` link URL, or ``""`` for anything invalid."""
    if not isinstance(value, str):
        return ""
    try:
        return normalise_service_url(value)
    except ValueError:
        return ""


def normalise_languagarr_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge and validate persisted Languagarr settings with safe defaults."""
    raw = raw or {}
    defaults = DEFAULT_LANGUAGARR_SETTINGS
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "interval_minutes": bounded_int(
            raw.get("interval_minutes"),
            default=defaults["interval_minutes"],
            minimum=LANGUAGARR_INTERVAL_MIN,
            maximum=LANGUAGARR_INTERVAL_MAX,
        ),
        "searches_per_run": bounded_int(
            raw.get("searches_per_run"),
            default=defaults["searches_per_run"],
            minimum=LANGUAGARR_SEARCHES_PER_RUN_MIN,
            maximum=LANGUAGARR_SEARCHES_PER_RUN_MAX,
        ),
        "retry_after_hours": bounded_int(
            raw.get("retry_after_hours"),
            default=defaults["retry_after_hours"],
            minimum=LANGUAGARR_RETRY_HOURS_MIN,
            maximum=LANGUAGARR_RETRY_HOURS_MAX,
        ),
        "auto_queue": bool(raw.get("auto_queue", defaults["auto_queue"])),
        "monitored_only": bool(raw.get("monitored_only", defaults["monitored_only"])),
        "quality_profile_names": _normalise_languagarr_profile_names(
            raw.get("quality_profile_names", defaults["quality_profile_names"])
        ),
        "target_audio_languages": _normalise_languagarr_languages(
            raw.get("target_audio_languages", defaults["target_audio_languages"])
        ),
        "sonarr_link_url": _normalise_link_url(raw.get("sonarr_link_url")),
    }


# Cleanarr bounds. The API rejects out-of-range input (HTTP 422); the normaliser
# below clamps or falls back for anything already persisted.
CLEANARR_INTERVAL_MIN = 5
CLEANARR_INTERVAL_MAX = 1440
CLEANARR_MAX_STRIKES_MIN = 3
CLEANARR_MAX_STRIKES_MAX = 20
CLEANARR_REMOVALS_PER_RUN_MIN = 1
CLEANARR_REMOVALS_PER_RUN_MAX = 50
CLEANARR_MIN_AGE_HOURS_MIN = 1
CLEANARR_MIN_AGE_HOURS_MAX = 720
CLEANARR_RETENTION_DAYS_MIN = 1
CLEANARR_RETENTION_DAYS_MAX = 365
CLEANARR_PATTERNS_MAX = 50
CLEANARR_PATTERN_LENGTH_MAX = 200
CLEANARR_EXTENSIONS_MAX = 100
CLEANARR_IGNORE_MAX = 500
CLEANARR_IGNORE_LENGTH_MAX = 200
CLEANARR_PATH_LENGTH_MAX = 1024
CLEANARR_EXTENSION_PATTERN = r"^\.[a-z0-9]{1,10}$"
VALID_CLEANARR_PATTERN_MODES: frozenset[str] = frozenset({"include", "exclude"})
CLEANARR_QUARANTINE_DIRNAME = "_cleanarr_quarantine"

# Cleanarr: strikes and removes stuck Sonarr/Radarr usenet queue items, warns
# about risky SABnzbd and Arr settings, deletes blocked-extension files from
# completed jobs and quarantines orphaned completed entries. It ships disabled
# and in dry-run; the file passes are opt-in on top of that.
DEFAULT_CLEANARR_SETTINGS: dict[str, Any] = {
    "enabled": False,
    "dry_run": True,
    "interval_minutes": 10,
    "max_strikes": 3,
    "max_removals_per_run": 10,
    "queue": {
        "enabled": True,
        # In exclude mode a failed import is struck unless one of these
        # case-insensitive substrings appears in its status messages or title.
        "pattern_mode": "exclude",
        "patterns": [
            "matched to series by ID",
            "matched to movie by ID",
            "Unable to determine if file is a sample",
        ],
    },
    "malware": {
        "enabled": False,
        "extensions": [
            ".exe",
            ".scr",
            ".bat",
            ".cmd",
            ".com",
            ".pif",
            ".lnk",
            ".vbs",
            ".vbe",
            ".js",
            ".jse",
            ".wsf",
            ".jar",
            ".msi",
            ".ps1",
            ".hta",
            ".cpl",
            ".reg",
        ],
    },
    "orphans": {
        "enabled": False,
        "min_age_hours": 24,
        "quarantine_retention_days": 14,
    },
    "paths": {
        "completed_root": "/downloads/complete",
        "quarantine_dir": f"/downloads/complete/{CLEANARR_QUARANTINE_DIRNAME}",
    },
    "apps": {"sonarr": {"enabled": True}, "radarr": {"enabled": True}},
    "ignore": {"download_ids": [], "categories": [], "title_contains": []},
}


def _section(raw: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``raw[key]`` when it is a dict, else an empty dict."""
    value = raw.get(key)
    return value if isinstance(value, dict) else {}


def _normalise_string_list(value: Any, *, max_items: int, max_length: int) -> list[str]:
    """Return stripped, case-insensitively de-duplicated strings in input order.

    Non-string and blank entries, and entries longer than ``max_length``, are
    dropped; the result is capped at ``max_items``.
    """
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        text = entry.strip()
        folded = text.casefold()
        if not text or len(text) > max_length or folded in seen:
            continue
        seen.add(folded)
        result.append(text)
    return result[:max_items]


def _normalise_cleanarr_patterns(value: Any) -> list[str]:
    """Return the failed-import patterns; a non-list falls back to the seeds."""
    if not isinstance(value, list):
        return list(DEFAULT_CLEANARR_SETTINGS["queue"]["patterns"])
    return _normalise_string_list(
        value, max_items=CLEANARR_PATTERNS_MAX, max_length=CLEANARR_PATTERN_LENGTH_MAX
    )


def _normalise_cleanarr_extensions(value: Any) -> list[str]:
    """Return lower-case ``.ext`` entries, falling back to the defaults when empty.

    A missing leading dot is added; anything not matching
    :data:`CLEANARR_EXTENSION_PATTERN` is dropped, so a corrupt store never
    disables the malware blocker silently.
    """
    default = list(DEFAULT_CLEANARR_SETTINGS["malware"]["extensions"])
    if not isinstance(value, list):
        return default
    result: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        text = entry.strip().lower()
        extension = text if text.startswith(".") else f".{text}"
        if re.fullmatch(CLEANARR_EXTENSION_PATTERN, extension) and (
            extension not in result
        ):
            result.append(extension)
    return result[:CLEANARR_EXTENSIONS_MAX] or default


def _normalise_cleanarr_ignore(raw: dict[str, Any]) -> dict[str, list[str]]:
    """Return the three bounded ignore lists (download IDs, categories, titles)."""
    return {
        key: _normalise_string_list(
            raw.get(key),
            max_items=CLEANARR_IGNORE_MAX,
            max_length=CLEANARR_IGNORE_LENGTH_MAX,
        )
        for key in ("download_ids", "categories", "title_contains")
    }


def _normalise_absolute_path(value: Any, *, default: str) -> str:
    """Return a normalised absolute POSIX path, or ``default`` when invalid."""
    if not isinstance(value, str):
        return default
    text = value.strip()
    if not text.startswith("/") or len(text) > CLEANARR_PATH_LENGTH_MAX:
        return default
    normalised = posixpath.normpath(text)
    # normpath keeps a leading "//" (POSIX allows it to be special); fold it.
    return "/" + normalised.lstrip("/")


def _normalise_cleanarr_paths(raw: dict[str, Any]) -> dict[str, str]:
    """Return the completed and quarantine paths.

    The quarantine folder must sit strictly under the completed folder, so a
    quarantine move is a same-filesystem rename; otherwise it falls back to
    ``<completed_root>/_cleanarr_quarantine``.
    """
    defaults = DEFAULT_CLEANARR_SETTINGS["paths"]
    completed_root = _normalise_absolute_path(
        raw.get("completed_root"), default=defaults["completed_root"]
    )
    fallback = posixpath.join(completed_root, CLEANARR_QUARANTINE_DIRNAME)
    quarantine_dir = _normalise_absolute_path(
        raw.get("quarantine_dir"), default=fallback
    )
    if not is_strictly_under(quarantine_dir, completed_root):
        quarantine_dir = fallback
    return {"completed_root": completed_root, "quarantine_dir": quarantine_dir}


def is_strictly_under(path: str, root: str) -> bool:
    """Return whether POSIX ``path`` lies strictly below ``root`` (both absolute)."""
    prefix = root if root.endswith("/") else f"{root}/"
    return path != root and path.startswith(prefix)


def normalise_cleanarr_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge and validate persisted Cleanarr settings with safe defaults."""
    raw = raw or {}
    defaults = DEFAULT_CLEANARR_SETTINGS
    queue = _section(raw, "queue")
    malware = _section(raw, "malware")
    orphans = _section(raw, "orphans")
    apps = _section(raw, "apps")
    pattern_mode = queue.get("pattern_mode")
    return {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "dry_run": bool(raw.get("dry_run", defaults["dry_run"])),
        "interval_minutes": bounded_int(
            raw.get("interval_minutes"),
            default=defaults["interval_minutes"],
            minimum=CLEANARR_INTERVAL_MIN,
            maximum=CLEANARR_INTERVAL_MAX,
        ),
        "max_strikes": bounded_int(
            raw.get("max_strikes"),
            default=defaults["max_strikes"],
            minimum=CLEANARR_MAX_STRIKES_MIN,
            maximum=CLEANARR_MAX_STRIKES_MAX,
        ),
        "max_removals_per_run": bounded_int(
            raw.get("max_removals_per_run"),
            default=defaults["max_removals_per_run"],
            minimum=CLEANARR_REMOVALS_PER_RUN_MIN,
            maximum=CLEANARR_REMOVALS_PER_RUN_MAX,
        ),
        "queue": {
            "enabled": bool(queue.get("enabled", defaults["queue"]["enabled"])),
            "pattern_mode": pattern_mode
            if pattern_mode in VALID_CLEANARR_PATTERN_MODES
            else defaults["queue"]["pattern_mode"],
            "patterns": _normalise_cleanarr_patterns(
                queue.get("patterns", defaults["queue"]["patterns"])
            ),
        },
        "malware": {
            "enabled": bool(malware.get("enabled", defaults["malware"]["enabled"])),
            "extensions": _normalise_cleanarr_extensions(malware.get("extensions")),
        },
        "orphans": {
            "enabled": bool(orphans.get("enabled", defaults["orphans"]["enabled"])),
            "min_age_hours": bounded_int(
                orphans.get("min_age_hours"),
                default=defaults["orphans"]["min_age_hours"],
                minimum=CLEANARR_MIN_AGE_HOURS_MIN,
                maximum=CLEANARR_MIN_AGE_HOURS_MAX,
            ),
            "quarantine_retention_days": bounded_int(
                orphans.get("quarantine_retention_days"),
                default=defaults["orphans"]["quarantine_retention_days"],
                minimum=CLEANARR_RETENTION_DAYS_MIN,
                maximum=CLEANARR_RETENTION_DAYS_MAX,
            ),
        },
        "paths": _normalise_cleanarr_paths(_section(raw, "paths")),
        "apps": {
            name: {"enabled": bool(_section(apps, name).get("enabled", True))}
            for name in ("sonarr", "radarr")
        },
        "ignore": _normalise_cleanarr_ignore(_section(raw, "ignore")),
    }
