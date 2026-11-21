"""Tests for Remindarr settings normalisation and persistence."""

from __future__ import annotations

import json

import pytest

from core.settings_normalisers import (
    DEFAULT_REMINDARR_SETTINGS,
    REMINDARR_TAG_IDS_MAX,
    normalise_remindarr_settings,
)
from core.settings_store import SettingsStore


def test_defaults_are_safe() -> None:
    assert normalise_remindarr_settings() == DEFAULT_REMINDARR_SETTINGS
    assert DEFAULT_REMINDARR_SETTINGS == {
        "enabled": False,
        "interval_minutes": 60,
        "tag_ids": [],
        "monitored_only": True,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 15), (14, 15), (15, 15), (1440, 1440), (99999, 1440), ("bad", 60), (None, 60)],
)
def test_interval_is_bounded(value: object, expected: int) -> None:
    assert normalise_remindarr_settings({"interval_minutes": value})[
        "interval_minutes"
    ] == (expected)


def test_tag_ids_are_unique_positive_ints_in_order() -> None:
    raw = [3, 1, 3, 0, -2, True, "4", 2.0, None, 7, 1]
    assert normalise_remindarr_settings({"tag_ids": raw})["tag_ids"] == [3, 1, 7]


@pytest.mark.parametrize("value", [None, "1,2", {"1": True}, 5])
def test_non_list_tag_ids_track_nothing(value: object) -> None:
    assert normalise_remindarr_settings({"tag_ids": value})["tag_ids"] == []


def test_tag_ids_are_capped() -> None:
    raw = list(range(1, REMINDARR_TAG_IDS_MAX + 20))
    tag_ids = normalise_remindarr_settings({"tag_ids": raw})["tag_ids"]
    assert tag_ids == list(range(1, REMINDARR_TAG_IDS_MAX + 1))


def test_booleans_are_coerced() -> None:
    settings = normalise_remindarr_settings({"enabled": 1, "monitored_only": 0})
    assert settings["enabled"] is True
    assert settings["monitored_only"] is False


def test_store_seeds_updates_persists_and_migrates(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    assert store.remindarr_settings() == DEFAULT_REMINDARR_SETTINGS
    assert store.remindarr_interval_minutes() == 60
    assert json.loads(path.read_text())["remindarr"] == DEFAULT_REMINDARR_SETTINGS
    assert store.masked()["remindarr"] == DEFAULT_REMINDARR_SETTINGS

    updated = store.update_remindarr_settings(
        {
            "enabled": True,
            "interval_minutes": 120,
            "tag_ids": [4, 4, 2],
            "monitored_only": None,
            "unknown": "ignored",
        }
    )
    assert updated == {
        "enabled": True,
        "interval_minutes": 120,
        "tag_ids": [4, 2],
        "monitored_only": True,
    }
    # The returned copy is detached from the store's state.
    updated["tag_ids"].append(99)
    assert store.remindarr_settings()["tag_ids"] == [4, 2]

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="c", client_secret="s")
    assert reopened.remindarr_settings()["tag_ids"] == [4, 2]
    assert reopened.remindarr_interval_minutes() == 120

    # A store written before Remindarr existed gains the section on load.
    data = json.loads(path.read_text())
    data.pop("remindarr")
    path.write_text(json.dumps(data), encoding="utf-8")
    migrated = SettingsStore(str(path))
    migrated.load_or_seed(client_id="c", client_secret="s")
    assert migrated.remindarr_settings() == DEFAULT_REMINDARR_SETTINGS
    assert json.loads(path.read_text())["remindarr"] == DEFAULT_REMINDARR_SETTINGS


def test_store_normalises_a_corrupt_persisted_section(tmp_path) -> None:
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="c", client_secret="s")
    data = json.loads(path.read_text())
    data["remindarr"] = {"interval_minutes": 5, "tag_ids": ["x", 9], "enabled": "y"}
    path.write_text(json.dumps(data), encoding="utf-8")
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    assert store.remindarr_settings() == {
        "enabled": True,
        "interval_minutes": 15,
        "tag_ids": [9],
        "monitored_only": True,
    }
