"""Tests for core.animation."""

from __future__ import annotations

import pytest

from core.animation import (
    ANIMATION_GENRE_ID,
    ANIME_ORIGINAL_LANGUAGE,
    TRAKT_ANIMATION_GENRE,
    TRAKT_ANIME_GENRE,
    is_anime_language,
    keeps_discover_row,
    keeps_search_row,
)


def test_constants_match_provider_identifiers() -> None:
    # TMDB's Animation genre id (shared by Seer) and Trakt's genre slugs.
    assert ANIMATION_GENRE_ID == 16
    assert ANIME_ORIGINAL_LANGUAGE == "ja"
    assert TRAKT_ANIMATION_GENRE == "animation"
    assert TRAKT_ANIME_GENRE == "anime"


@pytest.mark.parametrize(
    ("original_language", "expected"),
    [
        ("ja", True),
        ("en", False),
        ("JA", False),
        ("", False),
        (None, False),
        (16, False),
        (["ja"], False),
    ],
)
def test_is_anime_language_matches_only_japanese(
    original_language: object, expected: bool
) -> None:
    assert is_anime_language(original_language) is expected


@pytest.mark.parametrize(
    ("original_language", "expected"),
    [
        # Positively Japanese: anime, dropped.
        ("ja", False),
        # Another language: kept.
        ("en", True),
        # Missing or malformed: the feed is already genre filtered, so kept.
        (None, True),
        (42, True),
    ],
)
def test_keeps_discover_row_drops_only_positive_japanese(
    original_language: object, expected: bool
) -> None:
    assert keeps_discover_row(original_language) is expected


@pytest.mark.parametrize(
    ("genre_ids", "original_language", "expected"),
    [
        # Animation, not Japanese: kept.
        ([16, 35], "en", True),
        # Animation with a missing language: kept.
        ([16], None, True),
        # Animation but Japanese: anime, dropped.
        ([16], "ja", False),
        # Not Animation: dropped.
        ([18, 35], "en", False),
        ([], "en", False),
        # Missing or non-list genre ids: dropped (no positive genre evidence).
        (None, "en", False),
        ("16", "en", False),
        ((16,), "en", False),
        ({16: "Animation"}, "en", False),
    ],
)
def test_keeps_search_row_needs_animation_and_non_japanese(
    genre_ids: object, original_language: object, expected: bool
) -> None:
    assert keeps_search_row(genre_ids, original_language) is expected
