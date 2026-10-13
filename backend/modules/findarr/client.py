"""Async Servarr API helper used by Findarr."""

from __future__ import annotations

from typing import Any

from core.clients.servarr import ServarrClient, ServarrClientError
from core.clients.servarr import parse_version as parse_version
from modules.findarr.models import SearchUnit

# Movie ids per `/api/v3/moviefile` request; 100 ids keep the URL well under
# common proxy limits while reading a large library in a handful of calls.
_MOVIE_FILE_BATCH = 100


class FindarrClientError(ServarrClientError):
    """Raised when a Sonarr/Radarr API request cannot be completed."""


def _command_payload(unit: SearchUnit) -> dict[str, Any]:
    """Build the Sonarr/Radarr command body for a grouped search unit."""
    if unit.command == "EpisodeSearch":
        return {"name": "EpisodeSearch", "episodeIds": list(unit.episode_ids)}
    if unit.command == "SeasonSearch":
        return {
            "name": "SeasonSearch",
            "seriesId": unit.series_id,
            "seasonNumber": unit.season_number,
        }
    if unit.command == "SeriesSearch":
        return {"name": "SeriesSearch", "seriesId": unit.series_id}
    return {"name": "MoviesSearch", "movieIds": list(unit.movie_ids)}


class FindarrArrClient(ServarrClient):
    """Small client for the Sonarr/Radarr endpoints Findarr needs."""

    error_class = FindarrClientError
    feature_name = "Findarr"

    async def queue_size(self) -> int:
        """Return current download queue size."""
        data = await self._request(
            "GET", "/api/v3/queue", params={"page": 1, "pageSize": 1}
        )
        if isinstance(data, dict):
            return int(data.get("totalRecords", len(data.get("records", []))))
        if isinstance(data, list):
            return len(data)
        return 0

    async def wanted(self, kind: str) -> list[dict[str, Any]]:
        """Fetch every wanted page for `missing` or `cutoff`.

        Sonarr's `/wanted` records omit the embedded ``series`` object unless
        ``includeSeries=true`` is requested, leaving the episode normaliser with
        no series title to label rows ("Unknown series ..."). Radarr wanted
        records already carry the movie title, so the flag is Sonarr-only.
        """
        records: list[dict[str, Any]] = []
        page = 1
        page_size = 100
        while True:
            params: dict[str, Any] = {"page": page, "pageSize": page_size}
            if self.app == "sonarr":
                params["includeSeries"] = "true"
            data = await self._request(
                "GET",
                f"/api/v3/wanted/{kind}",
                params=params,
            )
            if isinstance(data, dict):
                page_records = data.get("records", [])
                if not isinstance(page_records, list):
                    raise FindarrClientError(
                        f"{self.app} wanted payload has invalid records"
                    )
                records.extend(
                    [record for record in page_records if isinstance(record, dict)]
                )
                # ``totalRecords`` is authoritative when present. When an older
                # Arr build omits it, fall back to "stop on the first empty page"
                # rather than treating the first page as the whole set — the
                # latter silently drops every record beyond page one.
                total = data.get("totalRecords")
                if (
                    total is not None and len(records) >= int(total)
                ) or not page_records:
                    break
            elif isinstance(data, list):
                records.extend([record for record in data if isinstance(record, dict)])
                break
            else:
                raise FindarrClientError(f"{self.app} wanted payload is invalid")
            page += 1
        return records

    async def trigger_search(self, unit: SearchUnit) -> int | None:
        """Trigger the search command for one grouped unit; return its command id.

        The id lets a later run ask the Arr what the search actually did. It is
        ``None`` when the Arr's response carries no usable id.
        """
        data = await self._request(
            "POST", "/api/v3/command", json=_command_payload(unit)
        )
        command_id = data.get("id") if isinstance(data, dict) else None
        return command_id if isinstance(command_id, int) else None

    async def command(self, command_id: int) -> dict[str, Any] | None:
        """Return `/api/v3/command/{id}`, or ``None`` once the Arr has purged it."""
        try:
            data = await self._request("GET", f"/api/v3/command/{command_id}")
        except FindarrClientError as exc:
            if exc.status_code == 404:
                return None
            raise
        if not isinstance(data, dict):
            raise FindarrClientError(f"{self.app} returned an invalid command payload")
        return data

    async def grabs_since(self, since_iso: str) -> list[dict[str, Any]]:
        """Return `grabbed` history events since ``since_iso``.

        Sonarr records are requested with their ``episode`` embedded so a
        season search can be matched on season number.
        """
        params: dict[str, Any] = {"date": since_iso, "eventType": "grabbed"}
        if self.app == "sonarr":
            params["includeEpisode"] = "true"
        return self._as_dicts(
            await self._request("GET", "/api/v3/history/since", params=params)
        )

    async def quality_profiles(self) -> list[dict[str, Any]]:
        """Return `/api/v3/qualityprofile`: cutoffs and custom-format cutoff scores."""
        return self._as_dicts(await self._request("GET", "/api/v3/qualityprofile"))

    async def episodes_with_files(self, series_id: int) -> list[dict[str, Any]]:
        """Return a series' episodes (Sonarr) with each embedded ``episodeFile``."""
        return self._as_dicts(
            await self._request(
                "GET",
                "/api/v3/episode",
                params={"seriesId": series_id, "includeEpisodeFile": "true"},
            )
        )

    async def movies(self) -> list[dict[str, Any]]:
        """Return `/api/v3/movie` (Radarr): every movie with its profile id."""
        return self._as_dicts(await self._request("GET", "/api/v3/movie"))

    async def movie_files(self, movie_ids: list[int]) -> list[dict[str, Any]]:
        """Return Radarr movie files (with ``customFormatScore``) for ``movie_ids``.

        `/api/v3/movie` embeds files without their custom-format score, so the
        files are read from `/api/v3/moviefile`, which accepts repeated
        ``movieId`` parameters; ids are sent in batches to keep URLs short.
        """
        files: list[dict[str, Any]] = []
        for start in range(0, len(movie_ids), _MOVIE_FILE_BATCH):
            batch = movie_ids[start : start + _MOVIE_FILE_BATCH]
            files.extend(
                self._as_dicts(
                    await self._request(
                        "GET",
                        "/api/v3/moviefile",
                        params=[("movieId", movie_id) for movie_id in batch],
                    )
                )
            )
        return files
