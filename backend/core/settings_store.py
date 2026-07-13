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

import copy
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.logging import get_logger
from core.service_registry import (
    BY_NAME,
    SERVICES,
    empty_values,
    masked_entry,
)
from core.settings_normalisers import (
    DEFAULT_ANIME_IDS_REFRESH_DAYS,
    DEFAULT_DELETARR_SETTINGS,
    DEFAULT_FINDARR_SETTINGS,
    DEFAULT_OMDB_DAILY_BUDGET_PER_KEY,
    DEFAULT_RATING_TTL_DAYS,
    DEFAULT_SAB_LIMIT_MBPS,
    DEFAULT_TRENDING_SYNC_INTERVAL,
    normalise_anime_ids_refresh_days,
    normalise_bandwidth_interval,
    normalise_deletarr_settings,
    normalise_findarr_settings,
    normalise_interval,
    normalise_omdb_daily_budget_per_key,
    normalise_rating_ttl_days,
    normalise_sab_limit_mbps,
    normalise_service_url,
    normalise_sync_interval,
    normalise_trending_sync_interval,
    service_seed,
)


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
        self._bandwidth_sab_limit_enabled = False
        self._bandwidth_sab_limit_mbps = DEFAULT_SAB_LIMIT_MBPS
        self._trending_sync_interval_minutes = DEFAULT_TRENDING_SYNC_INTERVAL
        self._anime_ids_refresh_days = DEFAULT_ANIME_IDS_REFRESH_DAYS
        self._rating_ttl_days = DEFAULT_RATING_TTL_DAYS
        self._omdb_daily_budget_per_key = DEFAULT_OMDB_DAILY_BUDGET_PER_KEY
        self._findarr_settings = copy.deepcopy(DEFAULT_FINDARR_SETTINGS)
        self._deletarr_settings = copy.deepcopy(DEFAULT_DELETARR_SETTINGS)
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
        trending_sync_interval_minutes: int = DEFAULT_TRENDING_SYNC_INTERVAL,
        anime_ids_refresh_days: int = DEFAULT_ANIME_IDS_REFRESH_DAYS,
        rating_ttl_days: int = DEFAULT_RATING_TTL_DAYS,
        omdb_daily_budget_per_key: int = DEFAULT_OMDB_DAILY_BUDGET_PER_KEY,
        deletarr_movies_path: str = DEFAULT_DELETARR_SETTINGS["movies_path"],
        deletarr_tv_path: str = DEFAULT_DELETARR_SETTINGS["tv_path"],
        deletarr_use_arr_source: bool = DEFAULT_DELETARR_SETTINGS["use_arr_source"],
    ) -> None:
        """Load persisted settings, or seed from the supplied defaults.

        On first run (no store file) the supplied environment-derived values are
        written to disk; thereafter the persisted file is authoritative. The set
        of synced lists is not seeded from the environment — it starts empty and
        is populated from the dashboard (discovered lists or added by URL).
        """
        with self._lock:
            deletarr_seed = {
                "movies_path": deletarr_movies_path,
                "tv_path": deletarr_tv_path,
                "use_arr_source": deletarr_use_arr_source,
            }
            if self._path.exists():
                self._load_locked(
                    seed_services=services or {}, seed_deletarr=deletarr_seed
                )
                self._log.info("loaded persisted settings")
            else:
                self._client_id = client_id
                self._client_secret = client_secret
                self._lists = []
                self._status_check_interval_seconds = normalise_interval(
                    status_check_interval_seconds
                )
                self._sync_interval_minutes = normalise_sync_interval(
                    sync_interval_minutes
                )
                self._auto_remove_when_available = bool(auto_remove_when_available)
                self._bandwidth_control_enabled = bool(bandwidth_control_enabled)
                self._bandwidth_check_interval_seconds = normalise_bandwidth_interval(
                    bandwidth_check_interval_seconds
                )
                self._trending_sync_interval_minutes = normalise_trending_sync_interval(
                    trending_sync_interval_minutes
                )
                self._anime_ids_refresh_days = normalise_anime_ids_refresh_days(
                    anime_ids_refresh_days
                )
                self._rating_ttl_days = normalise_rating_ttl_days(rating_ttl_days)
                self._omdb_daily_budget_per_key = normalise_omdb_daily_budget_per_key(
                    omdb_daily_budget_per_key
                )
                self._findarr_settings = normalise_findarr_settings()
                self._deletarr_settings = normalise_deletarr_settings(
                    deletarr_seed,
                    movies_path=deletarr_movies_path,
                    tv_path=deletarr_tv_path,
                    use_arr_source=deletarr_use_arr_source,
                )
                for desc in SERVICES:
                    self._services[desc.name] = service_seed(
                        desc, (services or {}).get(desc.name)
                    )
                self._save_locked()
                self._log.info("seeded settings from environment")

    def _load_locked(
        self,
        seed_services: dict[str, dict[str, str]] | None = None,
        seed_deletarr: dict[str, Any] | None = None,
    ) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        seed_deletarr = seed_deletarr or copy.deepcopy(DEFAULT_DELETARR_SETTINGS)
        trakt = data.get("trakt") or {}
        self._client_id = trakt.get("client_id", "")
        self._client_secret = trakt.get("client_secret", "")
        self._status_check_interval_seconds = normalise_interval(
            data.get("status_check_interval_seconds", 60)
        )
        self._sync_interval_minutes = normalise_sync_interval(
            data.get("sync_interval_minutes", 15)
        )
        migrated_bandwidth = (
            "bandwidth_control_enabled" not in data
            or "bandwidth_check_interval_seconds" not in data
        )
        self._bandwidth_control_enabled = bool(
            data.get("bandwidth_control_enabled", False)
        )
        self._bandwidth_check_interval_seconds = normalise_bandwidth_interval(
            data.get("bandwidth_check_interval_seconds", 15)
        )
        migrated_sab_limit = (
            "bandwidth_sab_limit_enabled" not in data
            or "bandwidth_sab_limit_mbps" not in data
        )
        self._bandwidth_sab_limit_enabled = bool(
            data.get("bandwidth_sab_limit_enabled", False)
        )
        self._bandwidth_sab_limit_mbps = normalise_sab_limit_mbps(
            data.get("bandwidth_sab_limit_mbps", DEFAULT_SAB_LIMIT_MBPS)
        )
        migrated_trending = "trending_sync_interval_minutes" not in data
        self._trending_sync_interval_minutes = normalise_trending_sync_interval(
            data.get("trending_sync_interval_minutes", DEFAULT_TRENDING_SYNC_INTERVAL)
        )
        migrated_anime_ids = "anime_ids_refresh_days" not in data
        self._anime_ids_refresh_days = normalise_anime_ids_refresh_days(
            data.get("anime_ids_refresh_days", DEFAULT_ANIME_IDS_REFRESH_DAYS)
        )
        migrated_rating_ttl = "rating_ttl_days" not in data
        self._rating_ttl_days = normalise_rating_ttl_days(
            data.get("rating_ttl_days", DEFAULT_RATING_TTL_DAYS)
        )
        migrated_omdb_budget = "omdb_daily_budget_per_key" not in data
        self._omdb_daily_budget_per_key = normalise_omdb_daily_budget_per_key(
            data.get("omdb_daily_budget_per_key", DEFAULT_OMDB_DAILY_BUDGET_PER_KEY)
        )
        migrated_findarr = "findarr" not in data
        self._findarr_settings = normalise_findarr_settings(data.get("findarr"))
        migrated_deletarr = "deletarr" not in data
        self._deletarr_settings = normalise_deletarr_settings(
            data.get("deletarr"),
            movies_path=seed_deletarr.get(
                "movies_path", DEFAULT_DELETARR_SETTINGS["movies_path"]
            ),
            tv_path=seed_deletarr.get("tv_path", DEFAULT_DELETARR_SETTINGS["tv_path"]),
            use_arr_source=seed_deletarr.get(
                "use_arr_source", DEFAULT_DELETARR_SETTINGS["use_arr_source"]
            ),
        )
        # Migration: the flag was historically persisted as ``auto_remove_on_import``
        # (remove when Radarr/Sonarr imported the title). It now means "remove from
        # Trakt once Seer reports the item available". An existing store is read
        # under the legacy key so the user's choice carries over; when only the legacy
        # key is present the store is re-saved under the new key on load (see the
        # ``migrated_auto_remove`` save trigger below).
        migrated_auto_remove = (
            "auto_remove_when_available" not in data and "auto_remove_on_import" in data
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
        # Load stored services; one-time migrations backfill from the env seed:
        # whole services a pre-existing (older) store file does not yet contain,
        # and individual fields added to a service after the store was written
        # (e.g. the OMDb rotation keys). A field the user cleared is present but
        # empty and is therefore never overwritten.
        stored_services = data.get("services") or {}
        seed = seed_services or {}
        backfilled = False
        fields_backfilled = False
        for desc in SERVICES:
            name = desc.name
            if name in stored_services:
                entry = stored_services[name]
                seed_entry = seed.get(name) or {}
                values: dict[str, str] = {}
                for field in desc.fields:
                    if field in entry:
                        values[field] = entry.get(field) or ""
                    else:
                        values[field] = (seed_entry.get(field) or "").strip()
                        fields_backfilled = True
                self._services[name] = values
            else:
                self._services[name] = service_seed(desc, seed.get(name))
                backfilled = True
        if (
            backfilled
            or fields_backfilled
            or migrated_auto_remove
            or migrated_bandwidth
            or migrated_sab_limit
            or migrated_trending
            or migrated_anime_ids
            or migrated_rating_ttl
            or migrated_omdb_budget
            or migrated_findarr
            or migrated_deletarr
        ):
            self._save_locked()
            self._log.info(
                "persisted store migration (services_backfilled=%s "
                "service_fields_backfilled=%s auto_remove_key_migrated=%s "
                "bandwidth_keys_migrated=%s sab_limit_keys_migrated=%s "
                "trending_key_migrated=%s "
                "anime_ids_key_migrated=%s rating_ttl_key_migrated=%s "
                "omdb_budget_key_migrated=%s findarr_keys_migrated=%s "
                "deletarr_keys_migrated=%s)",
                backfilled,
                fields_backfilled,
                migrated_auto_remove,
                migrated_bandwidth,
                migrated_sab_limit,
                migrated_trending,
                migrated_anime_ids,
                migrated_rating_ttl,
                migrated_omdb_budget,
                migrated_findarr,
                migrated_deletarr,
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
            "bandwidth_sab_limit_enabled": self._bandwidth_sab_limit_enabled,
            "bandwidth_sab_limit_mbps": self._bandwidth_sab_limit_mbps,
            "trending_sync_interval_minutes": self._trending_sync_interval_minutes,
            "anime_ids_refresh_days": self._anime_ids_refresh_days,
            "rating_ttl_days": self._rating_ttl_days,
            "omdb_daily_budget_per_key": self._omdb_daily_budget_per_key,
            "findarr": self._findarr_settings,
            "deletarr": self._deletarr_settings,
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
        seconds = normalise_interval(seconds)
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
        minutes = normalise_sync_interval(minutes)
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
        seconds = normalise_bandwidth_interval(seconds)
        with self._lock:
            self._bandwidth_check_interval_seconds = seconds
            self._save_locked()
            self._log.info("updated bandwidth check interval to %s seconds", seconds)
            return seconds

    def bandwidth_sab_limit_enabled(self) -> bool:
        """Whether Bandwidth-Controllarr caps SABnzbd's download speed."""
        with self._lock:
            return self._bandwidth_sab_limit_enabled

    def update_bandwidth_sab_limit_enabled(self, enabled: bool) -> bool:
        """Enable or disable the SABnzbd download limiter; returns the new value."""
        enabled = bool(enabled)
        with self._lock:
            self._bandwidth_sab_limit_enabled = enabled
            self._save_locked()
            self._log.info("updated SABnzbd download limiter enabled to %s", enabled)
            return enabled

    def bandwidth_sab_limit_mbps(self) -> float:
        """Return the configured SABnzbd download limit in MB/s."""
        with self._lock:
            return self._bandwidth_sab_limit_mbps

    def update_bandwidth_sab_limit_mbps(self, mbps: float) -> float:
        """Update the SABnzbd download limit; values clamp to 0.1–1024 MB/s."""
        mbps = normalise_sab_limit_mbps(mbps)
        with self._lock:
            self._bandwidth_sab_limit_mbps = mbps
            self._save_locked()
            self._log.info("updated SABnzbd download limit to %s MB/s", mbps)
            return mbps

    # ---- trending sync interval ----

    def trending_sync_interval_minutes(self) -> int:
        """Return the configured trending-sync interval in minutes."""
        with self._lock:
            return self._trending_sync_interval_minutes

    def update_trending_sync_interval(self, minutes: int) -> int:
        """Update the trending-sync interval; invalid values fall back to 60 min."""
        minutes = normalise_trending_sync_interval(minutes)
        with self._lock:
            self._trending_sync_interval_minutes = minutes
            self._save_locked()
            self._log.info("updated trending sync interval to %s minutes", minutes)
            return minutes

    # ---- anime id-mapping refresh ----

    def anime_ids_refresh_days(self) -> int:
        """Return the configured anime id-mapping refresh cadence in days."""
        with self._lock:
            return self._anime_ids_refresh_days

    def update_anime_ids_refresh_days(self, days: int) -> int:
        """Update the anime id-mapping cadence; invalid values fall back to 3 days."""
        days = normalise_anime_ids_refresh_days(days)
        with self._lock:
            self._anime_ids_refresh_days = days
            self._save_locked()
            self._log.info("updated anime id-mapping refresh to %s days", days)
            return days

    # ---- IMDb-rating refresh window ----

    def rating_ttl_days(self) -> int:
        """Return the configured IMDb-rating refresh window in days."""
        with self._lock:
            return self._rating_ttl_days

    def update_rating_ttl_days(self, days: int) -> int:
        """Update the rating refresh window; invalid values fall back to 7 days."""
        days = normalise_rating_ttl_days(days)
        with self._lock:
            self._rating_ttl_days = days
            self._save_locked()
            self._log.info("updated rating refresh window to %s days", days)
            return days

    def omdb_daily_budget_per_key(self) -> int:
        """Return the per-key daily OMDb request budget for the backfill."""
        with self._lock:
            return self._omdb_daily_budget_per_key

    def update_omdb_daily_budget_per_key(self, budget: int) -> int:
        """Update the per-key OMDb budget; values clamp to the 100-1000 bounds."""
        budget = normalise_omdb_daily_budget_per_key(budget)
        with self._lock:
            self._omdb_daily_budget_per_key = budget
            self._save_locked()
            self._log.info("updated OMDb daily budget to %s per key", budget)
            return budget

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
            self._findarr_settings = normalise_findarr_settings(merged)
            self._save_locked()
            self._log.info("updated Findarr settings")
            return copy.deepcopy(self._findarr_settings)

    # ---- Deletarr ----

    def deletarr_settings(self) -> dict[str, Any]:
        """Return a copy of the persisted Deletarr settings."""
        with self._lock:
            return dict(self._deletarr_settings)

    def update_deletarr_settings(
        self,
        *,
        movies_path: str | None = None,
        tv_path: str | None = None,
        use_arr_source: bool | None = None,
    ) -> dict[str, Any]:
        """Update Deletarr settings; ``None`` leaves a field unchanged."""
        with self._lock:
            merged = dict(self._deletarr_settings)
            if movies_path is not None:
                merged["movies_path"] = movies_path
            if tv_path is not None:
                merged["tv_path"] = tv_path
            if use_arr_source is not None:
                merged["use_arr_source"] = use_arr_source
            self._deletarr_settings = normalise_deletarr_settings(
                merged,
                movies_path=self._deletarr_settings["movies_path"],
                tv_path=self._deletarr_settings["tv_path"],
                use_arr_source=self._deletarr_settings["use_arr_source"],
            )
            self._save_locked()
            self._log.info("updated Deletarr settings")
            return dict(self._deletarr_settings)

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
            self._lists.append(TrackedList(owner_user=owner_user, slug=slug, name=name))
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
        keyword (e.g. ``username`` for a URL/API-key service) is ignored. URLs
        are normalised so browser deep-links do not end up with unsupported
        schemes such as ``seer:5055``.
        """
        desc = BY_NAME[name]
        with self._lock:
            entry = self._services[name]
            for field in desc.fields:
                value = fields.get(field)
                if value is not None:
                    if field == "url":
                        value = normalise_service_url(value)
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
                "bandwidth_sab_limit_enabled": self._bandwidth_sab_limit_enabled,
                "bandwidth_sab_limit_mbps": self._bandwidth_sab_limit_mbps,
                "trending_sync_interval_minutes": self._trending_sync_interval_minutes,
                "anime_ids_refresh_days": self._anime_ids_refresh_days,
                "rating_ttl_days": self._rating_ttl_days,
                "omdb_daily_budget_per_key": self._omdb_daily_budget_per_key,
                "findarr": copy.deepcopy(self._findarr_settings),
                "deletarr": dict(self._deletarr_settings),
                "lists": [item.to_dict() for item in self._lists],
                "services": self.masked_services(),
            }
