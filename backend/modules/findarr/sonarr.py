"""Sonarr item normalisation for Findarr."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from modules.findarr.models import FindarrItem


def _is_future(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) > datetime.now(timezone.utc)


def normalise(record: dict[str, Any], *, mode: str) -> FindarrItem | None:
    """Convert a Sonarr wanted record into a Findarr item."""
    episode = record.get("episode") if isinstance(record.get("episode"), dict) else record
    episode_id = episode.get("id")
    if episode_id is None:
        return None
    series = record.get("series") if isinstance(record.get("series"), dict) else episode.get("series", {})
    series_title = series.get("title") if isinstance(series, dict) else None
    title = episode.get("title") or "Episode"
    season = episode.get("seasonNumber")
    episode_number = episode.get("episodeNumber")
    label = f"{series_title or 'Unknown series'}"
    if season is not None and episode_number is not None:
        label += f" S{int(season):02d}E{int(episode_number):02d}"
    label += f" - {title}"
    monitored = bool(episode.get("monitored", True)) and bool(
        series.get("monitored", True) if isinstance(series, dict) else True
    )
    return FindarrItem(
        app="sonarr",
        mode=mode,
        item_id=str(episode_id),
        title=label,
        monitored=monitored,
        is_future=_is_future(episode.get("airDateUtc")),
    )
