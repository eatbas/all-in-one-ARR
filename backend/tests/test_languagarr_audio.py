"""Tests for the Languagarr target-language audio compliance rule."""

from __future__ import annotations

import pytest

from modules.languagarr.audio import evaluate_audio, file_audio_verdict

_ENGLISH = ("eng",)


@pytest.mark.parametrize(
    ("audio", "status", "languages"),
    [
        ("jpn/eng", "compliant", ("jpn", "eng")),
        ("eng/jpn", "compliant", ("eng", "jpn")),
        ("ENG/JPN", "compliant", ("eng", "jpn")),
        ("en/ja", "compliant", ("eng", "jpn")),
        (" jpn / english ", "compliant", ("jpn", "eng")),
        ("eng/und/jpn", "compliant", ("eng", "jpn")),
        ("jpn/eng/por/spa", "compliant", ("jpn", "eng", "por", "spa")),
        ("jpn/por", "missing_language", ("jpn", "por")),
        ("jpn", "missing_language", ("jpn",)),
        ("jpn/jpn", "missing_language", ("jpn",)),
        ("ger/jpn", "missing_language", ("ger", "jpn")),
        ("eng", "compliant", ("eng",)),
        ("eng/eng", "compliant", ("eng",)),
        ("und/eng", "compliant", ("eng",)),
        ("ENGLISH", "compliant", ("eng",)),
        ("zxx", "unknown", ()),
        ("und/mis/mul", "unknown", ()),
        ("", "unknown", ()),
        (None, "unknown", ()),
        ("/ /", "unknown", ()),
    ],
)
def test_evaluate_audio_for_english(
    audio: str | None, status: str, languages: tuple
) -> None:
    verdict = evaluate_audio(audio, _ENGLISH)
    assert verdict.status == status
    assert verdict.languages == languages
    assert verdict.compliant is (status == "compliant")


@pytest.mark.parametrize(
    ("audio", "status"),
    [
        # Any one target language is enough.
        ("jpn/eng", "compliant"),
        ("jpn/tur", "compliant"),
        ("tur", "compliant"),
        ("jpn", "missing_language"),
        ("jpn/ger", "missing_language"),
    ],
)
def test_evaluate_audio_passes_with_any_target(audio: str, status: str) -> None:
    assert evaluate_audio(audio, ("eng", "tur")).status == status


@pytest.mark.parametrize("audio", ["deu", "ger", "de", "German", "jpn/deu"])
def test_evaluate_audio_folds_alternative_spellings(audio: str) -> None:
    verdict = evaluate_audio(audio, ("ger",))
    assert verdict.compliant is True
    assert "ger" in verdict.languages


def test_evaluate_audio_keeps_uncatalogued_codes_distinct() -> None:
    verdict = evaluate_audio("nep/jpn", _ENGLISH)
    assert verdict.status == "missing_language"
    assert verdict.languages == ("nep", "jpn")


def test_file_audio_verdict_reads_media_info() -> None:
    verdict, raw = file_audio_verdict(
        {"mediaInfo": {"audioLanguages": "jpn/tur"}}, ("tur",)
    )
    assert verdict.compliant is True
    assert raw == "jpn/tur"
    verdict, raw = file_audio_verdict({"mediaInfo": None}, ("tur",))
    assert verdict.status == "unknown"
    assert raw == ""
