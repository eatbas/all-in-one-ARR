"""The Languagarr compliance rule: anime must be dual audio with an English track.

Sonarr reports a file's real audio tracks in ``mediaInfo.audioLanguages`` as
ISO-639-2 codes joined with ``/`` (for example ``"jpn/eng"``). That field is read
from the file itself, unlike the episode file's ``languages`` label, which can
disagree with the actual tracks, so the rule is evaluated on the tracks only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AudioStatus = Literal["compliant", "missing_english", "single_language", "unknown"]

ENGLISH = "eng"

# Aliases some muxers write instead of the ISO-639-2 code for English.
_ENGLISH_ALIASES = frozenset({"en", "eng", "english"})

# Codes that say nothing about the spoken language: undetermined, no linguistic
# content, uncoded and multiple. They never count towards "dual audio".
_IGNORED_CODES = frozenset({"und", "zxx", "mis", "mul"})


@dataclass(frozen=True)
class AudioVerdict:
    """Outcome of the compliance rule for one episode file.

    ``languages`` holds the distinct meaningful track languages in first-seen
    order, with English normalised to ``"eng"``.
    """

    status: AudioStatus
    languages: tuple[str, ...]

    @property
    def compliant(self) -> bool:
        """Whether the file satisfies the dual-audio-with-English rule."""
        return self.status == "compliant"


def _normalise_code(raw: str) -> str:
    code = raw.strip().lower()
    return ENGLISH if code in _ENGLISH_ALIASES else code


def evaluate_audio(audio_languages: str | None) -> AudioVerdict:
    """Apply the compliance rule to a Sonarr ``mediaInfo.audioLanguages`` value.

    The value is split on ``/``; each code is trimmed and lower-cased, English
    aliases map to ``eng``, and blank or non-linguistic codes (``und``, ``zxx``,
    ``mis``, ``mul``) are discarded. Duplicates (two Japanese tracks) count once.

    * ``compliant``: ``eng`` is present and at least two distinct languages remain.
    * ``single_language``: ``eng`` is the only distinct language (an English-only dub).
    * ``missing_english``: at least one language remains but none is English.
    * ``unknown``: nothing remains — Sonarr has no usable audio-language data, so
      the file is reported for review but never actioned automatically.
    """
    languages: list[str] = []
    for raw in (audio_languages or "").split("/"):
        code = _normalise_code(raw)
        if code and code not in _IGNORED_CODES and code not in languages:
            languages.append(code)
    distinct = tuple(languages)
    if not distinct:
        return AudioVerdict("unknown", distinct)
    if ENGLISH not in distinct:
        return AudioVerdict("missing_english", distinct)
    if len(distinct) < 2:
        return AudioVerdict("single_language", distinct)
    return AudioVerdict("compliant", distinct)


def file_audio_verdict(episode_file: dict[str, Any]) -> tuple[AudioVerdict, str]:
    """Return the verdict and raw ``mediaInfo.audioLanguages`` of a Sonarr file."""
    media_info = episode_file.get("mediaInfo")
    audio = media_info.get("audioLanguages") if isinstance(media_info, dict) else None
    raw = audio if isinstance(audio, str) else ""
    return evaluate_audio(raw or None), raw
