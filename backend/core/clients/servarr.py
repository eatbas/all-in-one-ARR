"""Shared base for the internal Sonarr/Radarr (Servarr) API clients.

Findarr and Deletarr each need a small outbound client that holds a base URL +
API key and issues authenticated requests against the shared Servarr v3 contract.
This base owns that plumbing (the ``X-Api-Key`` header, ``raise_for_status``,
empty-body handling) so the feature clients only declare the endpoints they use.

Each feature client sets :attr:`ServarrClient.error_class` to its own error type
(a :class:`ServarrClientError` subclass) so callers keep catching the specific
error they already expect.
"""

from __future__ import annotations

from typing import Any

import httpx


class ServarrClientError(RuntimeError):
    """Base error for a Sonarr/Radarr API request that cannot be completed."""


class ServarrClient:
    """Async base client for the Servarr v3 API shared by feature clients."""

    error_class: type[ServarrClientError] = ServarrClientError

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
        return response.json()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
