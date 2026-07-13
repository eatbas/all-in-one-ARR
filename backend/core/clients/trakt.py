"""Trakt API client: device auth, token refresh, list read and list remove.

Only official REST endpoints are used.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

from core.logging import get_logger, log_action
from core.trakt_url import OFFICIAL_OWNER

TRAKT_BASE_URL = "https://api.trakt.tv"

# Maps the app's media type onto Trakt's path segment for discovery endpoints.
_MEDIA_SEGMENT = {"movie": "movies", "show": "shows"}


def _is_official(owner_user: str) -> bool:
    """Return True when the owner is the Trakt-curated official account."""
    return owner_user == OFFICIAL_OWNER


_OAUTH_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"
# Refresh this many seconds before the access token actually expires.
_REFRESH_MARGIN_SECONDS = 24 * 60 * 60

# Indirection points so tests can control time and sleeping deterministically.
_now: Callable[[], float] = time.time
_monotonic: Callable[[], float] = time.monotonic
_sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


class TraktAuthError(RuntimeError):
    """Raised when an authenticated call is attempted without valid tokens."""


class TraktClient:
    """Async client for the subset of the Trakt API the service needs."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_store_path: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_store_path = token_store_path
        self._log = get_logger("trakt")
        self._tokens: dict[str, Any] | None = None
        self._client = http_client or httpx.AsyncClient(
            base_url=TRAKT_BASE_URL, timeout=30.0
        )

    # ---- credentials ----

    def update_credentials(self, *, client_id: str, client_secret: str) -> None:
        """Replace the in-use Trakt credentials (set from the dashboard).

        Subsequent authenticated calls and any new device-auth use these values,
        so a credential change in the UI takes effect without a restart.
        """
        self._client_id = client_id
        self._client_secret = client_secret

    # ---- headers ----

    async def _auth_headers(self) -> dict[str, str]:
        """Headers for authenticated calls (list read/remove/add)."""
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self._client_id,
            "Authorization": f"Bearer {await self.ensure_token()}",
        }

    def _public_headers(self) -> dict[str, str]:
        """Headers for public endpoints (trending/popular): API key only.

        Trakt's discovery endpoints require only the API key, not an OAuth bearer
        token, so they work even before the account is authorised.
        """
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self._client_id,
        }

    # ---- token store ----

    def load_tokens(self) -> None:
        """Load persisted tokens from disk, if present."""
        path = Path(self._token_store_path)
        if path.exists():
            self._tokens = json.loads(path.read_text(encoding="utf-8"))
            self._log.info("loaded persisted Trakt tokens")
        else:
            self._tokens = None
            self._log.info("no persisted Trakt tokens found")

    def _save_tokens(self, data: dict[str, Any]) -> None:
        expires_at = _now() + float(data.get("expires_in", 0))
        self._tokens = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": expires_at,
        }
        path = Path(self._token_store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._tokens), encoding="utf-8")
        os.chmod(path, 0o600)
        self._log.info("persisted refreshed Trakt tokens")

    def is_authenticated(self) -> bool:
        """Whether usable tokens are loaded."""
        return bool(self._tokens and self._tokens.get("access_token"))

    # ---- device auth ----

    async def request_device_code(self) -> dict[str, Any]:
        """Begin device auth; logs the user code and verification URL."""
        response = await self._client.post(
            "/oauth/device/code",
            headers={"Content-Type": "application/json"},
            json={"client_id": self._client_id},
        )
        response.raise_for_status()
        data = response.json()
        self._log.warning(
            "Trakt authorisation required: visit %s and enter code %s",
            data.get("verification_url"),
            data.get("user_code"),
        )
        return data

    async def poll_for_token(self, device: dict[str, Any]) -> bool:
        """Poll for an access token until the device code is authorised or expires.

        Returns ``True`` on success, ``False`` if the code expired or was denied.
        """
        interval = float(device.get("interval", 5))
        deadline = _monotonic() + float(device.get("expires_in", 600))
        while _monotonic() < deadline:
            response = await self._client.post(
                "/oauth/device/token",
                headers={"Content-Type": "application/json"},
                json={
                    "code": device["device_code"],
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            if response.status_code == 200:
                self._save_tokens(response.json())
                self._log.info("Trakt device authorisation complete")
                return True
            if response.status_code == 400:
                # Authorisation still pending; wait and retry.
                await _sleep(interval)
                continue
            # 404/409/410/418/429 etc: stop polling.
            self._log.error(
                "Trakt device authorisation failed (status=%s)",
                response.status_code,
            )
            return False
        self._log.error("Trakt device authorisation timed out")
        return False

    # ---- token refresh ----

    async def ensure_token(self) -> str:
        """Return a valid access token, refreshing proactively when near expiry."""
        if not self.is_authenticated():
            raise TraktAuthError("Trakt is not authenticated; run device auth first")
        assert self._tokens is not None
        expires_at = float(self._tokens.get("expires_at", 0))
        if _now() >= expires_at - _REFRESH_MARGIN_SECONDS:
            await self._refresh()
        return self._tokens["access_token"]

    async def _refresh(self) -> None:
        """Refresh the access token without blocking the event loop."""
        assert self._tokens is not None
        response = await self._client.post(
            "/oauth/token",
            headers={"Content-Type": "application/json"},
            json={
                "refresh_token": self._tokens["refresh_token"],
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "redirect_uri": _OAUTH_REDIRECT,
            },
        )
        if response.status_code != 200:
            raise TraktAuthError(
                f"Trakt token refresh failed (status={response.status_code})"
            )
        self._save_tokens(response.json())

    # ---- list discovery ----

    @staticmethod
    def _normalise_list(entry: dict[str, Any], owner_user: str) -> dict[str, Any]:
        """Normalise a Trakt list object into a compact dict.

        Official curated lists must be addressed by their numeric Trakt id on the
        items/remove endpoints, so for official lists the numeric id is used as the
        stored slug. User lists continue to use their slug.
        """
        ids = entry.get("ids") or {}
        slug: str | None
        if _is_official(owner_user):
            if not ids.get("trakt"):
                raise ValueError("Official list response missing numeric trakt id")
            slug = str(ids["trakt"])
        else:
            slug = ids.get("slug") or (str(ids["trakt"]) if ids.get("trakt") else None)
        return {
            "name": entry.get("name"),
            "slug": slug,
            "owner_user": owner_user,
            "item_count": entry.get("item_count"),
        }

    async def get_user_lists(self, *, user: str | None = None) -> list[dict[str, Any]]:
        """Return all of a user's lists (name, slug, owner, item count).

        Defaults to the connected account (``me``); pass ``user`` to discover
        another account's public lists.
        """
        owner = user or "me"
        response = await self._client.get(
            f"/users/{owner}/lists", headers=await self._auth_headers()
        )
        response.raise_for_status()
        lists = [self._normalise_list(entry, owner) for entry in response.json()]
        return [item for item in lists if item["slug"]]

    async def get_list_summary(
        self, *, owner_user: str, slug: str
    ) -> dict[str, Any] | None:
        """Return a single list's summary, or ``None`` if it does not exist.

        Official curated lists live under the generic ``/lists/{slug}`` endpoint,
        whereas user lists are under ``/users/{owner_user}/lists/{slug}``.
        """
        if _is_official(owner_user):
            path = f"/lists/{slug}"
        else:
            path = f"/users/{owner_user}/lists/{slug}"
        response = await self._client.get(path, headers=await self._auth_headers())
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._normalise_list(response.json(), owner_user)

    # ---- discovery (trending / popular) ----

    @staticmethod
    def _discovery_params(limit: int, genres: str | None) -> dict[str, Any]:
        """Query parameters shared by the trending and popular endpoints.

        ``genres`` is Trakt's comma-separated genre-slug filter (e.g. ``anime``),
        omitted from the request when not set.
        """
        params: dict[str, Any] = {"limit": limit}
        if genres:
            params["genres"] = genres
        return params

    @staticmethod
    def _discovery_row(obj: dict[str, Any], media_type: str) -> dict[str, Any]:
        """Normalise a Trakt movie/show object into a uniform discovery row.

        The shape matches the rows the TMDB and Seer clients emit so
        :mod:`core.trending` can map every source the same way.
        """
        ids = obj.get("ids") or {}
        return {
            "media_type": media_type,
            "tmdb": ids.get("tmdb"),
            "imdb": ids.get("imdb"),
            "tvdb": ids.get("tvdb"),
            "trakt": ids.get("trakt"),
            # The slug deep-links to the title's trakt.tv page; only Trakt rows
            # carry it (TMDB/Seer rows leave it unset and so it normalises to None).
            "slug": ids.get("slug"),
            "title": obj.get("title"),
            "year": obj.get("year"),
        }

    async def get_trending(
        self, *, media_type: str, limit: int = 20, genres: str | None = None
    ) -> list[dict[str, Any]]:
        """Return Trakt trending movies or shows as uniform discovery rows.

        ``media_type`` is ``movie`` or ``show``. Trakt wraps each trending entry in
        a ``{"watchers": N, "<media>": {...}}`` object; the inner media object is
        unwrapped and normalised. Uses the public (API-key-only) headers. See
        :meth:`_discovery_params` for the ``genres`` filter.
        """
        segment = _MEDIA_SEGMENT[media_type]
        response = await self._client.get(
            f"/{segment}/trending",
            headers=self._public_headers(),
            params=self._discovery_params(limit, genres),
        )
        response.raise_for_status()
        return [
            self._discovery_row(entry[media_type], media_type)
            for entry in response.json()
            if isinstance(entry.get(media_type), dict)
        ]

    async def get_popular(
        self, *, media_type: str, limit: int = 20, genres: str | None = None
    ) -> list[dict[str, Any]]:
        """Return Trakt popular movies or shows as uniform discovery rows.

        ``media_type`` is ``movie`` or ``show``. Unlike trending, the popular
        endpoint returns flat media objects (no ``watchers`` wrapper). See
        :meth:`_discovery_params` for the ``genres`` filter.
        """
        segment = _MEDIA_SEGMENT[media_type]
        response = await self._client.get(
            f"/{segment}/popular",
            headers=self._public_headers(),
            params=self._discovery_params(limit, genres),
        )
        response.raise_for_status()
        return [
            self._discovery_row(entry, media_type)
            for entry in response.json()
            if isinstance(entry, dict)
        ]

    async def lookup_ids(
        self,
        *,
        id_type: Literal["tmdb", "imdb", "tvdb"],
        id_value: int | str,
        media_type: str,
    ) -> dict[str, int | str] | None:
        """Resolve an external id to a Trakt item's id set via the ID-lookup search.

        Discovery rows outside the Trakt tabs carry no ``trakt`` id, which
        Trakt's list-add resolves unreliably from weak ids (the title can land
        in ``not_found``). Looking the strongest known id up first yields the
        ``trakt`` id (plus ``imdb``/``tvdb``/``tmdb``) so the add posts a strong
        id. Uses the public (API-key-only) headers, like the discovery
        endpoints. Returns the matched item's id mapping, or ``None`` when
        nothing matches. TVDB lookups are only valid for shows — Trakt does not
        index movies by TVDB id — so callers gate that id type accordingly.
        """
        search_type = "movie" if media_type == "movie" else "show"
        # The id value originates from a request body, so it is quoted into a
        # single path segment rather than interpolated raw into the URL.
        response = await self._client.get(
            f"/search/{id_type}/{quote(str(id_value), safe='')}",
            headers=self._public_headers(),
            params={"type": search_type},
        )
        response.raise_for_status()
        for entry in response.json():
            if entry.get("type") == search_type:
                ids = (entry.get(search_type) or {}).get("ids") or {}
                wanted = {
                    key: ids[key]
                    for key in ("trakt", "imdb", "tvdb", "tmdb")
                    if ids.get(key) is not None
                }
                if wanted:
                    return wanted
        return None

    async def test_connection(self) -> dict[str, Any]:
        """Verify the saved token by reading the account settings.

        Returns ``{"ok": True, "detail": "...", "username": ...}`` on success and
        ``{"ok": False, "detail": "...", "username": None}`` on failure so the
        status checker can treat Trakt like every other managed client.
        """
        try:
            response = await self._client.get(
                "/users/settings", headers=await self._auth_headers()
            )
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - expected failures are surfaced in detail
            return {
                "ok": False,
                "detail": f"Trakt connection failed: {exc}",
                "username": None,
            }
        data = response.json()
        username = (data.get("user") or {}).get("username")
        return {
            "ok": True,
            "detail": f"Connected as {username}" if username else "Connected to Trakt",
            "username": username,
        }

    # ---- list read ----

    def _list_read_path(self, owner_user: str, list_id: str) -> str:
        if list_id.strip().lower() == "watchlist":
            return "/sync/watchlist/movies,shows"
        if _is_official(owner_user):
            return f"/lists/{list_id}/items/movies,shows"
        return f"/users/{owner_user}/lists/{list_id}/items/movies,shows"

    def _list_remove_path(self, owner_user: str, list_id: str) -> str:
        if list_id.strip().lower() == "watchlist":
            return "/sync/watchlist/remove"
        # Deliberate symmetry with _list_read_path; in production, removal is skipped
        # upstream for lists not owned by "me", so this branch is currently unreachable.
        if _is_official(owner_user):
            return f"/lists/{list_id}/items/remove"
        return f"/users/{owner_user}/lists/{list_id}/items/remove"

    def _list_add_path(self, owner_user: str, list_id: str) -> str:
        # Adds only target personal lists the account owns (the dashboard restricts
        # the destination to owned, tracked, non-watchlist lists), mirroring the
        # read/remove path construction.
        return f"/users/{owner_user}/lists/{list_id}/items"

    async def read_list_items(
        self, *, list_id: str, owner_user: str | None = None
    ) -> list[dict[str, Any]]:
        """Read and normalise a Trakt list (or the watchlist).

        ``owner_user`` defaults to the connected account (``me``). Follows Trakt
        pagination via the ``X-Pagination-Page-Count`` header so lists larger than
        a single page are fully synced.
        """
        owner = owner_user or "me"
        path = self._list_read_path(owner, list_id)
        headers = await self._auth_headers()
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await self._client.get(
                path, headers=headers, params={"page": page, "limit": 100}
            )
            response.raise_for_status()
            for entry in response.json():
                media_type = entry.get("type")
                obj = entry.get(media_type) if media_type else None
                if not isinstance(obj, dict):
                    continue
                ids = obj.get("ids") or {}
                items.append(
                    {
                        "trakt_id": ids.get("trakt"),
                        "type": media_type,
                        "title": obj.get("title"),
                        "year": obj.get("year"),
                        "tmdb": ids.get("tmdb"),
                        "tvdb": ids.get("tvdb"),
                        "imdb": ids.get("imdb"),
                        "ids": ids,
                    }
                )
            page_count = int(response.headers.get("X-Pagination-Page-Count", 1))
            if page >= page_count:
                break
            page += 1
        return items

    # ---- list remove ----

    async def remove_items(
        self,
        *,
        movies: list[int] | None = None,
        shows: list[int] | None = None,
        list_id: str,
        owner_user: str | None = None,
    ) -> dict[str, Any]:
        """Remove items from a Trakt list.

        ``movies`` are TMDB ids; ``shows`` are TVDB ids. ``owner_user`` defaults to
        the connected account (``me``).
        """
        owner = owner_user or "me"
        movie_ids = movies or []
        show_ids = shows or []
        body = {
            "movies": [{"ids": {"tmdb": tmdb}} for tmdb in movie_ids],
            "shows": [{"ids": {"tvdb": tvdb}} for tvdb in show_ids],
        }
        response = await self._client.post(
            self._list_remove_path(owner, list_id),
            headers=await self._auth_headers(),
            json=body,
        )
        response.raise_for_status()
        log_action(
            self._log,
            "trakt_remove",
            list_id=list_id,
            movies=",".join(str(m) for m in movie_ids) or None,
            shows=",".join(str(s) for s in show_ids) or None,
        )
        return response.json()

    async def add_items(
        self,
        *,
        movies: list[dict[str, int | str]] | None = None,
        shows: list[dict[str, int | str]] | None = None,
        list_id: str,
        owner_user: str | None = None,
    ) -> dict[str, Any]:
        """Add items to a personal Trakt list.

        ``movies`` and ``shows`` are lists of Trakt ``ids`` mappings (e.g.
        ``{"tmdb": 680}``); Trakt accepts a TMDB id for both movies and shows on
        add, so a TMDB id alone is sufficient. ``owner_user`` defaults to the
        connected account (``me``). Returns Trakt's added/not-found summary (or an
        empty dict when the response carries no body).
        """
        owner = owner_user or "me"
        movie_ids = movies or []
        show_ids = shows or []
        body = {
            "movies": [{"ids": ids} for ids in movie_ids],
            "shows": [{"ids": ids} for ids in show_ids],
        }
        response = await self._client.post(
            self._list_add_path(owner, list_id),
            headers=await self._auth_headers(),
            json=body,
        )
        response.raise_for_status()
        log_action(
            self._log,
            "trakt_add",
            list_id=list_id,
            movies=",".join(str(ids) for ids in movie_ids) or None,
            shows=",".join(str(ids) for ids in show_ids) or None,
        )
        return response.json() if response.content else {}

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
