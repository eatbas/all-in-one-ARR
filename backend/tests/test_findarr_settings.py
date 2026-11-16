"""Tests for Findarr settings persistence."""

from __future__ import annotations

import pytest

from core.settings_normalisers import normalise_findarr_settings
from core.settings_store import SettingsStore


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Unparseable input (including NaN) disables the queue guard.
        (None, -1),
        ("bad", -1),
        ("2.5", -1),
        ([], -1),
        ({}, -1),
        (float("nan"), -1),
        # Numeric strings and in-range values pass through unchanged.
        ("50", 50),
        (" 7 ", 7),
        (0, 0),
        (100, 100),
        # Floats truncate towards zero before the clamp, so -0.5 becomes 0.
        (2.9, 2),
        (-0.5, 0),
        (100.9, 100),
        # Booleans are ints and convert like them.
        (True, 1),
        (False, 0),
        # Every negative value is the -1 "no guard" sentinel; the cap is 100.
        (-1, -1),
        (-5, -1),
        ("-3", -1),
        (-1.5, -1),
        (101, 100),
        ("250", 100),
    ],
)
def test_findarr_queue_limit_normalisation_matrix(raw: object, expected: int) -> None:
    assert normalise_findarr_settings({"queue_limit": raw})["queue_limit"] == expected


def test_findarr_queue_limit_infinity_is_not_swallowed() -> None:
    # ``int(inf)`` raises OverflowError, which is deliberately not a fallback.
    with pytest.raises(OverflowError):
        normalise_findarr_settings({"queue_limit": float("inf")})


def test_findarr_queue_limit_update_persists_and_reloads(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    assert store.findarr_settings()["queue_limit"] == -1
    assert store.update_findarr_settings({"queue_limit": "40"})["queue_limit"] == 40
    assert store.update_findarr_settings({"queue_limit": 500})["queue_limit"] == 100

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.findarr_settings()["queue_limit"] == 100


def test_findarr_defaults_are_seeded_and_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    settings = store.findarr_settings()
    assert settings["enabled"] is False
    assert settings["interval_minutes"] == 30
    assert settings["command_sleep_seconds"] == 0
    assert settings["state_reset_hours"] == 168
    assert set(settings["apps"]) == {"sonarr", "radarr"}
    assert settings["apps"]["sonarr"]["missing_mode"] == "episodes"
    assert settings["apps"]["sonarr"]["upgrade_mode"] == "episodes"
    # Radarr always searches whole movies, so it carries no search modes.
    assert "missing_mode" not in settings["apps"]["radarr"]
    assert store.masked()["findarr"]["hourly_cap"] == 20


def test_findarr_drops_radarr_search_modes_from_older_settings(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    updated = store.update_findarr_settings(
        {"apps": {"radarr": {"missing_mode": "seasons", "upgrade_mode": "shows"}}}
    )
    assert "missing_mode" not in updated["apps"]["radarr"]
    assert "upgrade_mode" not in updated["apps"]["radarr"]


def test_findarr_updates_are_normalised_and_persisted(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    updated = store.update_findarr_settings(
        {
            "enabled": True,
            "interval_minutes": 999,
            "hourly_cap": 999,
            "queue_limit": -5,
            "command_sleep_seconds": 999,
            "state_reset_hours": 99999,
            "apps": {
                "sonarr": {
                    "missing_limit": 999,
                    "skip_future": False,
                    "missing_mode": "seasons",
                },
            },
        }
    )
    assert updated["enabled"] is True
    assert updated["interval_minutes"] == 30
    assert updated["hourly_cap"] == 100
    assert updated["queue_limit"] == -1
    assert updated["command_sleep_seconds"] == 60
    assert updated["state_reset_hours"] == 8760
    assert updated["apps"]["sonarr"]["missing_limit"] == 100
    assert updated["apps"]["sonarr"]["skip_future"] is False
    assert updated["apps"]["sonarr"]["missing_mode"] == "seasons"

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.findarr_settings()["enabled"] is True


def test_findarr_invalid_values_fall_back_to_defaults(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    updated = store.update_findarr_settings(
        {
            "hourly_cap": "bad",
            "queue_limit": "bad",
            "command_sleep_seconds": "bad",
            "state_reset_hours": "bad",
            "apps": {
                "sonarr": {
                    "upgrade_limit": "bad",
                    "missing_limit": None,
                    "upgrade_mode": "bogus",
                }
            },
        }
    )
    assert updated["hourly_cap"] == 20
    assert updated["queue_limit"] == -1
    assert updated["command_sleep_seconds"] == 0
    assert updated["state_reset_hours"] == 168
    assert updated["apps"]["sonarr"]["upgrade_limit"] == 5
    assert updated["apps"]["sonarr"]["upgrade_mode"] == "episodes"
    assert store.findarr_interval_minutes() == 30


def test_findarr_ignores_malformed_app_update(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    updated = store.update_findarr_settings({"apps": "bad"})
    assert updated["apps"]["sonarr"]["missing_limit"] == 5


def test_findarr_migrates_existing_store_without_key(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"trakt":{"client_id":"c","client_secret":"s"},"lists":[]}')
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="x", client_secret="x")
    assert store.findarr_settings()["apps"]["radarr"]["upgrade_limit"] == 5
    assert "findarr" in path.read_text()
