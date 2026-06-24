"""Trakt API client: device auth, token refresh, list read and list remove.

Only official REST endpoints are used. Writes (list removal) honour the live
DRY_RUN flag via the injected ``dry_run_provider`` callable: when DRY_RUN is on
the exact payload is logged and a simulated result returned, with no request
sent.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from core.logging import get_logger, log_action

TRAKT_BASE_URL = "https://api.trakt.tv"
_OAUTH_REDIRECT = "urn:ietf:wg:oauth:2.0:oob"
# Refresh this many seconds before the access token actually expires.
_REFRESH_MARGIN_SECONDS = 24 * 60 * 60

# Indirection points so tests can control time and sleeping deterministically.
_now: Callable[[], float] = time.time
_monotonic: Callable[[], float] = time.monotonic
_sleep: Callable[[float], "asyncio.Future[None]"] = asyncio.sleep


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
        dry_run_provider: Callable[[], bool],
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_store_path = token_store_path
        self._dry_run_provider = dry_run_provider
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
        """Headers for authenticated calls (list read/remove)."""
        return {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": self._client_id,
            "Authorization": f"Bearer {await self.ensure_token()}",
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
        """Normalise a Trakt list object into a compact dict."""
        ids = entry.get("ids") or {}
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
        """Return a single list's summary, or ``None`` if it does not exist."""
        response = await self._client.get(
            f"/users/{owner_user}/lists/{slug}", headers=await self._auth_headers()
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return self._normalise_list(response.json(), owner_user)

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
        return f"/users/{owner_user}/lists/{list_id}/items/movies,shows"

    def _list_remove_path(self, owner_user: str, list_id: str) -> str:
        if list_id.strip().lower() == "watchlist":
            return "/sync/watchlist/remove"
        return f"/users/{owner_user}/lists/{list_id}/items/remove"

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
        the connected account (``me``). Honours DRY_RUN: when on, the payload is
        logged and a simulated result is returned without sending.
        """
        owner = owner_user or "me"
        movie_ids = movies or []
        show_ids = shows or []
        body = {
            "movies": [{"ids": {"tmdb": tmdb}} for tmdb in movie_ids],
            "shows": [{"ids": {"tvdb": tvdb}} for tvdb in show_ids],
        }
        dry_run = self._dry_run_provider()
        if dry_run:
            log_action(
                self._log,
                "trakt_remove_skipped",
                dry_run=True,
                list_id=list_id,
                movies=",".join(str(m) for m in movie_ids) or None,
                shows=",".join(str(s) for s in show_ids) or None,
            )
            return {"dry_run": True, "would_remove": body}

        response = await self._client.post(
            self._list_remove_path(owner, list_id),
            headers=await self._auth_headers(),
            json=body,
        )
        response.raise_for_status()
        log_action(
            self._log,
            "trakt_remove",
            dry_run=False,
            list_id=list_id,
            movies=",".join(str(m) for m in movie_ids) or None,
            shows=",".join(str(s) for s in show_ids) or None,
        )
        return response.json()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
