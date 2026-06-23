"""Static registry describing the managed connection services.

Single source of truth for *which* connection services the dashboard manages and
*what fields* each one needs. The settings store, the services API and the
frontend all follow these descriptors, so adding a service is a one-entry change
here rather than a parallel edit scattered across modules.

Services differ in shape. Most are a ``{url, api_key}`` pair
(Jellyseerr/Sonarr/Radarr/SABnzbd/qBittorrent); TMDB and OMDb are API-key-only
against a fixed public endpoint (no user URL). qBittorrent authenticates with its
WebUI API key (``Authorization: Bearer``, available since v5.2.0). The descriptor
captures those differences declaratively. ``secret_fields`` are the values that
must never be returned in clear — they are reduced to ``<field>_set`` booleans
when masked.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceDescriptor:
    """Declarative description of one managed service connection."""

    name: str
    label: str
    # Ordered field names this service stores, drawn from
    # ("url", "api_key", "username", "password").
    fields: tuple[str, ...]
    # Subset of ``fields`` that are secret (masked to ``<field>_set`` booleans).
    secret_fields: tuple[str, ...]
    # Fixed base URL for services with no user-configurable URL (TMDB/OMDb).
    default_url: str = ""


SERVICES: tuple[ServiceDescriptor, ...] = (
    ServiceDescriptor("jellyseerr", "Jellyseerr", ("url", "api_key"), ("api_key",)),
    ServiceDescriptor("sonarr", "Sonarr", ("url", "api_key"), ("api_key",)),
    ServiceDescriptor("radarr", "Radarr", ("url", "api_key"), ("api_key",)),
    ServiceDescriptor(
        "tmdb",
        "TMDB",
        ("api_key",),
        ("api_key",),
        default_url="https://api.themoviedb.org",
    ),
    ServiceDescriptor(
        "omdb",
        "OMDb",
        ("api_key",),
        ("api_key",),
        default_url="https://www.omdbapi.com",
    ),
    ServiceDescriptor("sabnzbd", "SABnzbd", ("url", "api_key"), ("api_key",)),
    ServiceDescriptor("qbittorrent", "qBittorrent", ("url", "api_key"), ("api_key",)),
)

# Ordered service names and a name→descriptor lookup, derived once from SERVICES.
SERVICE_NAMES: tuple[str, ...] = tuple(desc.name for desc in SERVICES)
BY_NAME: dict[str, ServiceDescriptor] = {desc.name: desc for desc in SERVICES}


def empty_values(desc: ServiceDescriptor) -> dict[str, str]:
    """Return a blank value dict holding exactly this service's fields."""
    return {field: "" for field in desc.fields}


def masked_entry(desc: ServiceDescriptor, values: dict[str, str]) -> dict[str, object]:
    """Return a response-safe view: secrets reduced to ``<field>_set`` booleans.

    Non-secret fields (``url``, ``username``) are returned as-is; secret fields
    (``api_key``, ``password``) are replaced by a ``<field>_set`` boolean.
    """
    entry: dict[str, object] = {}
    for field in desc.fields:
        if field in desc.secret_fields:
            entry[f"{field}_set"] = bool(values.get(field))
        else:
            entry[field] = values.get(field, "")
    return entry
