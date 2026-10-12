"""Outbound Sonarr client for Languagarr's audit, search and delete actions.

Series and episode-file listing, the system-status call and the version check
are inherited from :class:`ServarrClient`; this client adds only the endpoints
Languagarr alone needs. Deletion goes through Sonarr's own API so Sonarr stays
the owner of the file (and of its recycle-bin behaviour) — Languagarr never
touches the filesystem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from core.clients.servarr import ServarrClient, ServarrClientError

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class LanguagarrClientError(ServarrClientError):
    """Raised when a Sonarr request made by Languagarr cannot be completed."""


class LanguagarrSonarrClient(ServarrClient):
    """Sonarr client exposing the endpoints Languagarr needs."""

    error_class = LanguagarrClientError
    feature_name = "Languagarr"

    async def quality_profiles(self) -> list[dict[str, Any]]:
        """Return `/api/v3/qualityprofile` (id, name, cutoffFormatScore, ...)."""
        return self._as_dicts(await self._request("GET", "/api/v3/qualityprofile"))

    async def episodes(self, series_id: int) -> list[dict[str, Any]]:
        """Return `/api/v3/episode?seriesId=`; each carries ``episodeFileId``."""
        return self._as_dicts(
            await self._request(
                "GET", "/api/v3/episode", params={"seriesId": series_id}
            )
        )

    async def episodes_for_file(self, episode_file_id: int) -> list[dict[str, Any]]:
        """Return `/api/v3/episode?episodeFileId=`: the episodes one file covers."""
        return self._as_dicts(
            await self._request(
                "GET", "/api/v3/episode", params={"episodeFileId": episode_file_id}
            )
        )

    async def series_by_id(self, series_id: int) -> dict[str, Any] | None:
        """Return `/api/v3/series/{id}`, or ``None`` when Sonarr reports 404."""
        try:
            data = await self._request("GET", f"/api/v3/series/{series_id}")
        except LanguagarrClientError as exc:
            if _is_not_found(exc):
                return None
            raise
        if not isinstance(data, dict):
            raise LanguagarrClientError(
                f"{self.app} returned an invalid series payload"
            )
        return data

    async def episode_file(self, episode_file_id: int) -> dict[str, Any] | None:
        """Return `/api/v3/episodefile/{id}`, or ``None`` when Sonarr reports 404."""
        try:
            data = await self._request("GET", f"/api/v3/episodefile/{episode_file_id}")
        except LanguagarrClientError as exc:
            if _is_not_found(exc):
                return None
            raise
        if not isinstance(data, dict):
            raise LanguagarrClientError(
                f"{self.app} returned an invalid episode file payload"
            )
        return data

    async def delete_episode_file(self, episode_file_id: int) -> None:
        """Delete one episode file through Sonarr (`DELETE /api/v3/episodefile/{id}`)."""
        await self._request("DELETE", f"/api/v3/episodefile/{episode_file_id}")

    async def episode_search(self, episode_ids: list[int]) -> None:
        """Queue a Sonarr ``EpisodeSearch`` command for ``episode_ids``."""
        await self._request(
            "POST",
            "/api/v3/command",
            json={"name": "EpisodeSearch", "episodeIds": list(episode_ids)},
        )


def _is_not_found(exc: LanguagarrClientError) -> bool:
    """Whether a wrapped request error was an HTTP 404 from Sonarr."""
    cause = exc.__cause__
    return (
        isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404
    )


def client_for(ctx: AppContext) -> LanguagarrSonarrClient:
    """Build a Languagarr Sonarr client from the context's Sonarr connection.

    The URL and API key come from the shared context client (managed from the
    dashboard) so Languagarr never owns its own copy of the credentials.
    """
    fields = ctx.sonarr.connection_fields()
    return LanguagarrSonarrClient(
        app="sonarr", base_url=fields["base_url"], api_key=fields["api_key"]
    )
