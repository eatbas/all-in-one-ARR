"""Custom-format upgrade candidates that the Arr cutoff-unmet lists leave out.

Sonarr's and Radarr's ``/wanted/cutoff`` lists only compare a file's *quality*
with the profile cutoff. A file whose quality already meets the cutoff but whose
custom-format score is still below the profile's ``cutoffFormatScore`` is
upgradeable (the Arr grabs a release that scores higher) yet never appears on
that list. This module finds those files and returns them as wanted-style
records, so the engine's normalisers and grouping treat them exactly like
cutoff-unmet records.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.coerce import parse_int

if TYPE_CHECKING:  # pragma: no cover
    from modules.findarr.client import FindarrArrClient


def _format_cutoffs(profiles: list[dict[str, Any]]) -> dict[int, int]:
    """Map profile id to ``cutoffFormatScore`` for profiles that allow upgrades."""
    cutoffs: dict[int, int] = {}
    for profile in profiles:
        profile_id = parse_int(profile.get("id"))
        cutoff = parse_int(profile.get("cutoffFormatScore"))
        if profile_id is None or cutoff is None or not profile.get("upgradeAllowed"):
            continue
        cutoffs[profile_id] = cutoff
    return cutoffs


def _profile_cutoff(resource: dict[str, Any], cutoffs: dict[int, int]) -> int | None:
    """Return the CF cutoff score of a series/movie's profile, if it upgrades."""
    profile_id = parse_int(resource.get("qualityProfileId"))
    return None if profile_id is None else cutoffs.get(profile_id)


def _below_cutoff(media_file: dict[str, Any], cutoff: int) -> bool:
    """Whether a file's custom-format score is below the profile's cutoff score."""
    score = parse_int(media_file.get("customFormatScore"))
    return score is not None and score < cutoff


def _has_files(series: dict[str, Any]) -> bool:
    """Whether a Sonarr series has any episode file; unknown counts as yes."""
    statistics = series.get("statistics")
    if not isinstance(statistics, dict):
        return True
    return bool(parse_int(statistics.get("episodeFileCount")))


async def sonarr_records(
    client: FindarrArrClient, *, monitored_only: bool
) -> list[dict[str, Any]]:
    """Return Sonarr episodes whose file is below its profile's CF cutoff score.

    Each record is the episode resource with its ``series`` embedded, matching
    the shape of a ``/wanted`` record. Unmonitored series are not read at all
    when ``monitored_only`` is set, which avoids one request per such series.
    """
    cutoffs = _format_cutoffs(await client.quality_profiles())
    records: list[dict[str, Any]] = []
    for series in await client.series():
        series_id = parse_int(series.get("id"))
        cutoff = _profile_cutoff(series, cutoffs)
        if series_id is None or cutoff is None or not _has_files(series):
            continue
        if monitored_only and not series.get("monitored", True):
            continue
        for episode in await client.episodes_with_files(series_id):
            episode_file = episode.get("episodeFile")
            if isinstance(episode_file, dict) and _below_cutoff(episode_file, cutoff):
                records.append({**episode, "series": series})
    return records


async def radarr_records(
    client: FindarrArrClient, *, monitored_only: bool
) -> list[dict[str, Any]]:
    """Return Radarr movies whose file is below its profile's CF cutoff score.

    Each record is the movie resource, matching the shape of a ``/wanted``
    record.
    """
    cutoffs = _format_cutoffs(await client.quality_profiles())
    candidates: dict[int, tuple[dict[str, Any], int]] = {}
    for movie in await client.movies():
        movie_id = parse_int(movie.get("id"))
        cutoff = _profile_cutoff(movie, cutoffs)
        if movie_id is None or cutoff is None or not movie.get("hasFile"):
            continue
        if monitored_only and not movie.get("monitored", True):
            continue
        candidates[movie_id] = (movie, cutoff)
    if not candidates:
        return []
    records: list[dict[str, Any]] = []
    for movie_file in await client.movie_files(sorted(candidates)):
        movie_id = parse_int(movie_file.get("movieId"))
        candidate = None if movie_id is None else candidates.get(movie_id)
        if candidate is not None and _below_cutoff(movie_file, candidate[1]):
            records.append(candidate[0])
    return records


async def records(
    client: FindarrArrClient, app: str, *, monitored_only: bool
) -> list[dict[str, Any]]:
    """Return the CF-below-cutoff records for ``app`` (Sonarr or Radarr)."""
    if app == "sonarr":
        return await sonarr_records(client, monitored_only=monitored_only)
    return await radarr_records(client, monitored_only=monitored_only)
