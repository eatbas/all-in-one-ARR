"""Async Servarr API helper used by Findarr."""

from __future__ import annotations

from typing import Any

from core.clients.servarr import ServarrClient, ServarrClientError
from core.clients.servarr import parse_version as parse_version
from modules.findarr.models import SearchUnit


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

    async def trigger_search(self, unit: SearchUnit) -> None:
        """Trigger the Sonarr/Radarr search command for one grouped unit."""
        await self._request("POST", "/api/v3/command", json=_command_payload(unit))
