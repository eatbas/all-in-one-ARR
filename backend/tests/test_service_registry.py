"""Tests for core.service_registry (the managed-service descriptor table)."""

from __future__ import annotations

from core.service_registry import (
    BY_NAME,
    SERVICE_NAMES,
    SERVICES,
    empty_values,
    masked_entry,
)


def test_service_names_and_order() -> None:
    assert SERVICE_NAMES == (
        "seer",
        "sonarr",
        "radarr",
        "tmdb",
        "omdb",
        "sabnzbd",
        "qbittorrent",
    )
    # BY_NAME indexes every descriptor by its name.
    assert set(BY_NAME) == set(SERVICE_NAMES)
    assert all(BY_NAME[name].name == name for name in SERVICE_NAMES)


def test_descriptor_field_shapes() -> None:
    assert BY_NAME["sonarr"].fields == ("url", "api_key")
    assert BY_NAME["tmdb"].fields == ("api_key",)
    assert BY_NAME["tmdb"].default_url == "https://api.themoviedb.org"
    assert BY_NAME["omdb"].default_url == "https://www.omdbapi.com"
    assert BY_NAME["qbittorrent"].fields == ("url", "api_key")
    assert BY_NAME["qbittorrent"].secret_fields == ("api_key",)


def test_empty_values_holds_exactly_the_declared_fields() -> None:
    assert empty_values(BY_NAME["seer"]) == {"url": "", "api_key": ""}
    assert empty_values(BY_NAME["tmdb"]) == {"api_key": ""}
    assert empty_values(BY_NAME["qbittorrent"]) == {"url": "", "api_key": ""}


def test_masked_entry_masks_only_secret_fields() -> None:
    # Legacy url/api_key service: api_key reduced to api_key_set.
    assert masked_entry(BY_NAME["seer"], {"url": "http://js", "api_key": "k"}) == {
        "url": "http://js",
        "api_key_set": True,
    }
    # API-key-only service: just the boolean.
    assert masked_entry(BY_NAME["tmdb"], {"api_key": ""}) == {"api_key_set": False}
    # qBittorrent is a url/api_key service: url in clear, api_key masked.
    assert masked_entry(
        BY_NAME["qbittorrent"], {"url": "http://qb", "api_key": "k"}
    ) == {"url": "http://qb", "api_key_set": True}


def test_every_secret_field_is_a_declared_field() -> None:
    for desc in SERVICES:
        assert set(desc.secret_fields).issubset(set(desc.fields))
