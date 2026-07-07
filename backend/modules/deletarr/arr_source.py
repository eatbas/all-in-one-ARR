"""Outbound Servarr client that gives Deletarr its authoritative library manifest.

Deletarr's heuristic scanner *guesses* which files are junk. When Radarr/Sonarr are
connected they are the source of truth for which media files *belong* on disk, so
this client fetches the managed inventory (the on-disk folder of each movie/series
and the files each app tracks). It mirrors the Findarr client's request pattern
(`X-Api-Key` header, raise on failure) but exposes only the read-only endpoints
Deletarr needs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.clients.servarr import ServarrClient, ServarrClientError
from modules.deletarr.models import LibraryType

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class DeletarrArrError(ServarrClientError):
    """Raised when a Radarr/Sonarr request for the Deletarr manifest fails."""


class DeletarrArrClient(ServarrClient):
    """Read-only Sonarr/Radarr client for building the Deletarr manifest."""

    error_class = DeletarrArrError

    @staticmethod
    def _as_dicts(data: Any) -> list[dict[str, Any]]:
        """Return only the dict entries of a JSON list payload."""
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    async def root_folders(self) -> list[dict[str, Any]]:
        """Return `/api/v3/rootfolder` entries (each carries a ``path``)."""
        return self._as_dicts(await self._request("GET", "/api/v3/rootfolder"))

    async def movies(self) -> list[dict[str, Any]]:
        """Return `/api/v3/movie` (Radarr): folder ``path`` + embedded ``movieFile``."""
        return self._as_dicts(await self._request("GET", "/api/v3/movie"))

    async def series(self) -> list[dict[str, Any]]:
        """Return `/api/v3/series` (Sonarr): folder ``path`` per series."""
        return self._as_dicts(await self._request("GET", "/api/v3/series"))

    async def episode_files(self, series_id: int) -> list[dict[str, Any]]:
        """Return `/api/v3/episodefile?seriesId=` (Sonarr): tracked episode files."""
        return self._as_dicts(
            await self._request(
                "GET", "/api/v3/episodefile", params={"seriesId": series_id}
            )
        )


def client_for(ctx: AppContext, library_type: LibraryType) -> DeletarrArrClient:
    """Build a Deletarr Servarr client from the context's Radarr/Sonarr connection.

    Movies map to Radarr and TV to Sonarr; the connection URL and API key are read
    from the shared context client (managed from the dashboard) so Deletarr never
    owns its own copy of the credentials.
    """
    if library_type == "movies":
        source, app = ctx.radarr, "radarr"
    else:
        source, app = ctx.sonarr, "sonarr"
    fields = source.connection_fields()
    return DeletarrArrClient(
        app=app, base_url=fields["base_url"], api_key=fields["api_key"]
    )
