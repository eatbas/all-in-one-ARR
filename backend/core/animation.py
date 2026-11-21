"""Shared rules for the Trending page's Animation genre view.

The Trakt, TMDB and Seer tabs offer an "All | Animation" toggle whose Animation
feeds (``trakt-animation`` / ``tmdb-animation`` / ``seer-animation``) show
animated titles with Japanese anime left out, because the Anime tab already
covers anime. TMDB and Seer both serve TMDB-shaped data (Seer proxies TMDB), so
they share one genre id and one exclusion rule; Trakt uses genre slugs instead.

Anime is identified by a Japanese original language. Two missing-field policies
apply, because the providers filter differently:

* Discover feeds are already filtered to the Animation genre by the provider, so
  a row is kept unless it positively reports a Japanese original language.
* Search endpoints accept no genre filter, so a row is kept only when its genre
  ids positively include Animation and its language is not Japanese.

Everything here is a constant or a pure function, so the module holds no state.
"""

from __future__ import annotations

from typing import Final

# TMDB's Animation genre id; Seer shares it because it proxies TMDB.
ANIMATION_GENRE_ID: Final = 16
# The original language that marks a title as anime for the exclusion rule.
ANIME_ORIGINAL_LANGUAGE: Final = "ja"
# Trakt genre slugs: the Animation feed includes the first and excludes the second.
TRAKT_ANIMATION_GENRE: Final = "animation"
TRAKT_ANIME_GENRE: Final = "anime"


def is_anime_language(original_language: object) -> bool:
    """Whether ``original_language`` positively marks a title as anime.

    Only the exact string :data:`ANIME_ORIGINAL_LANGUAGE` matches; a missing or
    non-string value is not evidence of anime.
    """
    return original_language == ANIME_ORIGINAL_LANGUAGE


def keeps_discover_row(original_language: object) -> bool:
    """Whether a provider-filtered Animation discover row is kept.

    The provider has already restricted the feed to the Animation genre, so the
    row is dropped only when it positively reports a Japanese original language.
    """
    return not is_anime_language(original_language)


def keeps_search_row(genre_ids: object, original_language: object) -> bool:
    """Whether a title-search row belongs in the Animation view.

    Search endpoints apply no genre filter, so the row must positively list
    :data:`ANIMATION_GENRE_ID` in ``genre_ids`` and must not report a Japanese
    original language. A missing or non-list ``genre_ids`` drops the row.
    """
    if not isinstance(genre_ids, list):
        return False
    return ANIMATION_GENRE_ID in genre_ids and not is_anime_language(original_language)
