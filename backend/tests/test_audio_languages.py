"""Tests for the shared audio-language catalogue."""

from __future__ import annotations

import pytest

from core.audio_languages import (
    AUDIO_LANGUAGES,
    DEFAULT_AUDIO_LANGUAGE,
    canonical_language,
    describe_languages,
    is_known_language,
    language_name,
)


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("eng", "eng"),
        (" EN ", "eng"),
        ("English", "eng"),
        ("deu", "ger"),
        ("fra", "fre"),
        ("zho", "chi"),
        ("nld", "dut"),
        ("nep", "nep"),
        ("", ""),
    ],
)
def test_canonical_language_folds_spellings(raw: str, canonical: str) -> None:
    assert canonical_language(raw) == canonical


def test_catalogue_codes_and_aliases_are_unique() -> None:
    spellings = [
        spelling
        for language in AUDIO_LANGUAGES
        for spelling in (language.code, *language.aliases)
    ]
    assert len(spellings) == len(set(spellings))
    assert DEFAULT_AUDIO_LANGUAGE == "eng"


def test_known_language_and_names() -> None:
    assert is_known_language("Turkish") is True
    assert is_known_language("nep") is False
    assert language_name("deu") == "German"
    assert language_name("nep") == "NEP"


@pytest.mark.parametrize(
    ("codes", "prose"),
    [
        ([], ""),
        (["eng"], "English"),
        (["eng", "tur"], "English or Turkish"),
        (("eng", "tur", "ger"), "English, Turkish or German"),
    ],
)
def test_describe_languages(codes: list[str], prose: str) -> None:
    assert describe_languages(codes) == prose
