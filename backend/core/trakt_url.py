"""Parse a Trakt list URL into its ``(owner_user, slug)`` parts.

The dashboard lets a user add a list by pasting its Trakt URL, for example
``https://trakt.tv/users/me/lists/anime``. This module isolates the (small but
fiddly) parsing and validation so it can be unit-tested independently.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# /users/{user}/lists/{slug-or-id}, ignoring any trailing path/query/fragment.
_LIST_PATH_RE = re.compile(r"^/users/(?P<user>[^/]+)/lists/(?P<slug>[^/?#]+)")


class TraktUrlError(ValueError):
    """Raised when a string is not a recognisable Trakt list URL."""


def parse_trakt_list_url(url: str) -> tuple[str, str]:
    """Return ``(owner_user, slug)`` for a Trakt list URL.

    Accepts URLs with or without a scheme (``https://`` is assumed when absent).
    Raises :class:`TraktUrlError` for anything that is not a ``trakt.tv`` list URL.
    """
    raw = url.strip()
    if not raw:
        raise TraktUrlError("Empty URL")
    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host != "trakt.tv" and not host.endswith(".trakt.tv"):
        raise TraktUrlError(f"Not a trakt.tv URL: {url!r}")

    match = _LIST_PATH_RE.match(parsed.path)
    if not match:
        raise TraktUrlError(f"Not a Trakt list URL: {url!r}")

    return match.group("user"), match.group("slug")
