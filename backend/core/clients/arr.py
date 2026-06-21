"""Defensive parsing of Radarr/Sonarr webhook payloads.

Webhook field names vary across Radarr/Sonarr versions, so the parser tries
several known field paths and tolerates missing keys. The raw payload should be
logged in full by the caller before parsing so unknown shapes can be inspected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Event types that indicate a completed import. Radarr/Sonarr historically send
# ``Download`` for a finished import; newer builds may send ``Import``.
IMPORT_EVENTS = frozenset({"Download", "Import"})


@dataclass(frozen=True)
class ArrEvent:
    """Normalised view of an arr webhook payload."""

    event: str | None
    tmdb: int | None
    tvdb: int | None

    @property
    def is_import(self) -> bool:
        """Whether this event represents a completed import."""
        return self.event in IMPORT_EVENTS


def _coerce_int(value: Any) -> int | None:
    """Best-effort conversion of a webhook id to ``int``; ``None`` on failure."""
    if value is None:
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _first_id(payload: dict[str, Any], paths: tuple[tuple[str, str], ...]) -> int | None:
    """Return the first positive integer id found among ``(parent, key)`` paths."""
    for parent, key in paths:
        section = payload.get(parent)
        if isinstance(section, dict):
            coerced = _coerce_int(section.get(key))
            if coerced is not None:
                return coerced
    return None


def parse_webhook(payload: dict[str, Any]) -> ArrEvent:
    """Parse a Radarr/Sonarr webhook payload into an :class:`ArrEvent`."""
    event = payload.get("eventType")
    if not isinstance(event, str):
        event = None

    tmdb = _first_id(
        payload,
        (("movie", "tmdbId"), ("remoteMovie", "tmdbId")),
    )
    tvdb = _first_id(
        payload,
        (("series", "tvdbId"), ("remoteSeries", "tvdbId")),
    )
    return ArrEvent(event=event, tmdb=tmdb, tvdb=tvdb)
