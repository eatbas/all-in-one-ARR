"""Outbound, read-only Plex Media Server client (connection test + watch state).

Remindarr reads three things from Plex: the TV library sections, each show's
external GUIDs (to match Sonarr series by TVDB id) and each matched show's
episodes with their watch count. All requests go to the official PMS HTTP API
with ``Accept: application/json``.

The X-Plex-Token is sent **only** in the ``X-Plex-Token`` request header — never
in the query string — so it cannot leak into request URLs, httpx error messages
or logs. Plex scopes watch state (``viewCount``) to the account that owns the
token, so results reflect that one account. Nothing here ever writes to Plex.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, NamedTuple
from urllib.parse import quote

import httpx

from core.coerce import coerce_int, parse_int, stripped_text

# Only the modern Plex agents' ``Guid`` entries are parsed; the legacy
# ``com.plexapp.agents.thetvdb://`` item ``guid`` is deliberately ignored.
_TVDB_GUID = re.compile(r"tvdb://(\d+)")


class PlexClientError(RuntimeError):
    """Raised when a Plex request cannot be completed.

    ``status_code`` carries the HTTP status when Plex answered with an error
    response (401 for a rejected token), and is ``None`` for transport failures,
    an unconfigured connection and invalid payloads.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PlexShow(NamedTuple):
    """One show in a Plex TV library section."""

    rating_key: str
    title: str
    tvdb_ids: frozenset[int]


class PlexEpisode(NamedTuple):
    """One episode of a Plex show with the token owner's watch count."""

    season: int
    episode: int
    view_count: int


def parse_tvdb_guid(guid_entries: Any) -> set[int]:
    """Return the TVDB ids in a Plex ``Guid`` array (``[{"id": "tvdb://123"}]``).

    Anything that is not a list of ``{"id": "tvdb://<digits>"}`` entries is
    ignored, so IMDb/TMDB-only items, malformed entries and non-positive ids
    yield no TVDB id.
    """
    if not isinstance(guid_entries, list):
        return set()
    ids: set[int] = set()
    for entry in guid_entries:
        if not isinstance(entry, Mapping):
            continue
        match = _TVDB_GUID.fullmatch(stripped_text(entry.get("id")))
        if match is not None and int(match.group(1)) > 0:
            ids.add(int(match.group(1)))
    return ids


def _collection(container: dict[str, Any], key: str, path: str) -> list[dict[str, Any]]:
    """Return the dict entries of a container's ``key`` list (``Metadata``…).

    Plex omits the list from an empty container, so a missing list is a valid
    empty result only while ``size`` is absent or zero. A non-list value, or a
    missing list beside a positive ``size``, is a malformed or incomplete
    payload and raises :class:`PlexClientError`: treating it as empty would
    replace the last good results with nothing. Individual non-dict entries are
    skipped, as are entries the callers cannot use.
    """
    items = container.get(key)
    if items is None:
        if coerce_int(container.get("size"), 0) > 0:
            raise PlexClientError(f"Plex returned an incomplete {key} list from {path}")
        return []
    if not isinstance(items, list):
        raise PlexClientError(f"Plex returned an invalid {key} list from {path}")
    return [item for item in items if isinstance(item, dict)]


class PlexClient:
    """Async, read-only client for the Plex Media Server HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    def update_credentials(self, *, base_url: str, api_key: str) -> None:
        """Replace the in-use base URL and X-Plex-Token (set from the dashboard)."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    @property
    def configured(self) -> bool:
        """Whether both a server URL and a token are set."""
        return bool(self._base_url.strip() and self._api_key.strip())

    def _headers(self) -> dict[str, str]:
        """Return the JSON + token headers shared by every Plex request.

        The token is stripped of stray whitespace (e.g. a trailing newline from
        a paste), which would otherwise be an illegal header value.
        """
        return {
            "Accept": "application/json",
            "X-Plex-Token": self._api_key.strip(),
        }

    async def test_connection(self) -> dict[str, Any]:
        """Validate the URL + token against ``GET /`` (the server identity).

        Returns ``{ok, detail}``; never raises for an expected failure so the
        dashboard can show the reason. A blank URL or token is reported without
        a request.
        """
        if not self._base_url.strip():
            return {"ok": False, "detail": "Plex URL is not set"}
        if not self._api_key.strip():
            return {"ok": False, "detail": "Plex token is not set"}
        try:
            container = await self._get_container("/")
        except PlexClientError as exc:
            return {"ok": False, "detail": str(exc)}
        name = stripped_text(container.get("friendlyName"))
        version = stripped_text(container.get("version"))
        detail = "Connected to Plex Media Server"
        if name:
            detail += f" “{name}”"
        if version:
            detail += f" (version {version})"
        return {"ok": True, "detail": detail}

    async def show_sections(self) -> list[str]:
        """Return the keys of every TV (``type == "show"``) library section."""
        path = "/library/sections"
        container = await self._get_container(path)
        return [
            key
            for directory in _collection(container, "Directory", path)
            if directory.get("type") == "show"
            and (key := stripped_text(str(directory.get("key") or "")))
        ]

    async def shows(self, section_key: str) -> list[PlexShow]:
        """Return a TV section's shows with the TVDB ids from their GUIDs."""
        path = f"/library/sections/{quote(section_key, safe='')}/all"
        container = await self._get_container(path, params={"includeGuids": 1})
        shows: list[PlexShow] = []
        for item in _collection(container, "Metadata", path):
            rating_key = stripped_text(str(item.get("ratingKey") or ""))
            if not rating_key:
                continue
            shows.append(
                PlexShow(
                    rating_key=rating_key,
                    title=stripped_text(item.get("title")),
                    tvdb_ids=frozenset(parse_tvdb_guid(item.get("Guid"))),
                )
            )
        return shows

    async def episodes(self, rating_key: str) -> list[PlexEpisode]:
        """Return every episode (``allLeaves``) of one show with its watch count.

        An episode without a numeric season (``parentIndex``) or episode
        (``index``) number cannot be matched and is skipped. A missing
        ``viewCount`` means the token owner has not watched it.
        """
        path = f"/library/metadata/{quote(rating_key, safe='')}/allLeaves"
        container = await self._get_container(path)
        episodes: list[PlexEpisode] = []
        for item in _collection(container, "Metadata", path):
            season = parse_int(item.get("parentIndex"))
            number = parse_int(item.get("index"))
            if season is None or number is None:
                continue
            episodes.append(
                PlexEpisode(
                    season=season,
                    episode=number,
                    view_count=max(coerce_int(item.get("viewCount"), 0), 0),
                )
            )
        return episodes

    async def _get_container(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET ``path`` and return its ``MediaContainer``; raise on any failure."""
        if not self.configured:
            raise PlexClientError("Plex connection is not configured")
        try:
            response = await self._client.get(
                f"{self._base_url}{path}", headers=self._headers(), params=params
            )
        except httpx.HTTPError as exc:
            raise PlexClientError(f"Connection to Plex failed: {exc}") from exc
        if response.status_code in (401, 403):
            raise PlexClientError(
                "Plex rejected the token", status_code=response.status_code
            )
        if response.status_code != 200:
            raise PlexClientError(
                f"Plex returned HTTP {response.status_code} from {path}",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise PlexClientError(
                f"Plex returned a non-JSON response from {path}"
            ) from exc
        container = data.get("MediaContainer") if isinstance(data, dict) else None
        if not isinstance(container, dict):
            raise PlexClientError(f"Plex returned an invalid payload from {path}")
        return container

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
