"""The Languagarr compliance rule: a file must carry one of the target languages.

The target audio languages are a setting (English by default). A file passes
when at least one of its audio tracks is in a target language — a dub, a dual
audio or a multi-audio release alike. A file with none of them fails, whatever
else it carries.

Sonarr reports a file's real audio tracks in ``mediaInfo.audioLanguages`` as
ISO-639-2 codes joined with ``/`` (for example ``"jpn/eng"``). That field is read
from the file itself, unlike the episode file's ``languages`` label, which can
disagree with the actual tracks, so the rule is evaluated on the tracks only.
Spellings are folded through :func:`core.audio_languages.canonical_language`, so
``ger`` and ``deu`` (or ``fre`` and ``fra``) count as the same language.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, Literal

from core.audio_languages import canonical_language

AudioStatus = Literal["compliant", "missing_language", "unknown"]

# Codes that say nothing about the spoken language: undetermined, no linguistic
# content, uncoded and multiple. They are ignored when reading the tracks.
_IGNORED_CODES = frozenset({"und", "zxx", "mis", "mul"})


@dataclass(frozen=True)
class AudioVerdict:
    """Outcome of the compliance rule for one episode file.

    ``languages`` holds the distinct meaningful track languages in first-seen
    order, as canonical codes.
    """

    status: AudioStatus
    languages: tuple[str, ...]

    @property
    def compliant(self) -> bool:
        """Whether the file has an audio track in a target language."""
        return self.status == "compliant"


def evaluate_audio(
    audio_languages: str | None, targets: Collection[str]
) -> AudioVerdict:
    """Apply the compliance rule to a Sonarr ``mediaInfo.audioLanguages`` value.

    The value is split on ``/``; each code is folded to its canonical form, and
    blank or non-linguistic codes (``und``, ``zxx``, ``mis``, ``mul``) are
    discarded. Duplicates (two Japanese tracks) count once. ``targets`` are
    canonical codes.

    * ``compliant``: a track in one of ``targets`` is present.
    * ``missing_language``: at least one language remains but none is a target.
    * ``unknown``: nothing remains — Sonarr has no usable audio-language data, so
      the file is reported for review but never actioned automatically.
    """
    languages: list[str] = []
    for raw in (audio_languages or "").split("/"):
        code = canonical_language(raw)
        if code and code not in _IGNORED_CODES and code not in languages:
            languages.append(code)
    distinct = tuple(languages)
    if not distinct:
        return AudioVerdict("unknown", distinct)
    if not any(code in targets for code in distinct):
        return AudioVerdict("missing_language", distinct)
    return AudioVerdict("compliant", distinct)


def file_audio_verdict(
    episode_file: dict[str, Any], targets: Collection[str]
) -> tuple[AudioVerdict, str]:
    """Return the verdict and raw ``mediaInfo.audioLanguages`` of a Sonarr file."""
    media_info = episode_file.get("mediaInfo")
    audio = media_info.get("audioLanguages") if isinstance(media_info, dict) else None
    raw = audio if isinstance(audio, str) else ""
    return evaluate_audio(raw or None, targets), raw
