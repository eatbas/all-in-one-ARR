"""Tests for core.settings_store."""

from __future__ import annotations

import json

from core.settings_store import SettingsStore, TrackedList


def _seed(store: SettingsStore, **overrides) -> None:
    store.load_or_seed(
        client_id=overrides.get("client_id", "cid"),
        client_secret=overrides.get("client_secret", "secret"),
        user=overrides.get("user", "me"),
        lists=overrides.get(
            "lists", [TrackedList(owner_user="me", slug="movies", name="Movies")]
        ),
    )


def test_seeds_and_persists_on_first_run(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    _seed(store)
    assert path.exists()
    assert store.trakt_credentials() == ("cid", "secret", "me")
    assert [item.slug for item in store.tracked_lists()] == ["movies"]


def test_loads_existing_and_ignores_seed(tmp_path) -> None:
    path = tmp_path / "settings.json"
    _seed(SettingsStore(str(path)))  # write once

    reopened = SettingsStore(str(path))
    # Different seed values must be ignored because the file already exists.
    reopened.load_or_seed(
        client_id="other", client_secret="x", user="bob", lists=[]
    )
    assert reopened.trakt_credentials() == ("cid", "secret", "me")
    assert [item.slug for item in reopened.tracked_lists()] == ["movies"]


def test_load_skips_entries_without_slug_and_defaults_name(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "trakt": {"client_id": "c", "client_secret": "s", "user": "me"},
                "lists": [
                    {"owner_user": "me", "slug": "tv"},  # no name -> name == slug
                    {"owner_user": "me"},  # no slug -> skipped
                ],
            }
        )
    )
    store = SettingsStore(str(path))
    _seed(store)  # file exists -> loads
    tracked = store.tracked_lists()
    assert len(tracked) == 1
    assert tracked[0].slug == "tv"
    assert tracked[0].name == "tv"


def test_seed_blank_user_defaults_to_me(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store, user="")
    assert store.trakt_credentials()[2] == "me"


def test_update_credentials_leaves_unset_fields(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_trakt_credentials(user="bob")
    assert store.trakt_credentials() == ("cid", "secret", "bob")
    store.update_trakt_credentials(client_id="new", client_secret="ns")
    assert store.trakt_credentials() == ("new", "ns", "bob")
    store.update_trakt_credentials(user="   ")  # blank -> "me"
    assert store.trakt_credentials()[2] == "me"


def test_update_credentials_survives_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    _seed(store)
    store.update_trakt_credentials(client_id="persisted")
    assert SettingsStore(str(path)) and json.loads(path.read_text())["trakt"][
        "client_id"
    ] == "persisted"


def test_owner_for_found_and_default(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(
        store,
        user="erena",
        lists=[TrackedList(owner_user="sean", slug="shared", name="Shared")],
    )
    assert store.owner_for("shared") == "sean"
    assert store.owner_for("unknown") == "erena"


def test_add_and_remove_list_are_idempotent(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store, lists=[])
    assert store.add_list(owner_user="me", slug="tv", name="TV") is True
    assert store.add_list(owner_user="me", slug="tv", name="TV") is False
    assert [item.slug for item in store.tracked_lists()] == ["tv"]
    assert store.remove_list(owner_user="me", slug="tv") is True
    assert store.remove_list(owner_user="me", slug="tv") is False
    assert store.tracked_lists() == []


def test_masked_with_and_without_credentials(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store, client_id="abc1234")
    masked = store.masked()
    assert masked["client_id_hint"] == "1234"
    assert masked["client_id_set"] is True
    assert masked["client_secret_set"] is True
    assert masked["lists"][0]["slug"] == "movies"

    empty = SettingsStore(str(tmp_path / "empty.json"))
    empty.load_or_seed(client_id="", client_secret="", user="me", lists=[])
    masked_empty = empty.masked()
    assert masked_empty["client_id_hint"] == ""
    assert masked_empty["client_id_set"] is False
    assert masked_empty["client_secret_set"] is False


def test_tracked_list_helpers() -> None:
    item = TrackedList(owner_user="me", slug="Watchlist", name="WL")
    assert item.is_watchlist is True
    assert item.key == ("me", "Watchlist")
    assert item.to_dict() == {"owner_user": "me", "slug": "Watchlist", "name": "WL"}
