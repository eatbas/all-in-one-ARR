"""Tests for the pure Cleanarr decision rules."""

from __future__ import annotations

import pytest

from core.settings_normalisers import DEFAULT_CLEANARR_SETTINGS
from modules.cleanarr.models import QueueItem
from modules.cleanarr.rules import (
    classify,
    import_failure_counts,
    import_failures_count,
    is_blocked_file,
    is_ignored,
    matches_any_pattern,
    select_removals,
)

_SEEDS: list[str] = DEFAULT_CLEANARR_SETTINGS["queue"]["patterns"]


def _item(**overrides) -> QueueItem:
    fields = {
        "app": "sonarr",
        "queue_id": 1,
        "download_id": "nzo_1",
        "protocol": "usenet",
        "download_client": "SABnzbd",
        "title": "Show.S01E01.1080p",
        "status": "completed",
        "tracked_status": "warning",
        "tracked_state": "importBlocked",
        "messages": ("Show.S01E01.mkv", "Episode was not found"),
        "output_path": "/downloads/complete/tv/Show.S01E01.1080p",
    }
    fields.update(overrides)
    return QueueItem(**fields)


@pytest.mark.parametrize(
    ("state", "status", "failed_ids", "expected"),
    [
        ("importBlocked", "warning", frozenset(), "failed_import"),
        ("importFailed", "ok", frozenset(), "failed_import"),
        ("importPending", "warning", frozenset(), "failed_import"),
        ("importPending", "ok", frozenset(), None),
        ("importing", "warning", frozenset(), None),
        ("downloading", "ok", frozenset(), None),
        ("imported", "ok", frozenset(), None),
        ("failedPending", "error", frozenset(), "failed_download"),
        ("failed", "error", None, "failed_download"),
        ("downloading", "ok", frozenset({"nzo_1"}), "failed_download"),
        ("importBlocked", "warning", frozenset({"nzo_1"}), "failed_download"),
        ("downloading", "ok", None, None),
        ("IMPORTBLOCKED", "warning", None, "failed_import"),
    ],
)
def test_classify_states(
    state: str, status: str, failed_ids: frozenset[str] | None, expected: str | None
) -> None:
    assert (
        classify(_item(tracked_state=state, tracked_status=status), failed_ids)
        == expected
    )


def test_classify_ignores_torrents() -> None:
    assert classify(_item(protocol="torrent", tracked_state="failed"), None) is None


@pytest.mark.parametrize(
    ("messages", "title", "mode", "expected"),
    [
        (("Found matching series via grab history, but release was matched to series by ID.",), "x", "exclude", False),
        (("Found matching movie via grab history, but release was MATCHED TO MOVIE BY ID",), "x", "exclude", False),
        (("Unable to determine if file is a sample",), "x", "exclude", False),
        (("Episode was not found",), "x", "exclude", True),
        (("Episode was not found",), "x", "include", False),
        (("Unable to determine if file is a sample",), "x", "include", True),
        ((), "release matched to series by id", "exclude", False),
    ],
)  # fmt: skip
def test_seeded_patterns_in_both_modes(
    messages: tuple[str, ...], title: str, mode: str, expected: bool
) -> None:
    item = _item(messages=messages, title=title)
    assert import_failure_counts(item, mode=mode, patterns=_SEEDS) is expected


def test_empty_patterns_match_nothing() -> None:
    assert matches_any_pattern(_item(), []) is False
    assert matches_any_pattern(_item(), [""]) is False
    assert import_failure_counts(_item(), mode="exclude", patterns=[]) is True
    assert import_failure_counts(_item(), mode="include", patterns=[]) is False


def test_patterns_over_every_record_of_a_download() -> None:
    plain = _item(messages=("Episode was not found",))
    matched = _item(messages=("Unable to determine if file is a sample",))
    assert (
        import_failures_count([plain, matched], mode="exclude", patterns=_SEEDS)
        is False
    )
    assert (
        import_failures_count([plain, matched], mode="include", patterns=_SEEDS) is True
    )
    assert import_failures_count([plain], mode="exclude", patterns=_SEEDS) is True


_IGNORE = {
    "download_ids": ["nzo_ignored"],
    "categories": ["Anime"],
    "title_contains": ["Sample Show"],
}


@pytest.mark.parametrize(
    ("download_id", "title", "category", "expected"),
    [
        ("nzo_ignored", "x", "", True),
        ("NZO_IGNORED", "x", "", False),
        ("nzo_1", "x", "anime", True),
        ("nzo_1", "x", "tv", False),
        ("nzo_1", "The SAMPLE show S01", "", True),
        ("nzo_1", "Other", "", False),
        # An unknown category cannot be told apart from an ignored one ...
        ("nzo_1", "Other", None, None),
        # ... unless the id or the title already exempts the download.
        ("nzo_ignored", "Other", None, True),
        ("nzo_1", "The SAMPLE show S01", None, True),
    ],
)
def test_is_ignored_variants(
    download_id: str, title: str, category: str | None, expected: bool | None
) -> None:
    assert (
        is_ignored(
            download_id=download_id, title=title, category=category, ignore=_IGNORE
        )
        is expected
    )


def test_is_ignored_with_empty_lists() -> None:
    assert is_ignored(download_id="a", title="b", category="c", ignore={}) is False
    # Without category entries, an unknown category changes nothing.
    assert is_ignored(download_id="a", title="b", category=None, ignore={}) is False


def test_select_removals_orders_oldest_first_and_caps() -> None:
    rows = [
        {"download_id": "b", "strikes": 3, "first_seen_at": "2026-01-02"},
        {"download_id": "a", "strikes": 5, "first_seen_at": "2026-01-01"},
        {"download_id": "c", "strikes": 2, "first_seen_at": "2025-12-31"},
        {"download_id": "d", "strikes": 3, "first_seen_at": "2026-01-02"},
    ]
    selected = select_removals(rows, max_strikes=3, cap=2)
    assert [row["download_id"] for row in selected] == ["a", "b"]
    assert select_removals(rows, max_strikes=3, cap=0) == []
    assert len(select_removals(rows, max_strikes=3, cap=10)) == 3


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("setup.exe", True),
        ("SETUP.EXE", True),
        ("name.exe.mkv", False),
        ("movie.mkv", False),
        ("README", False),
        (".exe", False),
        ("archive.tar.js", True),
    ],
)
def test_is_blocked_file_checks_final_suffix(name: str, expected: bool) -> None:
    assert is_blocked_file(name, frozenset({".exe", ".js"})) is expected
