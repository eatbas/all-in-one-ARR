"""Tests for Cleanarr's read-only health checks."""

from __future__ import annotations

from modules.cleanarr.health import arr_warnings, sab_warnings
from modules.cleanarr.models import ArrDownloadHandling, SabConfig


def _config(**overrides) -> SabConfig:
    fields = {
        "complete_dir": "/data/complete",
        "unwanted_extensions": (".exe", ".scr", ".lnk", ".bat"),
        "unwanted_action": 2,
        "encrypted_rar_action": 2,
        "category_dirs": ("tv",),
    }
    fields.update(overrides)
    return SabConfig(**fields)


def _codes(warnings) -> list[tuple[str, str]]:
    return [(warning.code, warning.level) for warning in warnings]


def test_healthy_sab_has_no_warnings() -> None:
    assert sab_warnings(_config()) == []


def test_unreachable_sab_warns() -> None:
    assert _codes(sab_warnings(None)) == [("sab_unreachable", "warning")]


def test_sab_warning_branches() -> None:
    warnings = sab_warnings(
        _config(
            unwanted_action=1,
            unwanted_extensions=(".exe",),
            encrypted_rar_action=0,
        )
    )
    assert _codes(warnings) == [
        ("unwanted_action_not_abort", "warning"),
        ("unwanted_extensions_incomplete", "warning"),
        ("encrypted_rar_not_abort", "warning"),
    ]
    assert warnings[1].detail.endswith("missing .scr, .lnk.")
    assert all(warning.source == "sabnzbd" for warning in warnings)


def test_unknown_sab_values_are_informational() -> None:
    warnings = sab_warnings(
        _config(unwanted_action=None, encrypted_rar_action=None, unwanted_extensions=())
    )
    assert _codes(warnings) == [
        ("unwanted_action_unknown", "info"),
        ("unwanted_extensions_incomplete", "warning"),
        ("encrypted_rar_unknown", "info"),
    ]


def test_healthy_arr_has_no_warnings() -> None:
    handling = ArrDownloadHandling(
        completed_handling=True,
        redownload_failed=True,
        remove_failed=True,
        remove_completed=False,
    )
    assert arr_warnings("sonarr", handling) == []


def test_arr_warning_branches() -> None:
    handling = ArrDownloadHandling(
        completed_handling=False,
        redownload_failed=False,
        remove_failed=None,
        remove_completed=None,
    )
    warnings = arr_warnings("radarr", handling)
    assert _codes(warnings) == [
        ("completed_handling_off", "warning"),
        ("redownload_failed_off", "warning"),
        ("remove_failed_unknown", "info"),
    ]
    assert warnings[0].detail == "Radarr: Completed download handling is off."
    assert {warning.source for warning in warnings} == {"radarr"}


def test_unreadable_arr_handling_is_informational() -> None:
    warnings = arr_warnings("sonarr", None)
    assert _codes(warnings) == [("download_handling_unknown", "info")]
    assert "Sonarr" in warnings[0].detail
    assert "lidarr" in arr_warnings("lidarr", None)[0].detail
