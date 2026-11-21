"""Outbound, read-only Sonarr client for Remindarr.

Every endpoint Remindarr reads (series, episodes, episode files, tags and the
version check) lives on :class:`ServarrClient`; this subclass only names the
feature and its error type. Remindarr never writes to Sonarr.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.clients.servarr import ServarrClient, ServarrClientError

if TYPE_CHECKING:  # pragma: no cover
    from core.context import AppContext


class RemindarrClientError(ServarrClientError):
    """Raised when a Sonarr request made by Remindarr cannot be completed."""


class RemindarrSonarrClient(ServarrClient):
    """Sonarr client carrying Remindarr's feature name and error type."""

    error_class = RemindarrClientError
    feature_name = "Remindarr"


def client_for(ctx: AppContext) -> RemindarrSonarrClient:
    """Build a Remindarr Sonarr client from the context's Sonarr connection.

    The URL and API key come from the shared context client (managed from the
    dashboard), so Remindarr never owns its own copy of the credentials.
    """
    fields = ctx.sonarr.connection_fields()
    return RemindarrSonarrClient(
        app="sonarr", base_url=fields["base_url"], api_key=fields["api_key"]
    )
