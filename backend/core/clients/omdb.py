"""Outbound OMDb client: rating/poster lookups with API-key rotation.

OMDb returns HTTP 200 even for an invalid key, signalling failure via the JSON
body (``"Response": "False"`` plus an ``"Error"`` message), so the connection
test inspects the body rather than the status alone. A key that has exhausted
its daily request limit (or is invalid) answers HTTP 401: the data lookups
rotate to the next configured key and retry, so several free-tier keys pool
their quotas. The base URL is OMDb's fixed public endpoint and is not
user-configurable; all four keys are UI-managed from the Settings OMDb tab
(the env vars only seed the store).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from core.logging import get_logger

# OMDb's public API base; not user-configurable.
_BASE_URL = "https://www.omdbapi.com"
# A stable, well-known IMDb id used only to probe the key (Ready Player One).
_PROBE_IMDB_ID = "tt3896198"

# Indirection point so tests can control the day rollover deterministically.
_today: Callable[[], str] = lambda: datetime.now(UTC).date().isoformat()  # noqa: E731


def _parse_rating(value: Any) -> float | None:
    """Parse an OMDb ``imdbRating`` (e.g. ``"8.6"`` or ``"N/A"``) to a float."""
    if not value or value == "N/A":
        return None
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _parse_votes(value: Any) -> int | None:
    """Parse an OMDb ``imdbVotes`` (e.g. ``"1,234,567"`` or ``"N/A"``) to an int."""
    if not value or value == "N/A":
        return None
    try:
        return int(str(value).replace(",", ""))
    except TypeError, ValueError:
        return None


class OmdbClient:
    """Async OMDb client with quota-driven rotation across configured keys."""

    def __init__(
        self,
        *,
        api_key: str,
        api_key_2: str = "",
        api_key_3: str = "",
        api_key_4: str = "",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._extra_api_keys = [api_key_2, api_key_3, api_key_4]
        self._log = get_logger("omdb")
        self._client = http_client or httpx.AsyncClient(timeout=30.0)
        # Rotation state: which key the data lookups currently use, reset to
        # the primary on every new UTC day (quotas reset daily).
        self._active_index = 0
        self._active_day = _today()

    def _keys(self) -> list[str]:
        """The ordered, deduplicated key pool: primary first."""
        pool: list[str] = []
        for key in (self._api_key, *self._extra_api_keys):
            if key and key not in pool:
                pool.append(key)
        return pool

    def key_count(self) -> int:
        """How many distinct keys are configured (drives the daily budget)."""
        return len(self._keys())

    def update_credentials(
        self,
        *,
        api_key: str,
        api_key_2: str = "",
        api_key_3: str = "",
        api_key_4: str = "",
    ) -> None:
        """Replace the UI-managed key pool and restart the rotation."""
        self._api_key = api_key
        self._extra_api_keys = [api_key_2, api_key_3, api_key_4]
        self._active_index = 0

    async def _rotating_get(self, params: dict[str, str]) -> httpx.Response | None:
        """GET with the active key, rotating past quota-exhausted keys.

        OMDb answers HTTP 401 both for an exhausted daily quota and an invalid
        key; either way the key is useless right now, so the next one is tried.
        The rotation resets to the primary on a new UTC day (quotas reset).
        Returns the first non-401 response, the final 401 when every key is
        exhausted, or ``None`` on a network error (which is not key-specific,
        so it does not advance the rotation).
        """
        keys = self._keys()
        if not keys:
            return None
        day = _today()
        if day != self._active_day:
            self._active_day = day
            self._active_index = 0
        # The pointer is always in bounds: parking clamps to len-1, and both
        # update_credentials and the day rollover reset it to the primary.
        # Walk a local index and only ever move the shared pointer forward
        # monotonically: concurrent lookups each retry the same failed key at
        # worst, but can never leapfrog a key none of them has tried yet.
        index = self._active_index
        response: httpx.Response | None = None
        while index < len(keys):
            try:
                response = await self._client.get(
                    _BASE_URL, params={**params, "apikey": keys[index]}
                )
            except httpx.HTTPError as exc:
                self._log.debug("OMDb request failed: %s", exc)
                return None
            if response.status_code != 401:
                self._active_index = index
                return response
            if index + 1 < len(keys):
                self._log.info(
                    "OMDb key %d/%d rejected (limit reached or invalid); "
                    "rotating to the next key",
                    index + 1,
                    len(keys),
                )
            index += 1
            # Park on the last key when the whole pool is exhausted, so later
            # calls cost one probe instead of a full sweep.
            self._active_index = max(self._active_index, min(index, len(keys) - 1))
        return response

    async def _probe_key(self, key: str) -> str:
        """Classify one key: ``"ok"``, ``"limited"`` or a failure description.

        ``"limited"`` means the key is valid but has exhausted today's request
        quota (OMDb answers HTTP 401 with a request-limit error) — that must
        not read as a broken key. OMDb also reports an invalid key with HTTP
        200 and ``"Response": "False"``, so the body is inspected either way.
        """
        try:
            response = await self._client.get(
                _BASE_URL, params={"apikey": key, "i": _PROBE_IMDB_ID}
            )
        except httpx.HTTPError as exc:
            return f"connection failed: {exc}"
        try:
            data = response.json()
        except ValueError:
            data = {}
        error = str(data.get("Error") or "")
        if response.status_code == 401:
            if "limit" in error.lower():
                return "limited"
            return error or "invalid API key"
        if response.status_code != 200:
            return f"HTTP {response.status_code}"
        if data.get("Response") == "True":
            return "ok"
        return error or "OMDb rejected the API key"

    async def test_connection(self) -> dict[str, Any]:
        """Probe every configured key and report the pool's health.

        Backs the dashboard's Test connection button, so it sweeps the whole
        pool (one request per key): ``ok`` is true when at least one key is
        configured and none is broken; a quota-exhausted key counts as valid.
        The background status checker uses :meth:`status_probe` instead — this
        sweep would multiply into thousands of requests per day at its cadence.
        """
        keys = self._keys()
        if not keys:
            return {"ok": False, "detail": "No OMDb API key configured"}
        states = await asyncio.gather(*(self._probe_key(key) for key in keys))
        count = len(keys)
        plural = "s" if count != 1 else ""
        problems = [
            f"key {index + 1}: {state}"
            for index, state in enumerate(states)
            if state not in ("ok", "limited")
        ]
        if problems:
            return {
                "ok": False,
                "detail": f"{count} key{plural} configured — " + "; ".join(problems),
            }
        limited = sum(1 for state in states if state == "limited")
        if limited:
            return {
                "ok": True,
                "detail": (
                    f"Connected to OMDb ({count} key{plural} valid, "
                    f"{limited} at today's request limit)"
                ),
            }
        return {"ok": True, "detail": f"Connected to OMDb ({count} key{plural} OK)"}

    async def status_probe(self) -> dict[str, Any]:
        """Cheap health probe for the background status checker.

        Probes only the first configured key: the checker runs every 30–60
        seconds, so sweeping the whole pool there would burn thousands of OMDb
        requests per day. The dashboard's Test button uses
        :meth:`test_connection` for the full per-key report.
        """
        keys = self._keys()
        if not keys:
            return {"ok": False, "detail": "No OMDb API key configured"}
        state = await self._probe_key(keys[0])
        if state == "ok":
            return {"ok": True, "detail": "Connected to OMDb"}
        if state == "limited":
            return {
                "ok": True,
                "detail": "Connected to OMDb (key at today's request limit)",
            }
        return {"ok": False, "detail": f"OMDb: {state}"}

    async def fetch_rating(self, *, imdb_id: str) -> dict[str, Any] | None:
        """Return ``{"imdb_rating", "imdb_votes"}`` for an IMDb id, or ``None``.

        Reads ``imdbRating`` and ``imdbVotes`` from an OMDb lookup, rotating to
        the next configured key when the active one is quota-exhausted. The
        distinction in the return value matters: a **dict** is a definitive
        OMDb answer — including a genuine ``"N/A"``, which yields null values —
        and may be cached; ``None`` means the lookup **failed** (no key, every
        key rejected, network error, non-200, non-JSON) and must be retried
        later rather than remembered as "no rating". Never raises.
        """
        response = await self._rotating_get({"i": imdb_id})
        if response is None or response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return {
            "imdb_rating": _parse_rating(data.get("imdbRating")),
            "imdb_votes": _parse_votes(data.get("imdbVotes")),
        }

    async def fetch_poster(self, *, imdb_id: str) -> bytes | None:
        """Return poster image bytes for an IMDb id, or ``None`` if unavailable.

        Looks the title up by IMDb id (rotating past quota-exhausted keys),
        reads its ``Poster`` URL (OMDb reports a missing poster as the literal
        ``"N/A"``) and downloads it. Never raises: any error degrades to
        ``None``.
        """
        response = await self._rotating_get({"i": imdb_id})
        if response is None or response.status_code != 200:
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        poster = data.get("Poster")
        if not poster or poster == "N/A":
            return None
        try:
            image = await self._client.get(poster)
        except httpx.HTTPError as exc:
            self._log.debug("OMDb poster download failed for %s: %s", poster, exc)
            return None
        if image.status_code != 200:
            return None
        return image.content

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
