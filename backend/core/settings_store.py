"""Persistent, runtime-mutable application settings.

Trakt connection details (client id/secret/user) and the set of synced lists are
managed from the dashboard rather than static environment variables, so they live
in a small JSON store. The store is **seeded** from the environment on first run
and then becomes the source of truth; subsequent environment changes are ignored
(the UI owns these settings).

Secrets are persisted with ``0600`` permissions and never returned in clear by
:meth:`SettingsStore.masked`. The store is thread-safe so the scheduler thread and
the request handlers can share it within one Uvicorn worker.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.logging import get_logger

# URL + API-key services managed from the Settings page (besides Trakt).
SERVICE_NAMES = ("jellyseerr", "sonarr", "radarr")


def _service_seed(seed: dict[str, str] | None) -> dict[str, str]:
    """Normalise a seed entry (or ``None``) into a ``{url, api_key}`` dict."""
    seed = seed or {}
    return {
        "url": (seed.get("url") or "").strip(),
        "api_key": (seed.get("api_key") or "").strip(),
    }


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
        self._user = "me"
        self._lists: list[TrackedList] = []
        self._services: dict[str, dict[str, str]] = {
            name: {"url": "", "api_key": ""} for name in SERVICE_NAMES
        }

    # ---- load / seed / persist ----

    def load_or_seed(
        self,
        *,
        client_id: str,
        client_secret: str,
        user: str,
        lists: list[TrackedList],
        services: dict[str, dict[str, str]] | None = None,
    ) -> None:
        """Load persisted settings, or seed from the supplied defaults.

        On first run (no store file) the supplied environment-derived values are
        written to disk; thereafter the persisted file is authoritative.
        """
        with self._lock:
            if self._path.exists():
                self._load_locked(seed_services=services or {})
                self._log.info("loaded persisted settings")
            else:
                self._client_id = client_id
                self._client_secret = client_secret
                self._user = user or "me"
                self._lists = list(lists)
                for name in SERVICE_NAMES:
                    self._services[name] = _service_seed((services or {}).get(name))
                self._save_locked()
                self._log.info("seeded settings from environment")

    def _load_locked(self, seed_services: dict[str, dict[str, str]] | None = None) -> None:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        trakt = data.get("trakt") or {}
        self._client_id = trakt.get("client_id", "")
        self._client_secret = trakt.get("client_secret", "")
        self._user = trakt.get("user") or "me"
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
        for name in SERVICE_NAMES:
            if name in stored_services:
                entry = stored_services[name]
                self._services[name] = {
                    "url": entry.get("url", ""),
                    "api_key": entry.get("api_key", ""),
                }
            else:
                self._services[name] = _service_seed(seed.get(name))
                backfilled = True
        if backfilled:
            self._save_locked()
            self._log.info("backfilled new service connections from environment")

    def _save_locked(self) -> None:
        payload = {
            "trakt": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "user": self._user,
            },
            "lists": [item.to_dict() for item in self._lists],
            "services": self._services,
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.chmod(self._path, 0o600)

    # ---- Trakt credentials ----

    def trakt_credentials(self) -> tuple[str, str, str]:
        """Return ``(client_id, client_secret, user)``."""
        with self._lock:
            return (self._client_id, self._client_secret, self._user)

    def update_trakt_credentials(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        user: str | None = None,
    ) -> None:
        """Update the Trakt credentials; ``None`` leaves a field unchanged."""
        with self._lock:
            if client_id is not None:
                self._client_id = client_id.strip()
            if client_secret is not None:
                self._client_secret = client_secret.strip()
            if user is not None:
                self._user = user.strip() or "me"
            self._save_locked()
            self._log.info("updated Trakt credentials")

    # ---- tracked lists ----

    def tracked_lists(self) -> list[TrackedList]:
        """Return the lists selected for syncing (a copy)."""
        with self._lock:
            return list(self._lists)

    def owner_for(self, slug: str) -> str:
        """Return the owner of a tracked list by slug, defaulting to the user."""
        with self._lock:
            for item in self._lists:
                if item.slug == slug:
                    return item.owner_user
            return self._user

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

    # ---- service connections (jellyseerr / sonarr / radarr) ----

    def service_connection(self, name: str) -> tuple[str, str]:
        """Return ``(url, api_key)`` for a service. Raises ``KeyError`` if unknown."""
        with self._lock:
            entry = self._services[name]
            return (entry["url"], entry["api_key"])

    def update_service_connection(
        self, name: str, *, url: str | None = None, api_key: str | None = None
    ) -> None:
        """Update a service's URL/API key; ``None`` leaves a field unchanged."""
        with self._lock:
            entry = self._services[name]
            if url is not None:
                entry["url"] = url.strip()
            if api_key is not None:
                entry["api_key"] = api_key.strip()
            self._save_locked()
            self._log.info("updated %s connection", name)

    def masked_services(self) -> dict[str, dict[str, Any]]:
        """Return a response-safe view of services: ``{name: {url, api_key_set}}``."""
        with self._lock:
            return {
                name: {
                    "url": entry["url"],
                    "api_key_set": bool(entry["api_key"]),
                }
                for name, entry in self._services.items()
            }

    # ---- masking ----

    def masked(self) -> dict[str, Any]:
        """Return a log/response-safe view: secrets reduced to hints/booleans."""
        with self._lock:
            return {
                "client_id_hint": self._client_id[-4:] if self._client_id else "",
                "client_id_set": bool(self._client_id),
                "client_secret_set": bool(self._client_secret),
                "user": self._user,
                "lists": [item.to_dict() for item in self._lists],
                "services": self.masked_services(),
            }
