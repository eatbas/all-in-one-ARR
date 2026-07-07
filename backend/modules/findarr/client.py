"""Async Servarr API helper used by Findarr."""

from __future__ import annotations

from typing import Any

from core.clients.servarr import ServarrClient, ServarrClientError
from modules.findarr.models import Compatibility, SearchUnit


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


def parse_version(value: str) -> tuple[int, int, int]:
    """Parse a semantic-ish version into a comparable three-part tuple."""
    parts: list[int] = []
    for raw_part in value.split(".")[:3]:
        digits = ""
        for char in raw_part:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def _normalise_app_name(value: str) -> str:
    """Return a comparable application name from a Servarr status payload."""
    return value.strip().lower().replace(" ", "")


class FindarrArrClient(ServarrClient):
    """Small client for the Sonarr/Radarr endpoints Findarr needs."""

    error_class = FindarrClientError

    async def system_status(self) -> dict[str, Any]:
        """Return `/api/v3/system/status`."""
        data = await self._request("GET", "/api/v3/system/status")
        if not isinstance(data, dict):
            raise FindarrClientError(f"{self.app} returned an invalid status payload")
        return data

    async def compatibility(self) -> Compatibility:
        """Return whether the connected app satisfies Findarr's version target."""
        status = await self.system_status()
        version = str(status.get("version") or "0.0.0")
        app_name = str(status.get("appName") or self.app)
        expected_name = self.app.capitalize()
        if _normalise_app_name(app_name) != self.app:
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=(
                    f"Connected service is {app_name}; Findarr expected "
                    f"{expected_name} for the configured {self.app} connection"
                ),
            )
        minimum = (4, 0, 0) if self.app == "sonarr" else (6, 0, 0)
        actual = parse_version(version)
        if actual < minimum:
            required = "4+" if self.app == "sonarr" else "6+"
            return Compatibility(
                ok=False,
                app_name=app_name,
                version=version,
                detail=f"{app_name} {version} is unsupported; Findarr requires {self.app.capitalize()} {required}",
            )
        return Compatibility(
            ok=True,
            app_name=app_name,
            version=version,
            detail=f"Connected to {app_name} {version}",
        )

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
