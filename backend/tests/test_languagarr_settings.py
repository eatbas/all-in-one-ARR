"""Tests for Languagarr settings normalisation and persistence."""

from __future__ import annotations

import json

import pytest

from core.settings_normalisers import (
    DEFAULT_LANGUAGARR_SETTINGS,
    normalise_languagarr_settings,
)
from core.settings_store import SettingsStore


def test_defaults_are_safe() -> None:
    assert normalise_languagarr_settings() == DEFAULT_LANGUAGARR_SETTINGS
    assert DEFAULT_LANGUAGARR_SETTINGS["enabled"] is False
    assert DEFAULT_LANGUAGARR_SETTINGS["auto_queue"] is False


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("interval_minutes", 1, 15),
        ("interval_minutes", 99999, 1440),
        ("interval_minutes", "bad", 60),
        ("searches_per_run", 0, 1),
        ("searches_per_run", 500, 100),
        ("searches_per_run", None, 10),
        ("retry_after_hours", 1, 24),
        ("retry_after_hours", 10**6, 2160),
        ("retry_after_hours", "12", 24),
    ],
)
def test_numeric_fields_are_bounded(key: str, value: object, expected: int) -> None:
    assert normalise_languagarr_settings({key: value})[key] == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ([" Anime ", "Anime", "Anime 4K", ""], ["Anime", "Anime 4K"]),
        (["Anime", 3, None], ["Anime"]),
        ([], ["Anime"]),
        (["   "], ["Anime"]),
        ("Anime", ["Anime"]),
        (None, ["Anime"]),
        ([f"P{index}" for index in range(30)], [f"P{index}" for index in range(20)]),
    ],
)
def test_profile_names_are_cleaned_and_never_empty(
    value: object, expected: list[str]
) -> None:
    assert (
        normalise_languagarr_settings({"quality_profile_names": value})[
            "quality_profile_names"
        ]
        == expected
    )


def test_booleans_are_coerced() -> None:
    settings = normalise_languagarr_settings(
        {"enabled": 1, "auto_queue": 0, "monitored_only": 0}
    )
    assert settings["enabled"] is True
    assert settings["auto_queue"] is False
    assert settings["monitored_only"] is False
    assert normalise_languagarr_settings()["monitored_only"] is True


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.168.0.2:8989/", "http://192.168.0.2:8989"),
        (" https://sonarr.example/base/ ", "https://sonarr.example/base"),
        ("ftp://sonarr", ""),
        ("", ""),
        (None, ""),
        (8989, ""),
    ],
)
def test_sonarr_link_url_is_normalised_or_cleared(value: object, expected: str) -> None:
    assert (
        normalise_languagarr_settings({"sonarr_link_url": value})["sonarr_link_url"]
        == expected
    )


def test_store_seeds_updates_persists_and_migrates(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    assert store.languagarr_settings() == DEFAULT_LANGUAGARR_SETTINGS
    assert store.languagarr_interval_minutes() == 60

    updated = store.update_languagarr_settings(
        {"enabled": True, "interval_minutes": 30, "unknown_key": 1, "auto_queue": None}
    )
    assert updated["enabled"] is True
    assert updated["interval_minutes"] == 30
    assert updated["auto_queue"] is False
    assert "unknown_key" not in updated
    assert json.loads(path.read_text())["languagarr"]["interval_minutes"] == 30

    # A store written before Languagarr existed is backfilled and re-saved.
    data = json.loads(path.read_text())
    del data["languagarr"]
    path.write_text(json.dumps(data))
    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="y")
    assert reopened.languagarr_settings() == DEFAULT_LANGUAGARR_SETTINGS
    assert "languagarr" in json.loads(path.read_text())
    assert "languagarr" in reopened.masked()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["eng"], ["eng"]),
        (["deu", "ger", "German", "tur"], ["ger", "tur"]),
        (["klingon", 3, None, "jpn"], ["jpn"]),
        ([], ["eng"]),
        (["klingon"], ["eng"]),
        ("eng", ["eng"]),
        (None, ["eng"]),
        (
            [
                "eng",
                "jpn",
                "tur",
                "ger",
                "fre",
                "spa",
                "ita",
                "por",
                "rus",
                "kor",
                "chi",
            ],
            ["eng", "jpn", "tur", "ger", "fre", "spa", "ita", "por", "rus", "kor"],
        ),
    ],
)
def test_target_languages_are_canonical_and_never_empty(
    value: object, expected: list[str]
) -> None:
    assert (
        normalise_languagarr_settings({"target_audio_languages": value})[
            "target_audio_languages"
        ]
        == expected
    )
