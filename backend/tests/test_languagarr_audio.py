"""Tests for the Languagarr English-audio compliance rule."""

from __future__ import annotations

import pytest

from modules.languagarr.audio import evaluate_audio


@pytest.mark.parametrize(
    ("audio", "status", "languages"),
    [
        ("jpn/eng", "compliant", ("jpn", "eng")),
        ("eng/jpn", "compliant", ("eng", "jpn")),
        ("ENG/JPN", "compliant", ("eng", "jpn")),
        ("en/ja", "compliant", ("eng", "ja")),
        (" jpn / english ", "compliant", ("jpn", "eng")),
        ("eng/und/jpn", "compliant", ("eng", "jpn")),
        ("jpn/eng/por/spa", "compliant", ("jpn", "eng", "por", "spa")),
        ("jpn/por", "missing_english", ("jpn", "por")),
        ("jpn", "missing_english", ("jpn",)),
        ("jpn/jpn", "missing_english", ("jpn",)),
        ("ger/jpn", "missing_english", ("ger", "jpn")),
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
def test_evaluate_audio(audio: str | None, status: str, languages: tuple) -> None:
    verdict = evaluate_audio(audio)
    assert verdict.status == status
    assert verdict.languages == languages
    assert verdict.compliant is (status == "compliant")
