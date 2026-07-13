"""Tests for core.settings_store."""

from __future__ import annotations

import json

import pytest

from core.settings_normalisers import normalise_service_url
from core.settings_store import SettingsStore, TrackedList


def _seed(store: SettingsStore, **overrides) -> None:
    """Seed credentials, then add any requested lists.

    Lists are no longer seeded by ``load_or_seed`` (they come from the dashboard),
    so the helper adds them explicitly after the store is initialised.
    """
    store.load_or_seed(
        client_id=overrides.get("client_id", "cid"),
        client_secret=overrides.get("client_secret", "secret"),
    )
    for item in overrides.get(
        "lists", [TrackedList(owner_user="me", slug="movies", name="Movies")]
    ):
        store.add_list(owner_user=item.owner_user, slug=item.slug, name=item.name)


def test_seeds_and_persists_on_first_run(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    _seed(store)
    assert path.exists()
    assert store.trakt_credentials() == ("cid", "secret")
    assert [item.slug for item in store.tracked_lists()] == ["movies"]
    assert store.deletarr_settings() == {
        "movies_path": "/media/movies",
        "tv_path": "/media/tv",
        "use_arr_source": True,
    }


def test_loads_existing_and_ignores_seed(tmp_path) -> None:
    path = tmp_path / "settings.json"
    _seed(SettingsStore(str(path)))  # write once

    reopened = SettingsStore(str(path))
    # Different seed values must be ignored because the file already exists.
    reopened.load_or_seed(client_id="other", client_secret="x")
    assert reopened.trakt_credentials() == ("cid", "secret")
    assert [item.slug for item in reopened.tracked_lists()] == ["movies"]


def test_load_skips_entries_without_slug_and_defaults_name(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "trakt": {"client_id": "c", "client_secret": "s"},
                "lists": [
                    {"owner_user": "me", "slug": "tv"},  # no name -> name == slug
                    {"owner_user": "me"},  # no slug -> skipped
                ],
            }
        )
    )
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="cid", client_secret="secret")  # file exists -> loads
    tracked = store.tracked_lists()
    assert len(tracked) == 1
    assert tracked[0].slug == "tv"
    assert tracked[0].name == "tv"


def test_update_credentials_leaves_unset_fields(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_trakt_credentials(client_id="new")
    assert store.trakt_credentials() == ("new", "secret")
    store.update_trakt_credentials(client_secret="ns")
    assert store.trakt_credentials() == ("new", "ns")


def test_update_credentials_survives_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    _seed(store)
    store.update_trakt_credentials(client_id="persisted")
    assert (
        SettingsStore(str(path))
        and json.loads(path.read_text())["trakt"]["client_id"] == "persisted"
    )


def test_owner_for_found_and_default(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(
        store,
        lists=[TrackedList(owner_user="sean", slug="shared", name="Shared")],
    )
    assert store.owner_for("shared") == "sean"
    assert store.owner_for("unknown") == "me"


def test_add_and_remove_list_are_idempotent(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store, lists=[])
    assert store.add_list(owner_user="me", slug="tv", name="TV") is True
    assert store.add_list(owner_user="me", slug="tv", name="TV") is False
    assert [item.slug for item in store.tracked_lists()] == ["tv"]
    assert store.remove_list(owner_user="me", slug="tv") is True
    assert store.remove_list(owner_user="me", slug="tv") is False
    assert store.tracked_lists() == []


def test_added_lists_survive_reload(tmp_path) -> None:
    # Lists chosen from the dashboard are persisted and reloaded across restarts.
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    _seed(store, lists=[])
    store.add_list(owner_user="me", slug="tv", name="TV")
    store.add_list(owner_user="sean", slug="shared", name="Shared")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert [(i.owner_user, i.slug) for i in reopened.tracked_lists()] == [
        ("me", "tv"),
        ("sean", "shared"),
    ]


def test_masked_with_and_without_credentials(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store, client_id="abc1234")
    masked = store.masked()
    assert masked["client_id_hint"] == "1234"
    assert masked["client_id_set"] is True
    assert masked["client_secret_set"] is True
    assert masked["lists"][0]["slug"] == "movies"

    empty = SettingsStore(str(tmp_path / "empty.json"))
    empty.load_or_seed(client_id="", client_secret="")
    masked_empty = empty.masked()
    assert masked_empty["client_id_hint"] == ""
    assert masked_empty["client_id_set"] is False
    assert masked_empty["client_secret_set"] is False


def test_seeds_and_round_trips_services(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        services={
            "seer": {"url": "http://js", "api_key": "jk"},
            "sonarr": {"url": "http://sonarr", "api_key": ""},
        },
    )
    assert store.service_connection("seer") == ("http://js", "jk")
    assert store.service_connection("sonarr") == ("http://sonarr", "")
    assert store.service_connection("radarr") == ("", "")  # absent in seed

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x", services=None)
    assert reopened.service_connection("seer") == ("http://js", "jk")


def test_seeds_updates_and_reloads_deletarr_paths(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="c",
        client_secret="s",
        deletarr_movies_path="/mnt/movies",
        deletarr_tv_path="/mnt/tv",
        deletarr_use_arr_source=False,
    )
    assert store.deletarr_settings() == {
        "movies_path": "/mnt/movies",
        "tv_path": "/mnt/tv",
        "use_arr_source": False,
    }

    store.update_deletarr_settings(movies_path="/new/movies")
    assert store.deletarr_settings() == {
        "movies_path": "/new/movies",
        "tv_path": "/mnt/tv",
        "use_arr_source": False,
    }
    store.update_deletarr_settings(tv_path="/new/tv", use_arr_source=True)
    assert store.deletarr_settings() == {
        "movies_path": "/new/movies",
        "tv_path": "/new/tv",
        "use_arr_source": True,
    }

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(
        client_id="x",
        client_secret="x",
        deletarr_movies_path="/ignored",
        deletarr_tv_path="/ignored-tv",
    )
    assert reopened.deletarr_settings() == {
        "movies_path": "/new/movies",
        "tv_path": "/new/tv",
        "use_arr_source": True,
    }


def test_backfills_deletarr_paths_from_seed_on_upgrade(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"trakt": {"client_id": "c", "client_secret": "s"}}))
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="x",
        client_secret="x",
        deletarr_movies_path="/seed/movies",
        deletarr_tv_path="/seed/tv",
    )

    assert store.deletarr_settings() == {
        "movies_path": "/seed/movies",
        "tv_path": "/seed/tv",
        "use_arr_source": True,
    }
    assert json.loads(path.read_text())["deletarr"] == {
        "movies_path": "/seed/movies",
        "tv_path": "/seed/tv",
        "use_arr_source": True,
    }


def test_backfills_new_services_from_seed_on_upgrade(tmp_path) -> None:
    # An older store file without a "services" key (pre-dates the feature).
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "trakt": {"client_id": "c", "client_secret": "s"},
                "lists": [],
            }
        )
    )
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="x",
        client_secret="x",
        services={"seer": {"url": "http://js", "api_key": "jk"}},
    )
    assert store.service_connection("seer") == ("http://js", "jk")

    # The backfill was persisted, so a later load needs no re-seed.
    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x", services=None)
    assert reopened.service_connection("seer") == ("http://js", "jk")


def test_update_service_connection_leaves_unset_fields(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    store.update_service_connection("sonarr", url="http://sonarr:8989", api_key="sk")
    assert store.service_connection("sonarr") == ("http://sonarr:8989", "sk")
    store.update_service_connection("sonarr", url="http://new")  # key unchanged
    assert store.service_connection("sonarr") == ("http://new", "sk")
    store.update_service_connection("sonarr", api_key="sk2")  # url unchanged
    assert store.service_connection("sonarr") == ("http://new", "sk2")


def test_normalise_service_url() -> None:
    assert normalise_service_url("seer:5055") == "http://seer:5055"
    assert normalise_service_url("  http://js:5055/  ") == "http://js:5055"
    assert (
        normalise_service_url("https://req.example.com/path/")
        == "https://req.example.com/path"
    )
    assert normalise_service_url("") == ""
    assert normalise_service_url("http://localhost:5055") == "http://localhost:5055"


def test_normalise_service_url_rejects_unsupported_schemes() -> None:
    with pytest.raises(ValueError, match="http:// or https://"):
        normalise_service_url("ftp://host")
    with pytest.raises(ValueError, match="http:// or https://"):
        normalise_service_url("file:///etc/passwd")


def test_update_service_fields_normalises_url(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="c", client_secret="s")
    store.update_service_fields("seer", url="seer:5055")
    assert store.service_fields("seer")["url"] == "http://seer:5055"


def test_masked_services_hides_keys(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(
        client_id="c",
        client_secret="s",
        services={"seer": {"url": "http://js", "api_key": "jk"}},
    )
    masked = store.masked_services()
    assert masked["seer"] == {"url": "http://js", "api_key_set": True}
    assert masked["radarr"] == {"url": "", "api_key_set": False}
    assert store.masked()["services"]["seer"]["api_key_set"] is True


def test_seeds_and_masks_api_key_only_service(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(
        client_id="c",
        client_secret="s",
        services={"tmdb": {"api_key": "tk"}},
    )
    # An API-key-only service stores and masks just that field.
    assert store.service_fields("tmdb") == {"api_key": "tk"}
    assert store.masked_services()["tmdb"] == {"api_key_set": True}
    assert store.masked_services()["omdb"] == {
        "api_key_set": False,
        "api_key_2_set": False,
        "api_key_3_set": False,
        "api_key_4_set": False,
    }


def test_seeds_updates_and_reloads_qbittorrent_service(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="c",
        client_secret="s",
        services={"qbittorrent": {"url": "http://qb", "api_key": "qbt_key"}},
    )
    assert store.service_fields("qbittorrent") == {
        "url": "http://qb",
        "api_key": "qbt_key",
    }
    assert store.masked_services()["qbittorrent"] == {
        "url": "http://qb",
        "api_key_set": True,
    }
    # Updating leaves unspecified fields unchanged and ignores undeclared ones.
    store.update_service_fields("qbittorrent", api_key="qbt_new", password="ignored")
    fields = store.service_fields("qbittorrent")
    assert fields["api_key"] == "qbt_new"
    assert fields["url"] == "http://qb"
    assert "password" not in fields

    # The change survives a reload from disk.
    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x", services=None)
    assert reopened.service_fields("qbittorrent")["api_key"] == "qbt_new"


def test_tracked_list_helpers() -> None:
    item = TrackedList(owner_user="me", slug="Watchlist", name="WL")
    assert item.is_watchlist is True
    assert item.key == ("me", "Watchlist")
    assert item.to_dict() == {"owner_user": "me", "slug": "Watchlist", "name": "WL"}


def test_status_check_interval_defaults_to_sixty(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.status_check_interval_seconds() == 60


def test_status_check_interval_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        status_check_interval_seconds=30,
    )
    assert store.status_check_interval_seconds() == 30
    assert json.loads(path.read_text())["status_check_interval_seconds"] == 30

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.status_check_interval_seconds() == 30


def test_status_check_interval_invalid_value_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_status_check_interval(45) == 45
    assert store.update_status_check_interval(99) == 60
    assert store.status_check_interval_seconds() == 60


def test_status_check_interval_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_status_check_interval(45)
    assert store.masked()["status_check_interval_seconds"] == 45


def test_sync_interval_defaults_to_fifteen(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.sync_interval_minutes() == 15


def test_sync_interval_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        sync_interval_minutes=30,
    )
    assert store.sync_interval_minutes() == 30
    assert json.loads(path.read_text())["sync_interval_minutes"] == 30

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.sync_interval_minutes() == 30


def test_sync_interval_invalid_value_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_sync_interval(45) == 45
    assert store.update_sync_interval(7) == 15
    assert store.sync_interval_minutes() == 15


def test_sync_interval_invalid_seed_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(client_id="cid", client_secret="sec", sync_interval_minutes=999)
    assert store.sync_interval_minutes() == 15


def test_sync_interval_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_sync_interval(60)
    assert store.masked()["sync_interval_minutes"] == 60


def test_auto_remove_when_available_defaults_to_false(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.auto_remove_when_available() is False


def test_auto_remove_when_available_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        auto_remove_when_available=True,
    )
    assert store.auto_remove_when_available() is True
    assert json.loads(path.read_text())["auto_remove_when_available"] is True

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.auto_remove_when_available() is True


def test_auto_remove_when_available_update_and_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_auto_remove_when_available(True) is True
    assert store.auto_remove_when_available() is True
    assert store.masked()["auto_remove_when_available"] is True
    assert store.update_auto_remove_when_available(False) is False
    assert store.auto_remove_when_available() is False


def test_legacy_auto_remove_on_import_key_migrates(tmp_path) -> None:
    # A store persisted under the historical key (``auto_remove_on_import``) is read
    # under the new meaning AND re-saved under the new key purely on load, so an
    # existing install's choice carries over without a manual migration.
    path = tmp_path / "settings.json"
    # Seed a complete, current store first (all services present) so the load below
    # does NOT trigger a service backfill — the re-save must come from the migration
    # alone, not the backfill path.
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("auto_remove_when_available", None)
    data["auto_remove_on_import"] = True
    path.write_text(json.dumps(data), encoding="utf-8")

    store = SettingsStore(str(path))
    store.load_or_seed(client_id="cid", client_secret="sec")
    assert store.auto_remove_when_available() is True
    # The load itself rewrote the file under the new key and dropped the legacy one,
    # without any further update() call.
    saved = json.loads(path.read_text())
    assert saved["auto_remove_when_available"] is True
    assert "auto_remove_on_import" not in saved


def test_bandwidth_control_defaults_to_false(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.bandwidth_control_enabled() is False
    assert store.bandwidth_check_interval_seconds() == 15


def test_bandwidth_control_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        bandwidth_control_enabled=True,
        bandwidth_check_interval_seconds=30,
    )
    assert store.bandwidth_control_enabled() is True
    assert store.bandwidth_check_interval_seconds() == 30
    saved = json.loads(path.read_text())
    assert saved["bandwidth_control_enabled"] is True
    assert saved["bandwidth_check_interval_seconds"] == 30

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.bandwidth_control_enabled() is True
    assert reopened.bandwidth_check_interval_seconds() == 30


def test_bandwidth_check_interval_invalid_value_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_bandwidth_check_interval(10) == 10
    assert store.update_bandwidth_check_interval(99) == 15
    assert store.bandwidth_check_interval_seconds() == 15


def test_bandwidth_check_interval_invalid_seed_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        bandwidth_check_interval_seconds=999,
    )
    assert store.bandwidth_check_interval_seconds() == 15


def test_bandwidth_settings_update_and_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_bandwidth_control_enabled(True) is True
    assert store.bandwidth_control_enabled() is True
    assert store.update_bandwidth_check_interval(60) == 60
    masked = store.masked()
    assert masked["bandwidth_control_enabled"] is True
    assert masked["bandwidth_check_interval_seconds"] == 60


def test_legacy_store_without_bandwidth_keys_defaults(tmp_path) -> None:
    # A store created before Bandwidth-Controllarr existed loads without the new keys
    # and falls back to the default values.
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("bandwidth_control_enabled", None)
    data.pop("bandwidth_check_interval_seconds", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.bandwidth_control_enabled() is False
    assert reopened.bandwidth_check_interval_seconds() == 15
    # A subsequent save persists the defaults so the store stays current.
    saved = json.loads(path.read_text())
    assert saved["bandwidth_control_enabled"] is False
    assert saved["bandwidth_check_interval_seconds"] == 15


def test_trending_sync_interval_defaults_to_one_day(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.trending_sync_interval_minutes() == 1440


def test_trending_sync_interval_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        trending_sync_interval_minutes=2880,
    )
    assert store.trending_sync_interval_minutes() == 2880
    assert json.loads(path.read_text())["trending_sync_interval_minutes"] == 2880

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.trending_sync_interval_minutes() == 2880


def test_trending_sync_interval_invalid_value_falls_back(tmp_path) -> None:
    # Legacy sub-day cadences (e.g. the old hourly 60) fall back to the default
    # alongside arbitrary invalid values.
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_trending_sync_interval(2880) == 2880
    assert store.update_trending_sync_interval(60) == 1440
    assert store.trending_sync_interval_minutes() == 1440


def test_trending_sync_interval_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_trending_sync_interval(2880)
    assert store.masked()["trending_sync_interval_minutes"] == 2880


def test_anime_ids_refresh_defaults_to_three_days(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.anime_ids_refresh_days() == 3


def test_anime_ids_refresh_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid",
        client_secret="sec",
        anime_ids_refresh_days=5,
    )
    assert store.anime_ids_refresh_days() == 5
    assert json.loads(path.read_text())["anime_ids_refresh_days"] == 5

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.anime_ids_refresh_days() == 5


def test_anime_ids_refresh_invalid_value_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_anime_ids_refresh_days(1) == 1
    # 0, 2, 7 and negatives are outside the dashboard's 1/3/5 set.
    assert store.update_anime_ids_refresh_days(7) == 3
    assert store.anime_ids_refresh_days() == 3
    assert store.update_anime_ids_refresh_days(-1) == 3


def test_anime_ids_refresh_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_anime_ids_refresh_days(5)
    assert store.masked()["anime_ids_refresh_days"] == 5


def test_legacy_store_without_anime_ids_key_defaults(tmp_path) -> None:
    # A store created before the anime tab existed loads without the new key and
    # falls back to the default, persisting it on the next save.
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("anime_ids_refresh_days", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.anime_ids_refresh_days() == 3
    assert json.loads(path.read_text())["anime_ids_refresh_days"] == 3


def test_legacy_store_without_trending_key_defaults(tmp_path) -> None:
    # A store created before the App scheduler existed loads without the new key and
    # falls back to the default, persisting it on the next save.
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("trending_sync_interval_minutes", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.trending_sync_interval_minutes() == 1440
    assert json.loads(path.read_text())["trending_sync_interval_minutes"] == 1440


def test_rating_ttl_defaults_to_seven_days(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.rating_ttl_days() == 7


def test_rating_ttl_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="cid", client_secret="sec", rating_ttl_days=10)
    assert store.rating_ttl_days() == 10
    assert json.loads(path.read_text())["rating_ttl_days"] == 10

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.rating_ttl_days() == 10


def test_rating_ttl_invalid_value_falls_back(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_rating_ttl_days(5) == 5
    assert store.update_rating_ttl_days(6) == 7
    assert store.rating_ttl_days() == 7


def test_rating_ttl_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_rating_ttl_days(10)
    assert store.masked()["rating_ttl_days"] == 10


def test_legacy_store_without_rating_ttl_key_defaults(tmp_path) -> None:
    # A store created before the rating window existed loads without the key
    # and falls back to the default, persisting it on the next save.
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("rating_ttl_days", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.rating_ttl_days() == 7
    assert json.loads(path.read_text())["rating_ttl_days"] == 7


def test_new_service_fields_backfill_from_env_seed_on_upgrade(tmp_path) -> None:
    # An existing store written before the OMDb rotation keys existed carries
    # only {api_key}; the newly declared fields are filled from the env seed
    # once and persisted (the user's .env keys appear in the UI after upgrade).
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    data = json.loads(path.read_text())
    data["services"]["omdb"] = {"api_key": "primary"}
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(
        client_id="x",
        client_secret="x",
        services={"omdb": {"api_key": "ignored", "api_key_2": "extra2"}},
    )
    fields = reopened.service_fields("omdb")
    # The present field keeps its stored value; absent fields take the seed.
    assert fields["api_key"] == "primary"
    assert fields["api_key_2"] == "extra2"
    assert fields["api_key_3"] == ""
    assert json.loads(path.read_text())["services"]["omdb"]["api_key_2"] == "extra2"


def test_present_but_empty_service_field_is_not_reseeded(tmp_path) -> None:
    # A field the user explicitly cleared (present, empty) must never be
    # resurrected from the environment seed on a later boot.
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(client_id="c", client_secret="s")
    data = json.loads(path.read_text())
    data["services"]["omdb"] = {
        "api_key": "primary",
        "api_key_2": "",
        "api_key_3": "",
        "api_key_4": "",
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(
        client_id="x",
        client_secret="x",
        services={"omdb": {"api_key_2": "from-env"}},
    )
    assert reopened.service_fields("omdb")["api_key_2"] == ""


def test_omdb_budget_defaults_to_eight_hundred(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.omdb_daily_budget_per_key() == 800


def test_omdb_budget_seed_and_reload(tmp_path) -> None:
    path = tmp_path / "settings.json"
    store = SettingsStore(str(path))
    store.load_or_seed(
        client_id="cid", client_secret="sec", omdb_daily_budget_per_key=500
    )
    assert store.omdb_daily_budget_per_key() == 500
    assert json.loads(path.read_text())["omdb_daily_budget_per_key"] == 500

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.omdb_daily_budget_per_key() == 500


def test_omdb_budget_clamps_to_bounds(tmp_path) -> None:
    # Out-of-range values clamp to the 100-1000 bounds; unparseable input
    # falls back to the default.
    from core.settings_normalisers import normalise_omdb_daily_budget_per_key

    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    assert store.update_omdb_daily_budget_per_key(1500) == 1000
    assert store.update_omdb_daily_budget_per_key(1) == 100
    assert store.omdb_daily_budget_per_key() == 100
    assert normalise_omdb_daily_budget_per_key("abc") == 800


def test_omdb_budget_in_masked(tmp_path) -> None:
    store = SettingsStore(str(tmp_path / "settings.json"))
    _seed(store)
    store.update_omdb_daily_budget_per_key(900)
    assert store.masked()["omdb_daily_budget_per_key"] == 900


def test_legacy_store_without_omdb_budget_key_defaults(tmp_path) -> None:
    path = tmp_path / "settings.json"
    SettingsStore(str(path)).load_or_seed(client_id="cid", client_secret="sec")
    data = json.loads(path.read_text())
    data.pop("omdb_daily_budget_per_key", None)
    path.write_text(json.dumps(data), encoding="utf-8")

    reopened = SettingsStore(str(path))
    reopened.load_or_seed(client_id="x", client_secret="x")
    assert reopened.omdb_daily_budget_per_key() == 800
    assert json.loads(path.read_text())["omdb_daily_budget_per_key"] == 800
