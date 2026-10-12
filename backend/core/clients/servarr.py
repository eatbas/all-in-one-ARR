"""Shared base for the internal Sonarr/Radarr (Servarr) API clients.

Findarr, Deletarr and Languagarr each need a small outbound client that holds a
base URL + API key and issues authenticated requests against the shared Servarr
v3 contract. This base owns that plumbing (the ``X-Api-Key`` header,
``raise_for_status``, empty-body handling) plus the read endpoints and the
version/identity check more than one feature uses, so the feature clients only
declare the endpoints that are theirs alone.

Each feature client sets :attr:`ServarrClient.error_class` to its own error type
(a :class:`ServarrClientError` subclass) so callers keep catching the specific
error they already expect, and :attr:`ServarrClient.feature_name` so
compatibility messages name the feature that rejected the connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

# Minimum supported application versions shared by every Servarr feature.
_MINIMUM_VERSIONS: dict[str, tuple[int, int, int]] = {
    "sonarr": (4, 0, 0),
    "radarr": (6, 0, 0),
}


class ServarrClientError(RuntimeError):
    """Base error for a Sonarr/Radarr API request that cannot be completed."""


@dataclass(frozen=True)
class Compatibility:
    """Connected Servarr application compatibility result."""

    ok: bool
    app_name: str
    version: str
    detail: str


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a semantic-ish version into a comparable three-part tuple."""
    parts: list[int] = []
    for raw_part in value.split(".")[:3]:
        digits = ""
        for char in raw_part:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def _normalise_app_name(value: str) -> str:
    """Return a comparable application name from a Servarr status payload."""
    return value.strip().lower().replace(" ", "")


class ServarrClient:
    """Async base client for the Servarr v3 API shared by feature clients."""

    error_class: type[ServarrClientError] = ServarrClientError
    # Feature named in compatibility messages ("Findarr requires Sonarr 4+").
    feature_name: str = "aio-arr"

    def __init__(
        self,
        *,
        app: str,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    @property
    def configured(self) -> bool:
        """Whether this client has enough connection data to make requests."""
        return bool(self.base_url and self.api_key)

    @staticmethod
    def _as_dicts(data: Any) -> list[dict[str, Any]]:
        """Return only the dict entries of a JSON list payload."""
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue an authenticated request, raising ``error_class`` on failure."""
        if not self.configured:
            raise self.error_class(f"{self.app} connection is not configured")
        try:
            response = await self._client.request(
                method,
                f"{self.base_url}{path}",
                headers={"X-Api-Key": self.api_key},
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self.error_class(f"{self.app} API request failed: {exc}") from exc
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            # A 200 with a non-JSON body (e.g. a reverse-proxy login page) is a
            # connection problem, not a validation error in the caller's input.
            raise self.error_class(
                f"{self.app} returned a non-JSON response from {path}"
            ) from exc

    async def system_status(self) -> dict[str, Any]:
        """Return `/api/v3/system/status`."""
        data = await self._request("GET", "/api/v3/system/status")
        if not isinstance(data, dict):
            raise self.error_class(f"{self.app} returned an invalid status payload")
        return data

    async def compatibility(self) -> Compatibility:
        """Return whether the connected app is the expected, supported Servarr."""
        status = await self.system_status()
        version = str(status.get("version") or "0.0.0")
        app_name = str(status.get("appName") or self.app)
        expected_name = self.app.capitalize()
        if _normalise_app_name(app_name) != self.app:
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=(
                    f"Connected service is {app_name}; {self.feature_name} expected "
                    f"{expected_name} for the configured {self.app} connection"
                ),
            )
        minimum = _MINIMUM_VERSIONS.get(self.app, (0, 0, 0))
        if parse_version(version) < minimum:
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=(
                    f"{app_name} {version} is unsupported; {self.feature_name} "
                    f"requires {expected_name} {minimum[0]}+"
                ),
            )
        return Compatibility(
            ok=True,
            app_name=app_name,
            version=version,
            detail=f"Connected to {app_name} {version}",
        )

    async def series(self) -> list[dict[str, Any]]:
        """Return `/api/v3/series` (Sonarr): every series with its folder ``path``."""
        return self._as_dicts(await self._request("GET", "/api/v3/series"))

    async def episode_files(self, series_id: int) -> list[dict[str, Any]]:
        """Return `/api/v3/episodefile?seriesId=` (Sonarr): tracked episode files."""
        return self._as_dicts(
            await self._request(
                "GET", "/api/v3/episodefile", params={"seriesId": series_id}
            )
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
