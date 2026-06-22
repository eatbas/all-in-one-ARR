"""Tests for core.trakt_url."""

from __future__ import annotations

import pytest

from core.trakt_url import TraktUrlError, parse_trakt_list_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://trakt.tv/users/me/lists/anime", ("me", "anime")),
        ("http://trakt.tv/users/sean/lists/top-100", ("sean", "top-100")),
        ("trakt.tv/users/me/lists/movies", ("me", "movies")),  # no scheme
        ("https://trakt.tv/users/me/lists/123", ("me", "123")),  # numeric id
        ("https://www.trakt.tv/users/me/lists/anime?sort=rank", ("me", "anime")),
        ("https://trakt.tv/users/me/lists/anime/comments", ("me", "anime")),
        ("  https://trakt.tv/users/me/lists/anime  ", ("me", "anime")),  # trimmed
    ],
)
def test_parse_valid_urls(url, expected) -> None:
    assert parse_trakt_list_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "https://example.com/users/me/lists/anime",  # wrong host
        "https://trakt.tv/movies/popular",  # not a list path
        "https://trakt.tv/users/me",  # missing /lists/
    ],
)
def test_parse_invalid_urls(url) -> None:
    with pytest.raises(TraktUrlError):
        parse_trakt_list_url(url)
