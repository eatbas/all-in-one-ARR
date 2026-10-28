"""Per-module settings sections of :class:`core.settings_store.SettingsStore`.

Findarr, Deletarr, Languagarr and Cleanarr each own a small getter/updater pair over their
own settings dict. They live in this mixin so ``settings_store.py`` keeps the
shared concerns (load/seed/persist, Trakt, services, lists, masking) and does not
grow with every module. The host class owns the lock, the logger, the per-module
dicts and ``_save_locked``.
"""

from __future__ import annotations

import copy
import logging
import threading
from typing import TYPE_CHECKING, Any

from core.settings_normalisers import (
    CLEANARR_IGNORE_MAX,
    normalise_cleanarr_settings,
    normalise_deletarr_settings,
    normalise_findarr_settings,
    normalise_languagarr_settings,
)


class ModuleSettingsMixin:
    """Findarr / Deletarr / Languagarr / Cleanarr settings accessors for ``SettingsStore``."""

    _lock: threading.RLock
    _log: logging.Logger
    _findarr_settings: dict[str, Any]
    _deletarr_settings: dict[str, Any]
    _languagarr_settings: dict[str, Any]
    _cleanarr_settings: dict[str, Any]

    if TYPE_CHECKING:  # pragma: no cover

        def _save_locked(self) -> None: ...

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

    # ---- Languagarr ----

    def languagarr_settings(self) -> dict[str, Any]:
        """Return a copy of the persisted Languagarr settings."""
        with self._lock:
            return copy.deepcopy(self._languagarr_settings)

    def languagarr_interval_minutes(self) -> int:
        """Return the Languagarr scheduled-worker interval in minutes."""
        with self._lock:
            return int(self._languagarr_settings["interval_minutes"])

    def update_languagarr_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge ``updates`` into Languagarr settings; ``None`` leaves a field unchanged."""
        with self._lock:
            merged = copy.deepcopy(self._languagarr_settings)
            for key, value in updates.items():
                if key in merged and value is not None:
                    merged[key] = value
            self._languagarr_settings = normalise_languagarr_settings(merged)
            self._save_locked()
            self._log.info("updated Languagarr settings")
            return copy.deepcopy(self._languagarr_settings)

    # ---- Cleanarr ----

    # Nested Cleanarr sections merged key by key, so a partial update (for
    # example only ``queue.enabled``) keeps the section's other values.
    _CLEANARR_SECTIONS = ("queue", "malware", "orphans", "paths", "ignore")

    def cleanarr_settings(self) -> dict[str, Any]:
        """Return a copy of the persisted Cleanarr settings."""
        with self._lock:
            return copy.deepcopy(self._cleanarr_settings)

    def cleanarr_interval_minutes(self) -> int:
        """Return the Cleanarr scheduler interval in minutes."""
        with self._lock:
            return int(self._cleanarr_settings["interval_minutes"])

    def update_cleanarr_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Deep-merge ``updates`` into Cleanarr settings; ``None`` leaves a field unchanged."""
        with self._lock:
            merged = copy.deepcopy(self._cleanarr_settings)
            for key in (
                "enabled",
                "dry_run",
                "interval_minutes",
                "max_strikes",
                "max_removals_per_run",
            ):
                if updates.get(key) is not None:
                    merged[key] = updates[key]
            for section in self._CLEANARR_SECTIONS:
                _merge_section(merged[section], updates.get(section))
            app_updates = updates.get("apps")
            if isinstance(app_updates, dict):
                for app_name in ("sonarr", "radarr"):
                    _merge_section(merged["apps"][app_name], app_updates.get(app_name))
            self._cleanarr_settings = normalise_cleanarr_settings(merged)
            self._save_locked()
            self._log.info("updated Cleanarr settings")
            return copy.deepcopy(self._cleanarr_settings)

    def cleanarr_add_ignored_download(self, download_id: str) -> dict[str, Any]:
        """Add ``download_id`` to Cleanarr's ignore list (once) and persist.

        Raises :class:`CleanarrIgnoreListFull` (and changes nothing) when the
        id cannot be stored.
        """
        with self._lock:
            self._cleanarr_settings = with_ignored_download(
                self._cleanarr_settings, download_id
            )
            self._save_locked()
            self._log.info("added a download to the Cleanarr ignore list")
            return copy.deepcopy(self._cleanarr_settings)


class CleanarrIgnoreListFull(ValueError):
    """The download id cannot be added: the ignore list is at its limit."""

    def __init__(self) -> None:
        super().__init__(
            f"The ignore list already holds {CLEANARR_IGNORE_MAX} download IDs. "
            "Remove some in Settings before ignoring another download."
        )


def with_ignored_download(settings: dict[str, Any], download_id: str) -> dict[str, Any]:
    """Return normalised Cleanarr settings with ``download_id`` ignored.

    Adding an id already present is a no-op. Raises
    :class:`CleanarrIgnoreListFull` when normalisation would drop the new id
    (the list is full), so a caller never reports an ignore that did not stick.
    """
    merged = copy.deepcopy(settings)
    ignored = merged["ignore"]["download_ids"]
    if download_id not in ignored:
        ignored.append(download_id)
    normalised = normalise_cleanarr_settings(merged)
    if download_id not in normalised["ignore"]["download_ids"]:
        raise CleanarrIgnoreListFull()
    return normalised


def _merge_section(target: dict[str, Any], updates: Any) -> None:
    """Copy the non-``None`` values of ``updates`` (when a dict) into ``target``."""
    if not isinstance(updates, dict):
        return
    for key, value in updates.items():
        if value is not None:
            target[key] = value
