"""Tests for Cleanarr settings normalisation and persistence."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from core.settings_modules import CleanarrIgnoreListFull
from core.settings_normalisers import (
    CLEANARR_IGNORE_MAX,
    DEFAULT_CLEANARR_SETTINGS,
    is_strictly_under,
    normalise_cleanarr_settings,
)
from core.settings_store import SettingsStore


def test_defaults_are_safe() -> None:
    assert normalise_cleanarr_settings() == DEFAULT_CLEANARR_SETTINGS
    assert DEFAULT_CLEANARR_SETTINGS["enabled"] is False
    assert DEFAULT_CLEANARR_SETTINGS["dry_run"] is True
    assert DEFAULT_CLEANARR_SETTINGS["queue"]["enabled"] is True
    assert DEFAULT_CLEANARR_SETTINGS["malware"]["enabled"] is False
    assert DEFAULT_CLEANARR_SETTINGS["orphans"]["enabled"] is False
    assert len(DEFAULT_CLEANARR_SETTINGS["malware"]["extensions"]) == 18


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("interval_minutes", 1, 5),
        ("interval_minutes", 99999, 1440),
        ("interval_minutes", "bad", 10),
        ("max_strikes", 1, 3),
        ("max_strikes", 99, 20),
        ("max_strikes", None, 3),
        ("max_removals_per_run", 0, 1),
        ("max_removals_per_run", 51, 50),
        ("max_removals_per_run", "7", 7),
    ],
)
def test_top_level_numbers_are_bounded(key: str, value: object, expected: int) -> None:
    assert normalise_cleanarr_settings({key: value})[key] == expected


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("min_age_hours", 0, 1),
        ("min_age_hours", 10_000, 720),
        ("min_age_hours", [], 24),
        ("quarantine_retention_days", 0, 1),
        ("quarantine_retention_days", 400, 365),
        ("quarantine_retention_days", "x", 14),
    ],
)
def test_orphan_numbers_are_bounded(key: str, value: object, expected: int) -> None:
    settings = normalise_cleanarr_settings({"orphans": {key: value}})
    assert settings["orphans"][key] == expected


def test_bad_section_types_fall_back_to_defaults() -> None:
    settings = normalise_cleanarr_settings(
        {
            "queue": "nope",
            "malware": 3,
            "orphans": None,
            "paths": [],
            "apps": "x",
            "ignore": 1,
        }
    )
    assert settings == DEFAULT_CLEANARR_SETTINGS


def test_booleans_are_coerced() -> None:
    settings = normalise_cleanarr_settings(
        {
            "enabled": 1,
            "dry_run": 0,
            "queue": {"enabled": 0},
            "malware": {"enabled": 1},
            "orphans": {"enabled": "yes"},
            "apps": {"sonarr": {"enabled": 0}, "radarr": "bad"},
        }
    )
    assert settings["enabled"] is True
    assert settings["dry_run"] is False
    assert settings["queue"]["enabled"] is False
    assert settings["malware"]["enabled"] is True
    assert settings["orphans"]["enabled"] is True
    assert settings["apps"] == {
        "sonarr": {"enabled": False},
        "radarr": {"enabled": True},
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("include", "include"),
        ("exclude", "exclude"),
        ("regex", "exclude"),
        (None, "exclude"),
    ],
)
def test_pattern_mode_is_validated(value: object, expected: str) -> None:
    settings = normalise_cleanarr_settings({"queue": {"pattern_mode": value}})
    assert settings["queue"]["pattern_mode"] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([" Sample ", "sample", "", 3, "x" * 201, "Other"], ["Sample", "Other"]),
        ([], []),
        ("not a list", DEFAULT_CLEANARR_SETTINGS["queue"]["patterns"]),
        ([f"p{index}" for index in range(60)], [f"p{index}" for index in range(50)]),
    ],
)
def test_patterns_are_cleaned(value: object, expected: list[str]) -> None:
    settings = normalise_cleanarr_settings({"queue": {"patterns": value}})
    assert settings["queue"]["patterns"] == expected


def test_missing_patterns_keep_the_seeds() -> None:
    settings = normalise_cleanarr_settings({"queue": {"enabled": True}})
    assert (
        settings["queue"]["patterns"] == DEFAULT_CLEANARR_SETTINGS["queue"]["patterns"]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([".EXE", "scr", " .lnk ", ".exe", 7, ".bad-ext", ".toolongextension"],
         [".exe", ".scr", ".lnk"]),
        ([], DEFAULT_CLEANARR_SETTINGS["malware"]["extensions"]),
        (["!!"], DEFAULT_CLEANARR_SETTINGS["malware"]["extensions"]),
        (".exe", DEFAULT_CLEANARR_SETTINGS["malware"]["extensions"]),
        ([f".e{index}" for index in range(120)], [f".e{index}" for index in range(100)]),
    ],
)  # fmt: skip
def test_extensions_are_cleaned_and_never_empty(
    value: object, expected: list[str]
) -> None:
    settings = normalise_cleanarr_settings({"malware": {"extensions": value}})
    assert settings["malware"]["extensions"] == expected


def test_ignore_lists_are_cleaned() -> None:
    settings = normalise_cleanarr_settings(
        {
            "ignore": {
                "download_ids": ["SABnzbd_nzo_1", " SABnzbd_nzo_1 ", None, ""],
                "categories": "tv",
                "title_contains": [f"t{index}" for index in range(600)],
            }
        }
    )
    assert settings["ignore"]["download_ids"] == ["SABnzbd_nzo_1"]
    assert settings["ignore"]["categories"] == []
    assert len(settings["ignore"]["title_contains"]) == 500


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (
            {"completed_root": "/data/done/", "quarantine_dir": "/data/done/q/"},
            {"completed_root": "/data/done", "quarantine_dir": "/data/done/q"},
        ),
        (
            {"completed_root": "/data/done", "quarantine_dir": "/elsewhere/q"},
            {
                "completed_root": "/data/done",
                "quarantine_dir": "/data/done/_cleanarr_quarantine",
            },
        ),
        (
            {"completed_root": "/data/done", "quarantine_dir": "/data/done"},
            {
                "completed_root": "/data/done",
                "quarantine_dir": "/data/done/_cleanarr_quarantine",
            },
        ),
        (
            {"completed_root": "relative/path", "quarantine_dir": 5},
            DEFAULT_CLEANARR_SETTINGS["paths"],
        ),
        (
            {"completed_root": "//data//x/../done", "quarantine_dir": "/" + "a" * 2000},
            {
                "completed_root": "/data/done",
                "quarantine_dir": "/data/done/_cleanarr_quarantine",
            },
        ),
        (
            {"completed_root": "/", "quarantine_dir": "/q"},
            {"completed_root": "/", "quarantine_dir": "/q"},
        ),
    ],
)
def test_paths_are_absolute_and_quarantine_is_under_root(
    paths: dict[str, Any], expected: dict[str, str]
) -> None:
    assert normalise_cleanarr_settings({"paths": paths})["paths"] == expected


@pytest.mark.parametrize(
    ("path", "root", "expected"),
    [
        ("/a/b", "/a", True),
        ("/a", "/a", False),
        ("/ab", "/a", False),
        ("/x", "/", True),
    ],
)
def test_is_strictly_under(path: str, root: str, expected: bool) -> None:
    assert is_strictly_under(path, root) is expected


def _store(tmp_path) -> tuple[SettingsStore, Any]:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    return store, path


def test_store_deep_merges_partial_updates(tmp_path) -> None:
    store, path = _store(tmp_path)
    assert store.cleanarr_settings() == DEFAULT_CLEANARR_SETTINGS
    assert store.cleanarr_interval_minutes() == 10

    updated = store.update_cleanarr_settings(
        {
            "enabled": True,
            "dry_run": None,
            "interval_minutes": 30,
            "queue": {"pattern_mode": "include", "patterns": None},
            "orphans": "bad",
            "apps": {"radarr": {"enabled": False}, "sonarr": None},
            "unknown": 1,
        }
    )
    assert updated["enabled"] is True
    assert updated["dry_run"] is True
    assert updated["interval_minutes"] == 30
    assert updated["queue"]["pattern_mode"] == "include"
    assert (
        updated["queue"]["patterns"] == DEFAULT_CLEANARR_SETTINGS["queue"]["patterns"]
    )
    assert updated["queue"]["enabled"] is True
    assert updated["apps"] == {
        "sonarr": {"enabled": True},
        "radarr": {"enabled": False},
    }
    assert updated["orphans"] == DEFAULT_CLEANARR_SETTINGS["orphans"]
    assert "unknown" not in updated
    assert json.loads(path.read_text())["cleanarr"]["interval_minutes"] == 30

    # Returned copies never alias the stored settings.
    updated["queue"]["patterns"].append("mutated")
    assert "mutated" not in store.cleanarr_settings()["queue"]["patterns"]

    # An "apps" value that is not a dict leaves the per-app switches alone.
    assert store.update_cleanarr_settings({"apps": "x"})["apps"]["radarr"] == {
        "enabled": False
    }


def test_store_adds_ignored_download_once(tmp_path) -> None:
    store, path = _store(tmp_path)
    store.cleanarr_add_ignored_download("SABnzbd_nzo_a")
    settings = store.cleanarr_add_ignored_download("SABnzbd_nzo_a")
    assert settings["ignore"]["download_ids"] == ["SABnzbd_nzo_a"]
    persisted = json.loads(path.read_text())["cleanarr"]
    assert persisted["ignore"]["download_ids"] == ["SABnzbd_nzo_a"]


def test_store_refuses_an_ignore_the_full_list_would_drop(tmp_path) -> None:
    store, path = _store(tmp_path)
    full = [f"SABnzbd_nzo_{index}" for index in range(CLEANARR_IGNORE_MAX)]
    store.update_cleanarr_settings({"ignore": {"download_ids": full}})
    before = path.read_text()

    with pytest.raises(CleanarrIgnoreListFull, match="already holds 500"):
        store.cleanarr_add_ignored_download("SABnzbd_nzo_new")
    assert store.cleanarr_settings()["ignore"]["download_ids"] == full
    assert path.read_text() == before

    # Re-adding an id that is already listed stays an idempotent success.
    settings = store.cleanarr_add_ignored_download(full[-1])
    assert settings["ignore"]["download_ids"] == full


def test_store_accepts_the_last_free_ignore_slot(tmp_path) -> None:
    store, _path = _store(tmp_path)
    almost = [f"SABnzbd_nzo_{index}" for index in range(CLEANARR_IGNORE_MAX - 1)]
    store.update_cleanarr_settings({"ignore": {"download_ids": almost}})
    settings = store.cleanarr_add_ignored_download("SABnzbd_nzo_last")
    assert settings["ignore"]["download_ids"][-1] == "SABnzbd_nzo_last"
    assert len(settings["ignore"]["download_ids"]) == CLEANARR_IGNORE_MAX


def test_store_migrates_a_file_without_cleanarr(tmp_path) -> None:
    store, path = _store(tmp_path)
    store.update_cleanarr_settings({"enabled": True})
    data = json.loads(path.read_text())
    del data["cleanarr"]
    path.write_text(json.dumps(data))

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="y")
    assert reopened.cleanarr_settings() == DEFAULT_CLEANARR_SETTINGS
    assert json.loads(path.read_text())["cleanarr"] == DEFAULT_CLEANARR_SETTINGS
    masked = reopened.masked()
    assert masked["cleanarr"] == DEFAULT_CLEANARR_SETTINGS


def test_store_reloads_persisted_cleanarr(tmp_path) -> None:
    store, path = _store(tmp_path)
    store.update_cleanarr_settings({"max_strikes": 5})
    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="y")
    expected = copy.deepcopy(DEFAULT_CLEANARR_SETTINGS)
    expected["max_strikes"] = 5
    assert reopened.cleanarr_settings() == expected
