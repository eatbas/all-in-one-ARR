"""Audio-language catalogue shared by Languagarr's audit and its settings.

Sonarr reports a file's real audio tracks in ``mediaInfo.audioLanguages`` as
ISO-639-2 codes joined with ``/`` (for example ``"jpn/eng"``). The same language
can arrive under more than one spelling: ISO-639-2 has bibliographic and
terminologic forms (``ger``/``deu``, ``fre``/``fra``, ``chi``/``zho``), and
some muxers write ISO-639-1 codes (``en``) or English names (``english``). Every
spelling is folded to one canonical code — the bibliographic form, which is what
Sonarr reports for most files — so a target language matches all of them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioLanguage:
    """One selectable audio language: canonical code, display name, aliases."""

    code: str
    name: str
    aliases: tuple[str, ...] = ()


# Offered in this order in the Settings checklist; the first is the default.
AUDIO_LANGUAGES: tuple[AudioLanguage, ...] = (
    AudioLanguage("eng", "English", ("en", "english")),
    AudioLanguage("jpn", "Japanese", ("ja", "japanese")),
    AudioLanguage("tur", "Turkish", ("tr", "turkish")),
    AudioLanguage("ger", "German", ("de", "deu", "german")),
    AudioLanguage("fre", "French", ("fr", "fra", "french")),
    AudioLanguage("spa", "Spanish", ("es", "spanish")),
    AudioLanguage("ita", "Italian", ("it", "italian")),
    AudioLanguage("por", "Portuguese", ("pt", "portuguese")),
    AudioLanguage("rus", "Russian", ("ru", "russian")),
    AudioLanguage("kor", "Korean", ("ko", "korean")),
    AudioLanguage("chi", "Chinese", ("zh", "zho", "chinese")),
    AudioLanguage("ara", "Arabic", ("ar", "arabic")),
    AudioLanguage("hin", "Hindi", ("hi", "hindi")),
    AudioLanguage("tha", "Thai", ("th", "thai")),
    AudioLanguage("dut", "Dutch", ("nl", "nld", "dutch")),
    AudioLanguage("pol", "Polish", ("pl", "polish")),
    AudioLanguage("swe", "Swedish", ("sv", "swedish")),
    AudioLanguage("nor", "Norwegian", ("no", "nob", "nno", "norwegian")),
    AudioLanguage("dan", "Danish", ("da", "danish")),
    AudioLanguage("fin", "Finnish", ("fi", "finnish")),
    AudioLanguage("ukr", "Ukrainian", ("uk", "ukrainian")),
    AudioLanguage("vie", "Vietnamese", ("vi", "vietnamese")),
    AudioLanguage("ind", "Indonesian", ("id", "indonesian")),
    AudioLanguage("may", "Malay", ("ms", "msa", "malay")),
    AudioLanguage("heb", "Hebrew", ("he", "hebrew")),
    AudioLanguage("gre", "Greek", ("el", "ell", "greek")),
    AudioLanguage("cze", "Czech", ("cs", "ces", "czech")),
    AudioLanguage("hun", "Hungarian", ("hu", "hungarian")),
    AudioLanguage("rum", "Romanian", ("ro", "ron", "romanian")),
    AudioLanguage("per", "Persian", ("fa", "fas", "persian")),
)

DEFAULT_AUDIO_LANGUAGE = AUDIO_LANGUAGES[0].code

_NAMES: dict[str, str] = {language.code: language.name for language in AUDIO_LANGUAGES}

_CANONICAL: dict[str, str] = {
    spelling: language.code
    for language in AUDIO_LANGUAGES
    for spelling in (language.code, *language.aliases)
}


def canonical_language(raw: str) -> str:
    """Fold one reported language spelling to its canonical code.

    The value is trimmed and lower-cased; a known spelling maps to its catalogue
    code, and anything else is returned as-is (lower-cased) so an uncatalogued
    track still counts as a distinct language.
    """
    code = raw.strip().lower()
    return _CANONICAL.get(code, code)


def is_known_language(code: str) -> bool:
    """Whether ``code`` (any spelling) belongs to the selectable catalogue."""
    return canonical_language(code) in _NAMES


def language_name(code: str) -> str:
    """Display name for a code, falling back to the upper-cased code."""
    canonical = canonical_language(code)
    return _NAMES.get(canonical, canonical.upper())


def describe_languages(codes: list[str] | tuple[str, ...]) -> str:
    """Join language names as prose: ``"English"``, ``"English or Turkish"``,
    ``"English, Turkish or German"``."""
    names = [language_name(code) for code in codes]
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} or {names[-1]}"
