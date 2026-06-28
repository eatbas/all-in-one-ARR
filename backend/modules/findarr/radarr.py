"""Radarr item normalisation for Findarr."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from modules.findarr.models import FindarrItem


_RELEASE_FIELDS = ("digitalRelease", "physicalRelease", "inCinemas")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_future(movie: dict[str, Any]) -> bool:
    dates = [_parse_date(movie.get(field)) for field in _RELEASE_FIELDS]
    dates = [item for item in dates if item is not None]
    if not dates:
        return False
    delay_days = int(movie.get("minimumAvailabilityDelay", 0) or 0)
    available_at = min(dates) + timedelta(days=delay_days)
    return available_at > datetime.now(timezone.utc)


def normalise(record: dict[str, Any], *, mode: str) -> FindarrItem | None:
    """Convert a Radarr wanted record into a Findarr item."""
    movie = record.get("movie") if isinstance(record.get("movie"), dict) else record
    movie_id = movie.get("id")
    if movie_id is None:
        return None
    title = movie.get("title") or "Unknown movie"
    year = movie.get("year")
    label = f"{title} ({year})" if year else title
    return FindarrItem(
        app="radarr",
        mode=mode,
        item_id=str(movie_id),
        title=label,
        monitored=bool(movie.get("monitored", True)),
        is_future=_is_future(movie),
    )
