"""Persistent, runtime-mutable application settings.

Trakt connection details (client id/secret) and the set of synced lists are
managed from the dashboard rather than static environment variables, so they live
in a small JSON store. The connected account is always addressed as ``me``. The
store is **seeded** from the environment on first run and then becomes the source
of truth; subsequent environment changes are ignored (the UI owns these settings).

Secrets are persisted with ``0600`` permissions and never returned in clear by
:meth:`SettingsStore.masked`. The store is thread-safe so the scheduler thread and
the request handlers can share it within one Uvicorn worker.
"""

from __future__ import annotations

import json
import os
import threading
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.service_registry import (
    BY_NAME,
    SERVICES,
    ServiceDescriptor,
    empty_values,
    masked_entry,
)

# Allowed status-check intervals offered by the dashboard.
VALID_STATUS_INTERVALS: frozenset[int] = frozenset({30, 45, 60})

# Allowed Trakt sync (poll) intervals in minutes offered by the dashboard.
VALID_SYNC_INTERVALS: frozenset[int] = frozenset({15, 30, 45, 60})

# Allowed Bandwidth-Controllarr check intervals in seconds offered by the dashboard.
VALID_BANDWIDTH_INTERVALS: frozenset[int] = frozenset({10, 15, 30, 60})

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


def _service_seed(
    desc: ServiceDescriptor, seed: dict[str, str] | None
) -> dict[str, str]:
    """Normalise a seed entry (or ``None``) into this service's field dict."""
    seed = seed or {}
    return {field: (seed.get(field) or "").strip() for field in desc.fields}


def _normalise_interval(value: int) -> int:
    """Return a valid status-check interval, defaulting to 60 seconds."""
    return value if value in VALID_STATUS_INTERVALS else 60


def _normalise_sync_interval(value: int) -> int:
    """Return a valid Trakt sync interval in minutes, defaulting to 15."""
    return value if value in VALID_SYNC_INTERVALS else 15


def _normalise_bandwidth_interval(value: int) -> int:
    """Return a valid Bandwidth-Controllarr interval in seconds, defaulting to 15."""
    return value if value in VALID_BANDWIDTH_INTERVALS else 15


def _normalise_findarr_interval(value: int) -> int:
    """Return a valid Findarr interval in minutes, defaulting to 30."""
    return value if value in VALID_FINDARR_INTERVALS else 30


def _normalise_findarr_limit(value: Any, *, default: int) -> int:
    """Return a bounded non-negative Findarr per-cycle/API limit."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, _FINDARR_LIMIT_MAX))


def _normalise_findarr_queue_limit(value: Any) -> int:
    """Return a Findarr queue limit, where ``-1`` means no queue guard."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return -1
    return -1 if parsed < 0 else min(parsed, _FINDARR_LIMIT_MAX)


def _normalise_findarr_search_mode(value: Any, *, default: str = "episodes") -> str:
    """Return a valid Sonarr search-mode granularity, defaulting to episodes."""
    return value if value in VALID_FINDARR_SEARCH_MODES else default


def _normalise_findarr_sleep_seconds(value: Any) -> int:
    """Return a bounded inter-command sleep in seconds, defaulting to 0."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(parsed, _FINDARR_SLEEP_MAX))


def _normalise_findarr_reset_hours(value: Any) -> int:
    """Return a bounded stateful-reset window in hours, defaulting to 168."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 168
    return max(_FINDARR_RESET_HOURS_MIN, min(parsed, _FINDARR_RESET_HOURS_MAX))


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_findarr_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge and validate persisted Findarr settings with safe defaults."""
    raw = raw or {}
    defaults = copy.deepcopy(DEFAULT_FINDARR_SETTINGS)
    apps = raw.get("apps") if isinstance(raw.get("apps"), dict) else {}

    normalised = {
        "enabled": bool(raw.get("enabled", defaults["enabled"])),
        "interval_minutes": _normalise_findarr_interval(
            _coerce_int(raw.get("interval_minutes"), defaults["interval_minutes"])
        ),
        "hourly_cap": _normalise_findarr_limit(
            raw.get("hourly_cap", defaults["hourly_cap"]),
            default=defaults["hourly_cap"],
        ),
        "queue_limit": _normalise_findarr_queue_limit(raw.get("queue_limit", defaults["queue_limit"])),
        "command_sleep_seconds": _normalise_findarr_sleep_seconds(
            raw.get("command_sleep_seconds", defaults["command_sleep_seconds"])
        ),
        "state_reset_hours": _normalise_findarr_reset_hours(
            raw.get("state_reset_hours", defaults["state_reset_hours"])
        ),
        "apps": {},
    }

    for app_name, app_defaults in defaults["apps"].items():
        raw_app = apps.get(app_name) if isinstance(apps.get(app_name), dict) else {}
        normalised["apps"][app_name] = {
            "enabled": bool(raw_app.get("enabled", app_defaults["enabled"])),
            "missing_limit": _normalise_findarr_limit(
                raw_app.get("missing_limit", app_defaults["missing_limit"]),
                default=app_defaults["missing_limit"],
            ),
            "upgrade_limit": _normalise_findarr_limit(
                raw_app.get("upgrade_limit", app_defaults["upgrade_limit"]),
                default=app_defaults["upgrade_limit"],
            ),
            "monitored_only": bool(raw_app.get("monitored_only", app_defaults["monitored_only"])),
            "skip_future": bool(raw_app.get("skip_future", app_defaults["skip_future"])),
            "missing_mode": _normalise_findarr_search_mode(
                raw_app.get("missing_mode", app_defaults["missing_mode"])
            ),
            "upgrade_mode": _normalise_findarr_search_mode(
                raw_app.get("upgrade_mode", app_defaults["upgrade_mode"])
            ),
        }
    return normalised


@dataclass(frozen=True)
class TrackedList:
    """A Trakt list selected for syncing.

    ``owner_user`` is the Trakt username that owns the list (``"me"`` for the
    connected account); ``slug`` is the list slug (or ``"watchlist"``).
    """

    owner_user: str
    slug: str
    name: str

    @property
    def is_watchlist(self) -> bool:
        """Whether this entry refers to the account watchlist."""
        return self.slug.strip().lower() == "watchlist"

    @property
    def key(self) -> tuple[str, str]:
        """The identity of a list: its owner and slug."""
        return (self.owner_user, self.slug)

    def to_dict(self) -> dict[str, str]:
        """Serialise to a plain dict for persistence and API responses."""
        return {"owner_user": self.owner_user, "slug": self.slug, "name": self.name}


class SettingsStore:
    """Thread-safe JSON-backed store for UI-managed settings."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._log = get_logger("settings_store")
        self._client_id = ""
        self._client_secret = ""
        self._lists: list[TrackedList] = []
        self._status_check_interval_seconds = 60
        self._sync_interval_minutes = 15
        self._auto_remove_when_available = False
        self._bandwidth_control_enabled = False
        self._bandwidth_check_interval_seconds = 15
        self._findarr_settings = copy.deepcopy(DEFAULT_FINDARR_SETTINGS)
        self._services: dict[str, dict[str, str]] = {
            desc.name: empty_values(desc) for desc in SERVICES
        }

    # ---- load / seed / persist ----

    def load_or_seed(
        self,
        *,
        client_id: str,
        client_secret: str,
        services: dict[str, dict[str, str]] | None = None,
        status_check_interval_seconds: int = 60,
        sync_interval_minutes: int = 15,
        auto_remove_when_available: bool = False,
        bandwidth_control_enabled: bool = False,
        bandwidth_check_interval_seconds: int = 15,
    ) -> None:
        """Load persisted settings, or seed from the supplied defaults.

        On first run (no store file) the supplied environment-derived values are
        written to disk; thereafter the persisted file is authoritative. The set
        of synced lists is not seeded from the environment — it starts empty and
        is populated from the dashboard (discovered lists or added by URL).
        """
        with self._lock:
            if self._path.exists():
                self._load_locked(seed_services=services or {})
                self._log.info("loaded persisted settings")
            else:
                self._client_id = client_id
                self._client_secret = client_secret
                self._lists = []
                self._status_check_interval_seconds = _normalise_interval(
                    status_check_interval_seconds
                )
                self._sync_interval_minutes = _normalise_sync_interval(
                    sync_interval_minutes
                )
                self._auto_remove_when_available = bool(auto_remove_when_available)
                self._bandwidth_control_enabled = bool(bandwidth_control_enabled)
                self._bandwidth_check_interval_seconds = _normalise_bandwidth_interval(
                    bandwidth_check_interval_seconds
                )
                self._findarr_settings = _normalise_findarr_settings()
                for desc in SERVICES:
                    self._services[desc.name] = _service_seed(
                        desc, (services or {}).get(desc.name)
                    )
                self._save_locked()
                self._log.info("seeded settings from environment")

    def _load_locked(self, seed_services: dict[str, dict[str, str]] | None = None) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        trakt = data.get("trakt") or {}
        self._client_id = trakt.get("client_id", "")
        self._client_secret = trakt.get("client_secret", "")
        self._status_check_interval_seconds = _normalise_interval(
            data.get("status_check_interval_seconds", 60)
        )
        self._sync_interval_minutes = _normalise_sync_interval(
            data.get("sync_interval_minutes", 15)
        )
        migrated_bandwidth = (
            "bandwidth_control_enabled" not in data
            or "bandwidth_check_interval_seconds" not in data
        )
        self._bandwidth_control_enabled = bool(
            data.get("bandwidth_control_enabled", False)
        )
        self._bandwidth_check_interval_seconds = _normalise_bandwidth_interval(
            data.get("bandwidth_check_interval_seconds", 15)
        )
        migrated_findarr = "findarr" not in data
        self._findarr_settings = _normalise_findarr_settings(data.get("findarr"))
        # Migration: the flag was historically persisted as ``auto_remove_on_import``
        # (remove when Radarr/Sonarr imported the title). It now means "remove from
        # Trakt once Seer reports the item available". An existing store is read
        # under the legacy key so the user's choice carries over; when only the legacy
        # key is present the store is re-saved under the new key on load (see the
        # ``migrated_auto_remove`` save trigger below).
        migrated_auto_remove = (
            "auto_remove_when_available" not in data
            and "auto_remove_on_import" in data
        )
        self._auto_remove_when_available = bool(
            data.get(
                "auto_remove_when_available",
                data.get("auto_remove_on_import", False),
            )
        )
        self._lists = [
            TrackedList(
                owner_user=entry.get("owner_user", "me"),
                slug=entry["slug"],
                name=entry.get("name") or entry["slug"],
            )
            for entry in data.get("lists", [])
            if entry.get("slug")
        ]
        # Load stored services; one-time migration backfills services that a
        # pre-existing (older) store file does not yet contain from the env seed.
        stored_services = data.get("services") or {}
        seed = seed_services or {}
        backfilled = False
        for desc in SERVICES:
            name = desc.name
            if name in stored_services:
                entry = stored_services[name]
                self._services[name] = {
                    field: entry.get(field, "") for field in desc.fields
                }
            else:
                self._services[name] = _service_seed(desc, seed.get(name))
                backfilled = True
        if backfilled or migrated_auto_remove or migrated_bandwidth or migrated_findarr:
            self._save_locked()
            self._log.info(
                "persisted store migration (services_backfilled=%s "
                "auto_remove_key_migrated=%s bandwidth_keys_migrated=%s "
                "findarr_keys_migrated=%s)",
                backfilled,
                migrated_auto_remove,
                migrated_bandwidth,
                migrated_findarr,
            )

    def _save_locked(self) -> None:
        payload = {
            "trakt": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
            "status_check_interval_seconds": self._status_check_interval_seconds,
            "sync_interval_minutes": self._sync_interval_minutes,
            "auto_remove_when_available": self._auto_remove_when_available,
            "bandwidth_control_enabled": self._bandwidth_control_enabled,
            "bandwidth_check_interval_seconds": self._bandwidth_check_interval_seconds,
            "findarr": self._findarr_settings,
            "lists": [item.to_dict() for item in self._lists],
            "services": self._services,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.chmod(self._path, 0o600)

    # ---- Trakt credentials ----

    def trakt_credentials(self) -> tuple[str, str]:
        """Return ``(client_id, client_secret)``."""
        with self._lock:
            return (self._client_id, self._client_secret)

    def update_trakt_credentials(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        """Update the Trakt credentials; ``None`` leaves a field unchanged."""
        with self._lock:
            if client_id is not None:
                self._client_id = client_id.strip()
            if client_secret is not None:
                self._client_secret = client_secret.strip()
            self._save_locked()
            self._log.info("updated Trakt credentials")

    # ---- status check interval ----

    def status_check_interval_seconds(self) -> int:
        """Return the configured dashboard status-check interval in seconds."""
        with self._lock:
            return self._status_check_interval_seconds

    def update_status_check_interval(self, seconds: int) -> int:
        """Update the status-check interval; invalid values fall back to 60 s."""
        seconds = _normalise_interval(seconds)
        with self._lock:
            self._status_check_interval_seconds = seconds
            self._save_locked()
            self._log.info("updated status check interval to %s seconds", seconds)
            return seconds

    # ---- Trakt sync interval ----

    def sync_interval_minutes(self) -> int:
        """Return the configured Trakt poll interval in minutes."""
        with self._lock:
            return self._sync_interval_minutes

    def update_sync_interval(self, minutes: int) -> int:
        """Update the Trakt sync interval; invalid values fall back to 15 min."""
        minutes = _normalise_sync_interval(minutes)
        with self._lock:
            self._sync_interval_minutes = minutes
            self._save_locked()
            self._log.info("updated sync interval to %s minutes", minutes)
            return minutes

    # ---- auto-remove when available ----

    def auto_remove_when_available(self) -> bool:
        """Whether the poll removes an item from its Trakt list once it is in Seer.

        When ``True``, an item is dropped from its Trakt list during the sync once
        Seer reports it available or partially available — never the instant it is
        merely requested. Removal deletes both the Trakt entry and the Seer request;
        the media files in Radarr/Sonarr are never touched. When ``False`` (the
        default), removal is fully manual — the dashboard's per-item and "Delete
        availables" controls are the only ways an item leaves a Trakt list. The key
        name is retained for backward compatibility with persisted stores.
        """
        with self._lock:
            return self._auto_remove_when_available

    def update_auto_remove_when_available(self, enabled: bool) -> bool:
        """Set whether available items are auto-removed from Trakt; returns the new value."""
        enabled = bool(enabled)
        with self._lock:
            self._auto_remove_when_available = enabled
            self._save_locked()
            self._log.info("updated auto-remove when available to %s", enabled)
            return enabled

    # ---- Bandwidth-Controllarr ----

    def bandwidth_control_enabled(self) -> bool:
        """Whether Bandwidth-Controllarr pauses SABnzbd while torrents are active."""
        with self._lock:
            return self._bandwidth_control_enabled

    def update_bandwidth_control_enabled(self, enabled: bool) -> bool:
        """Enable or disable Bandwidth-Controllarr; returns the new value."""
        enabled = bool(enabled)
        with self._lock:
            self._bandwidth_control_enabled = enabled
            self._save_locked()
            self._log.info("updated bandwidth control enabled to %s", enabled)
            return enabled

    def bandwidth_check_interval_seconds(self) -> int:
        """Return the configured Bandwidth-Controllarr check interval in seconds."""
        with self._lock:
            return self._bandwidth_check_interval_seconds

    def update_bandwidth_check_interval(self, seconds: int) -> int:
        """Update the Bandwidth-Controllarr check interval; invalid values fall back to 15 s."""
        seconds = _normalise_bandwidth_interval(seconds)
        with self._lock:
            self._bandwidth_check_interval_seconds = seconds
            self._save_locked()
            self._log.info("updated bandwidth check interval to %s seconds", seconds)
            return seconds

    # ---- Findarr ----

    def findarr_settings(self) -> dict[str, Any]:
        """Return a copy of the persisted Findarr settings."""
        with self._lock:
            return copy.deepcopy(self._findarr_settings)

    def findarr_interval_minutes(self) -> int:
        """Return Findarr's configured scheduler interval in minutes."""
        with self._lock:
            return int(self._findarr_settings["interval_minutes"])

    def update_findarr_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge, validate, persist, and return Findarr settings."""
        with self._lock:
            merged = copy.deepcopy(self._findarr_settings)
            for key in (
                "enabled",
                "interval_minutes",
                "hourly_cap",
                "queue_limit",
                "command_sleep_seconds",
                "state_reset_hours",
            ):
                if key in updates and updates[key] is not None:
                    merged[key] = updates[key]
            app_updates = updates.get("apps")
            if isinstance(app_updates, dict):
                merged.setdefault("apps", {})
                for app_name in ("sonarr", "radarr"):
                    if isinstance(app_updates.get(app_name), dict):
                        merged["apps"].setdefault(app_name, {})
                        for key, value in app_updates[app_name].items():
                            if value is not None:
                                merged["apps"][app_name][key] = value
            self._findarr_settings = _normalise_findarr_settings(merged)
            self._save_locked()
            self._log.info("updated Findarr settings")
            return copy.deepcopy(self._findarr_settings)

    # ---- tracked lists ----

    def tracked_lists(self) -> list[TrackedList]:
        """Return the lists selected for syncing (a copy)."""
        with self._lock:
            return list(self._lists)

    def owner_for(self, slug: str) -> str:
        """Return the owner of a tracked list by slug, defaulting to ``me``."""
        with self._lock:
            for item in self._lists:
                if item.slug == slug:
                    return item.owner_user
            return "me"

    def add_list(self, *, owner_user: str, slug: str, name: str) -> bool:
        """Add a list to the synced set. Returns ``False`` if already present."""
        with self._lock:
            key = (owner_user, slug)
            if any(item.key == key for item in self._lists):
                return False
            self._lists.append(
                TrackedList(owner_user=owner_user, slug=slug, name=name)
            )
            self._save_locked()
            self._log.info("added list owner=%s slug=%s", owner_user, slug)
            return True

    def remove_list(self, *, owner_user: str, slug: str) -> bool:
        """Remove a list from the synced set. Returns ``False`` if absent."""
        with self._lock:
            key = (owner_user, slug)
            remaining = [item for item in self._lists if item.key != key]
            if len(remaining) == len(self._lists):
                return False
            self._lists = remaining
            self._save_locked()
            self._log.info("removed list owner=%s slug=%s", owner_user, slug)
            return True

    # ---- service connections (seer / sonarr / radarr) ----

    def service_fields(self, name: str) -> dict[str, str]:
        """Return a copy of the stored field dict for a service.

        Raises ``KeyError`` for an unknown service name.
        """
        with self._lock:
            return dict(self._services[name])

    def service_connection(self, name: str) -> tuple[str, str]:
        """Return ``(url, api_key)`` for a service (blank for absent fields).

        A thin wrapper over :meth:`service_fields` for callers that only need the
        legacy URL/API-key pair (Seer/Sonarr/Radarr/SABnzbd).
        """
        fields = self.service_fields(name)
        return (fields.get("url", ""), fields.get("api_key", ""))

    def update_service_fields(self, name: str, **fields: str | None) -> None:
        """Update a service's stored fields; ``None`` leaves a field unchanged.

        Only the keys declared by the service descriptor are applied; any other
        keyword (e.g. ``username`` for a URL/API-key service) is ignored.
        """
        desc = BY_NAME[name]
        with self._lock:
            entry = self._services[name]
            for field in desc.fields:
                value = fields.get(field)
                if value is not None:
                    entry[field] = value.strip()
            self._save_locked()
            self._log.info("updated %s connection", name)

    def update_service_connection(
        self, name: str, *, url: str | None = None, api_key: str | None = None
    ) -> None:
        """Update a service's URL/API key; ``None`` leaves a field unchanged.

        Retained for the legacy URL/API-key call site; delegates to
        :meth:`update_service_fields`.
        """
        self.update_service_fields(name, url=url, api_key=api_key)

    def masked_services(self) -> dict[str, dict[str, Any]]:
        """Return a response-safe view: ``{name: <descriptor-masked entry>}``.

        Each service emits only its declared fields, with secrets reduced to
        ``<field>_set`` booleans (see :func:`core.service_registry.masked_entry`).
        """
        with self._lock:
            return {
                desc.name: masked_entry(desc, self._services[desc.name])
                for desc in SERVICES
            }

    # ---- masking ----

    def masked(self) -> dict[str, Any]:
        """Return a log/response-safe view: secrets reduced to hints/booleans."""
        with self._lock:
            return {
                "client_id_hint": self._client_id[-4:] if self._client_id else "",
                "client_id_set": bool(self._client_id),
                "client_secret_set": bool(self._client_secret),
                "status_check_interval_seconds": self._status_check_interval_seconds,
                "sync_interval_minutes": self._sync_interval_minutes,
                "auto_remove_when_available": self._auto_remove_when_available,
                "bandwidth_control_enabled": self._bandwidth_control_enabled,
                "bandwidth_check_interval_seconds": self._bandwidth_check_interval_seconds,
                "findarr": copy.deepcopy(self._findarr_settings),
                "lists": [item.to_dict() for item in self._lists],
                "services": self.masked_services(),
            }
